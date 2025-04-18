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
        ci_config = load_and_resolve(ci_file_path)
        
        # Print the loaded configuration
        print("Loaded configuration:")
        print(yaml.dump(ci_config, default_flow_style=False))
        
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
        
        # Print what we're passing to the simulation engine
        print("Jobs:", jobs)
        print("Global variables:", global_vars)
        
        # Run the simulation with the combined variables
        simulation = simulate_pipeline(jobs, {}, global_vars)
        
        # Print the entire simulation result for debugging
        print("Simulation result:")
        print(yaml.dump(simulation, default_flow_style=False))
        
        # Get the expanded job
        job = simulation["jobs"]["job1"]
        all_expanded_job = simulation["all_expanded_jobs"]["job1"]
        
        # Print the script sections for debugging
        print("Job script:", job["script"])
        print("All expanded job script:", all_expanded_job["script"])
        
        # Check that global variables from the .gitlab-ci.yml file are correctly expanded
        assert job["script"][0] == 'echo "Using global var: global-value-from-gitlab-ci"'
        assert job["script"][1] == 'echo "Using image: ubuntu:20.04"'
        
        # Also check the all_expanded_jobs section
        assert all_expanded_job["script"][0] == 'echo "Using global var: global-value-from-gitlab-ci"'
        assert all_expanded_job["script"][1] == 'echo "Using image: ubuntu:20.04"'
        
        # Verify that global_variables in the simulation summary contains the GitLab CI variables
        assert "GLOBAL_VAR" in simulation["global_variables"]
        assert simulation["global_variables"]["GLOBAL_VAR"] == "global-value-from-gitlab-ci"
        assert "BUILD_IMAGE" in simulation["global_variables"]
        assert simulation["global_variables"]["BUILD_IMAGE"] == "ubuntu:20.04"
        
    finally:
        # Clean up the temporary file
        if os.path.exists(ci_file_path):
            os.unlink(ci_file_path)