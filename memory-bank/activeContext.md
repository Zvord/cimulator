# Active Context

## Current Focus
The current focus is on improving test coverage and enhancing the functionality of the Cimulator project. We've recently fixed two key issues: the GitLab CI `!reference` tag handling and a test failure in the CLI module.

Previously, we focused on fixing an issue with the YAML parsing functionality, specifically the tool's inability to handle the GitLab CI `!reference` tag, which is used for referencing parts of the YAML document.

## Recent Changes
- Fixed the GitLab CI `!reference` tag handling in the loader.py file by implementing a custom reference resolution mechanism
- Fixed a test failure in test_simulate_cli_with_profile by including global variables in the simulation summary
- Added a new test specifically for the `!reference` tag functionality
- Verified that all tests are now passing
- Modified the CLI module to save the output of validate and simulate commands to files instead of printing to the terminal
  - Added --output/-o option to both commands to specify the output file path
  - Updated tests to verify the new behavior
- Improved reference tag handling to resolve references after all includes are processed
  - Modified the loader.py file to delay reference resolution until after all includes are resolved
  - Updated the test_reference_tag.py file to account for the new behavior
  - Verified that references across included files are now resolved correctly
- Added configurable logging level to control debug output
  - Added a global --log-level/-l argument to the CLI
  - Centralized logging configuration in the CLI module
  - Removed duplicate logging setup in simulation_engine.py
  - Default log level is now INFO, with DEBUG available for detailed output
- Enhanced validation for job dependencies
  - Added validation for jobs that extend or need non-existing jobs in the validate command
  - Added validation for jobs that need other jobs which won't run in the pipeline in the simulate command
  - Created a new validator module with dedicated validation functions
  - Added tests for the new validation functionality
  - Fixed handling of complex "needs" format (dictionary with 'job' key) to support GitLab CI's advanced syntax
  - Fixed validation to skip template jobs (starting with a dot) since they will never run
  - Added tests for template job validation
  - Changed dependency errors to warnings in the simulate command (not hard errors)
  - Added all expanded jobs with variables substituted to the simulation output for debugging
  - Fixed variable expansion in rules to properly handle variables in conditions and rule variables
  - Fixed a bug where template jobs were incorrectly validated for dependencies
  - Improved variable expansion in job definitions to correctly handle nested variables and variable references in rule conditions
  - Fixed handling of non-existing variables to expand them to empty strings instead of causing errors
  - Added tests for non-existing variables in various contexts

## Active Decisions
1. **Documentation Structure**: Organizing the memory bank with clear separation of concerns:
   - Project brief: High-level overview
   - Product context: Why the project exists and what problems it solves
   - System patterns: Architecture and design decisions
   - Technical context: Technologies, dependencies, and constraints
   - Active context: Current focus and next steps
   - Progress: Current status and roadmap

2. **Architecture Documentation**: Documenting the modular architecture with clear component responsibilities:
   - Loader Module: For loading and resolving YAML files
   - Job Expander Module: For expanding job definitions
   - Workflow Module: For evaluating workflow rules
   - Variable Expander Module: For expanding variables
   - Configuration Module: For loading simulation configurations
   - Simulation Engine Module: For orchestrating the simulation process
   - CLI Module: For providing the command-line interface

## Current Considerations
1. **YAML Tag Support**: We've implemented support for the GitLab CI `!reference` tag and improved its handling to resolve references after all includes are processed. There may be other GitLab CI-specific YAML tags that need to be handled.

2. **Code Completeness**: The codebase appears to have implemented most of the core functionality described in the implementation plan, but further analysis is needed to determine if any features are missing.

3. **Testing Coverage**: The project has test files for various components, and we've added a new test for the `!reference` tag functionality. However, more comprehensive test coverage may be needed, especially for edge cases and real-world configurations.

4. **Documentation Needs**: While the memory bank now provides high-level documentation, more detailed documentation may be needed for:
   - Usage examples
   - Configuration file formats
   - Error handling and troubleshooting
   - Contributing guidelines

5. **Feature Completeness**: Need to assess if all planned features from the implementation plan have been implemented.

## Next Steps
1. Test the `!reference` tag implementation with real GitLab CI configuration files
2. Identify and implement support for other GitLab CI-specific YAML tags if needed
3. Enhance error handling for edge cases in YAML parsing and job expansion
4. Further improve validation against GitLab CI's schema and best practices
5. Expand test coverage, particularly for edge cases and real-world configurations
6. Optimize performance for large configurations
7. Consider implementing visualization of job dependencies and workflow
8. Add more user-friendly output messages and error handling for file operations
9. Add tests for the new logging level functionality
10. Test the new validation functionality with real-world GitLab CI configurations
