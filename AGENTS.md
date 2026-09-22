# Repository Agent Notes

This repo is public and contains local-first automation agents. Keep changes safe, documented, and easy to review.

## Pull Requests

PR titles must be valid conventional commit titles because this repo uses squash merge and the PR title becomes the commit message on `main`.

Use:

```text
<type>(<agent-or-area>): <Capitalized summary>
```

Examples:

```text
fix(gmail-inbox-agent): Update to support ARM Docker hosts
feat(gmail-inbox-agent): Add deterministic rules engine
docs(readme): Improve new user setup guide
chore(ci): Add reusable agent release workflow
```

Allowed types used in this repo include:

- `feat`
- `fix`
- `docs`
- `chore`
- `test`
- `build`
- `refactor`
- `perf`
- `style`

Avoid PR titles like `Update docs` or `arm docker fix`; they will become weak squash commit messages and may not drive semantic-release correctly.

## Pre-Push Independent Review Workflow (Mandatory)

Every pull request (PR) and every subsequent change pushed to a PR branch must undergo an independent review in a separate agent session (e.g. via `invoke_subagent` with an independent reviewer role) before pushing to GitHub (`origin`).

The review workflow is strictly iterative:

1. **Make Changes**: Implement code, tests, and documentation on a dedicated branch or isolated git worktree.
2. **Launch Independent Review**: Spawn an independent reviewer subagent in a separate conversation session to review the git diff against `main` (or the target branch).
   - The reviewer evaluates:
     - Functional correctness, bug risks, and edge cases.
     - Security and public repo safety (no credentials, tokens, private data, or runtime files).
     - Test coverage and verification.
     - Documentation updates (architecture, READMEs, etc.).
     - PR title and commit messages adhering to conventional commit specifications.
3. **Address Feedback**: The primary agent resolves all feedback, defects, and recommendations raised by the reviewer.
4. **Re-Review**: Re-run an independent review to evaluate the latest diff.
5. **Iterate Until Clean**: Repeat steps 3 and 4 until the independent review reports **zero issues**.
6. **Push & Open/Update PR**: Only once the review passes cleanly with no outstanding issues may the branch be pushed to `origin` and the PR opened or updated.


## Public Repo Safety

Never commit local secrets, OAuth tokens, Gmail credentials, runtime memory, private rules, logs, virtualenvs, or cache files.

Check ignored files before pushing when working near config/data paths:

```bash
git status --short --ignored
```

## Agent Docs

When behavior changes, update the relevant `docs/` file for that agent. For release workflow changes, update the agent release docs and any reusable workflow notes.
