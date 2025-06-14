#!/usr/bin/env python3

import os
import yaml
import logging
from typing import List, Union, Optional, Tuple, Set, Any
from cimulator.types import ConfigDict, JobDict, JobSourcesDict, JobOccurrencesDict

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

def ensure_script_items_are_strings(config: ConfigDict) -> ConfigDict:
    """
    Ensure that all script items in job definitions are strings.
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
        # If this is a job definition (not a reserved key) and it's a dictionary
        if key not in {"include", "workflow", "variables", "stages", "default"} and isinstance(value, dict):
            # If the job has a script section
            if "script" in value and isinstance(value["script"], list):
                # Process each script item
                for i, item in enumerate(value["script"]):
                    # If the item is not a string, convert it to a string
                    if not isinstance(item, str):
                        if isinstance(item, dict):
                            if len(item) == 1:
                                # Convert dictionary to "key: value" string format
                                dict_key, dict_value = list(item.items())[0]
                                value["script"][i] = f"{dict_key}: {dict_value}"
                            else:
                                # If the dictionary has more than one key-value pair, it's an error
                                raise ValueError(f"Invalid script item: {item}. Script items must be strings, but found a dictionary with multiple key-value pairs.")
                        else:
                            # For other types, use string representation
                            value["script"][i] = str(item)
        # Recursively process nested dictionaries
        elif isinstance(value, dict):
            config[key] = ensure_script_items_are_strings(value)

    return config

def load_yaml(file_path: str) -> ConfigDict:
    """
    Load a YAML file and return its contents as a dictionary.
    If the file is empty, return an empty dictionary.
    Uses a custom loader that supports GitLab CI-specific YAML tags.

    Note: This function does NOT resolve !reference tags. References will be
    resolved later, after all includes are processed and jobs are expanded.
    """
    with open(file_path, 'r') as f:
        document = yaml.load(f, Loader=GitLabCILoader) or {}
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

    reserved_keys = {"include", "workflow", "variables", "stages", "default"}
    for key in config:
        if key not in reserved_keys and isinstance(config[key], dict):
            # Record the source for all jobs, even if they've been seen before
            # This will ensure we have the most recent source for duplicate jobs
            job_sources[key] = current_file
            logger.debug(f"Tracking job '{key}' from file: {current_file}")

            # Track all occurrences of each job
            if key not in all_job_occurrences:
                all_job_occurrences[key] = []
            all_job_occurrences[key].append(current_file)

def resolve_includes(config: ConfigDict, base_path: str,
                    root_path: Optional[str] = None, depth: int = 0,
                    current_file: Optional[str] = None,
                    job_sources: Optional[JobSourcesDict] = None,
                    all_job_occurrences: Optional[JobOccurrencesDict] = None) -> ConfigDict:
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

    # Process each include entry.
    for inc in includes:
        try:
            # Determine the file path for the include.
            if isinstance(inc, str):
                include_path = os.path.normpath(os.path.join(base_path, inc))
            elif isinstance(inc, dict) and "local" in inc:
                include_path = os.path.normpath(os.path.join(base_path, inc["local"]))
            else:
                # Unsupported include format, you might want to raise an error or skip.
                continue

            # Load the included YAML file.
            included_config = load_yaml(include_path)

            # Recursively resolve includes in the included file.
            # Always use the root path for resolving nested includes
            included_config = resolve_includes(
                included_config,
                root_path,
                root_path,
                depth + 1,
                include_path,
                job_sources,
                all_job_occurrences
            )

            # Merge the included configuration into the current configuration.
            merge_dicts(config, included_config)
        except Exception as e:
            logger.warning(f"Error processing include {inc}: {e}")
            # Continue with other includes even if one fails

    return config

def load_and_resolve(file_path: str) -> Tuple[ConfigDict, JobSourcesDict]:
    """
    Load the root YAML file and resolve all includes recursively.

    Parameters:
        file_path (str): Path to the root .gitlab-ci.yml file.

    Returns:
        tuple: (resolved_config, job_sources)
            - resolved_config: The complete configuration with all includes merged.
            - job_sources: Dictionary mapping job names to their source files.
    """
    file_path = os.path.abspath(file_path)
    base_path = os.path.dirname(file_path)
    logger.info(f"Root file: {file_path}")
    logger.debug(f"Base path: {base_path}")
    config = load_yaml(file_path)

    # Initialize job_sources dictionary and all_jobs_occurrences
    job_sources: JobSourcesDict = {}
    all_job_occurrences: JobOccurrencesDict = {}

    # Track jobs in the root file
    track_job_sources(config, file_path, job_sources, all_job_occurrences)

    # Resolve includes and track job sources
    resolved_config = resolve_includes(config, base_path, base_path, 0, file_path, job_sources, all_job_occurrences)

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
