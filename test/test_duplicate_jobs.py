import os
import sys
import unittest
import tempfile
import yaml
from io import StringIO
from unittest.mock import patch

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.cimulator.loader import load_and_resolve
from src.cimulator.validator import detect_duplicate_jobs
from src.cimulator.cli import main

class TestDuplicateJobs(unittest.TestCase):
    def setUp(self):
        # Set up paths to test files
        self.test_dir = os.path.join(os.path.dirname(__file__), 'duplicate_jobs_test')
        self.ci_file = os.path.join(self.test_dir, '.gitlab-ci.yml')
        self.file1 = os.path.join(self.test_dir, 'file1.yml')
        self.file2 = os.path.join(self.test_dir, 'file2.yml')
        self.sim_config = os.path.join(self.test_dir, 'simulation_config.yml')

        # Create a temporary file for output
        self.output_file = tempfile.NamedTemporaryFile(delete=False)
        self.output_file.close()

    def tearDown(self):
        # Clean up the temporary output file
        if os.path.exists(self.output_file.name):
            os.unlink(self.output_file.name)

    def test_detect_duplicate_jobs(self):
        """Test that duplicate jobs are detected correctly."""
        # Load the configuration and get job sources
        config, job_sources = load_and_resolve(self.ci_file)

        # Extract jobs from the configuration
        reserved_keys = {"include", "workflow", "variables", "stages"}
        jobs = {k: v for k, v in config.items() if k not in reserved_keys and isinstance(v, dict)}

        # Check for duplicate jobs
        duplicate_warnings = detect_duplicate_jobs(jobs, job_sources)

        # Verify that we found the expected duplicates
        self.assertEqual(len(duplicate_warnings), 2)

        # Check that duplicate_job is detected
        duplicate_job_warning = next((w for w in duplicate_warnings if "duplicate_job" in w), None)
        self.assertIsNotNone(duplicate_job_warning)

        # Check that .template_job is detected
        template_job_warning = next((w for w in duplicate_warnings if ".template_job" in w), None)
        self.assertIsNotNone(template_job_warning)

    def test_validate_command_reports_duplicates(self):
        """Test that the validate command reports duplicate jobs."""
        # Capture stderr to check for warnings
        with patch('sys.stderr', new=StringIO()) as fake_stderr:
            with patch('sys.argv', ['cimulator', 'validate', self.ci_file, '--output', self.output_file.name]):
                main()

            stderr_output = fake_stderr.getvalue()

            # Check that warnings about duplicate jobs are reported
            self.assertIn("Warnings about duplicate jobs", stderr_output)
            self.assertIn("duplicate_job", stderr_output)
            self.assertIn(".template_job", stderr_output)

    def test_simulate_command_reports_duplicates(self):
        """Test that the simulate command reports duplicate jobs."""
        # Capture stderr to check for warnings
        with patch('sys.stderr', new=StringIO()) as fake_stderr:
            with patch('sys.argv', ['cimulator', 'simulate', self.ci_file, self.sim_config, 'default', '--output', self.output_file.name]):
                main()

            stderr_output = fake_stderr.getvalue()

            # Check that warnings about duplicate jobs are reported
            self.assertIn("Warnings about duplicate jobs", stderr_output)
            self.assertIn("duplicate_job", stderr_output)
            self.assertIn(".template_job", stderr_output)

if __name__ == '__main__':
    unittest.main()
