"""
Validator module for GitLab CI configuration validation.

This module provides functions to validate GitLab CI configurations,
focusing on job dependencies and relationships.
"""

import logging
from typing import List, Set, Optional, Union
from cimulator.types import JobDict, JobSourcesDict

# Get a logger for this module
logger = logging.getLogger(__name__)

def detect_duplicate_jobs(all_jobs: JobDict, job_sources: Optional[JobSourcesDict] = None) -> List[str]:
    """
    Detect duplicate job names in the configuration.

    Parameters:
        all_jobs (dict): Dictionary of job definitions.
        job_sources (dict, optional): Mapping of job names to their source files.
                                     Used to provide more detailed warnings.

    Returns:
        list: List of warnings about duplicate jobs.
    """
    logger.debug(f"Detecting duplicate jobs among {len(all_jobs)} jobs")
    logger.debug(f"Job sources: {job_sources}")

    duplicate_warnings = []
    seen_jobs = {}

    # Check for duplicates by processing job sources
    if job_sources:
        # Find duplicate jobs by looking for jobs with duplicate sources
        for job_name, _ in all_jobs.items():
            # Check if this job has duplicates entry in job_sources
            duplicate_key = f"{job_name}__duplicates"
            if duplicate_key in job_sources:
                # Get original source and duplicate sources
                original_source = job_sources[job_name]
                duplicate_sources = job_sources[duplicate_key]

                # Filter out duplicate sources that match the original source
                # This prevents false positives when a job is defined only once
                # but appears in duplicates due to how the loader processes the file
                unique_duplicate_sources = [src for src in duplicate_sources if src != original_source]

                # Only report as duplicate if there are sources different from the original
                if unique_duplicate_sources:
                    logger.debug(f"Found duplicates for {job_name} via job_sources")

                    # Create warning message
                    warning = f"Duplicate job '{job_name}' found (defined in: {original_source}, also defined in: {', '.join(unique_duplicate_sources)})."
                    logger.debug(f"Adding warning: {warning}")
                    duplicate_warnings.append(warning)
    else:
        # If no job_sources available, fall back to simple duplicate detection
        for job_name in all_jobs:
            if job_name in seen_jobs:
                warning = f"Duplicate job '{job_name}' found."
                duplicate_warnings.append(warning)
            else:
                seen_jobs[job_name] = True

    logger.debug(f"Found {len(duplicate_warnings)} duplicate warnings")
    return duplicate_warnings

def validate_job_dependencies(all_jobs: JobDict) -> List[str]:
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

def validate_job_needs_dependencies(simulation_jobs: JobDict, running_jobs: Set[str]) -> List[str]:
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
                is_optional = False
                if isinstance(needed_job, dict):
                    if 'job' in needed_job:
                        needed_job_name = needed_job['job']
                        # Check if this is an optional need
                        is_optional = needed_job.get('optional', False)
                    else:
                        # Skip if the dictionary doesn't have a 'job' key
                        continue
                else:
                    needed_job_name = needed_job

                if needed_job_name not in running_jobs:
                    # Add [Optional] prefix for optional needs
                    if is_optional:
                        dependency_errors.append(f"[Optional] Job '{job_name}' needs job '{needed_job_name}' which will not run in this pipeline")
                    else:
                        dependency_errors.append(f"Job '{job_name}' needs job '{needed_job_name}' which will not run in this pipeline")

    return dependency_errors
