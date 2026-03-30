# PR: reconcile-projects-fix

## Title
Allow KI DB fallback for project validation; add reconciliation script and admin endpoint

## Summary
This PR fixes a frontend-visible "Project not found (404)" issue by adding a fallback check to the KI database when `projects` is missing. It also adds a reconciliation tool (script + protected admin endpoint) to detect and optionally repair mismatched rows between the application DB and the KI DB.

## Changes
- `main.py`
  - `_validate_project_exists()` now falls back to the KI DB (`keyword_input_sessions`) before raising 404.
  - New protected endpoint `POST /api/admin/reconcile-projects` (dry-run / apply) to list and optionally repair missing `user_projects` mappings and placeholder `projects` rows.
- `scripts/reconcile_projects.py`
  - New CLI script with `--apply` option to perform the same reconciliation outside the API.
- `pytests/test_admin_reconcile.py`
  - New unit test covering dry-run and apply flows (test re-auth after role promotion to ensure JWT role is fresh).

## Rationale
Some endpoints (KI/engines) read project IDs from the KI DB while other API routes strictly check the `projects` table. This mismatch caused false 404s for projects that exist only in the KI DB. The fallback reduces false negatives, and the reconciliation tooling enables operators to repair persistent inconsistencies.

## Testing
- Unit test `pytests/test_admin_reconcile.py` added and passing locally.
- Full local pytest run previously passed (2264 passed, 4 skipped). Recommend running the suite in CI.

## Deployment
- Non-destructive by default. The admin endpoint and CLI support dry-run mode. When applying to production, make a DB backup first and confirm before running with `--apply`.

## Notes for reviewer
- See `scripts/reconcile_projects.py` for the repair logic and safety checks.
- The admin endpoint requires a user with `role=='admin'`.

---

If you want, I can open the PR for you (requires a GitHub token/`gh`), or you can paste this body into the PR creation UI.