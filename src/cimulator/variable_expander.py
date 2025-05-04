import re
from typing import Any, List, Union, Optional
from cimulator.types import VariablesDict

def expand_variables_in_string(text: str, variables: VariablesDict) -> str:
    """
    Replace placeholders in a string with corresponding variable values.
    Supports placeholders in the form $VAR or ${VAR}.
    """
    pattern = re.compile(r'\$(\w+)|\$\{(\w+)\}')

    def replace(match):
        var_name = match.group(1) or match.group(2)
        return str(variables.get(var_name, ""))

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
