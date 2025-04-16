# Cimulator

A tool to validate and simulate GitLab CI pipelines without running them.

## Overview

Cimulator is a Python tool designed to validate and simulate GitLab CI pipelines. It addresses the challenge of testing and validating complex CI/CD configurations without having to commit changes to a repository and wait for actual pipeline runs.

### Features

- **Configuration Validation**: Validates GitLab CI YAML files for syntax and structural errors
- **Include Resolution**: Recursively processes all included YAML files
- **Job Expansion**: Properly expands jobs according to the `extends` mechanism
- **Rule Evaluation**: Evaluates workflow and job rules to determine which jobs would run
- **Variable Interpolation**: Simulates how variables are expanded in different contexts
- **Pipeline Simulation**: Provides a "dry run" of what a pipeline would look like

## Installation

```bash
pip install cimulator
```

Or with Poetry:

```bash
poetry add cimulator
```

## Basic Usage

```bash
# Validate a CI configuration file
cimulator validate path/to/your/.gitlab-ci.yml

# Simulate a pipeline run for the default branch
cimulator simulate path/to/your/.gitlab-ci.yml

# Simulate a pipeline run for a specific event (merge request)
cimulator simulate path/to/your/.gitlab-ci.yml --event merge_request

# Get detailed output
cimulator simulate path/to/your/.gitlab-ci.yml --verbose
```

## Example

Given a GitLab CI configuration:

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - deploy

build:
  stage: build
  script: echo "Building..."
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      when: never
    - when: always

test:
  stage: test
  script: echo "Testing..."
  needs: [build]

deploy:
  stage: deploy
  script: echo "Deploying..."
  needs: [test]
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: on_success
```

You can validate and simulate this pipeline:

```bash
cimulator simulate .gitlab-ci.yml --branch feature

# Output might show:
# Jobs that would run:
# - build
# - test
# (deploy would not run because branch is not "main")
```

## License

MIT License - see the [LICENSE](LICENSE) file for details.