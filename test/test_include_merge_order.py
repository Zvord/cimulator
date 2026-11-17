"""Includes are merged in GitLab's order.

GitLab merges the included files in order, each one on top of the previous
ones, and then the including file's own content on top of them all. Mappings
are merged key by key; any other value, a list or null included, replaces
the previous one. A nested include is merged into the file that includes it,
so its content takes the position of that file.
"""
import textwrap

import pytest

import yaml

from cimulator.cli import main
from cimulator.loader import load_and_resolve
from cimulator.validator import detect_duplicate_jobs


def write(directory, files):
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content))
    return str(directory / ".gitlab-ci.yml")


def load(tmp_path, files):
    config, _ = load_and_resolve(write(tmp_path, files))
    return config


def test_including_file_overrides_its_includes(tmp_path):
    config = load(tmp_path, {
        ".gitlab-ci.yml": """
            include: base.yml
            build:
              stage: deploy
        """,
        "base.yml": """
            build:
              stage: build
              script: [make]
        """,
    })
    assert config["build"] == {"stage": "deploy", "script": ["make"]}


def test_later_include_overrides_earlier_one(tmp_path):
    files = {
        "first.yml": "build:\n  stage: first\n  script: [one]\n",
        "second.yml": "build:\n  stage: second\n",
    }
    config = load(tmp_path, {**files, ".gitlab-ci.yml": "include: [first.yml, second.yml]\n"})
    assert config["build"] == {"stage": "second", "script": ["one"]}

    config = load(tmp_path, {**files, ".gitlab-ci.yml": "include: [second.yml, first.yml]\n"})
    assert config["build"] == {"stage": "first", "script": ["one"]}


def test_nested_include_takes_the_position_of_its_includer(tmp_path):
    files = {
        "outer.yml": """
            include: inner.yml
            build:
              tags: [outer]
        """,
        "inner.yml": """
            build:
              stage: inner
              tags: [inner]
              script: [make]
        """,
        "other.yml": "build:\n  stage: other\n",
    }
    # outer.yml overrides inner.yml, and other.yml, included after both, overrides them.
    config = load(tmp_path, {**files, ".gitlab-ci.yml": "include: [outer.yml, other.yml]\n"})
    assert config["build"] == {"stage": "other", "tags": ["outer"], "script": ["make"]}

    # Included before outer.yml, other.yml is overridden by inner.yml.
    config = load(tmp_path, {**files, ".gitlab-ci.yml": "include: [other.yml, outer.yml]\n"})
    assert config["build"] == {"stage": "inner", "tags": ["outer"], "script": ["make"]}


def test_lists_and_nulls_replace_mappings_merge(tmp_path):
    config = load(tmp_path, {
        ".gitlab-ci.yml": """
            include: base.yml
            variables:
              SHARED: root
              DESCRIBED:
                description: from the root
            test:
              script: [root]
              parallel:
                matrix:
                  - SUITE: [only]
              artifacts: null
              variables:
                EXTRA: x
        """,
        "base.yml": """
            variables:
              SHARED: base
              KEPT: base
              DESCRIBED:
                value: "1"
            test:
              stage: test
              script: [base, more]
              parallel:
                matrix:
                  - SUITE: [a, b]
              artifacts:
                paths: [out/]
              variables:
                MODE: full
        """,
    })
    assert config["variables"] == {
        "SHARED": "root",
        "KEPT": "base",
        "DESCRIBED": {"value": "1", "description": "from the root"},
    }
    assert config["test"] == {
        "stage": "test",
        "script": ["root"],
        "parallel": {"matrix": [{"SUITE": ["only"]}]},
        "artifacts": None,
        "variables": {"MODE": "full", "EXTRA": "x"},
    }


def test_merge_does_not_change_an_aliased_mapping(tmp_path):
    config = load(tmp_path, {
        ".gitlab-ci.yml": """
            include: base.yml
            .settings:
              variables:
                MODE: root
        """,
        "base.yml": """
            .settings: &settings
              variables:
                MODE: base
            .copy: *settings
        """,
    })
    assert config[".settings"] == {"variables": {"MODE": "root"}}
    assert config[".copy"] == {"variables": {"MODE": "base"}}


def test_duplicate_job_is_reported_with_the_definition_that_wins(tmp_path):
    ci_file = write(tmp_path, {
        ".gitlab-ci.yml": """
            include: [first.yml, second.yml]
            build:
              script: [root]
        """,
        "first.yml": "build:\n  script: [first]\n",
        "second.yml": "build:\n  script: [second]\n",
    })
    config, job_sources = load_and_resolve(ci_file)
    warnings = detect_duplicate_jobs({"build": config["build"]}, job_sources)
    assert warnings == [
        f"Duplicate job 'build' found (defined in: {ci_file}, also defined in: "
        f"{tmp_path / 'first.yml'}, {tmp_path / 'second.yml'})."
    ]


def test_simulate_uses_the_overriding_rules(monkeypatch, tmp_path):
    ci_file = write(tmp_path, {
        ".gitlab-ci.yml": """
            include: jobs.yml
            deploy:
              rules:
                - if: $CI_COMMIT_BRANCH == "main"
        """,
        "jobs.yml": """
            build:
              script: [make]
            deploy:
              script: [ship]
              rules:
                - when: never
        """,
    })
    config_file = tmp_path / "profiles.yml"
    config_file.write_text("main:\n  CI_PIPELINE_SOURCE: push\n  CI_COMMIT_BRANCH: main\n")
    output_file = tmp_path / "simulation_output.yml"

    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", ci_file, str(config_file), "main",
                                     "--output", str(output_file)])
    main()

    simulation = yaml.safe_load(output_file.read_text())
    assert sorted(simulation["jobs_list"]) == ["build", "deploy"]
    assert simulation["jobs"]["deploy"]["script"] == ["ship"]


def test_repeated_include_is_merged_again_where_it_appears(tmp_path):
    config = load(tmp_path, {
        ".gitlab-ci.yml": "include: [first.yml, second.yml, first.yml]\n",
        "first.yml": "build:\n  stage: first\n",
        "second.yml": "build:\n  stage: second\n",
    })
    assert config["build"] == {"stage": "first"}


def test_file_included_by_two_files_is_merged_at_the_second(tmp_path):
    ci_file = write(tmp_path, {
        ".gitlab-ci.yml": "include: [a.yml, b.yml]\n",
        "a.yml": """
            include: shared.yml
            build:
              script: [from_a]
        """,
        "b.yml": "include: shared.yml\n",
        "shared.yml": "build:\n  script: [from_shared]\n",
    })
    config, job_sources = load_and_resolve(ci_file)
    # shared.yml is merged again after a.yml, through b.yml, so it overrides a.yml.
    assert config["build"] == {"script": ["from_shared"]}
    assert detect_duplicate_jobs({"build": config["build"]}, job_sources) == [
        f"Duplicate job 'build' found (defined in: {tmp_path / 'shared.yml'}, "
        f"also defined in: {tmp_path / 'a.yml'})."
    ]


def test_job_overridden_with_a_reference_is_reported(tmp_path):
    ci_file = write(tmp_path, {
        ".gitlab-ci.yml": """
            include: base.yml
            .template:
              script: [from_template]
            build: !reference [.template]
        """,
        "base.yml": "build:\n  script: [from_base]\n",
    })
    config, job_sources = load_and_resolve(ci_file)
    assert config["build"] == {"script": ["from_template"]}
    assert detect_duplicate_jobs({"build": config["build"]}, job_sources) == [
        f"Duplicate job 'build' found (defined in: {ci_file}, also defined in: {tmp_path / 'base.yml'})."
    ]


def test_keys_are_in_merge_order(tmp_path):
    # As in GitLab's merged configuration: the included keys first, then the
    # including file's own keys; an overridden key keeps its first position.
    config = load(tmp_path, {
        ".gitlab-ci.yml": """
            first_root_job:
              script: [x]
            include: base.yml
            variables:
              B: "2"
            last_root_job:
              script: [x]
        """,
        "base.yml": """
            variables:
              A: "1"
            included_job:
              script: [x]
        """,
    })
    assert list(config) == ["variables", "included_job", "first_root_job", "last_root_job"]


def test_file_included_twice_is_named_once_in_the_duplicate_warning(tmp_path):
    root = write(tmp_path, {
        "common.yml": "job:\n  script: [common]\n",
        "a.yml": "include: common.yml\n",
        "b.yml": "include: common.yml\n",
        ".gitlab-ci.yml": "include: [a.yml, b.yml]\njob:\n  script: [root]\n",
    })
    config, job_sources = load_and_resolve(root)
    [warning] = detect_duplicate_jobs({"job": config["job"]}, job_sources)
    assert warning.endswith(f"also defined in: {tmp_path / 'common.yml'}).")


def test_overriding_a_template_is_not_reported(tmp_path):
    root = write(tmp_path, {
        "templates.yml": ".tpl:\n  script: [a]\n",
        ".gitlab-ci.yml": "include: templates.yml\n.tpl:\n  script: [b]\njob:\n  extends: .tpl\n",
    })
    config, job_sources = load_and_resolve(root)
    jobs = {name: config[name] for name in (".tpl", "job")}
    assert detect_duplicate_jobs(jobs, job_sources) == []
    assert detect_duplicate_jobs({".tpl": {}, "job": {}}) == []


@pytest.mark.parametrize("key", ["variables", "workflow"])
def test_empty_global_keyword_replaces_the_included_one(tmp_path, monkeypatch, key):
    # As in GitLab: null replaces the included value, and is empty
    ci_file = write(tmp_path, {
        "base.yml": """
            variables:
              A: from_base
            workflow:
              rules:
                - when: never
        """,
        ".gitlab-ci.yml": f"include: base.yml\n{key}:\njob:\n  script: [echo $A]\n",
        "profiles.yml": "p:\n  X: '1'\n",
    })
    config, _ = load_and_resolve(ci_file)
    assert config[key] is None
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cimulator", "simulate", ci_file, str(tmp_path / "profiles.yml"),
                                     "p", "--output", str(output)])
    main()
    result = yaml.safe_load(output.read_text())
    if key == "variables":
        # The included workflow still never runs; A is gone
        assert result["workflow_run"] is False
    else:
        # No workflow rules: the pipeline runs, with the included A
        assert result["jobs"]["job"]["script"] == ["echo from_base"]


def test_null_keys_overriding_included_ones_are_absent(tmp_path, monkeypatch, capsys):
    # As in GitLab: a null extends, needs, variables or workflow rules is none
    ci_file = write(tmp_path, {
        "base.yml": """
            workflow:
              rules:
                - when: always
            .t:
              image: alpine
            a:
              script: [x]
            base:
              script: [echo $V]
              extends: .t
              needs: [a]
              variables:
                V: v
        """,
        ".gitlab-ci.yml": "include: base.yml\nworkflow:\n  rules:\nbase:\n  extends:\n  needs:\n  variables:\n",
        "profiles.yml": "p:\n  X: '1'\n",
    })
    monkeypatch.setattr("sys.argv", ["cimulator", "validate", ci_file, "--output", str(tmp_path / "v.yml")])
    main()
    assert "None" not in capsys.readouterr().err
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cimulator", "simulate", ci_file, str(tmp_path / "profiles.yml"),
                                     "p", "--output", str(output)])
    main()
    result = yaml.safe_load(output.read_text())
    assert result["workflow_run"] is True
    job = result["jobs"]["base"]
    assert "needs" not in job and "image" not in job
    assert job["script"] == ["echo "]


def test_null_keys_overriding_extended_ones_are_absent():
    from cimulator.job_expander import expand_job
    jobs = {".t": {"needs": ["nope"], "rules": [{"when": "never"}], "variables": {"V": "v"}},
            "b": {"extends": ".t", "script": ["x"], "needs": None, "rules": None, "variables": None}}
    assert expand_job("b", jobs) == {"script": ["x"]}
    assert expand_job("c", {"c": {"script": ["x"], "extends": None, "needs": None}}) == {"script": ["x"]}


def test_empty_workflow_rules_are_not_absent():
    # Only null rules are none: GitLab rejects `rules: []`
    from cimulator.workflow import evaluate_workflow
    assert evaluate_workflow({"rules": None}, {})[0] is True
    with pytest.raises(ValueError, match="must not be an empty list"):
        evaluate_workflow({"rules": []}, {})


def test_null_rule_variables_are_none(tmp_path, monkeypatch):
    # GitLab accepts a null `variables:` in a workflow or job rule
    ci_file = write(tmp_path, {
        ".gitlab-ci.yml": """
            workflow:
              rules:
                - variables:
            job:
              script: [x]
              rules:
                - variables:
        """,
        "profiles.yml": "p:\n  X: '1'\n",
    })
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cimulator", "simulate", ci_file, str(tmp_path / "profiles.yml"),
                                     "p", "--output", str(output)])
    main()
    result = yaml.safe_load(output.read_text())
    assert result["workflow_run"] is True
    assert result["jobs_list"] == ["job"]
