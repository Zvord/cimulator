#!/usr/bin/env python3

import os
import yaml

def load_yaml(file_path):
    """
    Load a YAML file and return its contents as a dictionary.
    If the file is empty, return an empty dictionary.
    """
    with open(file_path, 'r') as f:
        return yaml.safe_load(f) or {}

def merge_dicts(base, incoming):
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

def resolve_includes(config, base_path):
    """
    Recursively resolve and merge included YAML files.
    The 'include' key in the YAML file can be a string (for a single include),
    a dictionary (with a 'local' key), or a list of such entries.

    Parameters:
        config (dict): The current YAML configuration.
        base_path (str): The directory of the current YAML file to resolve relative paths.

    Returns:
        dict: The configuration with all includes resolved and merged.
    """
    # If there's no 'include' key, return the config as-is.
    if "include" not in config:
        return config

    # Retrieve and remove the 'include' key from the config.
    includes = config.pop("include")
    if not isinstance(includes, list):
        includes = [includes]

    # Process each include entry.
    for inc in includes:
        # Determine the file path for the include.
        if isinstance(inc, str):
            include_path = os.path.join(base_path, inc)
        elif isinstance(inc, dict) and "local" in inc:
            include_path = os.path.join(base_path, inc["local"])
        else:
            # Unsupported include format, you might want to raise an error or skip.
            continue

        # Load the included YAML file.
        included_config = load_yaml(include_path)

        # Recursively resolve includes in the included file.
        include_base_path = os.path.dirname(include_path)
        included_config = resolve_includes(included_config, include_base_path)

        # Merge the included configuration into the current configuration.
        merge_dicts(config, included_config)

    return config

def load_and_resolve(file_path):
    """
    Load the root YAML file and resolve all includes recursively.

    Parameters:
        file_path (str): Path to the root .gitlab-ci.yml file.

    Returns:
        dict: The complete configuration with all includes merged.
    """
    base_path = os.path.dirname(os.path.abspath(file_path))
    config = load_yaml(file_path)
    resolved_config = resolve_includes(config, base_path)
    return resolved_config

# Example usage:
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python loader.py path/to/.gitlab-ci.yml")
        sys.exit(1)

    root_file = sys.argv[1]
    try:
        final_config = load_and_resolve(root_file)
        print("Final merged configuration:")
        print(yaml.dump(final_config, default_flow_style=False))
    except Exception as e:
        print(f"Error processing the YAML files: {e}")
