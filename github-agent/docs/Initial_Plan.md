# GitHub Agent Initial Plan

## Goal

Build a GitHub maintenance agent that helps evaluate and act on native GitHub security signals rather than re-implementing scanners already available to public repositories.

## Current Decision

Pause custom scanner ingestion. This repo now has GitHub-native security features enabled, including Dependabot, code scanning, and secret scanning. We should observe those tools first, then design the agent around the real alerts and pull requests they produce.

## Phase 1: Observe Native Signals

- Let Dependabot generate dependency alerts and PRs.
- Let code scanning report code-level findings.
- Let secret scanning report any credential exposure.
- Capture examples of alert shape, labels, severity, ownership, and remediation flow.
- Record which findings are already well-handled by GitHub without extra automation.

## Phase 2: Evaluate Agent Value

- Identify where human review still takes time.
- Decide whether the agent should summarize alerts, comment on PRs, approve safe changes, or create follow-up issues.
- Prefer consuming GitHub-native alerts and PRs through APIs over running duplicate scanners.
- Keep all write behavior dry-run first.

## Phase 3: Remediation Agent

- Pick up actionable native alerts or Dependabot PRs.
- Attempt bounded fixes in a branch when GitHub did not already provide a fix.
- Open pull requests with conventional commit titles.
- Never push directly to `main`.

## Open Questions

- Which native GitHub signals are noisy, and which are useful?
- Are Dependabot PRs enough for Python, Docker, and GitHub Actions updates?
- What should the agent do with code scanning alerts: summarize, create issues, or attempt fixes?
- Should secret scanning alerts ever be automated, or only surfaced for human review?
- What criteria make an automated approval safe?
