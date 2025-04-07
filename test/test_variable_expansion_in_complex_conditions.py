import pytest
from cimulator.workflow import evaluate_condition, preprocess_condition
from cimulator.variable_expander import expand_variables_in_string

def test_variable_expansion_in_complex_conditions():
    """Test that variables are correctly expanded in complex conditions."""
    # Define variables
    variables = {
        "RUN_ALL_BUILDS": "1",
        "RUN_BUILD_COMPONENT_2048": "",
        "RUN_REGRESSIONS": "1",
        "RUN_REGRESSIONS_SPECIAL": "1"
    }

    # This is the condition that's causing the error
    condition = '($RUN_ALL_BUILDS == "1" || $RUN_BUILD_COMPONENT_2048 == "1") && ($RUN_REGRESSIONS != "1" && $RUN_REGRESSIONS_SPECIAL != "1")'

    # Let the evaluate_condition function handle the variable expansion
    # We'll just call it directly to test it
    result = evaluate_condition(condition, variables)
    print(f"Evaluation result: {result}")

    # The condition should evaluate to False
    assert result is False


def test_variable_expansion_with_underscore_suffix():
    """Test that variables with underscore suffixes are correctly expanded."""
    # Define variables
    variables = {
        "RUN_ALL_PROJECT_BUILDS": "1",
        "RUN_BUILD_COMPONENT_VARIANT": "",
        "RUN_REGRESSIONS": "1",
        "RUN_REGRESSIONS_SPECIAL_TYPE": "1"
    }

    # This is the condition from the error message
    condition = '($RUN_ALL_PROJECT_BUILDS == "1" || $RUN_BUILD_COMPONENT_VARIANT == "1") && ($RUN_REGRESSIONS != "1" && $RUN_REGRESSIONS_SPECIAL_TYPE != "1")'

    # Let the evaluate_condition function handle the variable expansion
    # We'll just call it directly to test it
    result = evaluate_condition(condition, variables)
    print(f"Evaluation result: {result}")

    # The condition should evaluate to False
    assert result is False
