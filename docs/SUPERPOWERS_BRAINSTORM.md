Superpowers — Brainstorming Guide for ANNASEOv1
=================================================

This short guide shows how to use the Superpowers "brainstorming" skill to plan projects on this repo.

When to use
- Planning a new feature, bugfix, refactor, or integration work (e.g. P5 rule change, P9 domain filtering, publisher E2E).

How to run (agent platforms)
- Claude Code / Cursor: install the `superpowers` plugin in your agent (see repo README or the plugin marketplace).
- Gemini CLI: `gemini extensions install https://github.com/obra/superpowers`

Workflow (fast)
1. Open an agent session with the Superpowers plugin enabled.
2. Paste the contents of `docs/agent_brainstorm_prompt.txt` into the chat (fill project-specific fields).
3. Ask the agent to run the `brainstorming` skill. It will return a short spec and clarifying questions.
4. Approve the spec (or answer clarifying questions) → use `writing-plans` to break into tasks.
5. Approve plan → use `executing-plans` to implement with TDD.

What I added to this repo
- A prompt template: [docs/agent_brainstorm_prompt.txt](docs/agent_brainstorm_prompt.txt)
- A short verification script: [scripts/superpowers-verify.sh](scripts/superpowers-verify.sh)

Next steps I can do for you
- Run a sample brainstorm here (I can generate a spec from a short description).
- Create a ready-to-run `git worktree` + CI snippet to let Superpowers open a branch and run tests automatically.

If you want to run a sample brainstorm now, tell me the project/feature to plan and I will generate the spec.
