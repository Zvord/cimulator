"""rules:if in simulate and validate, as GitLab checks and evaluates them."""
import textwrap

import pytest
import yaml

from cimulator.cli import main


def run(monkeypatch, tmp_path, command, config, profile="A: abc\n"):
    ci_file = tmp_path / ".gitlab-ci.yml"
    ci_file.write_text(textwrap.dedent(config))
    profiles = tmp_path / "profiles.yml"
    profiles.write_text("p:\n" + textwrap.indent(profile, "  "))
    output = tmp_path / "output.yml"
    arguments = [str(ci_file), str(profiles), "p"] if command == "simulate" else [str(ci_file)]
    monkeypatch.setattr("sys.argv", ["cli.py", command, *arguments, "--output", str(output)])
    main()
    return yaml.safe_load(output.read_text())


INVALID = {
    "after a rule that matches": """
        job:
          script: [x]
          rules:
            - when: always
            - if: '$A =~ /a(/'
    """,
    "in a job that never runs": """
        job:
          script: [x]
          rules:
            - when: never
            - if: '$A =='
    """,
    "from a hidden job, through extends": """
        .template:
          rules:
            - if: '$A =='
        job:
          extends: .template
          script: [x]
    """,
    "inside a nested list of rules": """
        .common: &common
          - if: '$A =='
        job:
          script: [x]
          rules:
            - when: always
            - *common
    """,
    "in a parallel:matrix job": """
        job:
          script: [x]
          parallel:
            matrix:
              - OS: [linux, mac]
          rules:
            - if: '$OS == "linux"'
            - if: '$A =='
    """,
    "in the workflow, after a rule that matches": """
        workflow:
          rules:
            - when: always
            - if: '$A =='
        job:
          script: [x]
    """,
}


@pytest.mark.parametrize("command", ["simulate", "validate"])
@pytest.mark.parametrize("config", INVALID.values(), ids=INVALID.keys())
def test_every_if_is_checked(monkeypatch, tmp_path, capsys, command, config):
    # GitLab: rules:rule if invalid expression syntax, for any rule of any
    # job that is not hidden, and of the workflow
    with pytest.raises(SystemExit):
        run(monkeypatch, tmp_path, command, config)
    assert "rules: invalid expression" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["simulate", "validate"])
def test_hidden_jobs_are_not_checked(monkeypatch, tmp_path, command):
    # GitLab accepts an invalid if in a hidden job that no job extends
    run(monkeypatch, tmp_path, command, """
        .hidden:
          script: [x]
          rules:
            - if: '$A =='
        job:
          script: [x]
    """)


def test_variables_written_as_mappings_have_their_value(monkeypatch, tmp_path):
    simulation = run(monkeypatch, tmp_path, "simulate", """
        variables:
          DEPLOY:
            value: prod
            description: where to deploy
          NOTE:
            description: no value
        job:
          variables:
            MODE:
              value: full
              description: test mode
          script: [echo $DEPLOY $MODE]
          rules:
            - if: $DEPLOY == "prod" && $MODE == "full" && $NOTE == ""
    """)
    assert simulation["jobs_list"] == ["job"]
    assert simulation["jobs"]["job"]["script"] == ["echo prod full"]


INVALID_RULES = {
    # GitLab: rules should be an array containing hashes and arrays of hashes
    "rules that are a mapping": "rules:\n    if: $A\n",
    "a rule that is not a mapping": "rules: [foo]\n",
    # GitLab: rules config can't be blank
    "empty rules": "rules: []\n",
    "rules nested in 11 levels": "rules:\n    - " + "[" * 10 + "{if: $A}" + "]" * 10 + "\n",
}


@pytest.mark.parametrize("command", ["simulate", "validate"])
@pytest.mark.parametrize("rules", INVALID_RULES.values(), ids=INVALID_RULES.keys())
def test_invalid_rules_are_errors(monkeypatch, tmp_path, capsys, command, rules):
    with pytest.raises(SystemExit):
        run(monkeypatch, tmp_path, command, "job:\n  script: [x]\n  " + rules)
    assert "Job 'job': rules: " in capsys.readouterr().err


def test_nested_lists_of_rules_are_flattened(monkeypatch, tmp_path):
    # As GitLab does, up to 10 levels in all, e.g. for rules shared through
    # YAML anchors
    simulation = run(monkeypatch, tmp_path, "simulate", """
        .common: &common
          - if: $A == "x"
            when: never
          - if: $A == "abc"
        workflow:
          rules:
            - [[{if: $A == "x", when: never}]]
            - when: always
        anchored:
          script: [x]
          rules:
            - *common
            - when: never
        deep:
          script: [x]
          rules:
            - [[[[[[[[[{if: $A == "abc"}]]]]]]]]]
            - when: never
        null_rules:
          script: [x]
          rules: null
        no_rule_left:
          script: [x]
          rules: [[]]
    """)
    # rules: [[]] is valid, with no rule that matches
    assert sorted(simulation["jobs_list"]) == ["anchored", "deep", "null_rules"]


def test_rules_of_hidden_jobs_are_not_evaluated(monkeypatch, tmp_path, caplog):
    run(monkeypatch, tmp_path, "simulate", """
        .hidden:
          rules:
            - if: $A =~ /\\p{L}/
        job:
          script: [x]
    """)
    assert "Cannot evaluate" not in caplog.text


@pytest.mark.parametrize("workflow", ["", "workflow:\n", "workflow: {}\n", "workflow:\n  rules: null\n",
                                      "workflow:\n  name: pipeline\n"])
def test_pipeline_runs_without_workflow_rules(monkeypatch, tmp_path, workflow):
    simulation = run(monkeypatch, tmp_path, "simulate", workflow + "job:\n  script: [x]\n")
    assert simulation["workflow_run"] is True
    assert simulation["jobs_list"] == ["job"]


@pytest.mark.parametrize("command", ["simulate", "validate"])
def test_empty_workflow_rules_are_an_error(monkeypatch, tmp_path, capsys, command):
    # GitLab: workflow:rules config can't be blank
    with pytest.raises(SystemExit):
        run(monkeypatch, tmp_path, command, "workflow:\n  rules: []\njob:\n  script: [x]\n")
    assert "workflow: rules: must not be an empty list" in capsys.readouterr().err


def test_variables_without_a_value_are_empty(monkeypatch, tmp_path):
    simulation = run(monkeypatch, tmp_path, "simulate", """
        variables:
          GLOBAL:
        job:
          variables:
            LOCAL: null
          script: [echo "$GLOBAL$LOCAL"]
          rules:
            - if: $GLOBAL == "" && $LOCAL == ""
    """)
    assert simulation["jobs_list"] == ["job"]
    assert simulation["jobs"]["job"]["script"] == ['echo ""']


def test_rules_of_matrix_jobs_use_their_matrix_variables(monkeypatch, tmp_path):
    output = run(monkeypatch, tmp_path, "simulate", """
        job:
          script: [x]
          parallel:
            matrix:
              - OS: [linux, mac]
          rules:
            - if: '$OS == "linux"'
    """)
    assert output["jobs_list"] == ["job: [linux]"]


def test_simulate_reports_every_invalid_rule(monkeypatch, tmp_path, capsys):
    # As validate: an error in the form of the rules, and one in an if
    with pytest.raises(SystemExit):
        run(monkeypatch, tmp_path, "simulate", """
            a:
              script: [x]
              rules: {if: $A}
            b:
              script: [x]
              rules: [{if: '$A =='}]
        """)
    err = capsys.readouterr().err
    assert "Job 'a': rules: must be a list of rules" in err
    assert "Job 'b': rules: invalid expression '$A =='" in err


def test_variables_are_text_in_scripts_as_in_rules(monkeypatch, tmp_path):
    # GitLab's value of `D: true` is the text "true", also in rule variables
    output = run(monkeypatch, tmp_path, "simulate", """
        variables:
          D: true
          N: 1
        job:
          script: [echo $D $N $R]
          rules:
            - if: '$D == "true"'
              variables:
                R: false
    """)
    assert output["jobs"]["job"]["script"] == ["echo true 1 false"]


@pytest.mark.parametrize("command", ["simulate", "validate"])
def test_every_invalid_if_of_a_job_is_reported(monkeypatch, tmp_path, capsys, command):
    with pytest.raises(SystemExit):
        run(monkeypatch, tmp_path, command, """
            job:
              script: [x]
              rules:
                - if: '$A =='
                - if: '$B =='
        """)
    err = capsys.readouterr().err
    assert "invalid expression '$A =='" in err
    assert "invalid expression '$B =='" in err


@pytest.mark.parametrize("config", [
    "variables:\njob:\n  script: [x]\n",
    "job:\n  script: [x]\n  variables:\n",
    "job:\n  script: [x]\n  rules:\n    - variables:\n",
    "workflow:\njob:\n  script: [x]\n",
    "default:\njob:\n  script: [x]\n",
], ids=["global variables", "job variables", "rule variables", "workflow", "default"])
def test_empty_sections_are_empty(monkeypatch, tmp_path, config):
    # GitLab accepts them, as having nothing
    output = run(monkeypatch, tmp_path, "simulate", config)
    assert output["jobs_list"] == ["job"]


def test_rules_are_shown_as_written(monkeypatch, tmp_path):
    # As needs: the expressions use the variables, but keep them as written
    output = run(monkeypatch, tmp_path, "simulate", """
        job:
          script: [echo $A]
          rules:
            - if: '$A == "abc"'
    """)
    assert output["jobs"]["job"]["rules"] == [{"if": '$A == "abc"'}]
    assert output["jobs"]["job"]["script"] == ["echo abc"]


def test_all_expanded_jobs_show_rules_and_needs_as_written(monkeypatch, tmp_path):
    output = run(monkeypatch, tmp_path, "simulate", """
        build:
          script: [x]
        job:
          script: [echo $A]
          needs: [build]
          rules:
            - if: '$A == "x" || $A'
    """)
    expanded = output["all_expanded_jobs"]["job"]
    assert expanded["rules"] == [{"if": '$A == "x" || $A'}]
    assert expanded["needs"] == ["build"]
    assert expanded["script"] == ["echo abc"]


def test_jobs_shown_as_written_share_nothing(monkeypatch, tmp_path):
    # jobs and all_expanded_jobs get their own copies of the needs and rules
    # as written: shared objects would be written as YAML aliases
    run(monkeypatch, tmp_path, "simulate", """
        build:
          script: [x]
        job:
          script: [x]
          needs: [build]
          rules:
            - if: '$A == "abc"'
    """)
    text = (tmp_path / "output.yml").read_text()
    assert "&id" not in text and "*id" not in text


def test_simulate_output_has_no_aliases(monkeypatch, tmp_path):
    # Rules as written keep what the configuration shares through anchors,
    # but the output writes every value in full
    output = run(monkeypatch, tmp_path, "simulate", """
        job:
          script: [x]
          rules:
            - if: '$A == "x"'
              changes: &files [a.txt]
            - if: '$A == "abc"'
              changes: *files
    """)
    text = (tmp_path / "output.yml").read_text()
    assert "&id" not in text and "*id" not in text
    assert output["jobs"]["job"]["rules"][1] == {"if": '$A == "abc"', "changes": ["a.txt"]}
