@AGENTS.md

## Claude Code specifics
- Use plan mode for multi-file tasks.
- Never start the next CRISP-DM step on your own: finish the current task and suggest what is next.
- Project skills live in `.claude/skills/` (extracted on 2026-11-15 from how this project was actually built); use them
  whenever a task matches their description:
  - `add-component`: schema → versioned prompt → component → deterministic metrics → eval script → dev → frozen config → test once → 04/05.
  - `run-eval`: smoke → cost projection → budget guard → full run; results JSON with git commit; worst-3; frozen sets; test lock.
  - `labeling-cli`: resumable human labelling/audit tools; rubric on screen; model outputs hidden; frozen cases; labels never overwritten.
  - `llm-judge`: deterministic metrics first; binary judge with edge-case rubric in prompt and CLI; κ ≥ 0.6; repeat consistency.
  - `crisp-dm-report`: phase files, decision log, iterations noted in both phases, reporting style.
  - `apache-jira-data`: Jira REST API, Duplicate-link direction, markup cleaning and PII masking, decisions D1–D5.
  - `user-simulator`: simulated-user e2e — opener leakage check, answer rules, honesty/role checks, policies, caveats.
- After each completed task, suggest a commit message: `[phase] <component>: <summary>`.