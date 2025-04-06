import re

def regex_match(value, pattern):
    """
    Check if the value matches the regex pattern.
    """
    try:
        return re.search(pattern, str(value)) is not None
    except Exception:
        return False

def preprocess_condition(condition):
    """
    Transform a condition string into a Python evaluable expression.

    This performs several transformations:
      - Replace logical operators '&&' and '||' with 'and' and 'or'.
      - Convert regex match operators '=~' into function calls to regex_match.
      - Replace variable references (e.g. $VAR) with plain variable names (VAR).

    Example:
      Input:  '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TITLE =~ /^(\[Draft\]|\(Draft\)|Draft:)/'
      Output: 'CI_PIPELINE_SOURCE == "merge_request_event" and regex_match(CI_MERGE_REQUEST_TITLE, r"^(\[Draft\]|\(Draft\)|Draft:)")'
    """
    # Replace && and || with Python operators.
    condition = condition.replace("&&", " and ").replace("||", " or ")

    # Process regex operator: replace patterns like $VAR =~ /regex/
    def regex_sub(match):
        left = match.group(1)  # e.g., $CI_MERGE_REQUEST_TITLE
        pattern = match.group(2)  # e.g., /^(...)/
        # Remove leading/trailing slashes from the regex literal.
        pattern_inner = pattern.strip('/')
        # Remove the '$' from the variable name.
        left_var = left[1:]
        return f"regex_match({left_var}, r'{pattern_inner}')"

    # This regex finds patterns of the form: $VAR =~ /pattern/
    condition = re.sub(r'(\$\w+)\s*=~\s*(\/[^\/]+\/)', regex_sub, condition)

    # Replace any remaining variables of the form $VAR with VAR.
    condition = re.sub(r'\$(\w+)', r'\1', condition)
    return condition

def evaluate_condition(condition, variables):
    """
    Evaluate a condition string against a set of variables.

    Returns True if the condition is satisfied, False otherwise.
    """
    processed = preprocess_condition(condition)
    # Create an evaluation environment: supply all variable values.
    eval_env = {key: value for key, value in variables.items()} # TODO isn't it the same as variables.copy()?
    # Add the regex_match helper.
    eval_env["regex_match"] = regex_match
    try:
        return bool(eval(processed, {"__builtins__": {}}, eval_env))
    except Exception:
        return False

def evaluate_rules(rules, variables):
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
            applied_variables = rule.get("variables", {})
            return (should_run, rule, applied_variables, condition)
    return (False, None, {}, None)

def evaluate_workflow(workflow_config, variables):
    """
    Evaluate a workflow configuration.

    This function extracts the rules from the workflow configuration and uses
    evaluate_rules() to determine if the pipeline should run.

    Returns a tuple:
       (should_run, triggered_rule, applied_variables, triggered_condition)
    """
    rules = workflow_config.get("rules", [])
    return evaluate_rules(rules, variables)
