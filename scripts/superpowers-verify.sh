#!/usr/bin/env bash
echo "Superpowers verify helper"

if command -v gemini >/dev/null 2>&1; then
  echo "Detected gemini CLI; listing extensions (may require login):"
  gemini extensions list || true
fi

echo "If you use Claude/ Cursor / Codex, verify Superpowers is installed in the platform UI or plugin marketplace."
echo "See docs/agent_brainstorm_prompt.txt for the brainstorming template to paste into the agent." 
