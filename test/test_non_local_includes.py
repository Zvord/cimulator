"""
Jobs that may come from non-local includes (remote, project, template,
component), which cimulator does not load: extending or needing a job that
is not defined is then only a warning.
"""
import pytest
from pathlib import Path

from cimulator.cli import main
from cimulator.loader import load_and_resolve
from cimulator.simulation_engine import simulate_pipeline
from cimulator.validator import validate_job_dependencies


def write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return str(path)


def external_includes_of(root, variables=None):
    external = []
    load_and_resolve(root, variables=variables, external_includes=external)
    return external


# Loader: which non-local includes GitLab would load

def test_every_kind_of_non_local_include_is_recorded(tmp_path):
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n"
        "  - https://example.com/ci.yml\n"
        "  - remote: https://example.com/other.yml\n"
        "  - project: group/repo\n"
        "    file: ci/jobs.yml\n"
        "  - template: Workflows/MergeRequest-Pipelines.gitlab-ci.yml\n"
        "  - component: example.com/group/component/build@1.0\n"
        "job:\n  script: [echo]\n"))
    assert len(external_includes_of(root)) == 5


def test_local_includes_are_not_recorded(tmp_path):
    write(tmp_path / "ci" / "jobs.yml", "job:\n  script: [echo]\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include:\n  - ci/jobs.yml\n  - local: ci/jobs.yml\n")
    assert external_includes_of(root) == []


def test_non_local_include_of_a_local_include_is_recorded(tmp_path):
    write(tmp_path / "ci" / "jobs.yml", "include:\n  - project: group/repo\n    file: ci/jobs.yml\n")
    root = write(tmp_path / ".gitlab-ci.yml", "include: ci/jobs.yml\njob:\n  script: [echo]\n")
    assert external_includes_of(root) == [{"project": "group/repo", "file": "ci/jobs.yml"}]


NON_LOCAL_WITH_RULES = (
    "include:\n"
    "  - component: example.com/group/component/build@1.0\n"
    "    rules:\n"
    "      - if: $RELEASE == \"1\"\n"
    "job:\n  script: [echo]\n")


def test_non_local_include_whose_rules_do_not_match_is_not_recorded(tmp_path):
    root = write(tmp_path / ".gitlab-ci.yml", NON_LOCAL_WITH_RULES)
    assert external_includes_of(root, {"RELEASE": "0"}) == []
    assert len(external_includes_of(root, {"RELEASE": "1"})) == 1


def test_non_local_include_with_rules_on_unknown_variables_is_recorded(tmp_path):
    # As in validate: GitLab may load it
    root = write(tmp_path / ".gitlab-ci.yml", NON_LOCAL_WITH_RULES)
    assert len(external_includes_of(root)) == 1


def test_non_local_include_with_when_never_is_not_recorded(tmp_path):
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n  - remote: https://example.com/ci.yml\n    rules:\n      - when: never\n"
        "job:\n  script: [echo]\n"))
    assert external_includes_of(root) == []


def test_invalid_rules_of_a_non_local_include_fail(tmp_path):
    # GitLab checks them, even without loading the include
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n  - remote: https://example.com/ci.yml\n    rules:\n      - if: $A\n        foo: 1\n"
        "job:\n  script: [echo]\n"))
    with pytest.raises(ValueError, match="unknown keys in a rule: foo"):
        load_and_resolve(root)


# validate

def validate(jobs, external_includes):
    warnings = []
    errors = validate_job_dependencies(jobs, external_includes, warnings)
    return errors, warnings


def test_need_of_an_undefined_job_is_a_warning_with_non_local_includes():
    jobs = {"b": {"script": ["x"], "needs": ["prepare"]}}
    errors, warnings = validate(jobs, True)
    assert errors == []
    assert len(warnings) == 1 and "'prepare'" in warnings[0] and "non-local include" in warnings[0]


def test_need_of_an_undefined_job_is_an_error_without_non_local_includes():
    jobs = {"b": {"script": ["x"], "needs": ["prepare"]}}
    errors, warnings = validate(jobs, False)
    assert errors == ["Job 'b' needs non-existing job 'prepare'"]
    assert warnings == []


@pytest.mark.parametrize("external_includes", [False, True])
@pytest.mark.parametrize("needed", ["prepare", ".template"])
def test_optional_need_of_an_undefined_job_is_accepted(external_includes, needed):
    # As in GitLab, also for a hidden job
    jobs = {".template": {"script": ["x"]},
            "b": {"script": ["x"], "needs": [{"job": needed, "optional": True}]}}
    assert validate(jobs, external_includes) == ([], [])


def test_need_of_a_hidden_job_is_an_error_with_non_local_includes():
    # A hidden job never runs, wherever it is defined
    jobs = {".template": {"script": ["x"]}, "b": {"script": ["x"], "needs": [".template"]}}
    errors, _ = validate(jobs, True)
    assert errors == ["Job 'b' needs non-existing job '.template'"]


def test_need_of_a_missing_combination_of_a_matrix_job_is_an_error_with_non_local_includes():
    # The matrix job of the configuration defines its jobs: an include
    # cannot add to them
    jobs = {"build": {"script": ["x"], "parallel": {"matrix": [{"OS": ["linux"]}]}},
            "b": {"script": ["x"], "needs": [{"job": "build", "parallel": {"matrix": [{"OS": "mac"}]}}]}}
    errors, warnings = validate(jobs, True)
    assert errors == ["Job 'b' needs non-existing job 'build: [mac]'"]
    assert warnings == []


def test_matrix_need_of_an_undefined_job_is_a_warning_with_non_local_includes():
    jobs = {"b": {"script": ["x"], "needs": [{"job": "build", "parallel": {"matrix": [{"OS": "mac"}]}}]}}
    errors, warnings = validate(jobs, True)
    assert errors == []
    assert len(warnings) == 1 and "'build: [mac]'" in warnings[0]


def test_extends_of_an_undefined_job_is_a_warning_with_non_local_includes():
    jobs = {"b": {"extends": ".remote_template", "script": ["x"]}}
    errors, warnings = validate(jobs, True)
    assert errors == []
    assert warnings == ["'.remote_template', extended by 'b', is not defined: "
                        "it may come from a non-local include, which cimulator does not load"]


@pytest.mark.parametrize("extends", [[{"x": 1}], [["a"]], {"x": 1}])
@pytest.mark.parametrize("external_includes", [True, False])
def test_extends_that_is_not_a_job_name_is_an_error(extends, external_includes):
    # GitLab: "unknown keys in `extends`"
    jobs = {"a": {"script": ["x"]}, "b": {"extends": extends, "script": ["x"]}}
    errors, _ = validate(jobs, external_includes)
    assert any("which is not a job name" in e for e in errors)
    with pytest.raises(Exception, match="which is not a job name"):
        simulate_pipeline(jobs, {}, {})


def test_extends_of_an_undefined_job_is_an_error_without_non_local_includes():
    jobs = {"b": {"extends": ".remote_template", "script": ["x"]}}
    errors, _ = validate(jobs, False)
    assert "Job 'b' extends non-existing job '.remote_template'" in errors


def test_needs_inherited_through_an_unknown_parent_are_still_checked():
    # The job is expanded with what is known of the jobs it extends
    jobs = {".local": {"extends": ".remote_template", "needs": ["missing"]},
            "b": {"extends": ".local", "script": ["x"]}}
    errors, warnings = validate(jobs, True)
    assert errors == []
    assert any("needs 'missing'" in w for w in warnings)


def test_need_of_a_job_only_known_as_a_parent_is_a_warning():
    # It is not defined: it does not exist as a job
    jobs = {"b": {"extends": "base", "script": ["x"]}, "c": {"script": ["x"], "needs": ["base"]}}
    errors, warnings = validate(jobs, True)
    assert errors == []
    assert any("Job 'c' needs 'base'" in w for w in warnings)


# simulate

def test_simulate_reports_an_undefined_needed_job_as_external():
    jobs = {"b": {"script": ["x"], "needs": ["prepare"]}}
    summary = simulate_pipeline(jobs, {}, {}, external_includes=True)
    assert summary["jobs_list"] == ["b"]
    assert [e.get("from_non_local_include") for e in summary["dependency_errors"]] == [True]


def test_simulate_keeps_reporting_a_defined_job_that_does_not_run():
    jobs = {"a": {"script": ["x"], "rules": [{"when": "never"}]},
            "b": {"script": ["x"], "needs": ["a"]}}
    summary = simulate_pipeline(jobs, {}, {}, external_includes=True)
    assert [e.get("from_non_local_include") for e in summary["dependency_errors"]] == [None]


def test_simulate_expands_a_job_that_extends_an_undefined_job():
    jobs = {"b": {"extends": "base", "script": ["x"]}}
    summary = simulate_pipeline(jobs, {}, {}, external_includes=True)
    assert summary["jobs_list"] == ["b"]
    assert "base" not in summary["all_expanded_jobs"]


# CLI

CI_WITH_COMPONENT = (
    "include:\n"
    "  - component: example.com/group/component/release@1.0\n"
    "build:\n  script: [x]\n"
    "publish:\n  script: [x]\n  needs: [build, \"release:prepare\"]\n")


def test_validate_cli_succeeds_with_a_warning(tmp_path, monkeypatch, capsys):
    root = write(tmp_path / ".gitlab-ci.yml", CI_WITH_COMPONENT)
    monkeypatch.setattr("sys.argv", ["cimulator", "validate", root, "-o", str(tmp_path / "out.yml")])
    main()
    captured = capsys.readouterr()
    assert "Validation successful" in captured.out
    assert "Job 'publish' needs 'release:prepare', which is not defined" in captured.err


def test_simulate_cli_succeeds_with_a_warning(tmp_path, monkeypatch, capsys):
    root = write(tmp_path / ".gitlab-ci.yml", CI_WITH_COMPONENT)
    profiles = write(tmp_path / "profiles.yml", "default:\n  CI_PIPELINE_SOURCE: push\n")
    monkeypatch.setattr("sys.argv", ["cimulator", "simulate", root, profiles, "default",
                                     "-o", str(tmp_path / "out.yml")])
    main()  # no SystemExit: the need is only a warning
    captured = capsys.readouterr()
    assert "[Non-local include] Job 'publish' needs job 'release:prepare'" in captured.err


def test_simulate_cli_fails_without_non_local_includes(tmp_path, monkeypatch):
    root = write(tmp_path / ".gitlab-ci.yml", CI_WITH_COMPONENT.split("\n", 2)[2])
    profiles = write(tmp_path / "profiles.yml", "default:\n  CI_PIPELINE_SOURCE: push\n")
    monkeypatch.setattr("sys.argv", ["cimulator", "simulate", root, profiles, "default",
                                     "-o", str(tmp_path / "out.yml")])
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1


# Include entries, as GitLab reads them

def test_empty_include_entry_is_ignored(tmp_path):
    # GitLab ignores it: it is no non-local include
    root = write(tmp_path / ".gitlab-ci.yml", "include:\n  - \njob:\n  script: [echo]\n")
    assert external_includes_of(root) == []


@pytest.mark.parametrize("entry", ["{}", "{locale: ci/jobs.yml}", "{project: group/repo}", "[ci/jobs.yml]",
                                   "{artifact: generated.yml}"])
def test_invalid_include_entry_fails(tmp_path, entry):
    # GitLab: "does not have a valid subkey for include", "must specify the file",
    # "must specify the job where to fetch the artifact from"
    root = write(tmp_path / ".gitlab-ci.yml", f"include:\n  - {entry}\njob:\n  script: [echo]\n")
    with pytest.raises(ValueError, match="not a valid include|must have a file|must have the job"):
        load_and_resolve(root)


# Rules of non-local includes, evaluated in order up to one that cannot be decided

@pytest.mark.parametrize("rules, recorded", [
    ("[{when: never}, {if: $FOO}]", False),     # the first rule decides
    ("[{if: $FOO}, {when: never}]", True),      # the first rule cannot be decided
    ("[{exists: [missing.yml]}, {if: $FOO}]", True),
    ("[{exists: [missing.yml]}]", False),
])
def test_validate_evaluates_rules_up_to_one_that_cannot_be_decided(tmp_path, rules, recorded):
    root = write(tmp_path / ".gitlab-ci.yml", (
        f"include:\n  - remote: https://example.com/ci.yml\n    rules: {rules}\n"
        "job:\n  script: [echo]\n"))
    assert bool(external_includes_of(root)) is recorded


def test_rule_that_cannot_be_evaluated_may_load_the_include(tmp_path):
    # In simulate: a job extending one of its templates still runs
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n  - remote: https://example.com/templates.yml\n"
        "    rules:\n      - if: $CI_PIPELINE_SOURCE =~ /\\p{L}/\n"
        "job:\n  extends: .remote_template\n  script: [echo]\n"))
    assert len(external_includes_of(root, {"CI_PIPELINE_SOURCE": "push"})) == 1


# Jobs that no include can define

@pytest.mark.parametrize("needed", ["stages", "default", "variables"])
def test_need_of_a_global_keyword_is_an_error_with_non_local_includes(needed):
    # GitLab: "undefined need": a global keyword is no job
    jobs = {"b": {"script": ["x"], "needs": [needed]}}
    errors, warnings = validate(jobs, True)
    assert errors == [f"Job 'b' needs non-existing job '{needed}'"]
    assert warnings == []
    summary = simulate_pipeline(jobs, {}, {}, external_includes=True)
    assert [e.get("from_non_local_include") for e in summary["dependency_errors"]] == [None]


# optional must be a boolean

@pytest.mark.parametrize("value", ["'false'", "'true'", "1"])
def test_optional_that_is_not_a_boolean_is_an_error(tmp_path, monkeypatch, capsys, value):
    # GitLab: "need optional should be a boolean value"
    root = write(tmp_path / ".gitlab-ci.yml",
                 f"a:\n  script: [x]\nb:\n  script: [x]\n  needs: [{{job: a, optional: {value}}}]\n")
    monkeypatch.setattr("sys.argv", ["cimulator", "validate", root, "-o", str(tmp_path / "out.yml")])
    with pytest.raises(SystemExit):
        main()
    assert "optional must be true or false" in capsys.readouterr().err


def test_optional_null_is_not_optional():
    # As in GitLab: the need of a missing job is then an error
    jobs = {"b": {"script": ["x"], "needs": [{"job": "nope", "optional": None}]}}
    errors, _ = validate(jobs, False)
    assert errors == ["Job 'b' needs non-existing job 'nope'"]
    summary = simulate_pipeline(jobs, {}, {})
    assert [e["is_optional"] for e in summary["dependency_errors"]] == [False]


def test_optional_false_string_is_not_optional_in_simulate():
    jobs = {"b": {"script": ["x"], "needs": [{"job": "nope", "optional": "false"}]}}
    summary = simulate_pipeline(jobs, {}, {})
    assert [e["is_optional"] for e in summary["dependency_errors"]] == [False]


@pytest.mark.parametrize("parent", ["default", "stages", "variables"])
def test_extends_of_a_global_keyword_is_an_error_with_non_local_includes(parent):
    # No include makes a global keyword a job: as without non-local includes
    jobs = {"b": {"extends": parent, "script": ["x"]}}
    errors, warnings = validate(jobs, True)
    assert f"Job 'b' extends non-existing job '{parent}'" in errors
    assert warnings == []


def test_validate_shows_the_warnings_when_it_fails(tmp_path, monkeypatch, capsys):
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n  - remote: https://example.com/ci.yml\n"
        "job:\n  script: [x]\n  needs: [remote_job, stages]\n"))
    monkeypatch.setattr("sys.argv", ["cimulator", "validate", root, "-o", str(tmp_path / "out.yml")])
    with pytest.raises(SystemExit):
        main()
    err = capsys.readouterr().err
    assert "Job 'job' needs 'remote_job', which is not defined" in err
    assert "Job 'job' needs non-existing job 'stages'" in err


def test_rule_that_cannot_be_evaluated_is_a_warning(tmp_path, caplog):
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n  - remote: https://example.com/templates.yml\n"
        "    rules:\n      - if: $CI_PIPELINE_SOURCE =~ /\\p{L}/\n"
        "job:\n  script: [echo]\n"))
    external_includes_of(root, {"CI_PIPELINE_SOURCE": "push"})
    assert "Cannot evaluate a rule of a non-local include, taken as possibly matching" in caplog.text


@pytest.mark.parametrize("rules, variables, recorded", [
    # A rule that cannot be decided but has when: never can only exclude
    ("[{if: $FOO, when: never}]", None, False),
    ("[{if: $FOO, when: never}, {when: always}]", None, True),
    ("[{if: '$CI_PIPELINE_SOURCE =~ /\\p{L}/', when: never}]", {"CI_PIPELINE_SOURCE": "push"}, False),
    ("[{if: '$CI_PIPELINE_SOURCE =~ /\\p{L}/', when: never}, {when: always}]",
     {"CI_PIPELINE_SOURCE": "push"}, True),
    # exists of another project, or a regexp, cannot be checked: undecided
    ("[{exists: {paths: [ci.yml], project: group/other}, when: never}, {when: always}]", None, True),
    ("[{exists: {paths: [ci.yml], project: group/other}, when: never}]", None, False),
    ("[{exists: {paths: [ci.yml], project: group/other}}]", {}, True),
    # changes cannot be known offline: undecided
    ("[{changes: [ci.yml], when: never}, {when: always}]", None, True),
    ("[{changes: [ci.yml], when: never}, {when: always}]", {}, True),
    ("[{changes: [ci.yml], when: never}]", None, False),
    ("[{changes: [ci.yml]}]", {}, True),
    # A local exists that matches no file decides, whatever the if
    ("[{if: $FOO, exists: [missing.yml]}]", None, False),
    ("[{if: '$CI_PIPELINE_SOURCE =~ /\\p{L}/', exists: [missing.yml]}]", {"CI_PIPELINE_SOURCE": "push"}, False),
    ("[{changes: [ci.yml], exists: [missing.yml]}]", {}, False),
    ("[{if: $FOO, exists: [missing.yml]}, {when: always}]", None, True),
    # unless its path has variables that are not known
    ("[{if: $FOO, exists: [$DIR/missing.yml]}]", None, True),
])
def test_rules_that_cannot_be_decided(tmp_path, rules, variables, recorded):
    root = write(tmp_path / ".gitlab-ci.yml", (
        f"include:\n  - remote: https://example.com/ci.yml\n    rules: {rules}\n"
        "job:\n  script: [echo]\n"))
    assert bool(external_includes_of(root, variables)) is recorded


def test_exists_that_cannot_be_checked_is_a_warning(tmp_path, caplog):
    root = write(tmp_path / ".gitlab-ci.yml", (
        "include:\n  - remote: https://example.com/ci.yml\n"
        "    rules: [{exists: {paths: [ci.yml], project: group/other}}]\n"
        "job:\n  script: [echo]\n"))
    external_includes_of(root, {})
    assert "Cannot check exists:project" in caplog.text


def test_pipeline_need_of_a_job_that_may_get_trigger_from_an_unknown_job():
    # The template it extends, maybe from a non-local include, may set trigger
    need = {"pipeline": "group/upstream"}
    jobs = {".local": {"extends": ".remote_trigger"},
            "t": {"extends": ".local", "needs": [need]}}
    errors, warnings = validate(jobs, True)
    assert errors == []
    assert any("may get trigger from a job that is not defined" in w for w in warnings)
    # Without such a parent, it is an error
    errors, _ = validate({"t": {"script": ["x"], "needs": [need]}}, True)
    assert errors == [f"Job 't' needs a pipeline without a job, which only a trigger job can: {need}"]


def test_artifact_include_is_described(tmp_path, caplog):
    import logging
    caplog.set_level(logging.INFO)
    root = write(tmp_path / ".gitlab-ci.yml",
                 "include:\n  - artifact: generated.yml\n    job: generate\njob:\n  script: [echo]\n")
    external_includes_of(root)
    assert "Not loading non-local include artifact generated.yml of job generate" in caplog.text
