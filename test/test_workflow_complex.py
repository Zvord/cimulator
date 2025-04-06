from cimulator.workflow import evaluate_condition, evaluate_rules, evaluate_workflow

def test_evaluate_condition_simple_true():
    variables = {"CI_COMMIT_BRANCH": "main"}
    condition = '$CI_COMMIT_BRANCH == "main"'
    assert evaluate_condition(condition, variables) is True

def test_evaluate_condition_simple_false():
    variables = {"CI_COMMIT_BRANCH": "dev"}
    condition = '$CI_COMMIT_BRANCH == "main"'
    assert evaluate_condition(condition, variables) is False

def test_evaluate_condition_complex_regex_true():
    variables = {
        "CI_PIPELINE_SOURCE": "merge_request_event",
        "CI_MERGE_REQUEST_TITLE": "[Draft] Work in progress"
    }
    condition = '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TITLE =~ /^(\[Draft\]|\(Draft\)|Draft:)/'
    assert evaluate_condition(condition, variables) is True

def test_evaluate_condition_complex_regex_false():
    variables = {
        "CI_PIPELINE_SOURCE": "merge_request_event",
        "CI_MERGE_REQUEST_TITLE": "Final title"
    }
    condition = '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TITLE =~ /^(\[Draft\]|\(Draft\)|Draft:)/'
    assert evaluate_condition(condition, variables) is False

def test_evaluate_rules_with_matching_rule():
    # Create a list of rules similar to your workflows.
    rules = [
        {
            "if": '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TITLE =~ /^(\[Draft\]|\(Draft\)|Draft:)/',
            "when": "never"
        },
        {
            "if": '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == "master"',
            "when": "always",
            "variables": {"PRODUCT_NAME": "bobolido"}
        }
    ]
    variables = {
        "CI_PIPELINE_SOURCE": "push",
        "CI_COMMIT_BRANCH": "master",
        "CI_MERGE_REQUEST_TITLE": "Anything"
    }
    should_run, triggered_rule, applied_variables, triggered_condition = evaluate_rules(rules, variables)
    assert should_run is True
    assert triggered_condition == '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == "master"'
    assert applied_variables == {"PRODUCT_NAME": "bobolido"}

def test_evaluate_workflow_returns_debug_info():
    workflow_config = {
        "rules": [
            {
                "if": '$CI_PIPELINE_SOURCE == "schedule" && $RUN_NIGHTLY == "1"',
                "variables": {"PIPELINE_NAME": "Nightly run dev", "PRODUCT_NAME": "bobolido dev"},
            },
            {
                "if": '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == "master"',
                "when": "always",
                "variables": {"COLLECT_METRICS": "1", "PRODUCT_NAME": "bobolido"}
            }
        ]
    }
    variables = {
        "CI_PIPELINE_SOURCE": "schedule",
        "RUN_NIGHTLY": "1",
        "CI_COMMIT_BRANCH": "any"
    }
    should_run, triggered_rule, applied_variables, triggered_condition = evaluate_workflow(workflow_config, variables)
    # For this configuration, the first rule should match.
    assert should_run is True
    assert triggered_condition == '$CI_PIPELINE_SOURCE == "schedule" && $RUN_NIGHTLY == "1"'
    assert applied_variables == {"PIPELINE_NAME": "Nightly run dev", "PRODUCT_NAME": "bobolido dev"}
