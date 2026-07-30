# Git Workflow for AI Agents

## Branch naming

```
agent/<ticket>-<short-description>
```

Every task gets its own branch. Never commit to `main` or a shared branch directly.

## Commit granularity

Commit after each passing test cycle. Each commit should contain **one logical change**:

| Good commit | What it contains |
|---|---|
| `Add data models for lesson analysis profiles` | models.py only |
| `Implement ACIM JSON source provider` | sources.py + tests |
| `Add MILP optimizer with style-spacing constraints` | optimizer.py changes |
| `Wire up CLI run-batch command` | cli.py changes only |

Avoid combining unrelated work (e.g., "Add models and fix validator bug in one commit").

## Diff size

- **Target:** ≤400 lines per commit
- Break larger work into vertical slices (e.g., model → provider → optimizer)
- If a diff exceeds 400 lines, split it

## Commit messages

```
< 72-char subject, imperative mood, no period

Body explains why, not what. Reference constraints or invariants
that drove the decision. ~75 char wrap recommended.
```

## Before committing

1. `git status` — confirm only intended files are changed
2. `git diff` — review every line for secrets, copyrighted text, or stale code
3. Run tests — `pytest` must pass
4. Run lint/typecheck if configured

## Never commit

- `outputs/` — generated artifacts, CSV exports, logs
- `__pycache__/`, `*.pyc`
- `.env`, `.env.local`, API keys
- `node_modules/`
- Copyrighted lesson text or private datasets
- Large binary files

## After commit

- Push to the same branch to update the existing PR
- Do not force-push, rebase, or amend commits on shared branches

## Reference

Based on mid-2026 industry consensus (DeployHQ, BuildMVPFast, Exceeds AI, Raine Virta): atomic commits, agent-prefixed branches, and sub-400-line diffs as a reviewability standard.
