import argparse
import sys
import yaml
import logging
from cimulator.loader import load_and_resolve
from cimulator.job_expander import expand_all_jobs
from cimulator.simulation_engine import simulate_pipeline
from cimulator.config import load_simulation_config

def main():
    parser = argparse.ArgumentParser(
        description="GitLab CI Simulator - Validate and simulate GitLab CI pipelines."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 'validate' subcommand: loads and prints the merged configuration.
    validate_parser = subparsers.add_parser("validate", help="Validate GitLab CI configuration")
    validate_parser.add_argument("ci_file", help="Path to the .gitlab-ci.yml file")

    # 'simulate' subcommand: runs the simulation.
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

    args = parser.parse_args()

    if args.command == "validate":
        try:
            config = load_and_resolve(args.ci_file)
            print("Merged GitLab CI configuration:")
            print(yaml.dump(config, default_flow_style=False))
        except Exception as e:
            print(f"Error during validation: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "simulate":
        try:
            # Load the GitLab CI configuration.
            ci_config = load_and_resolve(args.ci_file)
            # Extract jobs from the configuration.
            # For simplicity, we treat all keys that are not reserved as jobs.
            reserved_keys = {"include", "workflow", "variables", "stages"}
            jobs = {k: v for k, v in ci_config.items() if k not in reserved_keys}

            # Get the workflow configuration (if any).
            workflow_config = ci_config.get("workflow", {})
            # Load simulation configuration (global variables etc.)
            sim_config = load_simulation_config(args.simulation_config)
            # Get the variables from the specified profile
            if args.profile not in sim_config:
                raise ValueError(f"'{args.profile}' is not a valid key in the simulation configuration file. Expected keys: {list(sim_config.keys())}")
            global_vars = sim_config.get(args.profile, {})

            # Run the simulation.
            simulation_summary = simulate_pipeline(jobs, workflow_config, global_vars)
            print("Pipeline Simulation Summary:")
            print(yaml.dump(simulation_summary, default_flow_style=False))
        except Exception as e:
            print(f"Error during simulation: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
