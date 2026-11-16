import copy

import pytest

from cimulator.matrix import expand_matrix_jobs, matrix_combinations, matrix_job_name
from cimulator.simulation_engine import simulate_pipeline
from cimulator.validator import validate_job_dependencies


def simulate(jobs, variables=None):
    return simulate_pipeline(jobs, {}, variables or {})


class TestMatrixCombinations:
    def test_combinations_and_names(self):
        matrix = [
            {"PROVIDER": "aws", "STACK": ["app1", "app2"]},
            {"PROVIDER": "gcp"},
            {"VERSION": 3},
        ]
        names = [matrix_job_name("build", c) for c in matrix_combinations(matrix)]
        assert names == [
            "build: [aws, app1]",
            "build: [aws, app2]",
            "build: [gcp]",
            "build: [3]",
        ]

    def test_invalid_matrix(self):
        with pytest.raises(ValueError):
            matrix_combinations({"PROVIDER": "aws"})
        with pytest.raises(ValueError):
            matrix_combinations([{}])


class TestMatrixJobs:
    def test_one_job_per_combination(self):
        jobs = {
            "build": {
                "script": ["make $TARGET"],
                "variables": {"MODE": "fast", "TARGET": "overridden"},
                "parallel": {"matrix": [{"TARGET": ["a", "b"]}]},
            },
        }
        expanded, instances = expand_matrix_jobs(jobs)
        assert instances == {"build": ["build: [a]", "build: [b]"]}
        assert set(expanded) == {"build: [a]", "build: [b]"}
        assert expanded["build: [b]"]["variables"] == {"MODE": "fast", "TARGET": "b"}
        assert "parallel" not in expanded["build: [b]"]

    def test_templates_are_untouched(self):
        jobs = {".template": {"parallel": {"matrix": [{"TARGET": ["a", "b"]}]}}}
        expanded, instances = expand_matrix_jobs(jobs)
        assert expanded == jobs
        assert instances == {}

    def test_simulation_runs_each_combination_with_its_variables(self):
        jobs = {
            ".build": {"parallel": {"matrix": [{"TARGET": ["a", "b"]}]}},
            "build": {"extends": ".build", "script": ["make $TARGET"]},
        }
        summary = simulate(jobs)
        assert sorted(summary["jobs_list"]) == ["build: [a]", "build: [b]"]
        assert summary["jobs"]["build: [a]"]["script"] == ["make a"]
        assert summary["jobs"]["build: [b]"]["script"] == ["make b"]

    def test_rules_see_the_matrix_variables(self):
        jobs = {
            "build": {
                "script": ["make"],
                "rules": [{"if": '$RUN_ALL == "1"'}, {"if": '$TARGET == "a"'}],
                "parallel": {"matrix": [{"TARGET": ["a", "b"]}]},
            },
        }
        assert simulate(jobs)["jobs_list"] == ["build: [a]"]
        assert sorted(simulate(jobs, {"RUN_ALL": "1"})["jobs_list"]) == ["build: [a]", "build: [b]"]


class TestMatrixNeeds:
    jobs = {
        "build": {
            "script": ["make"],
            "rules": [{"if": '$TARGET != "c"'}],
            "parallel": {"matrix": [{"TARGET": ["a", "b", "c"]}]},
        },
    }

    def needing(self, needs, matrix=None):
        job = {"script": ["test"], "needs": needs}
        if matrix:
            job["parallel"] = {"matrix": matrix}
        # A deep copy: tests change the rules of the shared jobs
        return {**copy.deepcopy(self.jobs), "test": job}

    def errors(self, jobs):
        return [e["message"] for e in simulate(jobs)["dependency_errors"]]

    def test_needs_with_matrix_expression(self):
        jobs = self.needing(["build: [$[[ matrix.TARGET ]]]"], [{"TARGET": ["a", "b"]}])
        summary = simulate(jobs)
        assert summary["jobs"]["test: [a]"]["needs"] == ["build: [a]"]
        assert summary["dependency_errors"] == []

    def test_needs_with_matrix_expression_on_a_job_that_does_not_run(self):
        jobs = self.needing([{"job": "build: [$[[ matrix.TARGET ]]]"}], [{"TARGET": ["a", "c"]}])
        assert self.errors(jobs) == [
            "Job 'test: [c]' needs job 'build: [c]' which will not run in this pipeline"
        ]

    def test_needs_parallel_matrix(self):
        jobs = self.needing([{"job": "build", "artifacts": True,
                              "parallel": {"matrix": [{"TARGET": ["a", "b"]}]}}])
        summary = simulate(jobs)
        assert summary["jobs"]["test"]["needs"] == [
            {"job": "build: [a]", "artifacts": True},
            {"job": "build: [b]", "artifacts": True},
        ]
        assert summary["dependency_errors"] == []

    def test_needs_parallel_matrix_with_matrix_expression(self):
        jobs = self.needing([{"job": "build", "parallel": {"matrix": [{"TARGET": "$[[ matrix.T ]]"}]}}],
                            [{"T": ["b", "c"]}])
        assert self.errors(jobs) == [
            "Job 'test: [c]' needs job 'build: [c]' which will not run in this pipeline"
        ]

    def test_needs_on_the_matrix_job_name_needs_each_of_its_jobs(self):
        # As in GitLab: one job that does not run is enough to break the need
        assert self.errors(self.needing(["build"])) == [
            "Job 'test' needs job 'build: [c]' which will not run in this pipeline",
        ]

    def test_needs_on_the_matrix_job_name_when_all_of_its_jobs_run(self):
        jobs = self.needing(["build"])
        del jobs["build"]["rules"]
        assert self.errors(jobs) == []

    def test_needs_on_a_matrix_job_none_of_whose_jobs_run(self):
        jobs = self.needing(["build"])
        jobs["build"]["rules"] = [{"when": "never"}]
        assert self.errors(jobs) == [
            f"Job 'test' needs job 'build: [{t}]' which will not run in this pipeline" for t in "abc"
        ]

    def test_optional_needs_on_the_matrix_job_name(self):
        errors = simulate(self.needing([{"job": "build", "optional": True}]))["dependency_errors"]
        assert errors == [{
            "message": "Job 'test' needs job 'build: [c]' which will not run in this pipeline",
            "is_optional": True,
        }]

    def test_job_needed_twice_is_reported_once(self):
        needs = ["build", {"job": "build", "parallel": {"matrix": [{"TARGET": "c"}]}}]
        assert self.errors(self.needing(needs)) == [
            "Job 'test' needs job 'build: [c]' which will not run in this pipeline",
        ]

    def test_variables_in_matrix_values_are_not_expanded_in_needs(self):
        # GitLab names the job with the value as written, and matches needs
        # against it as written
        jobs = {
            "build": {"script": ["make"], "parallel": {"matrix": [{"IMAGE": ["$ARCH-img"]}]}},
            "test": {"script": ["test"], "needs": ["build: [$ARCH-img]"]},
        }
        result = simulate(jobs, {"ARCH": "x86"})
        assert sorted(result["jobs_list"]) == ["build: [$ARCH-img]", "test"]
        assert result["dependency_errors"] == []
        assert result["jobs"]["build: [$ARCH-img]"]["variables"]["IMAGE"] == "x86-img"

    def test_matrix_expression_of_an_unknown_variable(self):
        jobs = self.needing(["build: [$[[ matrix.NOPE ]]]"], [{"TARGET": ["a"]}])
        with pytest.raises(ValueError, match="'NOPE' does not exist in its matrix configuration"):
            simulate(jobs)

    def test_matrix_expression_outside_of_a_matrix_job(self):
        with pytest.raises(ValueError, match="has no parallel:matrix"):
            simulate(self.needing(["build: [$[[ matrix.TARGET ]]]"]))


class TestValidateMatrixNeeds:
    def test_matrix_needs_are_valid(self):
        jobs = {
            ".build": {"parallel": {"matrix": [{"TARGET": ["a", "b"]}]}},
            "build": {"extends": ".build", "script": ["make"]},
            "test": {"script": ["test"], "needs": ["build: [$[[ matrix.T ]]]", "build"],
                     "parallel": {"matrix": [{"T": ["a", "b"]}]}},
        }
        assert validate_job_dependencies(jobs) == []

    def test_matrix_needs_on_a_missing_combination(self):
        jobs = {
            "build": {"script": ["make"], "parallel": {"matrix": [{"TARGET": ["a"]}]}},
            "test": {"script": ["test"], "needs": [{"job": "build", "parallel": {"matrix": [{"TARGET": "b"}]}}]},
        }
        assert validate_job_dependencies(jobs) == ["Job 'test' needs non-existing job 'build: [b]'"]

    def test_matrix_expression_errors_do_not_stop_validation(self):
        jobs = {
            "build": {"script": ["make"], "parallel": {"matrix": [{"TARGET": ["a"]}]}},
            "test": {"script": ["test"], "parallel": {"matrix": [{"TARGET": ["a"]}]},
                     "needs": ["build: [$[[ matrix.OTHER ]]]"]},
            "lint": {"script": ["lint"], "needs": ["build: [$[[ matrix.TARGET ]]]"]},
            "deploy": {"script": ["deploy"], "needs": ["missing"]},
        }
        assert validate_job_dependencies(jobs) == [
            "Job 'test': 'OTHER' does not exist in its matrix configuration",
            "Job 'lint' uses a matrix expression in its needs but has no parallel:matrix",
            "Job 'deploy' needs non-existing job 'missing'",
        ]

    def test_invalid_need_is_dropped_and_the_others_are_checked(self):
        jobs = {
            "build": {"script": ["make"], "parallel": {"matrix": [{"TARGET": ["a", "b"]}]},
                      "needs": ["$[[ matrix.NOPE ]]", "missing"]},
            "test": {"script": ["test"], "needs": ["build: [a]"]},
        }
        assert validate_job_dependencies(jobs) == [
            "Job 'build': 'NOPE' does not exist in its matrix configuration",
            "Job 'build' needs non-existing job 'missing'",
        ]

    def test_invalid_matrix(self):
        jobs = {
            "build": {"script": ["make"], "parallel": {"matrix": {"TARGET": "a"}}},
            "test": {"script": ["test"], "parallel": {"matrix": [{"DEBUG": [True]}]}},
        }
        assert validate_job_dependencies(jobs) == [
            "Job 'build': parallel:matrix must be a list, got dict",
            "Job 'test': parallel:matrix values must be strings or numbers, got True",
        ]

    def test_need_missing_in_some_combinations_only(self):
        jobs = {
            "build": {"script": ["make"], "parallel": {"matrix": [{"TARGET": ["a"]}]}},
            "test": {"script": ["test"], "parallel": {"matrix": [{"TARGET": ["a", "b", "c"]}]},
                     "needs": ["build: [$[[ matrix.TARGET ]]]"]},
        }
        assert validate_job_dependencies(jobs) == [
            "Job 'test' needs non-existing job 'build: [b]'",
            "Job 'test' needs non-existing job 'build: [c]'",
        ]


class TestMatrixValues:
    def test_numbers_are_accepted(self):
        assert matrix_combinations([{"N": [1, 2.5]}]) == [{"N": "1"}, {"N": "2.5"}]

    @pytest.mark.parametrize("value", [True, None, {"a": 1}])
    def test_other_types_are_rejected(self, value):
        with pytest.raises(ValueError, match="must be strings or numbers"):
            matrix_combinations([{"V": [value]}])


class TestEmptyMatrix:
    """GitLab creates no job for an empty matrix, and ignores the needs on it."""

    JOBS = {
        "build": {"script": ["make"], "parallel": {"matrix": [{"STACK": []}]}},
        "test": {"script": ["test"], "needs": ["build"]},
    }

    def test_simulate(self):
        result = simulate(self.JOBS)
        assert result["jobs_list"] == ["test"]
        assert result["dependency_errors"] == []

    def test_validate(self):
        assert validate_job_dependencies(self.JOBS) == []
