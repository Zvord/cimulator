import re
from typing import List, Tuple, Optional, Union
from cimulator.types import ConfigDict, VariablesDict
from cimulator.variable_expander import expand_variables, expand_variables_in_string

def regex_match(value: str, pattern: str) -> bool:
    """
    Check if the value matches the regex pattern.
    """
    try:
        return re.search(pattern, str(value)) is not None
    except Exception:
        return False

def regex_not_match(value: str, pattern: str) -> bool:
    """
    Check if the value does NOT match the regex pattern.
    """
    try:
        return re.search(pattern, str(value)) is None
    except Exception:
        return True

def preprocess_condition(condition: str) -> str:
    """
    Transform a condition string into a Python evaluable expression.

    This performs several transformations:
      - Replace logical operators '&&' and '||' with 'and' and 'or'.
      - Convert regex match operators '=~' into function calls to regex_match.
      - Replace variable references (e.g. $VAR) with plain variable names (VAR).

    Example:
      Input:  '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TITLE =~ /^(\\[Draft\\]|\\(Draft\\)|Draft:)/'
      Output: 'CI_PIPELINE_SOURCE == "merge_request_event" and regex_match(CI_MERGE_REQUEST_TITLE, r"^(\\[Draft\\]|\\(Draft\\)|Draft:)")'
    """
    # Replace && and || with Python operators.
    condition = condition.replace("&&", " and ").replace("||", " or ")

    # Process regex operators: =~ (match) and !~ (not match)
    def regex_sub(match):
        left = match.group(1)  # e.g., $CI_MERGE_REQUEST_TITLE
        operator = match.group(2)  # =~ or !~
        pattern = match.group(3)  # e.g., /^(...)/ or "/^(...)/"

        # Check if the pattern is quoted
        if pattern.startswith('"') and pattern.endswith('"'):
            # Remove the quotes and then the leading/trailing slashes
            pattern_inner = pattern[1:-1].strip('/')
        else:
            # Just remove leading/trailing slashes
            pattern_inner = pattern.strip('/')

        # Remove the '$' from the variable name
        left_var = left[1:]

        # Use the appropriate function based on the operator
        if operator == "=~":
            return f"regex_match({left_var}, r'{pattern_inner}')"
        else:  # operator == "!~"
            return f"regex_not_match({left_var}, r'{pattern_inner}')"

    # First, try to match patterns with quotes: $VAR =~ "/pattern/" or $VAR !~ "/pattern/"
    condition = re.sub(r'(\$\w+)\s*(=~|!~)\s*"(\/.+?\/)"', regex_sub, condition)

    # Then, try to match patterns without quotes: $VAR =~ /pattern/ or $VAR !~ /pattern/
    condition = re.sub(r'(\$\w+)\s*(=~|!~)\s*(\/.+?\/)', regex_sub, condition)

    # Replace any remaining variables of the form $VAR with VAR.
    condition = re.sub(r'\$(\w+)', r'\1', condition)
    return condition

def evaluate_condition(condition: str, variables: VariablesDict) -> bool:
    """
    Evaluate a condition string against a set of variables.

    Returns True if the condition is satisfied, False otherwise.
    """
    # Special case for regex conditions
    if "=~" in condition or "!~" in condition:
        # Process the condition directly using the original preprocess_condition function
        processed = preprocess_condition(condition)
        # Create an evaluation environment: supply all variable values
        eval_env = {key: value for key, value in variables.items()}
        # Add the regex helpers
        eval_env["regex_match"] = regex_match
        eval_env["regex_not_match"] = regex_not_match
        try:
            return bool(eval(processed, {"__builtins__": {}}, eval_env))
        except Exception as e:
            print(f"Error evaluating regex condition '{condition}': {e}")
            return False

    # For conditions with variable references like "$COVERAGE_TOOL == $TOOL"
    # Use a regex-based approach to expand variables to avoid issues with variable names
    # that are prefixes of other variable names

    def replace_var(match):
        var_name = match.group(1)
        var_value = variables.get(var_name, "")  # Default to empty string for non-existing variables
        if isinstance(var_value, str):
            # For string values, we need to add quotes
            return f'"{var_value}"'
        else:
            # For non-string values, we can just use the value directly
            return str(var_value)

    # Use regex to find and replace all variable references
    expanded_condition = re.sub(r'\$(\w+)', replace_var, condition)

    # Now process the expanded condition
    processed = preprocess_condition(expanded_condition)

    # Create an evaluation environment: supply all variable values
    eval_env = {key: value for key, value in variables.items()}
    # Add the regex helpers
    eval_env["regex_match"] = regex_match
    eval_env["regex_not_match"] = regex_not_match

    try:
        return bool(eval(processed, {"__builtins__": {}}, eval_env))
    except Exception as e:
        print(f"Error evaluating condition '{condition}' (expanded to '{expanded_condition}'): {e}")
        return False

def evaluate_rules(rules: List[ConfigDict], variables: VariablesDict) -> Tuple[bool, Optional[ConfigDict], VariablesDict, Optional[str]]:
    """
    Evaluate a list of rules.

    For each rule:
      - If the rule has no 'if' clause, it always matches.
      - Otherwise, the condition is evaluated with the given variables.

    The first rule that matches is used to determine:
      - Whether to run (if its 'when' value is not "never"),
      - And which variables to apply (from its "variables" section).

    Returns a tuple:
       (should_run, triggered_rule, applied_variables, triggered_condition)

    If no rule matches, returns (False, None, {}, None).
    """
    for rule in rules:
        condition = rule.get("if")
        if condition is None or evaluate_condition(condition, variables):
            # Determine the 'when' behavior.
            when = rule.get("when", "always")
            should_run = (when != "never") # TODO what is this parenthesis syntax?
            # Get the variables from the rule and expand them
            rule_variables = rule.get("variables", {})
            applied_variables = expand_variables(rule_variables, variables)
            return (should_run, rule, applied_variables, condition)
    return (False, None, {}, None)

def evaluate_workflow(workflow_config: ConfigDict, variables: VariablesDict) -> Tuple[bool, Optional[ConfigDict], VariablesDict, Optional[str]]:
    """
    Evaluate a workflow configuration.

    This function extracts the rules from the workflow configuration and uses
    evaluate_rules() to determine if the pipeline should run.

    Returns a tuple:
       (should_run, triggered_rule, applied_variables, triggered_condition)
    """
    rules = workflow_config.get("rules", [])
    return evaluate_rules(rules, variables)
