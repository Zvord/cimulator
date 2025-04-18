import tempfile
import os
import yaml
import pytest
from cimulator.cli import main

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
    # Simulate command-line args for the 'validate' subcommand.
    monkeypatch.setattr("sys.argv", ["cli.py", "validate", ci_file])
    try:
        main()
        captured = capsys.readouterr().out
        assert "job1" in captured
        assert "echo hello" in captured
    finally:
        os.remove(ci_file)

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
Nightly-Main:
  CI_PIPELINE_SOURCE: "schedule"
  RUN_NIGHTLY_CUSTOMER_BRANCH: "1"

MR-Push-Frozen:
  CI_PIPELINE_SOURCE: "merge_request_event"
  CI_MERGE_REQUEST_EVENT_TYPE: ""
  CI_MERGE_REQUEST_TARGET_BRANCH_NAME: "master"
"""
    sim_file = create_temp_file(sim_content)

    # Simulate command-line arguments for the 'simulate' subcommand.
    # The new CLI expects an additional profile argument, e.g., "Nightly-Main".
    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", ci_file, sim_file, "Nightly-Main"])
    try:
        main()
        captured = capsys.readouterr().out
        # We expect that the simulation summary reflects the global variables from the "Nightly-Main" profile.
        # For instance, RUN_NIGHTLY_CUSTOMER_BRANCH should be set to "1".
        assert "RUN_NIGHTLY_CUSTOMER_BRANCH: '1'" in captured or 'RUN_NIGHTLY_CUSTOMER_BRANCH: "1"' in captured
    finally:
        os.remove(ci_file)
        os.remove(sim_file)
