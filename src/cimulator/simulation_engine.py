import logging
from cimulator.job_expander import expand_all_jobs
from cimulator.workflow import evaluate_workflow, evaluate_rules
from cimulator.variable_expander import expand_variables

# Set up logging for the simulation engine.
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def simulate_pipeline(all_jobs, workflow_config, global_variables):
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

    for job_name, job in expanded_jobs.items():
        logger.debug(f"Processing job '{job_name}': {job}")

        # Evaluate job-level rules if they exist.
        job_rules = job.get("rules")
        if job_rules:
            should_run, triggered_rule, job_vars, triggered_condition = evaluate_rules(job_rules, simulation_variables)
            logger.debug(f"Job '{job_name}' rules evaluation: should_run={should_run}, triggered_condition={triggered_condition}, variables={job_vars}")
            if not should_run:
                logger.debug(f"Job '{job_name}' will be skipped based on its rules.")
                continue
            # Merge job-specific variables into the simulation variables.
            simulation_variables.update(job_vars)

        # Expand variables in the job definition.
        expanded_job = expand_variables(job, simulation_variables)
        simulation_jobs[job_name] = expanded_job
        logger.debug(f"Final expanded job '{job_name}': {expanded_job}")

    simulation_summary = {
        "workflow_run": wf_run,
        "workflow_triggered_rule": wf_rule,
        "workflow_applied_variables": wf_vars,
        "global_variables": simulation_variables,
        "jobs": simulation_jobs
    }

    logger.debug("Pipeline simulation complete.")
    return simulation_summary
