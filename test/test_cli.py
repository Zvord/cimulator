import tempfile
import os
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

def test_simulate_cli(monkeypatch, capsys):
    # Create a simple .gitlab-ci file with a workflow and one job.
    ci_content = """
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "push"'
      when: always
      variables:
        PIPELINE: "push_pipeline"
job1:
  script: "echo $MESSAGE"
"""
    ci_file = create_temp_file(ci_content)

    # Create a simulation configuration file.
    sim_content = """
simulation:
  variables:
    CI_PIPELINE_SOURCE: "push"
    MESSAGE: "Hello from simulation"
"""
    sim_file = create_temp_file(sim_content)

    monkeypatch.setattr("sys.argv", ["cli.py", "simulate", ci_file, sim_file])
    try:
        main()
        captured = capsys.readouterr().out
        assert "Pipeline Simulation Summary" in captured
        assert "Hello from simulation" in captured
    finally:
        os.remove(ci_file)
        os.remove(sim_file)
