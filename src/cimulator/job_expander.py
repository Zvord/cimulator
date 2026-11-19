# src/cimulator/job_expander.py

from typing import Dict, List, Set, Optional, Tuple
from cimulator.types import JobDict
from cimulator.loader import GLOBAL_KEYWORDS, merge_dicts
from cimulator.matrix import ErrorHandler, MatrixInstancesDict, expand_matrix_jobs

# Keys of a job that GitLab reads as absent when null, e.g. a null that
# overrides an included or extended value
NULL_AS_ABSENT = ("extends", "needs", "variables", "rules")

def without_null_keys(job: JobDict) -> JobDict:
    """The job without the keys of NULL_AS_ABSENT whose value is null."""
    for key in NULL_AS_ABSENT:
        if key in job and job[key] is None:
            del job[key]
    return job

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

    # If there is no "extends" (or a null one), the job is already fully
    # defined. A null that overrides an inherited value is dropped below.
    if job.get('extends') is None:
        job = without_null_keys(job)
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
        # As GitLab: "unknown keys in `extends`"
        if not isinstance(parent_name, str):
            raise Exception(f"Job '{job_name}' extends {parent_name!r}, which is not a job name")
        if parent_name not in all_jobs:
            raise Exception(f"Job '{job_name}' extends non-existing job '{parent_name}'")
        # Recursively expand parent job
        parent_expanded = expand_job(parent_name, all_jobs, cache, visited, _path)
        # Merge parent's values into the accumulating parent configuration.
        merged_parent = merge_dicts(merged_parent, copy.deepcopy(parent_expanded))

    # Merge the current job over the merged parent's values.
    merged = without_null_keys(merge_dicts(merged_parent, job))
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

def with_unknown_parents(all_jobs: JobDict) -> Tuple[JobDict, Dict[str, List[str]]]:
    """
    The jobs, with an empty job for each job they extend that is not defined:
    one that may come from a non-local include, which cimulator does not
    load, so that the jobs can still be expanded with what is known of them.
    A global keyword (`default`, `stages`, ...) is not one: no include makes
    it a job, so extending it stays an error.

    Returns:
        tuple: (jobs, unknown_parents)
            - jobs: all_jobs with an empty job for each unknown parent.
            - unknown_parents: the jobs that extend each unknown parent.
    """
    unknown_parents: Dict[str, List[str]] = {}
    for job_name, job in all_jobs.items():
        if not isinstance(job, dict):
            continue
        parents = job.get("extends", [])
        for parent_name in parents if isinstance(parents, list) else [parents]:
            if isinstance(parent_name, str) and parent_name not in all_jobs \
                    and parent_name not in GLOBAL_KEYWORDS:
                unknown_parents.setdefault(parent_name, []).append(job_name)
    if not unknown_parents:
        return all_jobs, unknown_parents
    return {**all_jobs, **{name: {} for name in unknown_parents}}, unknown_parents

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
