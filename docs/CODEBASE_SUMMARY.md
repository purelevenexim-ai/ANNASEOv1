Project: ANNASEOv1
Date: 2026-03-31

Overview:
- Stack: Python (FastAPI) backend, React+Vite frontend, Zustand, React Query.
- Purpose: SEO strategy automation, keyword-intelligence workflows, E2E flows (spices tour).

Key frontend artifacts:
- frontend/src/App.jsx — global app, `api` client, and design tokens `T`.
- frontend/src/lib/fetchDebug.js — centralized fetch wrapper + debug logging.
- frontend/src/KeywordWorkflow.jsx — main KI workflow UI; uses `apiCall` / fetchDebug.
- frontend/src/components/Notification.jsx & store — toast UI replacing `alert()`.
- frontend/src/components/DebugPanel.jsx & store — debug mode for network/timing logs.
- frontend/dist/* — built assets (may contain stale `alert()` strings from older builds).

Key backend artifacts:
- main.py — FastAPI app and routes.
- core/, engines/, services/ — domain logic and processing engines.
- tests/ and pytests/ — test suite and E2E flows (spices tour tests present).

Recent changes & status:
- Centralized network instrumentation: `fetchDebug` used by `api` in `App.jsx`.
- `apiCall` updated to throw on non-OK responses; toasts (notification store) surface errors.
- Debug mode added and wired to capture network calls and timings.
- Theme tokens (`T`) corrected in `App.jsx` to prevent invalid inline CSS values.
- Spices E2E (`pytests/test_e2e_tour_spices.py::test_e2e_spices_ki_flow`) ran and passed: `1 passed, 22 warnings`.

Open / remaining items:
- Summarize deeper architecture (planned).
- Remove build artifacts or re-run frontend build to clear stale `dist` contents.
- Finish exhaustive migration of any non-instrumented network calls (current scan found fetch centralized in `fetchDebug`).
- UX polish for DebugPanel and finalize PRs for restructure.

How to reproduce frontend console warning locally:
1. Start backend: `uvicorn main:app --reload` (or existing dev script).
2. Start frontend dev server in `frontend/` (e.g., `npm run dev`).
3. Open browser with extensions disabled and check console for border-related parsing warnings.

Where to look next:
- `frontend/src/*` for remaining dynamic inline styles that reference `T.*`.
- `frontend/dist/*` if you want to clear legacy built code.

Contact me what you'd like done next: rebuild frontend, regenerate dist, or continue architecture summary.
