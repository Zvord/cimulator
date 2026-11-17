import logging
from typing import Any, List, Tuple, Optional
from cimulator.expression import ExpressionError, UnsupportedExpression, check_expression, evaluate_expression
from cimulator.types import ConfigDict, VariablesDict
from cimulator.variable_expander import expand_variables, variable_values

logger = logging.getLogger(__name__)

def evaluate_condition(condition: str, variables: VariablesDict, strict: bool = False) -> bool:
    """
    Evaluate a condition (a `rules:if` expression) against a set of variables,
    as GitLab does (see cimulator.expression).

    Returns True if the condition is satisfied, False otherwise. Raises
    ExpressionError if GitLab rejects the condition. A valid condition that
    cannot be evaluated here is logged and taken as not satisfied, or with
    `strict` raises UnsupportedExpression.
    """
    try:
        return evaluate_expression(condition, variables)
    except ExpressionError as e:
        raise ExpressionError(f"invalid expression '{condition}': {e}") from e
    except UnsupportedExpression as e:
        if strict:
            raise
        logger.warning(f"Cannot evaluate condition '{condition}', taken as not matching: {e}")
        return False

# GitLab flattens nested lists of rules (e.g. YAML anchors), up to 10 levels
MAX_RULES_DEPTH = 10

def rules_list(rules: Any) -> List[ConfigDict]:
    """
    The rules as GitLab reads them: null is no rules, nested lists (as from
    YAML anchors) are flattened up to 10 levels in all, and each rule must
    be a mapping. Raises ValueError otherwise, as GitLab rejects the
    configuration ("rules should be an array containing hashes and arrays
    of hashes"), and for an empty list ("rules config can't be blank").
    An empty nested list is valid, with no rules.
    """
    if rules is None:
        return []
    if not isinstance(rules, list):
        raise ValueError(f"must be a list of rules, not {rules!r}")
    if not rules:
        raise ValueError("must not be an empty list")
    flat: List[ConfigDict] = []

    def add(items: list, depth: int) -> None:
        for item in items:
            if isinstance(item, list):
                if depth >= MAX_RULES_DEPTH:
                    raise ValueError(f"rules can be nested in lists up to {MAX_RULES_DEPTH} levels")
                add(item, depth + 1)
            elif isinstance(item, dict):
                flat.append(item)
            else:
                raise ValueError(f"a rule must be a mapping, not {item!r}")

    add(rules, 1)
    return flat

def check_condition(condition: str) -> None:
    """
    Check the syntax of a condition without evaluating it, as GitLab does for
    every rule. Raises ExpressionError if GitLab rejects the condition.
    """
    try:
        check_expression(condition)
    except ExpressionError as e:
        raise ExpressionError(f"invalid expression '{condition}': {e}") from e

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
    for rule in rules_list(rules):
        condition = rule.get("if")
        if condition is None or evaluate_condition(condition, variables):
            # Determine the 'when' behavior.
            when = rule.get("when", "always")
            should_run = (when != "never") # TODO what is this parenthesis syntax?
            # Get the variables from the rule and expand them
            rule_variables = rule.get("variables", {})
            applied_variables = expand_variables(variable_values(rule_variables), variables)
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
    # Without workflow rules (no workflow, or rules: null), the pipeline runs
    if not isinstance(workflow_config, dict) or workflow_config.get("rules") is None:
        return (True, None, {}, None)
    return evaluate_rules(workflow_config["rules"], variables)
