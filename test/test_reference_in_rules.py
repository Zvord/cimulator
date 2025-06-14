import os  
import tempfile
import pytest
from cimulator.loader import load_yaml, resolve_references

def test_reference_tag_in_rules():
    """Test that the !reference tag works correctly inside rules section, including array flattening."""
    # Create a YAML file with a !reference tag in rules section
    yaml_content = """
template:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      when: always
    - if: '$CI_PIPELINE_SOURCE == "push"'
      when: manual

job1:
  script:
    - echo "Job 1 script"
  rules: !reference [template, rules]

job2:
  script:
    - echo "Job 2 script"  
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'
      when: manual
    - !reference [template, rules]
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
      when: on_success
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(yaml_content)
        file_path = tmp.name

    try:
        # Load the YAML file
        config = load_yaml(file_path)
        
        # Resolve references
        config = resolve_references(config, config)
        
        # Check that the !reference tag in rules was resolved correctly for job1
        expected_rules = [
            {"if": "$CI_PIPELINE_SOURCE == \"merge_request_event\"", "when": "always"},
            {"if": "$CI_PIPELINE_SOURCE == \"push\"", "when": "manual"}
        ]
        assert config["job1"]["rules"] == expected_rules
        
        # Check that the array reference in rules was resolved correctly for job2
        # The reference should be flattened in the middle of the array
        expected_job2_rules = [
            {"if": "$CI_PIPELINE_SOURCE == \"web\"", "when": "manual"},
            {"if": "$CI_PIPELINE_SOURCE == \"merge_request_event\"", "when": "always"},
            {"if": "$CI_PIPELINE_SOURCE == \"push\"", "when": "manual"},
            {"if": "$CI_PIPELINE_SOURCE == \"schedule\"", "when": "on_success"}
        ]
        assert config["job2"]["rules"] == expected_job2_rules
        
    finally:
        os.remove(file_path)

def test_reference_with_file_list_in_rules():
    """Test that !reference tag works with file lists in rules changes section."""
    # Create a YAML file with templates containing file lists and rules
    yaml_content = """
.files: &filelist
  - src/**/*.py
  - test/**/*.py
  - requirements.txt

.template:
  rules:
    - changes: *filelist
      when: always
    - when: manual

job_using_template:
  script:
    - echo "Running tests"
  rules: !reference [.template, rules]
"""
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(yaml_content)
        file_path = tmp.name

    try:
        # Load the YAML file
        config = load_yaml(file_path)
        
        # Resolve references
        config = resolve_references(config, config)
        
        # Check that the !reference tag resolved the rules correctly
        expected_rules = [
            {
                "changes": ["src/**/*.py", "test/**/*.py", "requirements.txt"],
                "when": "always"
            },
            {"when": "manual"}
        ]
        assert config["job_using_template"]["rules"] == expected_rules
        
        # Verify the file list template exists
        assert config[".files"] == ["src/**/*.py", "test/**/*.py", "requirements.txt"]
        
    finally:
        os.remove(file_path)