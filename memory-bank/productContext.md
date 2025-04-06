# Product Context

## Purpose
Cimulator is a Python tool designed to validate and simulate GitLab CI pipelines. It addresses the challenge of testing and validating complex CI/CD configurations without having to commit changes to a repository and wait for actual pipeline runs.

## Problems Solved
1. **Configuration Validation**: Validates GitLab CI YAML files for syntax and structural errors before committing them.
2. **Include Resolution**: Recursively processes all included YAML files, simulating GitLab's include mechanism.
3. **Job Expansion**: Properly expands jobs according to the `extends` mechanism, following GitLab's dictionary merge and array overwrite rules.
4. **Rule Evaluation**: Evaluates workflow and job rules to determine which jobs would run under specific conditions.
5. **Variable Interpolation**: Simulates how variables are expanded in different contexts (e.g., merge request vs. schedule).
6. **Pipeline Simulation**: Provides a "dry run" of what a pipeline would look like without actually running it.

## User Experience Goals
1. **Simplicity**: Provide a straightforward command-line interface for validating and simulating GitLab CI configurations.
2. **Accuracy**: Accurately simulate GitLab CI's behavior, including all edge cases and complex features.
3. **Feedback**: Provide clear, actionable feedback about configuration issues and simulation results.
4. **Efficiency**: Enable rapid iteration on CI/CD configurations without requiring actual pipeline runs.

## Target Users
1. **DevOps Engineers**: Professionals responsible for maintaining and improving CI/CD pipelines.
2. **Software Developers**: Team members who need to modify CI/CD configurations for their projects.
3. **CI/CD Administrators**: People who oversee CI/CD infrastructure and want to validate changes before implementation.

## Use Cases
1. **Configuration Testing**: Validate changes to CI configuration before committing them.
2. **Pipeline Debugging**: Troubleshoot why certain jobs are or aren't running in specific contexts.
3. **CI Optimization**: Test optimizations to CI pipelines without waiting for actual runs.
4. **Education**: Learn how GitLab CI works by simulating different configurations and scenarios.
