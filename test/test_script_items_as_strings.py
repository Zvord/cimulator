import pytest
import os
import tempfile
import yaml
from cimulator.loader import load_and_resolve
from cimulator.simulation_engine import simulate_pipeline

def test_script_items_with_colons_remain_strings():
    """Test that script items containing colons are preserved as strings during YAML parsing."""
    # Create a temporary .gitlab-ci.yml file with a script line containing a colon
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as ci_file:
        ci_content = """
# A job with a script line containing a colon
job1:
  script:
    - echo "Normal line"
    - run: echo "This line has a colon"
    - echo "Another normal line"
"""
        ci_file.write(ci_content)
        ci_file_path = ci_file.name

    try:
        # Load the .gitlab-ci.yml file
        ci_config, job_sources = load_and_resolve(ci_file_path)

        # Extract jobs from the configuration
        reserved_keys = {"include", "workflow", "variables", "stages"}
        jobs = {k: v for k, v in ci_config.items() if k not in reserved_keys and isinstance(v, dict)}

        # Print debug info about the job and script items
        print("\n=== DEBUG INFO ===")
        print(f"Job definition: {jobs['job1']}")
        print(f"Script items: {jobs['job1']['script']}")
        for i, item in enumerate(jobs['job1']['script']):
            print(f"Script item {i} type: {type(item)}")
            print(f"Script item {i} value: {item}")

        # Check that all script items are strings
        for i, item in enumerate(jobs['job1']['script']):
            assert isinstance(item, str), f"Script item {i} should be a string, got {type(item)}: {item}"

        # Check the specific values
        assert jobs['job1']['script'][0] == "echo \"Normal line\""
        assert jobs['job1']['script'][1] == "run: echo \"This line has a colon\""
        assert jobs['job1']['script'][2] == "echo \"Another normal line\""

        # Run a simulation to ensure the script items remain strings throughout the pipeline
        global_vars = {}
        simulation = simulate_pipeline(jobs, {}, global_vars)

        # Get the expanded job
        job = simulation["jobs"]["job1"]

        # Check that all script items in the expanded job are strings
        for i, item in enumerate(job["script"]):
            assert isinstance(item, str), f"Expanded script item {i} should be a string, got {type(item)}: {item}"

    finally:
        # Clean up the temporary file
        if os.path.exists(ci_file_path):
            os.unlink(ci_file_path)


def _load(tmp_path, content):
    ci_file = tmp_path / ".gitlab-ci.yml"
    ci_file.write_text(content)
    ci_config, _ = load_and_resolve(str(ci_file))
    return ci_config


def test_nested_script_lists_are_flattened(tmp_path):
    """Nested arrays in script sections are flattened, like GitLab does."""
    ci_config = _load(tmp_path, """
default:
  before_script:
    - [echo d1, [echo d2]]
job1:
  before_script:
    - [echo b1, echo b2]
  script:
    - echo s1
    - [echo s2, [echo s3, run: echo s4]]
    - echo s5
  after_script:
    - [echo a1]
""")
    assert ci_config["default"]["before_script"] == ["echo d1", "echo d2"]
    assert ci_config["job1"]["before_script"] == ["echo b1", "echo b2"]
    assert ci_config["job1"]["script"] == ["echo s1", "echo s2", "echo s3", "run: echo s4", "echo s5"]
    assert ci_config["job1"]["after_script"] == ["echo a1"]


def test_reference_in_script_list_is_flattened(tmp_path):
    """A !reference item in a script list is resolved and flattened, not stringified."""
    ci_config = _load(tmp_path, """
.setup:
  script:
    - echo setup1
    - echo setup2
job1:
  script:
    - !reference [.setup, script]
    - echo main
""")
    assert ci_config["job1"]["script"] == ["echo setup1", "echo setup2", "echo main"]
