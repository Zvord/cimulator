import pytest
from cimulator.simulation_engine import simulate_pipeline
import yaml

def test_variable_expansion_in_script_commands():
    """Test that variables are correctly expanded in script commands containing quotes."""
    # Define a job with script commands that use variables with quotes
    all_jobs = {
        "job1": {
            "script": [
                'echo "Build type: ${BUILD_TYPE}"',
                'echo "Platform: ${PLATFORM}"',
                'echo "Global var: ${GLOBAL_VAR}"'
            ],
            "variables": {
                "BUILD_TYPE": "release",
                "PLATFORM": "linux"
            }
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables
    global_variables = {
        "GLOBAL_VAR": "global-value"
    }

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Print the entire simulation result for debugging
    print(yaml.dump(simulation, default_flow_style=False))

    # Get the expanded jobs from both sections
    all_expanded_job = simulation["all_expanded_jobs"]["job1"]
    job = simulation["jobs"]["job1"]

    # Check that variables are correctly expanded in the all_expanded_jobs section
    assert all_expanded_job["script"][0] == 'echo "Build type: release"'
    assert all_expanded_job["script"][1] == 'echo "Platform: linux"'
    assert all_expanded_job["script"][2] == 'echo "Global var: global-value"'

    # Check that variables are correctly expanded in the jobs section
    assert job["script"][0] == 'echo "Build type: release"'
    assert job["script"][1] == 'echo "Platform: linux"'
    assert job["script"][2] == 'echo "Global var: global-value"'


def test_global_variable_expansion_in_script_commands():
    """Test that global variables are correctly expanded in script commands."""
    # Define a job with script commands that use only global variables
    all_jobs = {
        "job1": {
            "script": [
                'echo "Global var 1: ${GLOBAL_VAR1}"',
                'echo "Global var 2: ${GLOBAL_VAR2}"',
                'echo "CI pipeline source: ${CI_PIPELINE_SOURCE}"'
            ]
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables
    global_variables = {
        "GLOBAL_VAR1": "global-value-1",
        "GLOBAL_VAR2": "global-value-2",
        "CI_PIPELINE_SOURCE": "merge_request"
    }

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Print the entire simulation result for debugging
    print(yaml.dump(simulation, default_flow_style=False))

    # Get the expanded jobs from both sections
    all_expanded_job = simulation["all_expanded_jobs"]["job1"]
    job = simulation["jobs"]["job1"]

    # Check that global variables are correctly expanded in the all_expanded_jobs section
    assert all_expanded_job["script"][0] == 'echo "Global var 1: global-value-1"'
    assert all_expanded_job["script"][1] == 'echo "Global var 2: global-value-2"'
    assert all_expanded_job["script"][2] == 'echo "CI pipeline source: merge_request"'

    # Check that global variables are correctly expanded in the jobs section
    assert job["script"][0] == 'echo "Global var 1: global-value-1"'
    assert job["script"][1] == 'echo "Global var 2: global-value-2"'
    assert job["script"][2] == 'echo "CI pipeline source: merge_request"'