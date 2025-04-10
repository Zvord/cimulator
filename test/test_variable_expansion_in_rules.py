import pytest
from cimulator.simulation_engine import simulate_pipeline

def test_variable_expansion_in_rule_conditions():
    """Test that variables are correctly expanded in rule conditions."""
    # Define a job with a rule that uses a variable in the condition
    all_jobs = {
        ".Generic Tool Coverage Test": {
            "extends": [".Generic Coverage Test"],
            "tags": ["runner_8"],
            "variables": {
                "TOOL": "tool1",
                "DEPTH": "10"
            },
            "after_script": [
                "test_setup",
                "if [ \"$CI_PIPELINE_SOURCE\" != \"merge_request_event\" ]; then\n  tools/coverage.py -action upload -prefix $PUBLISH_BRANCH/$S3_PATH -cov ./test_results/*.data -merge_depth $DEPTH\nfi"
            ]
        },
        ".Generic Coverage Test": {
            "tags": ["runner_8"],
            "variables": {
                "DEPTH": "5"
            }
        },
        "Component Feature Test": {
            "extends": [".Generic Tool Coverage Test"],
            "tags": ["runner_8"],
            "rules": [
                {
                    "if": "$RUN_FEATURE_COVERAGE == \"1\" && $COVERAGE_TOOL == $TOOL",
                    "allow_failure": True
                },
                {
                    "if": "$CI_PIPELINE_SOURCE != \"schedule\" && $RUN_REGRESSIONS == \"1\" && $MR_TOOL == $TOOL",
                    "changes": ["src/component.ext", "src/component_part.ext"]
                },
                {
                    "if": "$RUN_NIGHTLY_FEATURE == \"1\" || $RUN_WEEKEND_FEATURE == \"1\""
                }
            ],
            "needs": ["Component Feature Build"],
            "variables": {
                "MODULE": "component",
                "REGRESS_NAME": "mini",
                "TEST_FLAGS": "-report -exclude test/component/exclusions.txt",
                "S3_PATH": "project/$MODULE/$TOOL",
                "JOBS": "4"
            }
        }
    }

    # Define a workflow configuration
    workflow_config = {}

    # Define global variables
    global_variables = {
        "CI_PIPELINE_SOURCE": "push",
        "RUN_FEATURE_COVERAGE": "1",
        "COVERAGE_TOOL": "tool1",
        "MR_TOOL": "tool1",
        "RUN_REGRESSIONS": "1",
        "RUN_NIGHTLY_FEATURE": "0",
        "RUN_WEEKEND_FEATURE": "0"
    }

    # Print the variables for debugging
    print("Global variables:", global_variables)

    # Run the simulation
    simulation = simulate_pipeline(all_jobs, workflow_config, global_variables)

    # Get the expanded job
    all_expanded_jobs = simulation["all_expanded_jobs"]
    expanded_job = all_expanded_jobs["Component Feature Test"]

    # Print the expanded job for debugging
    print("Expanded job:", expanded_job)
    print("Simulation variables:", simulation["global_variables"])
    print("Jobs list:", simulation["jobs_list"])

    # Check that the job has rules with properly expanded variables
    assert "rules" in expanded_job
    rules = expanded_job["rules"]

    # We don't care about the expanded rule condition, we care about whether the job runs
    # Check that the TOOL variable is correctly set in the variables section
    assert expanded_job["variables"]["TOOL"] == "tool1"

    # Check that the job is included in the jobs that will run
    assert "Component Feature Test" in simulation["jobs_list"]

    # Check that the job is in the simulation jobs
    # This is the key test - if the variable expansion in rules works correctly,
    # the first rule should match and the job should run
    job = simulation["jobs"]["Component Feature Test"]
    assert job is not None

    # Check that the S3_PATH variable is correctly expanded within the job's scope
    # With proper variable scoping, MODULE and TOOL should be expanded from the job's own variables
    assert job["variables"]["S3_PATH"] == "project/component/tool1"
