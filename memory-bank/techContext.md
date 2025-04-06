# Technical Context

## Technologies Used

### Core Technologies
- **Python**: The primary programming language (version 3.10+)
- **YAML**: The format used for GitLab CI configuration files
- **Poetry**: Dependency management and packaging

### Key Libraries
- **PyYAML (6.0.2)**: For parsing and manipulating YAML files
- **argparse** (standard library): For command-line argument parsing
- **re** (standard library): For regular expression operations, particularly in condition evaluation
- **logging** (standard library): For structured logging throughout the application
- **os** (standard library): For file path operations

### Testing
- **pytest (8.3.5)**: For unit and integration testing

## Development Setup

### Environment Setup
1. **Python Environment**: Requires Python 3.10 or higher
2. **Poetry**: Used for dependency management
   - Install dependencies: `poetry install`
   - Run the application: `poetry run cimulator [command]`
   - Run tests: `poetry run pytest`

### Project Structure
```
cimulator/
├── pyproject.toml       # Project metadata and dependencies
├── poetry.lock          # Locked dependencies
├── src/
│   └── cimulator/       # Main package
│       ├── __init__.py
│       ├── cli.py           # Command-line interface
│       ├── config.py        # Configuration loading
│       ├── job_expander.py  # Job expansion logic
│       ├── loader.py        # YAML loading and include resolution
│       ├── simulation_engine.py  # Core simulation logic
│       ├── variable_expander.py  # Variable expansion
│       └── workflow.py      # Workflow and rule evaluation
└── test/                # Test directory
    ├── __init__.py
    ├── test_cli.py
    ├── test_job_expander.py
    ├── test_loader.py
    ├── test_simulation_engine.py
    └── test_workflow_complex.py
```

## Technical Constraints

### GitLab CI Compatibility
- Must accurately simulate GitLab CI's behavior for:
  - Include resolution
  - Job expansion via `extends`
  - Workflow and rule evaluation
  - Variable expansion

### Performance Considerations
- Should handle large and complex GitLab CI configurations efficiently
- Recursive operations (include resolution, job expansion) must be optimized to avoid stack overflow

### Error Handling
- Must provide clear, actionable error messages for:
  - YAML syntax errors
  - Circular dependencies in job extends
  - Missing include files
  - Invalid rule conditions

## Dependencies

### Direct Dependencies
- **Python (^3.10)**: Core runtime
- **PyYAML (6.0.2)**: YAML parsing and manipulation
- **iniconfig (2.1.0)**: Configuration file parsing
- **packaging (24.2)**: Utilities for version handling
- **pluggy (1.5.0)**: Plugin system (likely a dependency of pytest)
- **setuptools (78.1.0)**: Package installation utilities

### Development Dependencies
- **pytest (^8.3.5)**: Testing framework

## Build and Distribution

### Package Configuration
- **Name**: cimulator
- **Version**: 0.1.0
- **Entry Point**: cimulator.cli:main

### Installation
- Can be installed via Poetry: `poetry install`
- Provides a command-line executable: `cimulator`

## Future Technical Considerations

### Potential Enhancements
1. **Parallel Processing**: For faster handling of large configurations
2. **Caching**: To avoid re-processing unchanged includes
3. **Visualization**: Graphical representation of job dependencies and workflow
4. **IDE Integration**: Plugins for popular IDEs to validate GitLab CI files in-editor
5. **GitLab API Integration**: To pull configuration directly from GitLab repositories
