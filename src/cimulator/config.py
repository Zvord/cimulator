import yaml

def load_simulation_config(file_path):
    """
    Load a simulation configuration YAML file.

    The configuration file is expected to contain a top-level dictionary.

    Parameters:
        file_path (str): Path to the simulation configuration YAML file.

    Returns:
        dict: The configuration dictionary.
    """
    with open(file_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    return config
