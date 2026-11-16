# src/cimulator/job_expander.py

from typing import List, Set, Optional, Tuple
from cimulator.types import JobDict
from cimulator.loader import merge_dicts
from cimulator.matrix import ErrorHandler, MatrixInstancesDict, expand_matrix_jobs

def expand_job(job_name: str, all_jobs: JobDict, cache: Optional[JobDict] = None, visited: Optional[Set[str]] = None,
               _path: Optional[List[str]] = None) -> JobDict:
    """
    Recursively expand a job definition using the "extends" mechanism.

    Parameters:
        job_name (str): The name of the job to expand.
        all_jobs (dict): A dictionary of all job definitions.
        cache (dict): A cache to store already expanded jobs.
        visited (set): A set to detect circular dependencies.
        _path (list): Internal: the jobs being expanded, in order, to name a cycle.

    Returns:
        dict: The expanded job definition.

    Raises:
        Exception: If a circular dependency is detected or a parent job is missing.
    """
    if cache is None:
        cache = {}
    if visited is None:
        visited = set()
    if _path is None:
        _path = []

    if job_name in cache:
        # Return a deep copy to avoid sharing references between jobs
        import copy
        return copy.deepcopy(cache[job_name])

    if job_name in visited:
        raise Exception(f"Circular dependency detected: {_describe_cycle(_path, job_name)}")

    visited.add(job_name)
    _path.append(job_name)

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
        _path.pop()
        return job

    # Process the extends field (which can be a string or a list)
    extends_field = job.pop('extends')
    if not isinstance(extends_field, list):
        extends_field = [extends_field]

    # Start with an empty parent configuration.
    merged_parent: JobDict = {}
    for parent_name in extends_field:
        if parent_name not in all_jobs:
            raise Exception(f"Job '{job_name}' extends non-existing job '{parent_name}'")
        # Recursively expand parent job
        parent_expanded = expand_job(parent_name, all_jobs, cache, visited, _path)
        # Merge parent's values into the accumulating parent configuration.
        merged_parent = merge_dicts(merged_parent, copy.deepcopy(parent_expanded))

    # Merge the current job over the merged parent's values.
    merged = merge_dicts(merged_parent, job)
    cache[job_name] = merged
    visited.remove(job_name)
    _path.pop()
    return merged

def _describe_cycle(path: List[str], job_name: str) -> str:
    """
    The extends cycle that reaches `job_name` again, e.g. "a -> b -> a",
    starting from its first job in sorted order, so that the same cycle is
    described the same way whichever of its jobs is expanded first.
    """
    cycle = path[path.index(job_name):] if job_name in path else [job_name]
    start = cycle.index(min(cycle))
    cycle = cycle[start:] + cycle[:start]
    return " -> ".join(cycle + [cycle[0]])

def expand_all_jobs(all_jobs: JobDict, skip_templates: bool = False,
                    on_error: Optional[ErrorHandler] = None) -> JobDict:
    """
    Expand all job definitions contained in all_jobs.

    Parameters:
        all_jobs (dict): A dictionary mapping job names to job definitions.
        skip_templates (bool): Keep template jobs (starting with a dot) as they
            are: they do not run, so they may extend anything.
        on_error (callable, optional): Called with the job name and the error
            for a job that cannot be expanded, which is then kept as it is.
            The error names the job where the problem is, e.g. the template
            that extends a missing job, so jobs that extend the same broken
            template get the same error. Without it, the error is raised.

    Returns:
        dict: A dictionary of expanded job definitions.
    """
    expanded = {}
    cache: JobDict = {}
    for job_name, job in all_jobs.items():
        if skip_templates and (job_name.startswith('.') or not isinstance(job, dict)):
            expanded[job_name] = job
            continue
        try:
            expanded[job_name] = expand_job(job_name, all_jobs, cache)
        except Exception as e:
            if on_error is None:
                raise
            on_error(job_name, str(e))
            expanded[job_name] = job
    return expanded

def expand_pipeline_jobs(all_jobs: JobDict, skip_templates: bool = False,
                         on_error: Optional[ErrorHandler] = None
                         ) -> Tuple[JobDict, MatrixInstancesDict]:
    """
    Return the jobs as GitLab creates them: with their extends expanded and
    their parallel:matrix split into one job per combination.

    See expand_all_jobs() for the parameters and expand_matrix_jobs() for the
    return value.
    """
    return expand_matrix_jobs(expand_all_jobs(all_jobs, skip_templates, on_error), on_error)
