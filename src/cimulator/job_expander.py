# src/cimulator/job_expander.py

from typing import Set, Optional
from cimulator.types import JobDict
from cimulator.loader import merge_dicts

def expand_job(job_name: str, all_jobs: JobDict, cache: Optional[JobDict] = None, visited: Optional[Set[str]] = None) -> JobDict:
    """
    Recursively expand a job definition using the "extends" mechanism.

    Parameters:
        job_name (str): The name of the job to expand.
        all_jobs (dict): A dictionary of all job definitions.
        cache (dict): A cache to store already expanded jobs.
        visited (set): A set to detect circular dependencies.

    Returns:
        dict: The expanded job definition.

    Raises:
        Exception: If a circular dependency is detected or a parent job is missing.
    """
    if cache is None:
        cache = {}
    if visited is None:
        visited = set()

    if job_name in cache:
        # Return a deep copy to avoid sharing references between jobs
        import copy
        return copy.deepcopy(cache[job_name])

    if job_name in visited:
        raise Exception(f"Circular dependency detected for job: {job_name}")

    visited.add(job_name)

    # Make a deep copy to avoid modifying the original job.
    import copy
    job_def = all_jobs[job_name]
    if not isinstance(job_def, dict):
        raise Exception(f"Job definition for '{job_name}' is not a dictionary: {type(job_def).__name__}")
    job = copy.deepcopy(job_def)

    # If there is no "extends", the job is already fully defined.
    if 'extends' not in job:
        cache[job_name] = job
        visited.remove(job_name)
        return job

    # Process the extends field (which can be a string or a list)
    extends_field = job.pop('extends')
    if not isinstance(extends_field, list):
        extends_field = [extends_field]

    # Start with an empty parent configuration.
    merged_parent: JobDict = {}
    for parent_name in extends_field:
        if parent_name not in all_jobs:
            raise Exception(f"Parent job '{parent_name}' not found for job '{job_name}'")
        # Recursively expand parent job
        parent_expanded = expand_job(parent_name, all_jobs, cache, visited)
        # Merge parent's values into the accumulating parent configuration.
        merged_parent = merge_dicts(merged_parent, copy.deepcopy(parent_expanded))

    # Merge the current job over the merged parent's values.
    merged = merge_dicts(merged_parent, job)
    cache[job_name] = merged
    visited.remove(job_name)
    return merged

def expand_all_jobs(all_jobs: JobDict) -> JobDict:
    """
    Expand all job definitions contained in all_jobs.

    Parameters:
        all_jobs (dict): A dictionary mapping job names to job definitions.

    Returns:
        dict: A dictionary of expanded job definitions.
    """
    expanded = {}
    for job_name in all_jobs:
        expanded[job_name] = expand_job(job_name, all_jobs)
    return expanded
