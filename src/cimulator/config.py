import yaml
from cimulator.types import ConfigDict

class TextValueLoader(yaml.SafeLoader):
    """
    A safe YAML loader that reads every value as written, as text: GitLab
    variables are text, so 1.10 stays 1.10, 010 stays 010 and yes stays yes.
    Only null (null, ~ or nothing) and << merges keep their YAML meaning.
    """

TextValueLoader.yaml_implicit_resolvers = {
    first: [(tag, regex) for tag, regex in resolvers
            if tag in ("tag:yaml.org,2002:null", "tag:yaml.org,2002:merge")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

def load_simulation_config(file_path: str) -> ConfigDict:
    """
    Load a simulation configuration YAML file.

    The configuration file is expected to contain a top-level dictionary.

    Parameters:
        file_path (str): Path to the simulation configuration YAML file.

    Returns:
        dict: The configuration dictionary.
    """
    with open(file_path, 'r') as f:
        config = yaml.load(f, Loader=TextValueLoader)
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError(f"The simulation configuration '{file_path}' must be a mapping "
                         f"of profiles, not a {type(config).__name__}")
    return config

def variable_value(value):
    """
    A variable value as GitLab sees it: a string. YAML gives `true` or `1` as
    a boolean or a number; GitLab's value is the text, `true` or `1`.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)

def profile_variables(profile, name: str = "") -> ConfigDict:
    """
    The variables of a simulation profile, as strings. An empty profile has
    none. Raises ValueError if the profile is not a mapping of variables
    whose values are text, numbers, booleans or null.
    """
    if profile is None:
        return {}
    if not isinstance(profile, dict):
        raise ValueError(f"Profile '{name}' must be a mapping of variables, "
                         f"not a {type(profile).__name__}")
    for variable, value in profile.items():
        if isinstance(value, (dict, list)):
            raise ValueError(f"Profile '{name}': the value of {variable} must be "
                             f"text, a number or a boolean, not a {type(value).__name__}")
    return {variable: variable_value(value) for variable, value in profile.items()}
