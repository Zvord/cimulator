import pytest
from cimulator.simulation_engine import simulate_pipeline
from cimulator.variable_expander import expand_variables_in_string

def test_non_existing_variables_expand_to_empty_string():
    """Test that non-existing variables are expanded to empty strings."""
    # Test the expand_variables_in_string function directly
    variables = {"EXISTING": "value"}
    text = "This is $EXISTING and $NON_EXISTING."
    expected = "This is value and ."
    result = expand_variables_in_string(text, variables)
    assert result == expected

def test_non_existing_variables_in_job_definition():
    """Test that non-existing variables in job definitions are expanded to empty strings."""
    # Define a job with a variable that references a non-existing variable
    all_jobs = {
        "job1": {
            "script": "echo $NON_EXISTING_VAR",
            "variables": {
                "PATH_WITH_NON_EXISTING": "path/$NON_EXISTING_DIR/file.txt"
            }
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables (without the non-existing variables)
    global_variables = {
        "EXISTING_VAR": "exists"
    }

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Get the expanded job
    job = simulation["jobs"]["job1"]

    # Check that non-existing variables are expanded to empty strings
    assert job["script"] == "echo "
    assert job["variables"]["PATH_WITH_NON_EXISTING"] == "path//file.txt"

def test_non_existing_variables_in_rule_conditions():
    """Test that non-existing variables in rule conditions are expanded to empty strings."""
    # Define a job with a rule that uses a non-existing variable
    all_jobs = {
        "job1": {
            "script": "echo test",
            "rules": [
                {
                    "if": "$NON_EXISTING_VAR == \"\"",  # This should evaluate to true
                    "when": "always"
                }
            ]
        },
        "job2": {
            "script": "echo test",
            "rules": [
                {
                    "if": "$NON_EXISTING_VAR == \"something\"",  # This should evaluate to false
                    "when": "always"
                }
            ]
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables (without the non-existing variables)
    global_variables = {}

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Check that job1 is included in the jobs that will run (since $NON_EXISTING_VAR == "" is true)
    assert "job1" in simulation["jobs_list"]

    # Check that job2 is not included in the jobs that will run (since $NON_EXISTING_VAR == "something" is false)
    assert "job2" not in simulation["jobs_list"]
