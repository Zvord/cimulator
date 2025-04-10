import pytest
from cimulator.simulation_engine import simulate_pipeline

def test_variable_expansion_within_job():
    """Test that variables are correctly expanded within a job's own scope."""
    # Define jobs with variables that reference other variables within the same job
    all_jobs = {
        "job1": {
            "script": "echo $PATH_WITH_BASE",
            "variables": {
                "BASE_DIR": "/var/lib",
                "PATH_WITH_BASE": "$BASE_DIR/data"  # This should be expanded to "/var/lib/data"
            }
        },
        "job2": {
            "script": "echo $NESTED_VAR",
            "variables": {
                "VAR1": "value1",
                "VAR2": "$VAR1/value2",
                "NESTED_VAR": "$VAR2/value3"  # This should be expanded to "value1/value2/value3"
            }
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables
    global_variables = {}

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Get the expanded jobs
    job1 = simulation["jobs"]["job1"]
    job2 = simulation["jobs"]["job2"]

    # Check that variables are correctly expanded within job1
    assert job1["variables"]["PATH_WITH_BASE"] == "/var/lib/data"
    assert job1["script"] == "echo /var/lib/data"

    # Check that nested variables are correctly expanded within job2
    assert job2["variables"]["VAR2"] == "value1/value2"
    assert job2["variables"]["NESTED_VAR"] == "value1/value2/value3"
    assert job2["script"] == "echo value1/value2/value3"
