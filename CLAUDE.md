@AGENTS.md

## Claude Code specifics
- Use plan mode for multi-file tasks.
- Never start the next CRISP-DM step on your own: finish the current task and suggest what is next.
- Project skills (added later) live in `.claude/skills/`; use them whenever a task matches their description.
- After each completed task, suggest a commit message: `[phase] <component>: <summary>`.