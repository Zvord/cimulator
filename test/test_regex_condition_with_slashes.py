import pytest
from cimulator.workflow import evaluate_condition, preprocess_condition

def test_regex_condition_with_slashes():
    """Test that regex conditions with slashes are processed correctly."""
    variables = {
        "CI_PIPELINE_SOURCE": "push",
        "CI_COMMIT_BRANCH": "protected/branch"
    }

    # This is the condition that's causing the error
    condition = '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH =~ "/^protected\/*/"'

    # First, test the preprocess_condition function directly
    processed = preprocess_condition(condition)
    print(f"Processed condition: {processed}")

    # The processed condition should be valid Python syntax
    # This will raise an exception if the syntax is invalid
    compile(processed, '<string>', 'eval')

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
    condition = '$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH =~ "/^protected\/feature\/.*/"'

    # First, test the preprocess_condition function directly
    processed = preprocess_condition(condition)
    print(f"Processed condition: {processed}")

    # The processed condition should be valid Python syntax
    compile(processed, '<string>', 'eval')

    # Now test the evaluate_condition function
    result = evaluate_condition(condition, variables)
    assert result is True

    # Test with a non-matching branch
    variables["CI_COMMIT_BRANCH"] = "protected/other/branch"
    result = evaluate_condition(condition, variables)
    assert result is False
