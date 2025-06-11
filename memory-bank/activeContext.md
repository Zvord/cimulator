# Active Context

## Current Focus
The current focus is on enhancing the GitLab CI `!reference` tag support with advanced array flattening capabilities. We've recently implemented sophisticated reference resolution that properly handles array flattening when references are used within lists, which is critical for GitLab CI rules that reference other rule arrays.

Previously, we focused on enhancing validation capabilities, implementing detection of duplicate jobs in included files, and improving test coverage for GitLab CI features.

## Recent Changes
- Fixed a bug where script lines containing colons were parsed as dictionaries instead of strings
  - Added a post-processing step in the `load_yaml` function to ensure all script items are strings
  - Created a new `ensure_script_items_are_strings` function that recursively processes the loaded YAML
  - Added a test case in `test_script_items_as_strings.py` to verify the fix
  - Ensured the fix doesn't break existing functionality for variable expansion in script commands
- Implemented detection of duplicate jobs in included files
  - Modified loader.py to track job sources (which file each job comes from)
  - Added a new function `detect_duplicate_jobs()` in validator.py to identify duplicate job definitions
  - Updated CLI to display warnings about duplicate jobs
  - Added tests for the new duplicate job detection functionality
- Enhanced the GitLab CI `!reference` tag handling with sophisticated array flattening capabilities
  - Implemented advanced reference resolution that properly handles array flattening when references are used within lists
  - Modified the `resolve_references` function in loader.py to detect when a ReferenceTag resolves to a list and flatten it into the parent array
  - Added comprehensive test coverage for array flattening scenarios in rules sections
  - Added test for file list templates with YAML anchors and references in rules changes section
  - Fixed edge cases where references to arrays within other arrays were not properly flattened
- Fixed a test failure in test_simulate_cli_with_profile by including global variables in the simulation summary
- Enhanced test coverage for the `!reference` tag functionality with multiple test scenarios
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
1. **Advanced Reference Tag Support**: We've implemented sophisticated support for the GitLab CI `!reference` tag with array flattening capabilities. The system now properly handles:
   - References that resolve to arrays and flatten them into parent lists
   - Complex scenarios like file list templates with YAML anchors referenced in rules changes sections
   - Edge cases where references appear in the middle of arrays and need to be flattened seamlessly
   - References across included files resolved after all includes are processed
   There may be other GitLab CI-specific YAML tags that need similar advanced handling.

2. **Duplicate Job Detection**: We've implemented detection of duplicate jobs in included files, which helps users identify potential issues in their GitLab CI configurations. This is particularly useful for large projects with many included files.

2. **Code Completeness**: The codebase appears to have implemented most of the core functionality described in the implementation plan, but further analysis is needed to determine if any features are missing.

3. **Testing Coverage**: The project has comprehensive test files for various components, and we've significantly enhanced test coverage for the `!reference` tag functionality with multiple test scenarios including:
   - Basic reference resolution in rules sections
   - Array flattening when references resolve to lists
   - File list templates with YAML anchors used in rules changes sections
   - Complex scenarios with references in the middle of arrays
   However, more comprehensive test coverage may still be needed for edge cases and real-world configurations.

4. **Documentation Needs**: While the memory bank now provides high-level documentation, more detailed documentation may be needed for:
   - Usage examples
   - Configuration file formats
   - Error handling and troubleshooting
   - Contributing guidelines

5. **Feature Completeness**: Need to assess if all planned features from the implementation plan have been implemented.

## Next Steps
1. Test the enhanced `!reference` tag implementation with array flattening in real GitLab CI configuration files
2. Verify the file list template functionality works correctly with complex GitLab CI configurations
3. Test the duplicate job detection with real GitLab CI configuration files
4. Consider adding more detailed information about duplicate jobs, such as how they differ
5. Identify and implement support for other GitLab CI-specific YAML tags that might need similar advanced handling
6. Enhance error handling for edge cases in YAML parsing and job expansion, particularly for reference resolution
7. Further improve validation against GitLab CI's schema and best practices
5. Expand test coverage, particularly for edge cases and real-world configurations
6. Optimize performance for large configurations
7. Consider implementing visualization of job dependencies and workflow
8. Add more user-friendly output messages and error handling for file operations
9. Add tests for the new logging level functionality
10. Test the new validation functionality with real-world GitLab CI configurations
