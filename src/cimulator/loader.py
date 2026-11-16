#!/usr/bin/env python3

import os
import re
import yaml
import logging
from typing import List, Union, Optional, Tuple, Set, Any, Iterator
from cimulator.types import ConfigDict, JobDict, JobSourcesDict, JobOccurrencesDict, VariablesDict
from cimulator.inputs import InputsDict, InputsError, apply_inputs
from cimulator.variable_expander import expand_variables_in_string
from cimulator.workflow import evaluate_condition

# Get a logger for this module
logger = logging.getLogger(__name__)

# Define a special class to represent a !reference tag that will be processed later
class ReferenceTag:
    def __init__(self, path_components: List[Union[str, int]]) -> None:
        self.path_components = path_components

    def resolve(self, document: ConfigDict) -> Any:
        """
        Resolve the reference by navigating through the document.

        Args:
            document: The complete YAML document

        Returns:
            The referenced value
        """
        # Start with the first component (the anchor name without the &)
        current: Any = document
        anchor_name = self.path_components[0]

        # First, find the node with the given name
        if isinstance(anchor_name, str) and anchor_name not in document:
            logger.warning(f"Unknown reference target: {anchor_name}")
            return None

        if isinstance(anchor_name, str):
            current = document[anchor_name]

        # Navigate through the remaining path components
        for component in self.path_components[1:]:
            if isinstance(current, dict) and isinstance(component, str) and component in current:
                current = current[component]
            elif isinstance(current, list) and isinstance(component, int) and 0 <= component < len(current):
                current = current[component]
            else:
                raise ValueError(f"Invalid reference path: {self.path_components}")

        return current

# Define a constructor for the !reference tag.
def reference_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    """
    Constructor for the !reference tag in GitLab CI YAML files.
    Returns a ReferenceTag object that will be resolved later.
    """
    if isinstance(node, yaml.SequenceNode):
        # Get the sequence of reference path components
        path_components = loader.construct_sequence(node)
        return ReferenceTag(path_components)
    else:
        # For other node types, just return the node as-is
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        elif isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        else:
            # Handle other node types safely
            return str(node)

# Create a custom YAML loader that includes our constructor
class GitLabCILoader(yaml.SafeLoader):
    pass

# Register the constructor with our custom loader
GitLabCILoader.add_constructor('!reference', reference_constructor)

def resolve_references(obj: Any, document: ConfigDict) -> Any:
    """
    Recursively resolve all ReferenceTag objects in the given object.

    Args:
        obj: The object to process (dict, list, or scalar)
        document: The complete YAML document

    Returns:
        The object with all references resolved
    """
    if isinstance(obj, dict):
        for key, value in list(obj.items()):
            obj[key] = resolve_references(value, document)
    elif isinstance(obj, list):
        i = 0
        while i < len(obj):
            item = obj[i]
            resolved_item = resolve_references(item, document)
            
            # If the resolved item is a list and the original item was a ReferenceTag,
            # flatten the resolved list into the parent list
            if isinstance(item, ReferenceTag) and isinstance(resolved_item, list):
                # Remove the current item and insert all elements from resolved_item
                obj.pop(i)
                for j, subitem in enumerate(resolved_item):
                    obj.insert(i + j, subitem)
                # Move index forward by the number of items we inserted
                i += len(resolved_item)
            else:
                obj[i] = resolved_item
                i += 1
    elif isinstance(obj, ReferenceTag):
        return obj.resolve(document)
    return obj

# Top-level keywords of a GitLab CI configuration that are not jobs.
# image, services, cache, before_script and after_script are the deprecated
# global forms of the `default` keywords.
GLOBAL_KEYWORDS = frozenset({
    "default", "include", "stages", "variables", "workflow",
    "image", "services", "cache", "before_script", "after_script",
})


def extract_jobs(config: ConfigDict) -> JobDict:
    """Return the jobs of a configuration: its mappings that are not global keywords."""
    return {k: v for k, v in config.items() if k not in GLOBAL_KEYWORDS and isinstance(v, dict)}


SCRIPT_KEYS = ("before_script", "script", "after_script")

def normalize_script_items(items: List[Any]) -> List[Any]:
    """
    Flatten nested lists of script items and convert the items to strings.

    GitLab flattens nested arrays in script sections, e.g. the result of a
    !reference or of an array input. ReferenceTag objects are kept as they are:
    resolve_references flattens them into the list once they are resolved.

    Raises:
        ValueError: If a script item is a dictionary with more than one key-value pair.
    """
    result: List[Any] = []
    for item in items:
        if isinstance(item, list):
            result.extend(normalize_script_items(item))
        elif isinstance(item, (str, ReferenceTag)):
            result.append(item)
        elif isinstance(item, dict):
            # PyYAML parses script lines with a colon, e.g. "run: echo", as dictionaries
            if len(item) == 1:
                # Convert dictionary to "key: value" string format
                dict_key, dict_value = list(item.items())[0]
                result.append(f"{dict_key}: {dict_value}")
            else:
                # If the dictionary has more than one key-value pair, it's an error
                raise ValueError(f"Invalid script item: {item}. Script items must be strings, but found a dictionary with multiple key-value pairs.")
        else:
            # For other types, use string representation
            result.append(str(item))
    return result

def ensure_script_items_are_strings(config: ConfigDict) -> ConfigDict:
    """
    Ensure that all script items in job definitions and `default` are strings,
    flattening nested lists of script items like GitLab does.
    This is necessary because PyYAML may parse items with colons as dictionaries.

    Args:
        config (dict): The configuration dictionary to process.

    Returns:
        dict: The processed configuration with all script items as strings.

    Raises:
        ValueError: If a script item is a dictionary with more than one key-value pair.
    """
    # Skip if config is not a dictionary
    if not isinstance(config, dict):
        return config

    # Process each key-value pair in the config
    for key, value in config.items():
        # If this is a job definition or `default` (not another reserved key) and it's a dictionary
        if key not in {"include", "workflow", "variables", "stages"} and isinstance(value, dict):
            for script_key in SCRIPT_KEYS:
                if isinstance(value.get(script_key), list):
                    value[script_key] = normalize_script_items(value[script_key])
        # Recursively process nested dictionaries
        elif isinstance(value, dict):
            config[key] = ensure_script_items_are_strings(value)

    return config

def load_yaml(file_path: str, inputs: Optional[InputsDict] = None) -> ConfigDict:
    """
    Load a YAML file and return its contents as a dictionary.
    If the file is empty, return an empty dictionary.
    Uses a custom loader that supports GitLab CI-specific YAML tags.

    If the file starts with a `spec:inputs` header, the header is dropped and
    `$[[ inputs.NAME ]]` is interpolated from `inputs` and the declared defaults.

    Note: This function does NOT resolve !reference tags. References will be
    resolved later, after all includes are processed and jobs are expanded.
    """
    with open(file_path, 'r') as f:
        documents = list(yaml.load_all(f, Loader=GitLabCILoader))
        document = apply_inputs(documents, inputs, file_path)
        # Only a file without content is an empty configuration: other values,
        # e.g. [] or false, are kept for the caller to reject
        if document is None:
            document = {}
        # Ensure all script items are strings
        document = ensure_script_items_are_strings(document)
        return document

def merge_dicts(base: ConfigDict, incoming: ConfigDict) -> ConfigDict:
    """
    Recursively merge two dictionaries.
    For keys that exist in both dictionaries and are themselves dictionaries,
    merge them recursively. Otherwise, values from the incoming dictionary
    will override those in the base.
    """
    for key, value in incoming.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            merge_dicts(base[key], value)
        else:
            base[key] = value
    return base

def track_job_sources(config: ConfigDict, current_file: str,
                     job_sources: Optional[JobSourcesDict] = None,
                     all_job_occurrences: Optional[JobOccurrencesDict] = None) -> None:
    """
    Track which file each job comes from.

    Parameters:
        config (dict): The current YAML configuration.
        current_file (str): Path to the current file being processed.
        job_sources (dict): Dictionary to track which file each job comes from.
        all_job_occurrences (dict): Dictionary to track all occurrences of each job.

    Returns:
        None: Updates the job_sources and all_job_occurrences dictionaries in place.
    """
    if job_sources is None:
        job_sources = {}

    if all_job_occurrences is None:
        all_job_occurrences = {}

    for key in config:
        if key not in GLOBAL_KEYWORDS and isinstance(config[key], dict):
            # Record the source for all jobs, even if they've been seen before
            # This will ensure we have the most recent source for duplicate jobs
            job_sources[key] = current_file
            logger.debug(f"Tracking job '{key}' from file: {current_file}")

            # Track all occurrences of each job
            if key not in all_job_occurrences:
                all_job_occurrences[key] = []
            all_job_occurrences[key].append(current_file)

def matches_no_file(path: str) -> bool:
    """
    Whether a path can match no file of the repository, as GitLab sees it:
    it has an empty, '.' or '..' segment (ci//a.yml, ./ci/a.yml,
    ci/../ci/a.yml), which GitLab does not normalise, or a '.git' one,
    which is not part of the repository.
    """
    return any(segment in ("", ".", "..", ".git") for segment in path.split("/"))

def in_nested_repository(root: str, directory: str) -> bool:
    """
    Whether `directory`, relative to the repository at `root`, is in a
    submodule or another nested repository: it or one of its parents, below
    the root, has a `.git` entry.
    """
    while directory:
        if os.path.lexists(os.path.join(root, directory, ".git")):
            return True
        directory = os.path.dirname(directory)
    return False

def repository_files(root: str, directory: str = "") -> Iterator[str]:
    """
    The files under `directory` of the repository at `root`, relative to
    the root and with '/' separators, as GitLab sees them: without `.git`
    (a directory, or a file in a worktree or a submodule), and without the
    files of submodules or other nested repositories.
    """
    if in_nested_repository(root, directory):
        return
    for current, subdirectories, files in os.walk(os.path.join(root, directory)):
        subdirectories[:] = [d for d in subdirectories
                             if d != ".git" and not os.path.lexists(os.path.join(current, d, ".git"))]
        for name in files:
            if name != ".git":
                yield os.path.relpath(os.path.join(current, name), root).replace(os.sep, "/")

def repository_file(root: str, relative: str) -> Optional[str]:
    """
    The path of the file `relative` of the repository at `root`, or None if
    it is not one as GitLab sees it: missing, or in a submodule or another
    nested repository (see repository_files()).
    """
    path = os.path.join(root, relative)
    if not os.path.isfile(path) or in_nested_repository(root, os.path.dirname(relative)):
        return None
    return os.path.normpath(path)

def matching_files(pattern: str, root: str) -> List[str]:
    """
    Return the files under `root` that a path or wildcard pattern matches, as
    in GitLab: relative to the root of the repository, with or without a
    leading slash, where `*` matches within a directory and `**` across
    directories (`ci/**.yml` is every .yml file under ci/).
    """
    relative = pattern.lstrip("/")
    if matches_no_file(relative):
        # e.g. from an undefined variable in ci/$DIR/a.yml
        return []
    if "*" not in relative:
        path = repository_file(root, relative)
        return [path] if path else []

    regex = re.compile("".join(
        ".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part)
        for part in re.split(r"(\*\*|\*)", relative)
    ) + "$")
    # Only walk the directory before the first wildcard
    fixed_prefix = os.path.dirname(relative[:relative.index("*")])
    return sorted(os.path.join(root, path) for path in repository_files(root, fixed_prefix)
                  if regex.match(path))

def local_include_paths(local: str, base_path: str) -> List[str]:
    """
    Return the files a local include refers to (see matching_files()).
    A missing file is an error; a wildcard that matches no file a warning.
    """
    matches = matching_files(local, base_path)
    if not matches:
        if "*" not in local:
            raise ValueError(f"Local include '{local}' does not exist")
        logger.warning(f"Local include '{local}' does not match any file")
    return matches

GLOB_SPECIAL = re.compile(r"[*?\[{]")

def glob_regex(pattern: str, segment_start: bool = True) -> str:
    """
    Translate a `rules:exists` glob into a regex, with the syntax GitLab uses
    there (Ruby's File.fnmatch with FNM_PATHNAME, FNM_DOTMATCH and
    FNM_EXTGLOB): `*` and `?` do not match `/`, `**/` matches any number of
    directories (none included), `[...]` is a character class and `{a,b}` an
    alternative. Dot files are matched like any other. `segment_start` is
    whether `pattern` starts a path segment, for a `{...}` alternative.
    """
    regex = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        # **/ is any number of directories only as a whole segment: a**/b is a*/b
        at_segment_start = pattern[i - 1] == "/" if i else segment_start
        if pattern.startswith("**/", i) and at_segment_start:
            regex.append("(?:.*/)?")
            i += 3
            continue
        if char == "*":
            # `**` not followed by a slash is a plain `*`
            while i + 1 < len(pattern) and pattern[i + 1] == "*":
                i += 1
            regex.append("[^/]*")
        elif char == "?":
            regex.append("[^/]")
        elif char == "[" and "]" in pattern[i + 2:]:
            end = pattern.index("]", i + 2)
            body = pattern[i + 1:end]
            if body.startswith("!"):
                body = "^" + body[1:]
            regex.append(f"[{body}]")
            i = end
        elif char == "{" and "}" in pattern[i:]:
            end = pattern.index("}", i)
            alternatives = pattern[i + 1:end].split(",")
            regex.append("(?:" + "|".join(glob_regex(a, at_segment_start)
                                          for a in alternatives) + ")")
            i = end
        else:
            regex.append(re.escape(char))
        i += 1
    return "".join(regex)

def exists_matches(pattern: str, root: str) -> bool:
    """
    Whether a `rules:exists` glob matches a file of the repository at `root`.
    Unlike an include path, the pattern is relative to the root and taken
    as written: a leading slash or an unnormalised segment (ci//a.yml,
    ./a.yml, ../a.yml) matches nothing, as in GitLab.
    """
    relative = pattern
    if relative.startswith("/") or matches_no_file(relative):
        return False
    special = GLOB_SPECIAL.search(relative)
    if not special:
        return repository_file(root, relative) is not None
    regex = re.compile(glob_regex(relative) + "$")
    # Only walk the directory before the first special character
    fixed_prefix = os.path.dirname(relative[:special.start()])
    return any(regex.match(path) for path in repository_files(root, fixed_prefix))

VARIABLE = re.compile(r"\$(\w+)|\$\{(\w+)\}")

def expand_defined_variables(text: str, variables: VariablesDict) -> str:
    """Expand the variables of `text` that are defined, leaving the others as written."""
    def replace(match: "re.Match[str]") -> str:
        name = match.group(1) or match.group(2)
        return str(variables[name]) if name in variables else match.group(0)
    return VARIABLE.sub(replace, text)

def unchecked_exists(rule: ConfigDict) -> Optional[str]:
    """
    The `exists` of a rule that cannot be checked here, if any: the files of
    another project (exists:project), or a regular expression (exists:regexp).
    """
    exists = rule.get("exists")
    if isinstance(exists, dict):
        if "project" in exists:
            return "exists:project, the files of another project"
        if "regexp" in exists:
            return "exists:regexp"
    return None

def exists_patterns(rule: ConfigDict) -> Optional[List[str]]:
    """
    The `exists` patterns of a rule, or None if it has no `exists` or one
    that cannot be checked (see unchecked_exists()). `exists: {}` has no
    pattern, so it matches nothing, as in GitLab.
    """
    if unchecked_exists(rule):
        return None
    exists = rule.get("exists")
    if isinstance(exists, dict):
        # paths: null is no path, as in GitLab
        exists = exists.get("paths") or []
    if exists is None:
        return None
    return [str(p) for p in (exists if isinstance(exists, list) else [exists])]

def rules_need_variables(rules: Any) -> bool:
    """
    Whether include rules, checked by check_include_rules(), can only be
    evaluated with the pipeline variables.
    """
    return any(rule.get("if") is not None
               or any("$" in p for p in exists_patterns(rule) or [])
               for rule in rules)

INCLUDE_RULE_KEYS = {"if", "exists", "changes", "when"}
EXISTS_KEYS = {"paths", "regexp", "project", "ref"}

def check_include_rules(rules: Any) -> None:
    """
    Check the form of the `rules` of an include, as GitLab does for every
    rule before evaluating any: a list of mappings with only the keys
    `if`, `exists`, `changes` and `when`, where `if` is an expression and
    `when` is `always` or `never`. Raises ValueError otherwise.

    The syntax of an `if` expression is not checked: see include_rules_match().
    """
    if not isinstance(rules, list):
        raise ValueError(f"must be a list of rules, not {rules!r}")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError(f"a rule must be a mapping, not {rule!r}")
        unknown = sorted(str(key) for key in set(rule) - INCLUDE_RULE_KEYS)
        if unknown:
            raise ValueError(f"unknown keys in a rule: {', '.join(unknown)}")
        # if: null is no condition, as in GitLab
        condition = rule.get("if")
        if condition is not None and not isinstance(condition, str):
            raise ValueError(f"if must be an expression, not {condition!r}")
        # when: null is always, as in GitLab; false, '' or 0 are invalid
        if rule.get("when") is not None and rule["when"] not in ("always", "never"):
            raise ValueError(f"when must be always or never, not {rule['when']!r}")
        exists = rule.get("exists")
        if isinstance(exists, dict) and exists:
            unknown = sorted(str(key) for key in set(exists) - EXISTS_KEYS)
            if unknown:
                raise ValueError(f"unknown keys in exists: {', '.join(unknown)}")
            # exists: {} is valid, and matches nothing
            if ("paths" in exists) == ("regexp" in exists):
                raise ValueError("exists must have either paths or regexp")

def include_rules_match(rules: Any, variables: VariablesDict, root: str) -> bool:
    """
    Whether the `rules` of an include keep it, as GitLab evaluates them: the
    first rule whose `if` and `exists` both match decides, and the include
    is kept unless its `when` is `never`. `exists` expands the variables that
    are defined and leaves the others as written, as GitLab does. `changes`
    cannot be known offline and is taken as matching, as for job rules, and
    so are exists:project and exists:regexp, with a warning.

    An `if` that cannot be evaluated is logged and taken as not matching,
    as for job rules: the expression may be valid in GitLab but not
    supported here. The rules must have been checked by check_include_rules().
    """
    for rule in rules:
        condition = rule.get("if")
        if condition is not None:
            try:
                matched = evaluate_condition(condition, variables, strict=True)
            except ValueError as e:
                logger.warning(f"Cannot evaluate an include rule, taken as not matching: {e}")
                matched = False
            if not matched:
                continue
        unchecked = unchecked_exists(rule)
        if unchecked:
            # As for changes, which is not known offline either
            logger.warning(f"Cannot check {unchecked} of an include rule, taken as matching")
        patterns = exists_patterns(rule)
        if patterns is not None and not any(
                exists_matches(expand_defined_variables(p, variables), root) for p in patterns):
            continue
        return rule.get("when") != "never"
    return False

SPEC_WITHOUT_CONFIGURATION = "has a spec header but no configuration after it"

def yaml_without_configuration(file_path: str) -> Optional[str]:
    """
    Why a YAML file has no configuration, if it has none: it is empty
    (e.g. only comments), or it has a `spec` header and nothing after it,
    which GitLab rejects too.
    """
    with open(file_path, 'r') as f:
        documents = list(yaml.load_all(f, Loader=GitLabCILoader))
    if all(document is None for document in documents):
        return "is empty"
    if (len(documents) == 2 and documents[1] is None
            and isinstance(documents[0], dict) and set(documents[0]) == {"spec"}):
        return SPEC_WITHOUT_CONFIGURATION
    return None

def resolve_includes(config: ConfigDict, base_path: str,
                    root_path: Optional[str] = None, depth: int = 0,
                    current_file: Optional[str] = None,
                    job_sources: Optional[JobSourcesDict] = None,
                    all_job_occurrences: Optional[JobOccurrencesDict] = None,
                    variables: Optional[VariablesDict] = None,
                    include_chain: Tuple[str, ...] = ()) -> ConfigDict:
    """
    Recursively resolve and merge included YAML files.
    The 'include' key in the YAML file can be a string (for a single include),
    a dictionary (with a 'local' key), or a list of such entries.

    Parameters:
        config (dict): The current YAML configuration.
        base_path (str): The directory of the current YAML file to resolve relative paths.
        root_path (str): The root directory of the project, used for resolving nested includes.
        depth (int): Current recursion depth, used for debugging.
        current_file (str): Path to the current file being processed.
        job_sources (dict): Dictionary to track which file each job comes from.
        all_job_occurrences (dict): Dictionary to track all occurrences of each job.
        variables (dict): The variables an include can use, in its path and its
            rules: the predefined, project and pipeline variables, i.e. those
            of a simulation profile (not the variables of the configuration,
            which GitLab does not use there). None if unknown, as in validate:
            an include that depends on them is then loaded if its file exists,
            and skipped with a warning otherwise.
        include_chain (tuple): The files that include the current one, to
            detect an include cycle.

    Returns:
        dict: The configuration with all includes resolved and merged.
    """
    # If root_path is not provided, use base_path as the root path
    if root_path is None:
        root_path = base_path

    # Initialize job_sources if not provided
    if job_sources is None:
        job_sources = {}

    # Initialize all_job_occurrences if not provided
    if all_job_occurrences is None:
        all_job_occurrences = {}

    # Track job sources for the current file
    if current_file:
        track_job_sources(config, current_file, job_sources, all_job_occurrences)

    # If there's no 'include' key, return the config as-is.
    if "include" not in config:
        return config

    # Retrieve and remove the 'include' key from the config.
    includes = config.pop("include")
    if not isinstance(includes, list):
        includes = [includes]

    chain = include_chain + ((current_file,) if current_file else ())

    # Process each include entry.
    for inc in includes:
        include_inputs = None
        rules = None
        if isinstance(inc, str):
            local = None if inc.startswith(("http://", "https://")) else inc
        elif isinstance(inc, dict) and "local" in inc:
            local = inc["local"]
            include_inputs = inc.get("inputs")
            rules = inc.get("rules")
            if not isinstance(local, str) or not local:
                raise ValueError(f"Include {inc}: 'local' must be the path of a file")
        else:
            local = None
        if local is None:
            # remote, project, template and component includes need access to
            # other repositories or servers: cimulator works offline, skip them.
            logger.debug(f"Skipping non-local include {inc}")
            continue

        if rules is not None:
            # Checked whether or not the rules can be evaluated, as GitLab
            # checks every rule, even after one that matches
            try:
                check_include_rules(rules)
            except ValueError as e:
                raise ValueError(f"Include {inc}: rules: {e}") from e

        # Whether the include depends on variables that are not known.
        # Rules without any variable (only exists, or when) are evaluated
        # even without them.
        undecidable = variables is None and (
            "$" in local or (rules is not None and rules_need_variables(rules)))
        if rules is not None and not undecidable:
            if not include_rules_match(rules, variables or {}, root_path):
                logger.debug(f"Skipping include {inc}: its rules do not match")
                continue
        if variables is not None:
            local = expand_variables_in_string(local, variables)
        if undecidable and not matching_files(local, base_path):
            logger.warning(f"Skipping include {inc}: it depends on variables, "
                           f"which are only known when simulating, and its file does not exist")
            continue

        for include_path in local_include_paths(local, base_path):
            # Load the included YAML file. An invalid file is an error, as
            # GitLab rejects such a configuration.
            shown_path = os.path.relpath(include_path, root_path)
            if include_path in chain:
                cycle = [os.path.relpath(f, root_path) for f in chain[chain.index(include_path):]]
                raise ValueError(f"Include cycle: {' -> '.join(cycle + [shown_path])}")
            if not include_path.endswith((".yml", ".yaml")):
                raise ValueError(f"Included file '{shown_path}' does not have a YAML extension")
            try:
                missing_configuration = yaml_without_configuration(include_path)
            except Exception as e:
                raise ValueError(f"Error processing included file '{shown_path}': {e}") from e
            # Before the inputs, which a file without configuration cannot use
            if missing_configuration:
                raise ValueError(f"Included file '{shown_path}' {missing_configuration}")
            try:
                included_config = load_yaml(include_path, include_inputs)
            except InputsError:
                raise
            except Exception as e:
                raise ValueError(f"Error processing included file '{shown_path}': {e}") from e
            if not isinstance(included_config, dict):
                raise ValueError(f"Included file '{shown_path}' must be a mapping of keywords, "
                                 f"not a {type(included_config).__name__}")

            # Recursively resolve includes in the included file.
            # Always use the root path for resolving nested includes
            included_config = resolve_includes(
                included_config,
                root_path,
                root_path,
                depth + 1,
                include_path,
                job_sources,
                all_job_occurrences,
                variables,
                chain
            )

            # Merge the included configuration into the current configuration.
            merge_dicts(config, included_config)

    return config

def load_and_resolve(file_path: str, inputs: Optional[InputsDict] = None,
                     variables: Optional[VariablesDict] = None) -> Tuple[ConfigDict, JobSourcesDict]:
    """
    Load the root YAML file and resolve all includes recursively.

    Parameters:
        file_path (str): Path to the root .gitlab-ci.yml file.
        inputs (dict): Pipeline inputs for the root file's `spec:inputs` header.
        variables (dict): The variables includes can use in their path and
            rules, e.g. those of a simulation profile. See resolve_includes().

    Returns:
        tuple: (resolved_config, job_sources)
            - resolved_config: The complete configuration with all includes merged.
            - job_sources: Dictionary mapping job names to their source files.
    """
    file_path = os.path.abspath(file_path)
    base_path = os.path.dirname(file_path)
    logger.info(f"Root file: {file_path}")
    logger.debug(f"Base path: {base_path}")
    # An empty root file is an empty pipeline, but a spec header with
    # nothing after it is rejected, as GitLab does
    if yaml_without_configuration(file_path) == SPEC_WITHOUT_CONFIGURATION:
        raise ValueError(f"'{os.path.basename(file_path)}' {SPEC_WITHOUT_CONFIGURATION}")
    config = load_yaml(file_path, inputs)
    if not isinstance(config, dict):
        raise ValueError(f"'{os.path.basename(file_path)}' must be a mapping of keywords, "
                         f"not a {type(config).__name__}")

    # Initialize job_sources dictionary and all_jobs_occurrences
    job_sources: JobSourcesDict = {}
    all_job_occurrences: JobOccurrencesDict = {}

    # Track jobs in the root file
    track_job_sources(config, file_path, job_sources, all_job_occurrences)

    # Resolve includes and track job sources
    resolved_config = resolve_includes(config, base_path, base_path, 0, file_path, job_sources,
                                       all_job_occurrences, variables)

    # Now that all includes are resolved, resolve any reference tags
    resolved_config = resolve_references(resolved_config, resolved_config)

    # Update job_sources to include information about all occurrences
    for job_name, occurrences in all_job_occurrences.items():
        if len(occurrences) > 1:
            # If there are multiple occurrences, store the last one as the source
            # but also add a special attribute to indicate it's a duplicate
            job_sources[job_name] = occurrences[-1]
            job_sources[f"{job_name}__duplicates"] = occurrences[:-1]

    return resolved_config, job_sources

# Example usage:
if __name__ == "__main__":
    import sys

    # Set up basic logging configuration
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if len(sys.argv) != 2:
        logger.error("Usage: python loader.py path/to/.gitlab-ci.yml")
        sys.exit(1)

    root_file = sys.argv[1]
    try:
        final_config, job_sources = load_and_resolve(root_file)
        logger.info("Final merged configuration:")
        logger.info(yaml.dump(final_config, default_flow_style=False))
        logger.info("\nJob sources:")
        for job_name, source_file in job_sources.items():
            logger.info(f"  {job_name}: {source_file}")
    except Exception as e:
        logger.error(f"Error processing the YAML files: {e}")
