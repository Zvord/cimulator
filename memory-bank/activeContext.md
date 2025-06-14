# Active Context

## Current Focus
Enhanced GitLab CI `!reference` tag support with array flattening capabilities for rules that reference other rule arrays. Recently focused on validation improvements and duplicate job detection.

## Recent Changes
- **Script parsing fix**: Script lines with colons now properly parsed as strings, not dictionaries
- **Duplicate job detection**: Track job sources across included files with validation warnings
- **Advanced `!reference` tag support**: Array flattening when references resolve to lists
- **CLI output improvements**: Save validate/simulate results to files with --output option
- **Cross-file references**: Resolve references after all includes are processed
- **Configurable logging**: Added --log-level option (default: INFO)
- **Enhanced validation**: Job dependency validation with template job handling
- **Variable expansion**: Fixed nested variables and non-existing variable handling

## Active Decisions
1. **Modular architecture**: Clear component separation (Loader, Job Expander, Workflow, Variable Expander, Simulation Engine, CLI)
2. **Advanced reference support**: Sophisticated `!reference` tag handling with array flattening
3. **Comprehensive validation**: Job dependencies, duplicate detection, template job handling

## Current Considerations
1. **GitLab CI compatibility**: May need additional YAML tag support beyond `!reference`
2. **Test coverage**: Need more edge cases and real-world configuration testing
3. **Documentation**: Usage examples, configuration formats, troubleshooting guides
4. **Performance**: Optimization for large/complex configurations
5. **Feature completeness**: Assessment of remaining implementation gaps

## Next Steps
1. **Real-world testing**: Test `!reference` and duplicate detection with actual GitLab CI configs
2. **Additional YAML tags**: Identify and implement other GitLab CI-specific tags
3. **Enhanced validation**: Improve schema validation and best practices checks
4. **Performance optimization**: Handle large configurations more efficiently
5. **User experience**: Better error messages, visualization, file operation handling
6. **Test expansion**: More edge cases, logging functionality, validation scenarios
