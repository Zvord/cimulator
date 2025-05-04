import pytest
import os
import tempfile
import yaml
from cimulator.loader import load_and_resolve
from cimulator.simulation_engine import simulate_pipeline

def test_global_variables_from_gitlab_ci_file():
    """Test that global variables from the .gitlab-ci.yml file are correctly used in the simulation."""
    # Create a temporary .gitlab-ci.yml file with global variables
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as ci_file:
        ci_content = """
# Global variables defined in the .gitlab-ci.yml file
variables:
  GLOBAL_VAR: "global-value-from-gitlab-ci"
  BUILD_IMAGE: "ubuntu:20.04"

# A job using the global variable
job1:
  script:
    - echo "Using global var: ${GLOBAL_VAR}"
    - echo "Using image: ${BUILD_IMAGE}"
"""
        ci_file.write(ci_content)
        ci_file_path = ci_file.name

    try:
        # Load the .gitlab-ci.yml file
        ci_config, job_sources = load_and_resolve(ci_file_path)

        # Extract jobs and variables from the configuration
        reserved_keys = {"include", "workflow", "variables", "stages"}
        jobs = {k: v for k, v in ci_config.items() if k not in reserved_keys and isinstance(v, dict)}

        # Get global variables from GitLab CI file
        gitlab_vars = ci_config.get("variables", {})

        # Define simulation profile variables
        profile_vars = {"CI_PIPELINE_SOURCE": "merge_request"}

        # Merge GitLab CI variables with profile variables
        # Profile variables take precedence over GitLab CI variables
        global_vars = {**gitlab_vars, **profile_vars}

        # Run the simulation with the combined variables
        simulation = simulate_pipeline(jobs, {}, global_vars)

        # Get the expanded job
        job = simulation["jobs"]["job1"]
        all_expanded_job = simulation["all_expanded_jobs"]["job1"]

        # Check that we have 2 script commands
        assert len(job["script"]) == 2

        # Check expanded variables in script - job section
        script_items = job["script"]

        # Script items should always be strings
        # Check first command - Using global var
        assert isinstance(script_items[0], str), f"Script item should be a string, got {type(script_items[0])}: {script_items[0]}"
        assert 'echo "Using global var' in script_items[0]
        assert 'global-value-from-gitlab-ci' in script_items[0]

        # Check second command - Using image
        assert isinstance(script_items[1], str), f"Script item should be a string, got {type(script_items[1])}: {script_items[1]}"
        assert 'echo "Using image' in script_items[1]
        assert 'ubuntu:20.04' in script_items[1]

        # Check expanded variables in script - all_expanded_jobs section
        script_items = all_expanded_job["script"]

        # Script items should always be strings
        # Check first command - Using global var
        assert isinstance(script_items[0], str), f"Script item should be a string, got {type(script_items[0])}: {script_items[0]}"
        assert 'echo "Using global var' in script_items[0]
        assert 'global-value-from-gitlab-ci' in script_items[0]

        # Check second command - Using image
        assert isinstance(script_items[1], str), f"Script item should be a string, got {type(script_items[1])}: {script_items[1]}"
        assert 'echo "Using image' in script_items[1]
        assert 'ubuntu:20.04' in script_items[1]

        # Verify that global_variables in the simulation summary contains the GitLab CI variables
        assert "GLOBAL_VAR" in simulation["global_variables"]
        assert simulation["global_variables"]["GLOBAL_VAR"] == "global-value-from-gitlab-ci"
        assert "BUILD_IMAGE" in simulation["global_variables"]
        assert simulation["global_variables"]["BUILD_IMAGE"] == "ubuntu:20.04"

    finally:
        # Clean up the temporary file
        if os.path.exists(ci_file_path):
            os.unlink(ci_file_path)
