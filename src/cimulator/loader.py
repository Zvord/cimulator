#!/usr/bin/env python3

import os
import yaml

# Define a special class to represent a !reference tag that will be processed later
class ReferenceTag:
    def __init__(self, path_components):
        self.path_components = path_components

    def resolve(self, document):
        """
        Resolve the reference by navigating through the document.

        Args:
            document: The complete YAML document

        Returns:
            The referenced value
        """
        # Start with the first component (the anchor name without the &)
        current = document
        anchor_name = self.path_components[0]

        # First, find the node with the given name
        if anchor_name not in document:
            raise ValueError(f"Unknown reference target: {anchor_name}")

        current = document[anchor_name]

        # Navigate through the remaining path components
        for component in self.path_components[1:]:
            if isinstance(current, dict) and component in current:
                current = current[component]
            elif isinstance(current, list) and isinstance(component, int) and 0 <= component < len(current):
                current = current[component]
            else:
                raise ValueError(f"Invalid reference path: {self.path_components}")

        return current

# Define a constructor for the !reference tag.
def reference_constructor(loader, node):
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
            return loader.construct_scalar(node)

# Create a custom YAML loader that includes our constructor
class GitLabCILoader(yaml.SafeLoader):
    pass

# Register the constructor with our custom loader
GitLabCILoader.add_constructor('!reference', reference_constructor)

def resolve_references(obj, document):
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
        for i, item in enumerate(obj):
            obj[i] = resolve_references(item, document)
    elif isinstance(obj, ReferenceTag):
        return obj.resolve(document)
    return obj

def load_yaml(file_path):
    """
    Load a YAML file and return its contents as a dictionary.
    If the file is empty, return an empty dictionary.
    Uses a custom loader that supports GitLab CI-specific YAML tags.

    This function also resolves any !reference tags in the loaded document.
    """
    with open(file_path, 'r') as f:
        document = yaml.load(f, Loader=GitLabCILoader) or {}
        # Resolve any reference tags in the document
        document = resolve_references(document, document)
        return document

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

def resolve_includes(config, base_path, root_path=None, depth=0):
    """
    Recursively resolve and merge included YAML files.
    The 'include' key in the YAML file can be a string (for a single include),
    a dictionary (with a 'local' key), or a list of such entries.

    Parameters:
        config (dict): The current YAML configuration.
        base_path (str): The directory of the current YAML file to resolve relative paths.
        root_path (str): The root directory of the project, used for resolving nested includes.
        depth (int): Current recursion depth, used for debugging.

    Returns:
        dict: The configuration with all includes resolved and merged.
    """
    # If root_path is not provided, use base_path as the root path
    if root_path is None:
        root_path = base_path

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
            included_config = resolve_includes(included_config, root_path, root_path, depth + 1)

            # Merge the included configuration into the current configuration.
            merge_dicts(config, included_config)
        except Exception as e:
            print(f"Warning: Error processing include {inc}: {e}")
            # Continue with other includes even if one fails

    return config

def load_and_resolve(file_path):
    """
    Load the root YAML file and resolve all includes recursively.

    Parameters:
        file_path (str): Path to the root .gitlab-ci.yml file.

    Returns:
        dict: The complete configuration with all includes merged.
    """
    file_path = os.path.abspath(file_path)
    base_path = os.path.dirname(file_path)
    print(f"Root file: {file_path}")
    print(f"Base path: {base_path}")
    config = load_yaml(file_path)
    resolved_config = resolve_includes(config, base_path, base_path)
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
