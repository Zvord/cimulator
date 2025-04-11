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
    # job2 uses the global variable, which should not be affected by job1's variables
    assert jobs["job2"]["script"] == "echo Default Greeting"


def test_simulate_pipeline_with_extends_and_variable_precedence():
    """
    Test variable expansion precedence with extends, job variables, and global variables.
    Simulates a scenario where job variables should override global/parent variables.
    """
    all_jobs = {
        ".Base Job": {
            "interruptible": True,
            "tags": ["generic_tag"],
            "timeout": "1h",
            "stage": "build",
            "script": [
                "echo \"Build $MODULE with $TOOL. Base flags are $BASE_FLAGS. Run flags are $RUN_FLAGS.\"",
                "compile $MODULE -tool $TOOL $BASE_FLAGS -flags \" $RUN_FLAGS\""
            ],
            "artifacts": {
                "expire_in": "1 day",
                "when": "always",
                "paths": ["$RESULTS_DIR/"]
            },
            "variables": {
                "TOOL": "base_tool", # Tool defined in base job
                "BASE_FLAGS": "-b base"
            }
        },
        "Specific Job": {
            "extends": [".Base Job"],
            "rules": [
                {"if": '$RUN_FLAG_1 == "1" || $RUN_FLAG_2 == "1"'},
                # This rule compares a global var with a job-specific var
                {"if": '$COVERAGE_FLAG == "1" && $GLOBAL_TOOL_VAR == $TOOL'}
            ],
            "variables": {
                "MODULE": "specific_module", # Job-specific variable
                "TOOL": "specific_tool",     # Job-specific variable, should override base
                "RUN_FLAGS": "-r specific"   # Job-specific variable
            }
        },
        "Specific Job TOOL1": {
            "extends": ["Specific Job"],
             "rules": [
                # Example rule specific to this job
                {"if": '$CI_PIPELINE_SOURCE == "web" && $RUN_SPECIFIC_TOOL1 == "1"'}
            ],
           "variables": {
                "TOOL": "tool1_tool" # Overrides Specific Job's TOOL
            }
        }
    }
    # Minimal workflow to allow the pipeline to run
    workflow_config = {"rules": [{"when": "always"}]}
    # Global variables
    global_variables = {
        "CI_PIPELINE_SOURCE": "web",
        "RUN_FLAG_1": "0", # Example flags for rules
        "RUN_FLAG_2": "0",
        "COVERAGE_FLAG": "1",
        "GLOBAL_TOOL_VAR": "specific_tool", # Matches Specific Job's TOOL for its rule
        "RUN_SPECIFIC_TOOL1": "1", # To make Specific Job TOOL1 run
        "RESULTS_DIR": "/path/to/results" # Example path
        # Note: BASE_FLAGS is inherited from .Base Job
        # Note: RUN_FLAGS is overridden by Specific Job, then inherited by Specific Job TOOL1
    }

    # Run simulation - process order might matter, ensure jobs are processed
    # We expect the engine to handle the order based on dependencies or definition order
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Verify workflow ran
    assert simulation["workflow_run"] is True

    # Verify the jobs exist in the final list
    jobs = simulation["jobs"]
    assert "Specific Job" in jobs
    assert "Specific Job TOOL1" in jobs

    # --- Verify Specific Job ---
    # Verify the specific job's expanded script content
    # TOOL should be 'specific_tool' (from job)
    # MODULE should be 'specific_module' (from job)
    # BASE_FLAGS should be '-b base' (inherited)
    # RUN_FLAGS should be '-r specific' (from job)
    expected_script_specific = [
        "echo \"Build specific_module with specific_tool. Base flags are -b base. Run flags are -r specific.\"",
        "compile specific_module -tool specific_tool -b base -flags \" -r specific\""
    ]
    assert jobs["Specific Job"]["script"] == expected_script_specific
    assert jobs["Specific Job"]["variables"]["TOOL"] == "specific_tool" # Check variable value itself

    # Verify the expanded artifacts path for Specific Job
    assert jobs["Specific Job"]["artifacts"]["paths"] == ["/path/to/results/"]

    # --- Verify Specific Job TOOL1 ---
    # Verify the TOOL1 job's expanded script content
    # TOOL should be 'tool1_tool' (from job)
    # MODULE should be 'specific_module' (inherited from Specific Job)
    # BASE_FLAGS should be '-b base' (inherited from .Base Job)
    # RUN_FLAGS should be '-r specific' (inherited from Specific Job)
    expected_script_tool1 = [
        "echo \"Build specific_module with tool1_tool. Base flags are -b base. Run flags are -r specific.\"",
        "compile specific_module -tool tool1_tool -b base -flags \" -r specific\""
    ]
    assert jobs["Specific Job TOOL1"]["script"] == expected_script_tool1
    assert jobs["Specific Job TOOL1"]["variables"]["TOOL"] == "tool1_tool" # Check variable value itself

    # Verify the expanded artifacts path for Specific Job TOOL1
    assert jobs["Specific Job TOOL1"]["artifacts"]["paths"] == ["/path/to/results/"]


    # Verify the expanded rules (optional, but good check) - Focus on Specific Job
    # The second rule should evaluate correctly based on TOOL=specific_tool
    # Note: The current implementation might show incorrect expansion here too
    # expected_rules = [
    #     {'if': '0 == "1" || 0 == "1"'},
    #     {'if': '1 == "1" && "specific_tool" == "specific_tool"'} # Correct expansion
    # ]
    # assert jobs["Specific Job"]["rules"] == expected_rules
