import pytest
from cimulator.simulation_engine import simulate_pipeline

def test_job_variables_should_not_affect_other_jobs():
    """Test that variables defined in one job do not affect other jobs."""
    # Define jobs with different variables
    all_jobs = {
        "job1": {
            "script": "echo $SHARED_VAR $JOB1_VAR",
            "variables": {
                "SHARED_VAR": "job1_value",  # This should only affect job1
                "JOB1_VAR": "value1"
            }
        },
        "job2": {
            "script": "echo $SHARED_VAR $JOB2_VAR",
            "variables": {
                "JOB2_VAR": "value2"
            }
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables
    global_variables = {
        "SHARED_VAR": "global_value"  # This should be used in job2
    }

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Get the expanded jobs
    job1 = simulation["jobs"]["job1"]
    job2 = simulation["jobs"]["job2"]

    # Check that job1's SHARED_VAR is set to job1_value
    assert job1["script"] == "echo job1_value value1"

    # Check that job2's SHARED_VAR is set to global_value, not job1_value
    # This is the key test - if variable scoping works correctly,
    # job2 should not be affected by job1's variables
    assert job2["script"] == "echo global_value value2"
