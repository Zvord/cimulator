import pytest
from cimulator.workflow import evaluate_condition

def test_regex_condition_with_slashes():
    """Test that regex conditions with slashes are processed correctly."""
    variables = {
        "CI_PIPELINE_SOURCE": "push",
        "CI_COMMIT_BRANCH": "protected/branch"
    }

    # This is the condition that's causing the error
    condition = r'$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH =~ "/^protected\/*/"'


    # Now test the evaluate_condition function
    result = evaluate_condition(condition, variables)
    assert result is True

    # Test with a non-matching branch
    variables["CI_COMMIT_BRANCH"] = "main"
    result = evaluate_condition(condition, variables)
    assert result is False

def test_regex_condition_with_complex_slashes():
    """Test regex conditions with more complex slash patterns."""
    variables = {
        "CI_PIPELINE_SOURCE": "push",
        "CI_COMMIT_BRANCH": "protected/feature/branch"
    }

    # Test with a more complex regex pattern
    condition = r'$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH =~ "/^protected\/feature\/.*/"'


    # Now test the evaluate_condition function
    result = evaluate_condition(condition, variables)
    assert result is True

    # Test with a non-matching branch
    variables["CI_COMMIT_BRANCH"] = "protected/other/branch"
    result = evaluate_condition(condition, variables)
    assert result is False
