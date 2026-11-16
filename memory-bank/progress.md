# Progress

## Current Status
The Cimulator project is in a functional state with core features implemented. Based on the codebase analysis, the project has implemented the key components outlined in the implementation plan:

- File loading and include resolution
- Job expansion with the `extends` mechanism
- Workflow and rule evaluation
- Variable expansion
- Pipeline simulation
- Command-line interface

The project is structured as a Python package with a clear modular architecture and has test files for various components.

## What Works

### Core Functionality
- ✅ Loading and parsing GitLab CI YAML files
- ✅ Recursively resolving and merging included YAML files
- ✅ Expanding job definitions using the `extends` mechanism
- ✅ Evaluating workflow rules to determine if a pipeline should run
- ✅ Expanding variables in job definitions
- ✅ Simulating pipeline execution based on configuration
- ✅ CI/CD inputs: `spec:inputs` headers, `$[[ inputs.NAME ]]` interpolation (pipeline `--input` and `include:inputs`)
- ✅ `parallel:matrix`: one job per combination, named as in GitLab, with matrix needs (`needs:parallel:matrix`, `$[[ matrix.NAME ]]`) resolved

### Command-Line Interface
- ✅ `validate` command for validating GitLab CI configuration
- ✅ `simulate` command for simulating pipeline execution

### Testing
- ✅ Unit tests for key components (loader, job expander, simulation engine)

## What's Left to Build

### Documentation
- ❌ User documentation (usage examples, configuration formats)
- ❌ Developer documentation (architecture, contributing guidelines)
- ❌ API documentation

### Features
- ❌ Detailed validation reporting (beyond basic YAML validation)
- ❌ Visualization of job dependencies and workflow
- ❌ Support for more GitLab CI features (e.g., `parallel: N`, `default:` keywords applied to jobs, etc.)
- ❌ Performance optimizations for large configurations

### Testing
- ❌ More comprehensive test coverage
- ❌ Integration tests with real-world GitLab CI configurations
- ❌ Performance benchmarks

## Recent Improvements

- **`parallel:matrix`**: matrix jobs expanded after `extends` (`matrix.py`); `validate` checks needs on the jobs as GitLab creates them and reports jobs that cannot be expanded (circular or missing `extends`, unknown matrix expression) as errors instead of stopping
- **Local includes**, loaded as GitLab does (checked against GitLab's pipeline dry run):
   - Missing or invalid includes are errors, not warnings: missing file, YAML syntax, no YAML extension, empty file, `spec` header with nothing after it, not a mapping, include cycle, and the form of every include rule (in both commands, even after a rule that matched)
   - Paths are taken as written: a leading slash is allowed in include paths but not in `exists`, and `.`, `..` or `//` segments are not normalised, so they match no file; `*`/`**` wildcards; `.git` and submodules (any directory with a `.git` entry) are not part of the repository
   - `include:rules`: `if` (an expression the evaluator cannot handle is a warning, taken as not matching), `exists` with GitLab's glob syntax (fnmatch), `changes` taken as matching, `exists:project` and `exists:regexp` taken as matching with a warning
   - In `simulate`, include rules and variables in include paths use the profile variables (not the configuration's `variables`, as in GitLab). `validate`, without a profile, evaluates only rules without variables, and skips an include that depends on them when its file is missing
   - Profiles must be a mapping of scalar values, read as written (text, not retyped by YAML; null and `<<` merges kept)
- **CI/CD inputs**: `spec:inputs` header parsed (`inputs.py`), inputs validated (type/options/regex) and interpolated; `--input KEY=VALUE` CLI option
- **Script parsing bug fix**: Script lines with colons now parsed as strings, not dictionaries
- **Duplicate job detection**: Track job sources across files with validation warnings
- **Advanced `!reference` support**: Array flattening, cross-file references, complex scenarios
- **CLI improvements**: File output with --output option, configurable logging levels
- **Enhanced validation**: Job dependencies, template job handling, variable expansion fixes

## Known Issues

1. **Limited error handling**: Edge cases in YAML parsing and job expansion
2. **Incomplete GitLab CI support**: Missing some advanced features
3. **Limited validation**: Need more schema and best practices validation
4. **Performance**: Large configurations may have performance issues
5. **Condition evaluator** (`workflow.py`): variable values are pasted into a Python expression, so values with quotes or backslashes are misread; `null`, regex flags, regexes held in variables and undefined variables in regexes are not supported (such job rules are taken as not matching, include rules too with a warning)

## Next Development Priorities

1. **Documentation**: Comprehensive user and developer guides
2. **Enhanced validation**: Schema validation, best practices, duplicate job details
3. **Test coverage**: Edge cases and real-world configurations
4. **Performance optimization**: Large configuration handling
5. **Visualization**: Job dependencies and workflow diagrams
