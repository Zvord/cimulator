"""
Validator module for GitLab CI configuration validation.

This module provides functions to validate GitLab CI configurations,
focusing on job dependencies and relationships.
"""

def validate_job_dependencies(all_jobs):
    """
    Validate job dependencies (extends and needs).

    Parameters:
        all_jobs (dict): Dictionary of job definitions.

    Returns:
        list: List of validation errors, empty if no errors.
    """
    errors = []

    # Check for extends dependencies (skip template jobs)
    for job_name, job in all_jobs.items():
        # Skip validation for template jobs (starting with a dot)
        if job_name.startswith('.'):
            continue

        if isinstance(job, dict) and 'extends' in job:
            extends_field = job['extends']
            if not isinstance(extends_field, list):
                extends_field = [extends_field]

            for parent_name in extends_field:
                if parent_name not in all_jobs:
                    errors.append(f"Job '{job_name}' extends non-existing job '{parent_name}'")

    # Check for needs dependencies (skip template jobs)
    for job_name, job in all_jobs.items():
        # Skip validation for template jobs (starting with a dot)
        if job_name.startswith('.'):
            continue

        if isinstance(job, dict) and 'needs' in job:
            needs_field = job['needs']
            if not isinstance(needs_field, list):
                needs_field = [needs_field]

            for needed_job in needs_field:
                # Handle both simple format (string) and complex format (dict with 'job' key)
                if isinstance(needed_job, dict):
                    if 'job' in needed_job:
                        needed_job_name = needed_job['job']
                    else:
                        # Skip if the dictionary doesn't have a 'job' key
                        continue
                else:
                    needed_job_name = needed_job

                # Consider template jobs as non-existing since they won't run
                if needed_job_name not in all_jobs or needed_job_name.startswith('.'):
                    errors.append(f"Job '{job_name}' needs non-existing job '{needed_job_name}'")

    return errors

def validate_job_needs_dependencies(simulation_jobs, running_jobs):
    """
    Validate that all jobs needed by running jobs are also running.

    Parameters:
        simulation_jobs (dict): Dictionary of expanded job definitions.
        running_jobs (set): Set of job names that will run in the pipeline.

    Returns:
        list: List of dependency errors, empty if no errors.
    """
    dependency_errors = []

    # Only check needs dependencies for jobs that will run
    for job_name in running_jobs:
        job = simulation_jobs[job_name]
        if 'needs' in job:
            needs_field = job['needs']
            if not isinstance(needs_field, list):
                needs_field = [needs_field]

            for needed_job in needs_field:
                # Handle both simple format (string) and complex format (dict with 'job' key)
                if isinstance(needed_job, dict):
                    if 'job' in needed_job:
                        needed_job_name = needed_job['job']
                    else:
                        # Skip if the dictionary doesn't have a 'job' key
                        continue
                else:
                    needed_job_name = needed_job

                if needed_job_name not in running_jobs:
                    dependency_errors.append(f"Job '{job_name}' needs job '{needed_job_name}' which will not run in this pipeline")

    return dependency_errors
