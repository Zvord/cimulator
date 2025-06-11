# System Patterns

## Architecture Overview

Cimulator follows a modular architecture with clear separation of concerns. Each module handles a specific aspect of GitLab CI pipeline simulation, allowing for independent development, testing, and maintenance.

```mermaid
flowchart TD
    CLI[CLI Module] --> Loader[Loader Module]
    CLI --> Config[Configuration Module]
    CLI --> SimEngine[Simulation Engine]
    CLI --> Validator[Validator Module]

    Loader --> JobExpander[Job Expander]

    SimEngine --> JobExpander
    SimEngine --> Workflow[Workflow Evaluator]
    SimEngine --> VarExpander[Variable Expander]
    SimEngine --> Validator

    Config --> SimEngine
```

## Core Components

### 1. Loader Module
- **Responsibility**: Loads and parses GitLab CI YAML files, resolving includes recursively, and handling advanced GitLab CI features like `!reference` tags with array flattening.
- **Key Functions**:
  - `load_yaml()`: Loads a YAML file into a dictionary using a custom GitLab CI YAML loader.
  - `merge_dicts()`: Recursively merges dictionaries.
  - `resolve_includes()`: Resolves and merges included YAML files.
  - `resolve_references()`: Recursively resolves `!reference` tags with sophisticated array flattening capabilities.
  - `load_and_resolve()`: Main entry point that loads the root file, resolves all includes, and processes references.
  - `ensure_script_items_are_strings()`: Post-processes YAML to ensure script items are always strings.
- **Design Pattern**: Composite pattern for handling nested includes, Visitor pattern for reference resolution.

### 2. Job Expander Module
- **Responsibility**: Expands job definitions using the "extends" mechanism.
- **Key Functions**:
  - `expand_job()`: Recursively expands a job definition.
  - `expand_all_jobs()`: Expands all job definitions in a configuration.
- **Design Pattern**: Decorator pattern for building up job definitions.

### 3. Workflow Module
- **Responsibility**: Evaluates workflow rules to determine if a pipeline should run.
- **Key Functions**:
  - `evaluate_condition()`: Evaluates a condition string against variables.
  - `evaluate_rules()`: Evaluates a list of rules to determine if a job should run.
  - `evaluate_workflow()`: Evaluates the workflow configuration.
- **Design Pattern**: Strategy pattern for rule evaluation.

### 4. Variable Expander Module
- **Responsibility**: Expands variables in strings, dictionaries, and lists.
- **Key Functions**:
  - `expand_variables_in_string()`: Replaces variable placeholders in a string.
  - `expand_variables()`: Recursively expands variables in an object.
- **Design Pattern**: Visitor pattern for traversing and transforming data structures.

### 5. Configuration Module
- **Responsibility**: Loads simulation configuration files.
- **Key Functions**:
  - `load_simulation_config()`: Loads a simulation configuration YAML file.
- **Design Pattern**: Simple factory for configuration objects.

### 6. Simulation Engine Module
- **Responsibility**: Orchestrates the simulation process.
- **Key Functions**:
  - `simulate_pipeline()`: Simulates a pipeline by processing jobs, evaluating workflow rules, and expanding variables.
- **Design Pattern**: Facade pattern providing a simplified interface to the complex subsystems.

### 7. Validator Module
- **Responsibility**: Validates job dependencies, relationships, and configuration issues.
- **Key Functions**:
  - `validate_job_dependencies()`: Validates that all referenced jobs exist.
  - `validate_job_needs_dependencies()`: Validates that all needed jobs will run in the pipeline.
  - `detect_duplicate_jobs()`: Detects duplicate job definitions across included files.
- **Design Pattern**: Visitor pattern for traversing and validating job relationships.

### 8. CLI Module
- **Responsibility**: Provides the command-line interface.
- **Key Functions**:
  - `main()`: Entry point for the CLI.
  - `setup_logging()`: Configures logging for the application.
- **Design Pattern**: Command pattern for encapsulating requests as objects.

## Data Flow

1. **Input Processing**:
   - CLI receives input paths for the GitLab CI file and simulation configuration file.
   - CLI configures logging based on the specified log level.

2. **File Loading**:
   - Loader module reads the root YAML and all included files, returning a merged configuration dictionary.

3. **Validation** (for validate command):
   - Extract job definitions.
   - Validator module checks for jobs that extend or need non-existing jobs.
   - If validation errors are found, the process exits with an error code.

4. **Job Extraction & Expansion** (for simulate command):
   - Extract job definitions.
   - Expand jobs by processing extends entries with the job expander module.

5. **Workflow Processing**:
   - Parse the workflow section and evaluate it based on the configuration manager's variable values.

6. **Variable Expansion**:
   - The variable expander applies configuration-provided variable values to the expanded jobs.

7. **Simulation**:
   - The simulation engine takes the final job definitions and workflow decisions to simulate the pipeline.
   - Validator module checks for jobs that need other jobs which won't run in the pipeline.
   - If dependency errors are found, the process exits with an error code.

8. **Output**:
   - Results (validation output, simulation summary, or error messages) are printed to the console.

## Key Technical Decisions

1. **Recursive Processing**: Using recursion for handling nested includes and job extensions.
2. **Deep Dictionary Merging**: Implementing GitLab's specific rules for merging dictionaries and arrays.
3. **Advanced Reference Resolution**: Implementing sophisticated `!reference` tag handling with:
   - Custom YAML loader that recognizes GitLab CI tags
   - Array flattening when references resolve to lists
   - Delayed resolution after all includes are processed
   - Support for complex scenarios like file list templates with YAML anchors
4. **Condition Evaluation**: Converting GitLab CI condition syntax to Python-evaluable expressions.
5. **Modular Design**: Separating concerns into distinct modules for better maintainability.
6. **Logging**: Using Python's logging module for detailed debugging information with configurable verbosity.
7. **Validation**: Implementing comprehensive validation for job dependencies to catch configuration errors early.
8. **Error Handling**: Using clear, actionable error messages that explain the specific issues found.
