import pytest
from cimulator.validator import validate_job_dependencies, validate_job_needs_dependencies

class TestValidator:
    def test_validate_job_dependencies_extends(self):
        """Test validation of extends dependencies."""
        # Test case: job extends a non-existing job
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"extends": "non-existing-job", "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 1
        assert "extends non-existing job" in errors[0]
        assert "job2" in errors[0]
        assert "non-existing-job" in errors[0]

        # Test case: job extends an existing job
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"extends": "job1", "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 0

        # Test case: job extends multiple jobs, one of which doesn't exist
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"extends": ["job1", "non-existing-job"], "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 1
        assert "extends non-existing job" in errors[0]
        assert "job2" in errors[0]
        assert "non-existing-job" in errors[0]

    def test_validate_job_dependencies_needs(self):
        """Test validation of needs dependencies."""
        # Test case: job needs a non-existing job
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": "non-existing-job", "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 1
        assert "needs non-existing job" in errors[0]
        assert "job2" in errors[0]
        assert "non-existing-job" in errors[0]

        # Test case: job needs an existing job
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": "job1", "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 0

        # Test case: job needs multiple jobs, one of which doesn't exist
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": ["job1", "non-existing-job"], "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 1
        assert "needs non-existing job" in errors[0]
        assert "job2" in errors[0]
        assert "non-existing-job" in errors[0]

        # Test case: job needs with complex format (dict with 'job' key)
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": [{"job": "job1", "artifacts": True}, {"job": "non-existing-job", "artifacts": False}], "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 1
        assert "needs non-existing job" in errors[0]
        assert "job2" in errors[0]
        assert "non-existing-job" in errors[0]

        # Test case: job needs with complex format, all jobs exist
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"script": "echo 'Middle'"},
            "job3": {"needs": [{"job": "job1", "artifacts": True}, {"job": "job2", "artifacts": False}], "script": "echo 'World'"}
        }
        errors = validate_job_dependencies(jobs)
        assert len(errors) == 0

    def test_validate_job_needs_dependencies(self):
        """Test validation of needs dependencies for running jobs."""
        # Test case: running job needs a job that won't run
        simulation_jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": "job1", "script": "echo 'World'"},
            "job3": {"needs": "job4", "script": "echo 'Test'"},
            "job4": {"script": "echo 'Not running'"}
        }
        running_jobs = {"job1", "job2", "job3"}  # job4 is not running
        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)
        assert len(errors) == 1
        assert "needs job 'job4' which will not run" in errors[0]["message"]
        assert "job3" in errors[0]["message"]

        # Test case: all needed jobs are running
        running_jobs = {"job1", "job2", "job3", "job4"}  # all jobs are running
        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)
        assert len(errors) == 0

        # Test case: job with multiple needs, some of which won't run
        simulation_jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": ["job1", "job3"], "script": "echo 'World'"},
            "job3": {"script": "echo 'Not running'"}
        }
        running_jobs = {"job1", "job2"}  # job3 is not running
        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)
        assert len(errors) == 1
        assert "needs job 'job3' which will not run" in errors[0]["message"]
        assert "job2" in errors[0]["message"]

        # Test case: job with complex needs format, some jobs won't run
        simulation_jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"needs": [{"job": "job1", "artifacts": True}, {"job": "job3", "artifacts": False}], "script": "echo 'World'"},
            "job3": {"script": "echo 'Not running'"}
        }
        running_jobs = {"job1", "job2"}  # job3 is not running
        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)
        assert len(errors) == 1
        assert "needs job 'job3' which will not run" in errors[0]["message"]
        assert "job2" in errors[0]["message"]

        # Test case: job with complex needs format, all needed jobs are running
        simulation_jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {"script": "echo 'Middle'"},
            "job3": {"needs": [{"job": "job1", "artifacts": True}, {"job": "job2", "artifacts": False}], "script": "echo 'World'"}
        }
        running_jobs = {"job1", "job2", "job3"}  # all jobs are running
        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)
        assert len(errors) == 0

    def test_template_jobs_validation(self):
        """Test that template jobs (starting with a dot) are not validated for dependencies."""
        # Test case: template job extends a non-existing job
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            ".template_job": {"extends": "non-existing-job", "script": "echo 'Template'"}
        }
        errors = validate_job_dependencies(jobs)
        # Should not report an error for template job
        assert len(errors) == 0

        # Test case: template job needs a non-existing job
        jobs = {
            "job1": {"script": "echo 'Hello'"},
            ".template_job": {"needs": "non-existing-job", "script": "echo 'Template'"}
        }
        errors = validate_job_dependencies(jobs)
        # Should not report an error for template job
        assert len(errors) == 0

        # Test case: regular job needs a template job
        jobs = {
            ".template_job": {"script": "echo 'Template'"},
            "job1": {"needs": ".template_job", "script": "echo 'Hello'"}
        }
        errors = validate_job_dependencies(jobs)
        # Should report an error because template jobs won't run
        assert len(errors) == 1
        assert "needs non-existing job" in errors[0]
        assert "job1" in errors[0]
        assert ".template_job" in errors[0]

        # Test case: template job needs another template job
        jobs = {
            ".template_job1": {"script": "echo 'Template 1'"},
            ".template_job2": {"needs": ".template_job1", "script": "echo 'Template 2'"}
        }
        errors = validate_job_dependencies(jobs)
        # Should not report an error for template jobs
        assert len(errors) == 0