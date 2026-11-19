"""
Validator module for GitLab CI configuration validation.

This module provides functions to validate GitLab CI configurations,
focusing on job dependencies and relationships.
"""

import logging
from typing import Any, Dict, List, Set, Optional, Union
from cimulator.expression import ExpressionError
from cimulator.job_expander import expand_job, expand_pipeline_jobs, with_unknown_parents
from cimulator.matrix import MatrixInstancesDict, is_external_need
from cimulator.types import ConfigDict, JobDict, JobSourcesDict
from cimulator.workflow import check_condition, rules_list
from cimulator.loader import GLOBAL_KEYWORDS

# Get a logger for this module
logger = logging.getLogger(__name__)

# The error of a need of the status of a pipeline in a job without trigger
PIPELINE_WITHOUT_JOB = "needs a pipeline without a job, which only a trigger job can"

def external_need_error(need: dict, job: object) -> Optional[str]:
    """
    Why GitLab rejects a need of another pipeline (see is_external_need()) in
    `job`, if it does:
    - `needs:pipeline` without a job (the status of an upstream pipeline) is
      only valid in a trigger job, and a trigger job cannot need a job of
      another pipeline ("needs config uses invalid types");
    - any other need must name a job ("need job should be a string");
    - `optional` is not allowed ("need config contains unknown keys").
    """
    trigger = isinstance(job, dict) and 'trigger' in job
    has_job = isinstance(need.get('job'), str)
    if 'pipeline' in need and not has_job and 'job' not in need:
        return None if trigger else PIPELINE_WITHOUT_JOB
    if not has_job:
        return "has a need without a job name"
    if trigger:
        return "is a trigger job, which cannot need a job of another pipeline"
    if 'optional' in need:
        return "needs a job of another pipeline with optional, which GitLab does not allow"
    return None

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
            # Overriding a template (a hidden job) is the usual way to
            # customise an included one: not reported
            if job_name.startswith('.'):
                continue
            # Check if this job has duplicates entry in job_sources
            duplicate_key = f"{job_name}__duplicates"
            if duplicate_key in job_sources:
                # Get original source and duplicate sources
                original_source = job_sources[job_name]
                duplicate_sources = job_sources[duplicate_key]

                # Filter out duplicate sources that match the original source
                # This prevents false positives when a job is defined only once
                # but appears in duplicates due to how the loader processes the file
                # A file included several times, e.g. through two files that
                # both include it, is named once, in order
                unique_duplicate_sources = list(dict.fromkeys(
                    src for src in duplicate_sources if src != original_source))

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
            if job_name.startswith('.'):
                continue
            if job_name in seen_jobs:
                warning = f"Duplicate job '{job_name}' found."
                duplicate_warnings.append(warning)
            else:
                seen_jobs[job_name] = True

    logger.debug(f"Found {len(duplicate_warnings)} duplicate warnings")
    return duplicate_warnings

# Why a job that is not defined is only a warning when the configuration has
# non-local includes
NON_LOCAL = "it may come from a non-local include, which cimulator does not load"

def unknown_parent_warnings(unknown_parents: Dict[str, List[str]]) -> List[str]:
    """
    The warnings for the jobs that are extended but not defined, as returned
    by with_unknown_parents().
    """
    return [f"'{parent}', extended by {', '.join(repr(child) for child in children)}, "
            f"is not defined: {NON_LOCAL}"
            for parent, children in unknown_parents.items()]

def may_be_external(job_name: str, matrix_instances: MatrixInstancesDict) -> bool:
    """
    Whether a job that is not defined may come from a non-local include: not
    a hidden job, which never runs, nor a global keyword, which is no job,
    nor a combination of a matrix job of the configuration.
    """
    return not (job_name.startswith('.') or job_name in GLOBAL_KEYWORDS
                or is_matrix_combination(job_name, matrix_instances))

def need_is_optional(need: Any) -> bool:
    """
    Whether a need is optional: `optional: true`. GitLab rejects any other
    value than a boolean or null, see optional_error().
    """
    return isinstance(need, dict) and need.get('optional') is True

def optional_error(need: Any) -> Optional[str]:
    """
    Why the `optional` of a need is invalid, as GitLab rejects it ("need
    optional should be a boolean value"), if it is.
    """
    if isinstance(need, dict) and need.get('optional') is not None \
            and not isinstance(need['optional'], bool):
        return f"optional must be true or false, not {need['optional']!r}"
    return None

def jobs_extending_unknown_jobs(all_jobs: JobDict, unknown_parents: Dict[str, List[str]]) -> Set[str]:
    """
    The jobs that extend a job that is not defined, directly or through
    other jobs: what they get from it (e.g. trigger) is unknown.
    """
    uncertain = {child for children in unknown_parents.values() for child in children}
    changed = True
    while changed:
        changed = False
        for job_name, job in all_jobs.items():
            if job_name in uncertain or not isinstance(job, dict):
                continue
            parents = job.get("extends") or []
            # Only names: another entry (e.g. a mapping) is reported as invalid elsewhere
            if any(isinstance(parent, str) and parent in uncertain
                   for parent in (parents if isinstance(parents, list) else [parents])):
                uncertain.add(job_name)
                changed = True
    return uncertain

def is_matrix_combination(job_name: str, matrix_instances: MatrixInstancesDict) -> bool:
    """
    Whether `job_name` is a combination of a matrix job of the configuration,
    e.g. "build: [linux]" for a job "build" with a parallel:matrix. Such a
    job is defined by that matrix: a non-local include cannot add to it, as
    the configuration is merged on top of what it includes.
    """
    return any(job_name.startswith(f"{matrix_job}: [") for matrix_job in matrix_instances)

def validate_job_dependencies(all_jobs: JobDict, external_includes: bool = False,
                              warnings: Optional[List[str]] = None) -> List[str]:
    """
    Validate job dependencies (extends and needs).

    Parameters:
        all_jobs (dict): Dictionary of job definitions.
        external_includes (bool): Whether the configuration has non-local
            includes, which cimulator does not load. A job that extends or
            needs a job that is not defined is then only a warning, as that
            job may come from one of them.
        warnings (list, optional): Filled with those warnings.

    Returns:
        list: List of validation errors, empty if no errors.
    """
    errors = []
    if warnings is None:
        warnings = []

    unknown_parents: Dict[str, List[str]] = {}
    if external_includes:
        # Expanded with what is known of the jobs they extend
        all_jobs, unknown_parents = with_unknown_parents(all_jobs)
        warnings.extend(unknown_parent_warnings(unknown_parents))

    # Check for extends dependencies (skip template jobs)
    for job_name, job in all_jobs.items():
        # Skip validation for template jobs (starting with a dot)
        if job_name.startswith('.'):
            continue

        if isinstance(job, dict) and job.get('extends') is not None:
            extends_field = job['extends']
            if not isinstance(extends_field, list):
                extends_field = [extends_field]

            for parent_name in extends_field:
                # As GitLab: "unknown keys in `extends`"
                if not isinstance(parent_name, str):
                    errors.append(f"Job '{job_name}' extends {parent_name!r}, which is not a job name")
                elif parent_name not in all_jobs:
                    errors.append(f"Job '{job_name}' extends non-existing job '{parent_name}'")

    # The needs are checked on the jobs as GitLab creates them: with their
    # extends expanded and their parallel:matrix split into one job per
    # combination. A job that cannot be expanded is reported and its own
    # definition is checked instead; an invalid need is reported and dropped.
    # Template jobs are not expanded: they do not run, so they may extend
    # anything.
    jobs, matrix_instances = expand_pipeline_jobs(
        all_jobs, skip_templates=True, on_error=lambda job_name, error: errors.append(error))
    uncertain_jobs = jobs_extending_unknown_jobs(all_jobs, unknown_parents)
    # A job that is only known as a parent is not defined: needing it is
    # checked as for any other such job
    for parent_name in unknown_parents:
        jobs.pop(parent_name, None)

    # Errors name a matrix job as written, not each of its jobs, so that a
    # need missing in every combination is one error
    written_names = {instance: matrix_job
                     for matrix_job, instances in matrix_instances.items()
                     for instance in instances}

    # Check for needs dependencies (skip template jobs)
    for job_name, job in jobs.items():
        # Skip validation for template jobs (starting with a dot)
        if job_name.startswith('.'):
            continue

        if isinstance(job, dict) and job.get('needs') is not None:
            needs_field = job['needs']
            if not isinstance(needs_field, list):
                needs_field = [needs_field]

            for needed_job in needs_field:
                shown_name = written_names.get(job_name, job_name)
                # The needs of other pipelines cannot be checked offline, only
                # how they are written
                if is_external_need(needed_job):
                    error = external_need_error(needed_job, job)
                    if error == PIPELINE_WITHOUT_JOB and shown_name in uncertain_jobs:
                        # It may get trigger from the job it extends
                        warnings.append(f"Job '{shown_name}' {error}, and may get trigger from a job "
                                        f"that is not defined: {needed_job}: {NON_LOCAL}")
                    elif error:
                        errors.append(f"Job '{shown_name}' {error}: {needed_job}")
                    continue
                # As GitLab: "need job should be a string"
                if isinstance(needed_job, dict) and not isinstance(needed_job.get('job'), str):
                    errors.append(f"Job '{shown_name}' has a need without a job name: {needed_job}")
                    continue
                # Handle both simple format (string) and complex format (dict with 'job' key)
                is_optional = need_is_optional(needed_job)
                invalid_optional = optional_error(needed_job)
                if invalid_optional:
                    errors.append(f"Job '{shown_name}' needs '{needed_job.get('job')}': {invalid_optional}")
                    continue
                if isinstance(needed_job, dict):
                    needed_job_name = needed_job['job']
                else:
                    needed_job_name = needed_job

                if not isinstance(needed_job_name, str):
                    errors.append(f"Job '{shown_name}' needs non-existing job '{needed_job_name}'")
                    continue
                # Consider template jobs as non-existing since they won't run
                hidden = needed_job_name.startswith('.')
                if not hidden and (needed_job_name in jobs or needed_job_name in matrix_instances):
                    continue
                # GitLab accepts an optional need of a job that does not exist
                if is_optional:
                    continue
                if external_includes and may_be_external(needed_job_name, matrix_instances):
                    warnings.append(f"Job '{shown_name}' needs '{needed_job_name}', "
                                    f"which is not defined: {NON_LOCAL}")
                else:
                    errors.append(f"Job '{shown_name}' needs non-existing job '{needed_job_name}'")

    # The same error is found once per job that extends the same broken
    # template, or once per job of a matrix job: report it once
    warnings[:] = list(dict.fromkeys(warnings))
    return list(dict.fromkeys(errors))

def validate_rules(all_jobs: JobDict, workflow_config: Optional[ConfigDict]) -> List[str]:
    """
    Check the form of the rules and the syntax of every `rules:if`, as
    GitLab does before evaluating any rule, even after one that matches: in
    the workflow, and in every job that is not hidden, with the rules it gets
    through `extends`. GitLab does not check hidden jobs. A job whose
    `extends` cannot be resolved is left to validate_job_dependencies().

    Returns:
        list: The errors, with the job or workflow they are in.
    """
    rules_of = []
    if isinstance(workflow_config, dict):
        rules_of.append(("workflow", workflow_config.get("rules")))
    cache: JobDict = {}
    for job_name in all_jobs:
        if job_name.startswith('.'):
            continue
        try:
            job = expand_job(job_name, all_jobs, cache)
        except Exception:
            continue
        rules_of.append((f"Job '{job_name}'", job.get("rules")))

    errors = []
    for where, rules in rules_of:
        try:
            rules = rules_list(rules)
        except ValueError as e:
            errors.append(f"{where}: rules: {e}")
            continue
        # Every invalid if, not only the first one
        for rule in rules:
            # if: null is no condition
            if rule.get("if") is not None:
                try:
                    check_condition(rule["if"])
                except ValueError as e:
                    errors.append(f"{where}: rules: {e}")
    return errors

def validate_job_needs_dependencies(simulation_jobs: JobDict, running_jobs: Set[str],
                                    matrix_instances: Optional[MatrixInstancesDict] = None,
                                    defined_jobs: Optional[Set[str]] = None,
                                    external_includes: bool = False) -> List[dict]:
    """
    Validate that all jobs needed by running jobs are also running.

    Parameters:
        simulation_jobs (dict): Dictionary of expanded job definitions.
        running_jobs (set): Set of job names that will run in the pipeline.
        matrix_instances (dict, optional): Names of the jobs each parallel:matrix
            job expands to. Needing a matrix job by its own name needs every
            one of them, as in GitLab; a matrix job with none is ignored.
        defined_jobs (set, optional): The jobs of the configuration, running
            or not.
        external_includes (bool): Whether the configuration has non-local
            includes, which cimulator does not load. A needed job that is not
            in defined_jobs may then come from one of them: its error has
            'from_non_local_include' set, as it may not be one.

    Returns:
        list: List of dependency error dictionaries with 'message' and 'is_optional'
              keys, and 'from_non_local_include' for the jobs that may come from a non-local
              include. Empty list if no errors.
    """
    dependency_errors = []

    # Only check needs dependencies for jobs that will run
    for job_name in running_jobs:
        job = simulation_jobs[job_name]
        if job.get('needs') is not None:
            needs_field = job['needs']
            if not isinstance(needs_field, list):
                needs_field = [needs_field]

            for needed_job in needs_field:
                if is_external_need(needed_job):
                    continue
                # Handle both simple format (string) and complex format (dict with 'job' key)
                is_optional = False
                if isinstance(needed_job, dict):
                    if 'job' in needed_job:
                        needed_job_name = needed_job['job']
                        # Check if this is an optional need
                        is_optional = need_is_optional(needed_job)
                    else:
                        # Skip if the dictionary doesn't have a 'job' key
                        continue
                else:
                    needed_job_name = needed_job

                # A matrix job by its own name: each of its jobs is needed
                for needed_name in (matrix_instances or {}).get(needed_job_name, [needed_job_name]):
                    if needed_name in running_jobs:
                        continue
                    if (external_includes and defined_jobs is not None
                            and isinstance(needed_name, str)
                            and needed_name not in defined_jobs
                            and may_be_external(needed_name, matrix_instances or {})):
                        dependency_errors.append({
                            "message": f"Job '{job_name}' needs job '{needed_name}', "
                                       f"which is not defined: {NON_LOCAL}",
                            "is_optional": is_optional,
                            "from_non_local_include": True,
                        })
                        continue
                    # Create error dict with message and is_optional flag
                    message = f"Job '{job_name}' needs job '{needed_name}' which will not run in this pipeline"

                    dependency_errors.append(
                        {"message": message, "is_optional": is_optional}
                    )

    # The same job can be needed twice, e.g. a matrix job by its own name and
    # one of its jobs: report it once
    unique = {(e["message"], e["is_optional"]): e for e in dependency_errors}
    return list(unique.values())
