import argparse
import sys
import yaml
import logging
import os
import traceback
from typing import List, Optional, Union, Tuple, Set, NoReturn
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from cimulator.types import ConfigDict, JobDict, JobSourcesDict
from cimulator.loader import load_and_resolve
from cimulator.job_expander import expand_all_jobs
from cimulator.simulation_engine import simulate_pipeline
from cimulator.config import load_simulation_config
from cimulator.validator import validate_job_dependencies, detect_duplicate_jobs

def setup_logging(level: int) -> None:
    """
    Set up logging configuration for the entire application.

    Parameters:
        level (int): The logging level to use (e.g., logging.DEBUG, logging.INFO)
    """
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add a console handler with a specific format
    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    ch.setFormatter(formatter)
    root_logger.addHandler(ch)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitLab CI Simulator - Validate and simulate GitLab CI pipelines."
    )

    # Add global arguments
    parser.add_argument(
        "--log-level", "-l",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Set the logging level (default: info)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 'validate' subcommand: loads and saves the merged configuration to a file.
    validate_parser = subparsers.add_parser("validate", help="Validate GitLab CI configuration")
    validate_parser.add_argument("ci_file", help="Path to the .gitlab-ci.yml file")
    validate_parser.add_argument(
        "--output", "-o",
        help="Path to the output file (default: validation_output.yml)",
        default="validation_output.yml"
    )

    # 'simulate' subcommand: runs the simulation and saves the results to a file.
    simulate_parser = subparsers.add_parser("simulate", help="Simulate GitLab CI pipeline")
    simulate_parser.add_argument("ci_file", help="Path to the .gitlab-ci.yml file")
    simulate_parser.add_argument(
        "simulation_config",
        help="Path to the simulation configuration YAML file (defines global variables, etc.)"
    )
    simulate_parser.add_argument(
        "profile",
        help="Name of the profile in the simulation configuration file to use"
    )
    simulate_parser.add_argument(
        "--output", "-o",
        help="Path to the output file (default: simulation_output.yml)",
        default="simulation_output.yml"
    )

    args = parser.parse_args()

    # Set up logging based on the specified level
    log_level_map = {
        "debug": DEBUG,
        "info": INFO,
        "warning": WARNING,
        "error": ERROR,
        "critical": CRITICAL
    }
    setup_logging(log_level_map[args.log_level])

    if args.command == "validate":
        try:
            config, job_sources = load_and_resolve(args.ci_file)

            # Extract jobs from the configuration
            reserved_keys = {"include", "workflow", "variables", "stages"}
            jobs = {k: v for k, v in config.items() if k not in reserved_keys and isinstance(v, dict)}

            # Validate job dependencies
            validation_errors = validate_job_dependencies(jobs)

            # Check for duplicate jobs
            duplicate_warnings = detect_duplicate_jobs(jobs, job_sources)

            if validation_errors:
                print("Validation failed with the following errors:", file=sys.stderr)
                for error in validation_errors:
                    print(f"  - {error}", file=sys.stderr)
                sys.exit(1)

            # Display warnings about duplicate jobs
            if duplicate_warnings:
                print("\nWarnings about duplicate jobs:", file=sys.stderr)
                for warning in duplicate_warnings:
                    print(f"  - {warning}", file=sys.stderr)

            # Save the output to a file instead of printing it
            with open(args.output, 'w') as f:
                f.write(yaml.dump(config, default_flow_style=False))
            print(f"Validation successful. Output saved to {os.path.abspath(args.output)}")
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb = traceback.extract_tb(exc_traceback)
            filename, line, func, text = tb[-1]
            print(f"Error during validation: {e} (File: {filename}, line {line})", file=sys.stderr)
            sys.exit(1)

    elif args.command == "simulate":
        try:
            # Load the GitLab CI configuration.
            ci_config, job_sources = load_and_resolve(args.ci_file)
            # Extract jobs from the configuration.
            # For simplicity, we treat all keys that are not reserved as jobs.
            # Also filter out non-dictionary values as they can't be valid jobs
            reserved_keys = {"include", "workflow", "variables", "stages"}
            jobs = {k: v for k, v in ci_config.items() if k not in reserved_keys and isinstance(v, dict)}

            # Check for duplicate jobs
            duplicate_warnings = detect_duplicate_jobs(jobs, job_sources)

            # Get the workflow configuration (if any).
            workflow_config = ci_config.get("workflow", {})

            # Get global variables from the GitLab CI file
            gitlab_vars = ci_config.get("variables", {})

            # Load simulation configuration (global variables etc.)
            sim_config = load_simulation_config(args.simulation_config)
            # Get the variables from the specified profile
            if args.profile not in sim_config:
                raise ValueError(f"'{args.profile}' is not a valid key in the simulation configuration file. Expected keys: {list(sim_config.keys())}")
            profile_vars = sim_config.get(args.profile, {})

            # Merge GitLab CI variables with profile variables
            # Profile variables take precedence over GitLab CI variables
            global_vars = {**gitlab_vars, **profile_vars}

            # Run the simulation.
            simulation_summary = simulate_pipeline(jobs, workflow_config, global_vars)

            # First, dump the simulation summary to YAML
            yaml_content = yaml.dump(simulation_summary, default_flow_style=False)

            # Post-process the YAML content to add empty lines between jobs
            lines = yaml_content.split('\n')
            processed_lines = []
            in_jobs_section = False
            job_indent = None

            # Keep track of whether we've seen the first job
            first_job = True

            for i, line in enumerate(lines):
                # Check if we're entering the jobs section
                if line.startswith('jobs:'):
                    in_jobs_section = True
                    processed_lines.append(line)
                    continue

                # If we're in the jobs section and this line defines a job (not indented)
                if in_jobs_section and line and not line.startswith(' '):
                    # We've moved past the jobs section
                    in_jobs_section = False
                    processed_lines.append(line)
                    continue

                # If we're in the jobs section and this is a job entry
                if in_jobs_section and line.strip() and line.startswith('  '):
                    # Determine the indentation level of job entries if not already set
                    if job_indent is None and not line.startswith('    '):
                        job_indent = len(line) - len(line.lstrip())

                    # If this is a job entry (not a property of a job)
                    if job_indent is not None and line.startswith(' ' * job_indent) and not line.startswith(' ' * (job_indent + 2)):
                        # Add an empty line before the job, but not before the first job
                        if not first_job:
                            processed_lines.append('')
                        else:
                            first_job = False

                processed_lines.append(line)

            # Save the processed content to the output file
            with open(args.output, 'w') as f:
                f.write('\n'.join(processed_lines))

            # Check for dependency errors (show as warnings, not hard errors)
            if simulation_summary.get("dependency_errors"):
                print("\nWarnings about job dependencies:", file=sys.stderr)
                for error in simulation_summary["dependency_errors"]:
                    print(f"  - {error}", file=sys.stderr)

            # Display warnings about duplicate jobs
            if duplicate_warnings:
                print("\nWarnings about duplicate jobs:", file=sys.stderr)
                for warning in duplicate_warnings:
                    print(f"  - {warning}", file=sys.stderr)

            print(f"Simulation successful. Output saved to {os.path.abspath(args.output)}")
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb = traceback.extract_tb(exc_traceback)
            filename, line, func, text = tb[-1]
            print(f"Error during simulation: {e} (File: {filename}, line {line})", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
