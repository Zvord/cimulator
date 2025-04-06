import os
import tempfile
import yaml
import pytest
from cimulator.loader import load_yaml, load_and_resolve

def test_reference_tag_handling():
    """Test that the !reference tag is handled correctly."""
    # Create a YAML file with a !reference tag
    yaml_content = """
base:
  script:
    - echo "Base script"
  variables:
    BASE_VAR: "base_value"

job1:
  script: !reference [base, script]
  variables:
    JOB_VAR: "job_value"
    BASE_VAR: !reference [base, variables, BASE_VAR]
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(yaml_content)
        file_path = tmp.name

    try:
        # Load the YAML file
        config = load_yaml(file_path)

        # Check that the !reference tags were resolved correctly
        assert config["job1"]["script"] == ["echo \"Base script\""]
        assert config["job1"]["variables"]["BASE_VAR"] == "base_value"
    finally:
        os.remove(file_path)
