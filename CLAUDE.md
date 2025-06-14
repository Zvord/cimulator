# Memory Bank System

Memory resets between sessions. Must read ALL memory bank files at start of every task.

## File Structure
```
memory-bank/
├── projectbrief.md      # Project foundation
├── productContext.md    # Purpose and goals  
├── systemPatterns.md    # Architecture
├── techContext.md       # Technologies
├── activeContext.md     # Current focus
└── progress.md          # Status and roadmap
```

## Workflow
1. **Start**: Read memory bank files
2. **Plan**: Develop strategy based on context
3. **Execute**: Complete task and update documentation

## Update Triggers
- After significant changes
- When user requests "**update memory bank**"
- When discovering new patterns
- When context needs clarification

## Project Tools
- **Poetry**: Dependency management (`poetry install`, `poetry run`)
- **pytest**: Testing framework (`poetry run pytest`)
