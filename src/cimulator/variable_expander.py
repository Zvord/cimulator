import re
from typing import Any, List, Union, Optional
from cimulator.types import VariablesDict

def variable_value(value: Any) -> str:
    """
    A variable's value as text, as GitLab has it: YAML gives `true` or `1`
    as a boolean or a number, while GitLab's value is the text `true` or
    `1`. A variable written as a mapping (`{value: ..., description: ...}`)
    has its `value`, and a variable without a value (`FOO:`) is empty.
    """
    if isinstance(value, dict):
        return variable_value(value.get("value"))
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value if isinstance(value, str) else str(value)

def variable_values(variables: Any) -> Any:
    """
    Variables as GitLab has them, as text: see variable_value(). An empty
    `variables:` (null) has none, as in GitLab.
    """
    if variables is None:
        return {}
    if not isinstance(variables, dict):
        return variables
    return {name: variable_value(value) for name, value in variables.items()}

def expand_variables_in_string(text: str, variables: VariablesDict) -> str:
    """
    Replace placeholders in a string with corresponding variable values.
    Supports placeholders in the form $VAR or ${VAR}.
    """
    pattern = re.compile(r'\$(\w+)|\$\{(\w+)\}')

    def replace(match):
        var_name = match.group(1) or match.group(2)
        return variable_value(variables.get(var_name))

    return pattern.sub(replace, text)

def expand_variables(obj: Any, variables: VariablesDict) -> Any:
    """
    Recursively expand variables in the given object.
    The object can be a dict, list, or string.
    """
    if isinstance(obj, dict):
        new_obj = {}
        for key, value in obj.items():
            new_key = expand_variables_in_string(key, variables) if isinstance(key, str) else key
            new_obj[new_key] = expand_variables(value, variables)
        return new_obj
    elif isinstance(obj, list):
        return [expand_variables(item, variables) for item in obj]
    elif isinstance(obj, str):
        return expand_variables_in_string(obj, variables)
    else:
        return obj
