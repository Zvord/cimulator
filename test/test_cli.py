import tempfile
import os
import yaml
import pytest
from cimulator.cli import main
import shutil

def create_temp_file(contents):
    """Helper to create a temporary file with given contents."""
    tmp = tempfile.NamedTemporaryFile("w", delete=False)
    tmp.write(contents)
    tmp.close()
    return tmp.name

def test_validate_cli(monkeypatch, capsys):
    # Create a simple .gitlab-ci file.
    ci_content = """
variables:
  GLOBAL: "value"
job1:
  script: "echo hello"
"""
    ci_file = create_temp_file(ci_content)
    output_file = "test_validation_output.yml"

    # Simulate command-line args for the 'validate' subcommand with output file.
    monkeypatch.setattr("sys.argv", ["cli.py", "validate", ci_file, "--output", output_file])
    try:
        main()
        # Check if the success message is printed to stdout
        captured = capsys.readouterr().out
        assert "Validation successful" in captured
        assert output_file in captured

        # Check if the output file exists and contains the expected content
        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            content = f.read()
            assert "job1" in content
            assert "echo hello" in content
    finally:
        os.remove(ci_file)
        # Clean up the output file
        if os.path.exists(output_file):
            os.remove(output_file)

def test_simulate_cli_with_profile(monkeypatch, capsys):
    # Create a simple .gitlab-ci file with a workflow and one job.
    ci_content = """
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
      when: always
      variables:
        PIPELINE: "scheduled_pipeline"
job1:
  script: "echo $STATUS"
"""
    ci_file = create_temp_file(ci_content)

    # Create a simulation configuration file with profiles.
    # This is your provided example.
    sim_content = """
Nightly-Product:
  CI_PIPELINE_SOURCE: "schedule"
  RUN_NIGHTLY_EXTRAS: "1"

MR-Push-Object:
  CI_PIPELINE_SOURCE: "merge_request_event"
  CI_MERGE_REQUEST_EVENT_TYPE: ""
  CI_MERGE_REQUEST_TARGET_BRANCH_NAME: "master"
"""
    sim_file = create_temp_file(sim_content)
    output_file = "test_simulation_output.yml"

    # The new CLI expects an additional profile argument, e.g., "Nightly-Product".
    # Simulate command-line arguments for the 'simulate' subcommand with output file.
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", ci_file, sim_file, "Nightly-Product", "--output", output_file])
    try:
        main()
        # Check if the success message is printed to stdout
        captured = capsys.readouterr().out
        assert "Simulation successful" in captured
        assert output_file in captured

        # Check if the output file exists and contains the expected content
        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            content = f.read()
            # We expect that the simulation summary reflects the global variables from the "Nightly-Product" profile.
            # For instance, RUN_NIGHTLY_EXTRAS should be set to "1".
            assert "RUN_NIGHTLY_EXTRAS: '1'" in content or 'RUN_NIGHTLY_EXTRAS: "1"' in content
    finally:
        os.remove(ci_file)
        os.remove(sim_file)
        # Clean up the output file
        if os.path.exists(output_file):
            os.remove(output_file)


def test_global_keywords_are_not_jobs(monkeypatch, tmp_path):
    """default, and the deprecated global image/cache, are not simulated as jobs."""
    ci_file = tmp_path / ".gitlab-ci.yml"
    ci_file.write_text("""
default:
  before_script:
    - echo setup
image:
  name: alpine
cache:
  paths: [vendor/]
job1:
  script: "echo hello"
""")
    config_file = tmp_path / "profiles.yml"
    config_file.write_text("profile:\n  CI_PIPELINE_SOURCE: push\n")
    output_file = tmp_path / "simulation_output.yml"

    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(ci_file), str(config_file), "profile",
                                     "--output", str(output_file)])
    main()

    simulation = yaml.safe_load(output_file.read_text())
    assert simulation["jobs_list"] == ["job1"]
    assert set(simulation["jobs"]) == {"job1"}


def test_simulate_cli_includes_use_the_profile_variables(monkeypatch, tmp_path):
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "push.yml").write_text("push_job:\n  script: [echo]\n")
    (tmp_path / ".gitlab-ci.yml").write_text(
        "include:\n"
        "  - local: ci/$CI_PIPELINE_SOURCE.yml\n"
        "    rules:\n"
        "      - if: $CI_PIPELINE_SOURCE == \"push\"\n"
        "job:\n  script: [echo]\n"
    )
    (tmp_path / "profiles.yml").write_text(
        "push:\n  CI_PIPELINE_SOURCE: push\nweb:\n  CI_PIPELINE_SOURCE: web\n")
    for profile, expected in (("push", ["job", "push_job"]), ("web", ["job"])):
        output = tmp_path / f"{profile}.yml"
        monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                         str(tmp_path / "profiles.yml"), profile, "--output", str(output)])
        main()
        assert sorted(yaml.safe_load(output.read_text())["jobs_list"]) == expected


def test_simulate_cli_with_an_empty_profile(monkeypatch, tmp_path):
    (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: [echo]\n")
    (tmp_path / "profiles.yml").write_text("empty:\n")
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "empty", "--output", str(output)])
    main()
    assert yaml.safe_load(output.read_text())["jobs_list"] == ["job"]


def test_simulate_cli_profile_values_are_strings(monkeypatch, tmp_path):
    # YAML gives true and 1 as a boolean and a number; GitLab's values are the text
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "true.yml").write_text("flag_job:\n  script: [echo]\n")
    (tmp_path / ".gitlab-ci.yml").write_text(
        "include: ci/$FLAG.yml\n"
        "job:\n  script: [echo]\n  rules:\n    - if: $FLAG == \"true\" && $COUNT == \"1\"\n"
    )
    (tmp_path / "profiles.yml").write_text("p:\n  FLAG: true\n  COUNT: 1\n")
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "p", "--output", str(output)])
    main()
    assert sorted(yaml.safe_load(output.read_text())["jobs_list"]) == ["flag_job", "job"]


@pytest.mark.parametrize("profiles, error", [
    ("p:\n  - CI\n", "Profile 'p' must be a mapping of variables, not a list"),
    ("p:\n  X: {a: 1}\n", "Profile 'p': the value of X must be text, a number or a boolean, not a dict"),
    ("p:\n  X: [1]\n", "Profile 'p': the value of X must be text, a number or a boolean, not a list"),
])
def test_simulate_cli_invalid_profile_fails(monkeypatch, tmp_path, capsys, profiles, error):
    (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: [echo]\n")
    (tmp_path / "profiles.yml").write_text(profiles)
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "p", "--output", str(tmp_path / "out.yml")])
    with pytest.raises(SystemExit):
        main()
    assert error in capsys.readouterr().err


def test_simulate_cli_simulation_config_that_is_not_a_mapping_fails(monkeypatch, tmp_path, capsys):
    (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: [echo]\n")
    (tmp_path / "profiles.yml").write_text("- p\n")
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "p", "--output", str(tmp_path / "out.yml")])
    with pytest.raises(SystemExit):
        main()
    assert "must be a mapping of profiles, not a list" in capsys.readouterr().err


def test_simulate_cli_profile_values_are_kept_as_written(monkeypatch, tmp_path):
    # Not retyped by YAML: 1.10 is not 1.1, 010 not 8, 1:30 not 90, yes not true
    (tmp_path / ".gitlab-ci.yml").write_text(
        "job:\n  script: [echo]\n  rules:\n"
        "    - if: $V == \"1.10\" && $O == \"010\" && $T == \"1:30\" && $Y == \"yes\" && $E == \"\"\n"
    )
    (tmp_path / "profiles.yml").write_text("p:\n  V: 1.10\n  O: 010\n  T: 1:30\n  Y: yes\n  E:\n")
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "p", "--output", str(output)])
    main()
    assert yaml.safe_load(output.read_text())["jobs_list"] == ["job"]


@pytest.mark.parametrize("empty", ["", " ~", " null"])
def test_simulate_cli_empty_profile_written_as_null(monkeypatch, tmp_path, empty):
    (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: [echo]\n")
    (tmp_path / "profiles.yml").write_text(f"p:{empty}\n")
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "p", "--output", str(output)])
    main()
    assert yaml.safe_load(output.read_text())["jobs_list"] == ["job"]


def test_simulate_cli_profile_anchors_and_null_values(monkeypatch, tmp_path):
    # << merges apply; null and ~ are empty values, not the text null
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "a.yml").write_text("a_job:\n  script: [echo]\n")
    (tmp_path / ".gitlab-ci.yml").write_text(
        "include: ci/a$N.yml\n"
        "job:\n  script: [echo]\n  rules:\n"
        "    - if: $A == \"1.10\" && $B == \"yes\" && $N == \"\" && $T == \"\"\n"
    )
    (tmp_path / "profiles.yml").write_text(
        "common: &common\n  A: 1.10\n  N: null\np:\n  <<: *common\n  B: yes\n  T: ~\n")
    output = tmp_path / "out.yml"
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", str(tmp_path / ".gitlab-ci.yml"),
                                     str(tmp_path / "profiles.yml"), "p", "--output", str(output)])
    main()
    assert sorted(yaml.safe_load(output.read_text())["jobs_list"]) == ["a_job", "job"]
