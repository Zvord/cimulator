# tests/test_job_expander.py

import pytest
from cimulator.job_expander import expand_job, expand_all_jobs

def test_expand_job_no_extends():
    # Job without extends should be returned as is.
    jobs = {
        'job1': {'script': 'echo Hello', 'variables': {'A': '1'}}
    }
    expanded = expand_job('job1', jobs)
    assert expanded == {'script': 'echo Hello', 'variables': {'A': '1'}}

def test_expand_job_single_extends():
    # Child job extends a parent job.
    jobs = {
        'parent': {'script': 'echo Parent', 'variables': {'A': '1'}},
        'child': {'extends': 'parent', 'script': 'echo Child'}
    }
    expanded = expand_job('child', jobs)
    # The child's script overrides parent's script; parent's variables are merged.
    expected = {'script': 'echo Child', 'variables': {'A': '1'}}
    assert expanded == expected

def test_expand_job_multiple_extends():
    # Job extends multiple parents; order matters.
    jobs = {
        'base': {'variables': {'A': '1', 'B': '2'}},
        'override': {'variables': {'B': '20', 'C': '30'}},
        'child': {'extends': ['base', 'override'], 'script': 'echo Child'}
    }
    expanded = expand_job('child', jobs)
    # 'base' and then 'override' are merged before child overrides
    expected = {
        'variables': {'A': '1', 'B': '20', 'C': '30'},
        'script': 'echo Child'
    }
    assert expanded == expected

def test_expand_job_nested_extends():
    # Nested extends: child extends a job that itself extends another.
    jobs = {
        'grandparent': {'variables': {'A': '1'}},
        'parent': {'extends': 'grandparent', 'script': 'echo Parent'},
        'child': {'extends': 'parent', 'script': 'echo Child', 'variables': {'B': '2'}}
    }
    expanded = expand_job('child', jobs)
    expected = {
        'variables': {'A': '1', 'B': '2'},
        'script': 'echo Child'
    }
    assert expanded == expected

def test_expand_all_jobs():
    # Test expanding all jobs at once.
    jobs = {
        'parent': {'script': 'echo Parent', 'variables': {'A': '1'}},
        'child': {'extends': 'parent', 'script': 'echo Child'},
        'independent': {'script': 'echo Independent'}
    }
    expanded = expand_all_jobs(jobs)
    expected = {
        'parent': {'script': 'echo Parent', 'variables': {'A': '1'}},
        'child': {'script': 'echo Child', 'variables': {'A': '1'}},
        'independent': {'script': 'echo Independent'}
    }
    assert expanded == expected

def test_circular_dependency_detection():
    # Test that circular dependency raises an Exception.
    jobs = {
        'job1': {'extends': 'job2', 'script': 'echo Job1'},
        'job2': {'extends': 'job1', 'script': 'echo Job2'}
    }
    with pytest.raises(Exception) as excinfo:
        expand_job('job1', jobs)
    assert "Circular dependency detected" in str(excinfo.value)
