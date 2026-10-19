"""
Support for GitLab CI/CD inputs (`spec:inputs`).

A configuration file can start with a header document declaring the inputs it
accepts, separated from the configuration by `---`:

    spec:
      inputs:
        version:
          default: ""
    ---
    job:
      script: echo $[[ inputs.version ]]

GitLab interpolates `$[[ inputs.NAME ]]` when the pipeline is created, using the
values passed to the pipeline (or to `include:inputs`) and the declared defaults.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from cimulator.types import ConfigDict

logger = logging.getLogger(__name__)

InputsDict = Dict[str, Any]

# $[[ inputs.NAME ]] with optional "| function" chain. Other contexts such as
# $[[ component.sha ]] or $[[ matrix.X ]] do not match and are left untouched.
INTERPOLATION_RE = re.compile(r"\$\[\[\s*inputs\.([A-Za-z0-9_-]+)\s*((?:\|[^|\]]*)*)\]\]")
FUNCTION_RE = re.compile(r"^\s*([a-z_]+)\s*(?:\(([^)]*)\))?\s*$")

TYPES = {
    "string": (str,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
}


class InputsError(ValueError):
    """Invalid inputs declaration, value or interpolation."""


def split_header(documents: List[Any], file_path: str) -> Tuple[Optional[ConfigDict], ConfigDict]:
    """
    Split the YAML documents of a file into the `spec` header and the configuration.

    Returns:
        tuple: (spec, config). spec is None when the file has no header.
    """
    documents = [d if d is not None else {} for d in documents]
    if not documents:
        return None, {}
    if len(documents) == 1:
        return None, documents[0]
    if len(documents) == 2 and isinstance(documents[0], dict) and set(documents[0]) == {"spec"}:
        return documents[0]["spec"] or {}, documents[1]
    raise InputsError(
        f"{file_path}: multiple YAML documents are only allowed as a `spec` header "
        "followed by the configuration"
    )


def _coerce(name: str, value: Any, input_type: str) -> Any:
    """Convert a string value (e.g. from the command line) to the declared type."""
    if not isinstance(value, str) or input_type == "string":
        return value
    if input_type == "boolean" and value.lower() in ("true", "false"):
        return value.lower() == "true"
    if input_type in ("number", "array"):
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError:
            parsed = None
        if not isinstance(parsed, bool) and isinstance(parsed, TYPES[input_type]):
            return parsed
    raise InputsError(f"input '{name}': expected a {input_type}, got {value!r}")


def resolve_inputs(spec: ConfigDict, provided: Optional[InputsDict], file_path: str) -> InputsDict:
    """
    Compute the value of each declared input from the provided values and defaults.

    Raises:
        InputsError: on unknown or missing inputs, or values that do not match
        the declared type, options or regex.
    """
    declared = spec.get("inputs") or {}
    provided = provided or {}

    unknown = sorted(set(provided) - set(declared))
    if unknown:
        raise InputsError(f"{file_path}: unknown input(s): {', '.join(unknown)}")

    values: InputsDict = {}
    for name, definition in declared.items():
        definition = definition or {}
        input_type = definition.get("type", "string")
        if input_type not in TYPES:
            raise InputsError(f"{file_path}: input '{name}' has unsupported type '{input_type}'")

        if name in provided:
            value = _coerce(name, provided[name], input_type)
        elif definition.get("default") is not None:
            value = definition["default"]
        else:
            raise InputsError(f"{file_path}: required input '{name}' was not provided")

        # bool is a subclass of int, don't accept it as a number
        if not isinstance(value, TYPES[input_type]) or (input_type == "number" and isinstance(value, bool)):
            raise InputsError(f"{file_path}: input '{name}': expected a {input_type}, got {value!r}")
        if "options" in definition and value not in definition["options"]:
            raise InputsError(
                f"{file_path}: input '{name}': {value!r} is not one of {definition['options']}"
            )
        if "regex" in definition and not re.search(definition["regex"], str(value)):
            raise InputsError(
                f"{file_path}: input '{name}': {value!r} does not match /{definition['regex']}/"
            )
        values[name] = value
    return values


def _to_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return yaml.safe_dump(value, default_flow_style=True).strip()
    return str(value)


def _posix_escape(value: str) -> str:
    """Escape shell meta characters, like Ruby's Shellwords.escape used by GitLab."""
    if value == "":
        return "''"
    escaped = re.sub(r"([^A-Za-z0-9_\-.,:+/@\n])", r"\\\1", value)
    return escaped.replace("\n", "'\n'")


def _apply_function(value: Any, function: str) -> Any:
    match = FUNCTION_RE.match(function)
    if not match:
        raise InputsError(f"invalid interpolation function '{function.strip()}'")
    name, args = match.group(1), match.group(2)
    if name == "expand_vars":
        # Variables are expanded later by the simulation, keep the reference
        return _to_string(value)
    if name == "posix_escape":
        return _posix_escape(_to_string(value))
    if name == "truncate":
        try:
            offset, length = (int(a) for a in (args or "").split(","))
        except ValueError:
            raise InputsError(f"truncate expects (offset,length), got '{function.strip()}'")
        return _to_string(value)[offset:offset + length]
    raise InputsError(f"unknown interpolation function '{name}'")


def _interpolate_string(text: str, values: InputsDict, file_path: str) -> Any:
    def evaluate(match: "re.Match[str]") -> Any:
        name = match.group(1)
        if name not in values:
            raise InputsError(f"{file_path}: unknown interpolation key 'inputs.{name}'")
        value = values[name]
        for function in match.group(2).split("|")[1:]:
            value = _apply_function(value, function)
        return value

    whole = INTERPOLATION_RE.fullmatch(text.strip())
    if whole:
        # The input is the whole value: keep its type (e.g. an array for needs)
        return evaluate(whole)
    return INTERPOLATION_RE.sub(lambda m: _to_string(evaluate(m)), text)


def interpolate(obj: Any, values: InputsDict, file_path: str) -> Any:
    """Recursively replace `$[[ inputs.NAME ]]` in keys and values."""
    if isinstance(obj, dict):
        return {
            (_to_string(_interpolate_string(k, values, file_path)) if isinstance(k, str) else k):
                interpolate(v, values, file_path)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [interpolate(item, values, file_path) for item in obj]
    if isinstance(obj, str):
        return _interpolate_string(obj, values, file_path)
    return obj


def apply_inputs(documents: List[Any], provided: Optional[InputsDict], file_path: str) -> ConfigDict:
    """
    Turn the YAML documents of a file into its configuration, interpolating inputs.

    Files without a `spec` header are returned as-is, and cannot receive inputs.
    """
    spec, config = split_header(documents, file_path)
    if spec is None:
        if provided:
            raise InputsError(f"{file_path}: inputs given but the file has no `spec:inputs` header")
        return config
    values = resolve_inputs(spec, provided, file_path)
    logger.debug(f"Inputs for {file_path}: {values}")
    return interpolate(config, values, file_path)


def parse_cli_inputs(items: Optional[List[str]]) -> InputsDict:
    """Parse repeated `--input KEY=VALUE` command line options."""
    inputs: InputsDict = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise InputsError(f"--input expects KEY=VALUE, got {item!r}")
        inputs[key] = value
    return inputs
