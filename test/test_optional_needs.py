import pytest
from cimulator.validator import validate_job_needs_dependencies

class TestOptionalNeeds:
    def test_optional_needs_warnings(self):
        """Test that optional needs are marked with [Optional] prefix in warnings."""
        # Test case: job with both optional and required needs that won't run
        simulation_jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {
                "needs": [
                    {"job": "job3", "optional": True},  # Optional need
                    {"job": "job4"}                     # Required need
                ],
                "script": "echo 'World'"
            },
            "job3": {"script": "echo 'Not running'"},
            "job4": {"script": "echo 'Not running either'"}
        }
        running_jobs = {"job1", "job2"}  # job3 and job4 are not running

        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)

        # Should have two errors, one for each missing dependency
        assert len(errors) == 2

        # Check that the optional need has the [Optional] prefix
        optional_error = next((e for e in errors if "job3" in e), None)
        assert optional_error is not None
        assert "[Optional]" in optional_error
        assert "job2" in optional_error
        assert "job3" in optional_error

        # Check that the required need does NOT have the [Optional] prefix
        required_error = next((e for e in errors if "job4" in e), None)
        assert required_error is not None
        assert "[Optional]" not in required_error
        assert "job2" in required_error
        assert "job4" in required_error

    def test_string_needs_not_affected(self):
        """Test that string needs (without optional field) are not affected."""
        simulation_jobs = {
            "job1": {"script": "echo 'Hello'"},
            "job2": {
                "needs": ["job3", "job4"],
                "script": "echo 'World'"
            },
            "job3": {"script": "echo 'Not running'"},
            "job4": {"script": "echo 'Not running either'"}
        }
        running_jobs = {"job1", "job2"}  # job3 and job4 are not running

        errors = validate_job_needs_dependencies(simulation_jobs, running_jobs)

        # Should have two errors, one for each missing dependency
        assert len(errors) == 2

        # Check that neither error has the [Optional] prefix
        for error in errors:
            assert "[Optional]" not in error
            assert "needs job" in error
            assert "which will not run" in error