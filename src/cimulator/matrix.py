"""
parallel:matrix support.

GitLab runs a job with `parallel: matrix:` once per combination of the matrix
variables, as a separate job named after the combination's values in the order
they are defined, e.g.:

    build:
      parallel:
        matrix:
          - PROVIDER: aws
            STACK: [app1, app2]
          - PROVIDER: gcp

runs `build: [aws, app1]`, `build: [aws, app2]` and `build: [gcp]`. Each one
has its matrix values as job variables, so its rules see them too.

`needs` can point at these jobs:
  - by the name of the matrix job (`needs: [build]`): all of its jobs,
  - with `needs:parallel:matrix`, which lists the combinations it needs,
  - with matrix expressions, `$[[ matrix.IDENTIFIER ]]`, which a matrix job
    can use in its needs to refer to the value of its own matrix variables.
"""

import copy
import itertools
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from cimulator.types import JobDict

MatrixCombination = Dict[str, str]
# Name of each matrix job -> names of the jobs it expands to
MatrixInstancesDict = Dict[str, List[str]]

# Called with a job name and an error message, instead of raising
ErrorHandler = Callable[[str, str], None]

MATRIX_EXPRESSION = re.compile(r"\$\[\[\s*matrix\.(\w+)\s*\]\]")


def matrix_combinations(matrix: Any) -> List[MatrixCombination]:
    """
    Return every combination of a `parallel:matrix` list, in GitLab's order.

    Each entry of the list is a mapping of variable names to a value or a list
    of values; an entry yields the cartesian product of its lists.
    """
    if not isinstance(matrix, list):
        raise ValueError(f"parallel:matrix must be a list, got {type(matrix).__name__}")

    combinations: List[MatrixCombination] = []
    for entry in matrix:
        if not isinstance(entry, dict) or not entry:
            raise ValueError(f"parallel:matrix entries must be non-empty mappings, got {entry!r}")
        names = list(entry.keys())
        values = [v if isinstance(v, list) else [v] for v in entry.values()]
        for value in itertools.chain.from_iterable(values):
            # GitLab rejects any other type, booleans included
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError(f"parallel:matrix values must be strings or numbers, got {value!r}")
        for combination in itertools.product(*values):
            combinations.append({name: str(value) for name, value in zip(names, combination)})
    return combinations


def matrix_job_name(job_name: str, combination: MatrixCombination) -> str:
    """Name of the job of `job_name` for one matrix combination."""
    return f"{job_name}: [{', '.join(combination.values())}]"


def expand_matrix_expressions(value: str, combination: MatrixCombination, job_name: str) -> str:
    """Replace the `$[[ matrix.IDENTIFIER ]]` expressions of a string."""

    def replace(match: "re.Match[str]") -> str:
        identifier = match.group(1)
        if identifier not in combination:
            raise ValueError(
                f"Job '{job_name}': '{identifier}' does not exist in its matrix configuration"
            )
        return combination[identifier]

    return MATRIX_EXPRESSION.sub(replace, value)


def expand_matrix_needs(needs: Any, combination: Optional[MatrixCombination], job_name: str,
                        on_error: Optional[ErrorHandler] = None) -> Any:
    """
    Resolve the matrix expressions and `needs:parallel:matrix` of a needs list
    into plain job names.

    `combination` is the matrix combination of the job that has the needs, or
    None if that job is not a matrix job. `job_name` is the name of the job as
    written, also for a matrix job, so that an error is the same for all of
    its jobs.

    An invalid need raises ValueError, unless `on_error` is given: it is then
    called with the job name and the error, and only that need is dropped.
    """
    if not isinstance(needs, list):
        needs = [needs]

    def expand(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if combination is None:
            if MATRIX_EXPRESSION.search(value):
                raise ValueError(
                    f"Job '{job_name}' uses a matrix expression in its needs but has no parallel:matrix"
                )
            return value
        return expand_matrix_expressions(value, combination, job_name)

    def expand_need(need: Any) -> List[Any]:
        if not isinstance(need, dict):
            return [expand(need)]

        need = copy.deepcopy(need)
        if "job" in need:
            need["job"] = expand(need["job"])

        parallel = need.pop("parallel", None)
        if not (isinstance(parallel, dict) and "matrix" in parallel and "job" in need):
            if parallel is not None:
                need["parallel"] = parallel
            return [need]

        matrix = parallel["matrix"]
        if isinstance(matrix, list):
            matrix = [
                {name: [expand(v) for v in vals] if isinstance(vals, list) else expand(vals)
                 for name, vals in entry.items()}
                if isinstance(entry, dict) else entry
                for entry in matrix
            ]
        try:
            needed_combinations = matrix_combinations(matrix)
        except ValueError as e:
            raise ValueError(f"Job '{job_name}' needs:parallel:matrix of '{need['job']}': {e}") from e
        return [{**need, "job": matrix_job_name(need["job"], c)} for c in needed_combinations]

    resolved: List[Any] = []
    for need in needs:
        try:
            resolved.extend(expand_need(need))
        except ValueError as e:
            if on_error is None:
                raise
            on_error(job_name, str(e))
    return resolved


def expand_matrix_jobs(jobs: JobDict, on_error: Optional[ErrorHandler] = None
                       ) -> Tuple[JobDict, MatrixInstancesDict]:
    """
    Replace every job with a `parallel:matrix` with one job per combination, and
    resolve the matrix needs of every job.

    Jobs must already have their `extends` expanded, so that a `parallel:matrix`
    inherited from a template is taken into account. Template jobs (starting
    with a dot) do not run and are left untouched.

    An invalid matrix or matrix expression raises ValueError, unless `on_error`
    is given: it is then called with the job name and the error. An invalid
    need is dropped; a job whose own matrix is invalid is kept under its own
    name, without its needs, as its jobs cannot be created.

    Returns:
        The jobs, and the names of the jobs each matrix job expands to.
    """
    expanded: JobDict = {}
    instances: MatrixInstancesDict = {}

    for job_name, job in jobs.items():
        if job_name.startswith(".") or not isinstance(job, dict):
            expanded[job_name] = job
            continue
        try:
            job_instances = _expand_matrix_job(job_name, job, on_error)
        except ValueError as e:
            if on_error is None:
                raise
            on_error(job_name, str(e))
            expanded[job_name] = {k: v for k, v in job.items() if k != "needs"}
            continue
        expanded.update(job_instances)
        if is_matrix_job(job):
            instances[job_name] = list(job_instances)

    return expanded, instances


def is_matrix_job(job: Dict[str, Any]) -> bool:
    """Whether a job has a `parallel:matrix`."""
    parallel = job.get("parallel")
    return isinstance(parallel, dict) and "matrix" in parallel


def _expand_matrix_job(job_name: str, job: Dict[str, Any],
                       on_error: Optional[ErrorHandler]) -> JobDict:
    """The jobs GitLab creates for one (non-template, expanded) job."""
    if not is_matrix_job(job):
        if "needs" in job:
            job = {**job, "needs": expand_matrix_needs(job["needs"], None, job_name, on_error)}
        return {job_name: job}

    try:
        combinations = matrix_combinations(job["parallel"]["matrix"])
    except ValueError as e:
        raise ValueError(f"Job '{job_name}': {e}") from e

    jobs: JobDict = {}
    for combination in combinations:
        name = matrix_job_name(job_name, combination)
        instance = copy.deepcopy(job)
        del instance["parallel"]
        variables = instance.get("variables") or {}
        instance["variables"] = {**variables, **combination}
        if "needs" in instance:
            instance["needs"] = expand_matrix_needs(instance["needs"], combination, job_name, on_error)
        jobs[name] = instance
    return jobs
