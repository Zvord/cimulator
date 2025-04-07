import pytest
from cimulator.workflow import evaluate_condition, preprocess_condition

def test_regex_negation_operator():
    """Test that the !~ operator (regex negation) works correctly."""
    variables = {
        "CI_PIPELINE_SOURCE": "schedule",
        "CI_MERGE_REQUEST_TITLE": ""
    }

    # This is the condition that's causing the error
    condition = '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TITLE !~ /^(\\[Draft\\]|\\(Draft\\)|Draft:)/'

    # Test the evaluate_condition function directly
    print(f"Original condition: {condition}")

    # Now test the evaluate_condition function
    result = evaluate_condition(condition, variables)
    print(f"Evaluation result: {result}")

    # The condition should evaluate to False because CI_PIPELINE_SOURCE doesn't match
    assert result is False

    # Test with a matching pipeline source but non-matching title
    variables["CI_PIPELINE_SOURCE"] = "merge_request_event"
    variables["CI_MERGE_REQUEST_TITLE"] = "Regular PR Title"
    result = evaluate_condition(condition, variables)
    assert result is True

    # Test with a matching pipeline source and a draft title
    variables["CI_MERGE_REQUEST_TITLE"] = "[Draft] Work in progress"
    result = evaluate_condition(condition, variables)
    assert result is False
