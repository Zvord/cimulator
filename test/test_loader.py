import os
import tempfile
import yaml

# Import the functions from your loader module.
# Adjust the import based on your actual module structure.
from cimulator.loader import load_yaml, merge_dicts, load_and_resolve


def test_merge_dicts_simple():
    base = {"a": 1, "b": {"x": 10}}
    incoming = {"b": {"y": 20}, "c": 3}
    expected = {"a": 1, "b": {"x": 10, "y": 20}, "c": 3}
    result = merge_dicts(base, incoming)
    assert result == expected


def test_merge_dicts_override():
    base = {"a": 1, "b": {"x": 10}, "d": [1, 2, 3]}
    incoming = {"a": 100, "b": {"x": 50}, "d": [4, 5]}
    expected = {"a": 100, "b": {"x": 50}, "d": [4, 5]}
    result = merge_dicts(base, incoming)
    assert result == expected


def test_load_yaml_empty_file():
    # Create a temporary empty file.
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        file_path = tmp.name
    try:
        result = load_yaml(file_path)
        assert result == {}
    finally:
        os.remove(file_path)


def test_resolve_includes_single():
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a child YAML file.
        child_content = {"child_key": "child_value"}
        child_file = os.path.join(temp_dir, "child.yml")
        with open(child_file, "w") as f:
            yaml.dump(child_content, f)

        # Create a main YAML file with an include directive.
        main_content = {"include": "child.yml", "main_key": "main_value"}
        main_file = os.path.join(temp_dir, "main.yml")
        with open(main_file, "w") as f:
            yaml.dump(main_content, f)

        # Load and resolve includes.
        result = load_and_resolve(main_file)
        expected = {"main_key": "main_value", "child_key": "child_value"}
        assert result == expected


def test_resolve_includes_recursive():
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the grandchild YAML file.
        grandchild_content = {"grandchild_key": "grandchild_value"}
        grandchild_file = os.path.join(temp_dir, "grandchild.yml")
        with open(grandchild_file, "w") as f:
            yaml.dump(grandchild_content, f)

        # Create a child YAML file that includes the grandchild.
        child_content = {"include": "grandchild.yml", "child_key": "child_value"}
        child_file = os.path.join(temp_dir, "child.yml")
        with open(child_file, "w") as f:
            yaml.dump(child_content, f)

        # Create a main YAML file that includes the child.
        main_content = {"include": "child.yml", "main_key": "main_value"}
        main_file = os.path.join(temp_dir, "main.yml")
        with open(main_file, "w") as f:
            yaml.dump(main_content, f)

        # Load and resolve includes.
        result = load_and_resolve(main_file)
        expected = {
            "main_key": "main_value",
            "child_key": "child_value",
            "grandchild_key": "grandchild_value",
        }
        assert result == expected


def test_include_as_dict():
    # Test include when specified as a dict with a 'local' key.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a child file.
        child_content = {"child_key": "child_value"}
        child_file = os.path.join(temp_dir, "child.yml")
        with open(child_file, "w") as f:
            yaml.dump(child_content, f)

        # Create a main file with include as a dict.
        main_content = {"include": {"local": "child.yml"}, "main_key": "main_value"}
        main_file = os.path.join(temp_dir, "main.yml")
        with open(main_file, "w") as f:
            yaml.dump(main_content, f)

        result = load_and_resolve(main_file)
        expected = {"main_key": "main_value", "child_key": "child_value"}
        assert result == expected
