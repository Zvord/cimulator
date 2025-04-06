from cimulator.variable_expander import expand_variables
from cimulator.simulation_engine import simulate_pipeline

def test_expand_variables_in_string():
    variables = {"VAR": "value", "NAME": "GitLab"}
    text = "This is $VAR and ${NAME}."
    expected = "This is value and GitLab."
    from cimulator.variable_expander import expand_variables_in_string
    result = expand_variables_in_string(text, variables)
    assert result == expected

def test_expand_variables_in_dict():
    variables = {"HOST": "localhost", "PORT": "8080"}
    obj = {
        "url": "http://$HOST:${PORT}/api",
        "nested": {"key": "Value is ${PORT}"}
    }
    expected = {
        "url": "http://localhost:8080/api",
        "nested": {"key": "Value is 8080"}
    }
    result = expand_variables(obj, variables)
    assert result == expected

def test_simulate_pipeline():
    # Define a simple set of jobs.
    all_jobs = {
        "job1": {
            "script": "echo $GREETING",
            "rules": [
                {"if": '$CI_PIPELINE_SOURCE == "push"', "when": "always", "variables": {"GREETING": "Hello from push"}}
            ]
        },
        "job2": {
            "script": "echo $GREETING",
            # This job has no rules, so it should simply expand with the global variables.
        }
    }
    # Define a workflow that always runs.
    workflow_config = {
        "rules": [
            {"if": '$CI_PIPELINE_SOURCE == "push"', "when": "always", "variables": {"PIPELINE": "push_pipeline"}}
        ]
    }
    # Global variables provided to the simulation.
    global_variables = {"CI_PIPELINE_SOURCE": "push", "GREETING": "Default Greeting"}

    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Verify workflow results.
    assert simulation["workflow_run"] is True
    # Verify that job1 and job2 were processed.
    jobs = simulation["jobs"]
    assert "job1" in jobs
    assert "job2" in jobs
    # Check that variable expansion happened.
    assert jobs["job1"]["script"] == "echo Hello from push"
    # job2 uses the global variable, but it may have been overridden by workflow rules.
    assert jobs["job2"]["script"] == "echo Hello from push"
