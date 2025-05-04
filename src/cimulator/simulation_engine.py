import logging
from typing import List, Set, Tuple, Optional, Union
from cimulator.types import JobDict, ConfigDict, VariablesDict
from cimulator.job_expander import expand_all_jobs
from cimulator.workflow import evaluate_workflow, evaluate_rules
from cimulator.variable_expander import expand_variables
from cimulator.validator import validate_job_needs_dependencies

# Get the logger for this module
logger = logging.getLogger(__name__)

def simulate_pipeline(all_jobs: JobDict, workflow_config: ConfigDict, global_variables: VariablesDict) -> ConfigDict:
    """
    Simulate a pipeline by processing jobs, evaluating workflow rules, and expanding variables.

    Steps:
      1. Evaluate the workflow configuration using the global variables.
         This returns whether the pipeline should run and any workflow-level variables.
      2. Merge the workflow-applied variables with the global variables.
      3. Expand all job definitions.
      4. For each job, if a job-level "rules" section exists, evaluate its rules
         (using the same generic rules evaluation function) and merge job-specific variables.
      5. Expand variables within the job definition.
      6. Log each step for debugging purposes.

    Parameters:
        all_jobs (dict): Dictionary of job definitions.
        workflow_config (dict): Workflow configuration dictionary.
        global_variables (dict): Global variables for the simulation.

    Returns:
        dict: A simulation summary that includes:
              - Whether the workflow permits a run.
              - The triggered workflow rule and its applied variables.
              - The final expanded jobs.
    """
    logger.debug("Starting pipeline simulation.")

    # Evaluate the workflow.
    wf_run, wf_rule, wf_vars, wf_triggered_condition = evaluate_workflow(workflow_config, global_variables)
    logger.debug(f"Workflow evaluation: should_run={wf_run}, triggered_condition={wf_triggered_condition}, variables={wf_vars}")

    # Merge workflow variables with the global variables.
    if not isinstance(global_variables, dict):
        logger.warning(f"Global variables is not a dictionary: {global_variables}")
        simulation_variables = {}
    else:
        simulation_variables = global_variables.copy()
    simulation_variables.update(wf_vars)
    logger.debug(f"Global variables after merging workflow variables: {simulation_variables}")

    # Expand all job definitions.
    expanded_jobs = expand_all_jobs(all_jobs)
    simulation_jobs = {}

    # Process jobs in a deterministic order to ensure dependencies are handled correctly
    # Sort job names to ensure consistent processing order
    sorted_job_names = sorted(expanded_jobs.keys())

    for job_name in sorted_job_names:
        job = expanded_jobs[job_name]
        logger.debug(f"Processing job '{job_name}': {job}")

        # Get the job's variables section
        job_variables = job.get("variables", {})

        # Create a copy of the simulation variables for this job
        job_simulation_variables = simulation_variables.copy()

        # Expand variables in multiple passes to handle nested references
        # First pass: expand using global variables
        expanded_job_variables = expand_variables(job_variables, job_simulation_variables)
        # Create a temporary variables dictionary that includes both global and job variables
        temp_variables = job_simulation_variables.copy()
        temp_variables.update(expanded_job_variables)
        # Second pass: expand again using the combined variables
        expanded_job_variables = expand_variables(job_variables, temp_variables)
        # Update the temporary variables with the new expanded values
        temp_variables = job_simulation_variables.copy()
        temp_variables.update(expanded_job_variables)
        # Third pass: expand once more to handle deeper nesting (e.g., $VAR2 in $VAR3)
        expanded_job_variables = expand_variables(job_variables, temp_variables)

        # Create a copy of the job with the fully expanded variables
        job_with_expanded_variables = job.copy()
        job_with_expanded_variables["variables"] = expanded_job_variables

        # Update the job's simulation variables with the fully expanded job variables
        job_simulation_variables = simulation_variables.copy()
        job_simulation_variables.update(expanded_job_variables)

        # Evaluate job-level rules if they exist.
        job_rules = job.get("rules")
        if job_rules:
            # Use the job's expanded variables when evaluating the job's rules
            # First, ensure job variables are properly expanded for rule evaluation
            job_simulation_variables_for_rules = job_simulation_variables.copy()
            job_simulation_variables_for_rules.update(expanded_job_variables)

            should_run, triggered_rule, job_vars, triggered_condition = evaluate_rules(job_rules, job_simulation_variables_for_rules)

            logger.debug(f"Job '{job_name}' rules evaluation: should_run={should_run}, triggered_condition={triggered_condition}, variables={job_vars}")
            if not should_run:
                logger.debug(f"Job '{job_name}' will be skipped based on its rules.")
                continue
            # Merge job-specific variables into the simulation variables.
            job_simulation_variables.update(job_vars)

        # Expand all variables in the job definition.
        expanded_job = expand_variables(job_with_expanded_variables, job_simulation_variables)
        simulation_jobs[job_name] = expanded_job
        logger.debug(f"Final expanded job '{job_name}': {expanded_job}")

        # We don't update the global simulation variables with job-specific variables
        # to maintain proper variable scoping between jobs

    # Create a list of job names that will run (excluding template jobs that start with a dot)
    jobs_list = [job_name for job_name in simulation_jobs.keys() if not job_name.startswith('.')]

    # Filter out template jobs from the simulation_jobs dictionary
    real_jobs = {job_name: job for job_name, job in simulation_jobs.items() if not job_name.startswith('.')}

    # Check for needs dependencies on jobs that won't run
    running_jobs = set(jobs_list)
    dependency_errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)

    # Include all expanded jobs (including template jobs) for debugging
    # TODO rewrite this AI garbage
    all_expanded_jobs = {}
    # Process each job by properly expanding variables using both global and job-specific variables
    for job_name, job in expanded_jobs.items():
        # Get the job's variables section
        job_variables = job.get("variables", {})

        # Create a copy of the simulation variables for this job
        job_simulation_variables = simulation_variables.copy()

        # Expand variables in multiple passes to handle nested references
        # First pass: expand using global variables
        expanded_job_variables = expand_variables(job_variables, job_simulation_variables)
        # Create a temporary variables dictionary that includes both global and job variables
        temp_variables = job_simulation_variables.copy()
        temp_variables.update(expanded_job_variables)
        # Second pass: expand again using the combined variables
        expanded_job_variables = expand_variables(job_variables, temp_variables)
        # Update the temporary variables with the new expanded values
        temp_variables = job_simulation_variables.copy()
        temp_variables.update(expanded_job_variables)
        # Third pass: expand once more to handle deeper nesting
        expanded_job_variables = expand_variables(job_variables, temp_variables)

        # Merge the expanded job variables into the simulation variables for this job
        job_simulation_variables.update(expanded_job_variables)

        # Apply the full variable expansion to the job
        all_expanded_jobs[job_name] = expand_variables(job.copy(), job_simulation_variables)

    simulation_summary = {
        "workflow_run": wf_run,
        "workflow_triggered_rule": wf_rule,
        "workflow_applied_variables": wf_vars,
        "global_variables": simulation_variables,
        "jobs_list": jobs_list,
        "jobs": real_jobs,
        "dependency_errors": dependency_errors,
        "all_expanded_jobs": all_expanded_jobs  # Include all expanded jobs with variables substituted
    }

    logger.debug("Pipeline simulation complete.")
    return simulation_summary
