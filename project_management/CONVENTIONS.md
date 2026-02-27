# DejaView — Plan & Execution Conventions

Reference for how plans and execution logs are structured in this project.

---

## Directory Structure

```
project_management/
├── CONVENTIONS.md              ← this file
├── manual_TODOS.md             ← ad-hoc user TODOs
├── manual_prompting.md         ← prompting notes
└── done/                       ← completed plans and execution logs
    ├── PLAN.md                 ← original project plan
    ├── EXECUTION.md            ← original project execution log
    ├── FEATURE_REQUEST_PLAN_*.md
    ├── FEATURE_REQUEST_EXECUTION_*.md
    └── FEATURE_REQUEST_*.md    ← combined plan+execution for smaller features
```

---

## Plan File Structure (`FEATURE_REQUEST_PLAN_*.md`)

```markdown
# DejaView — Feature Request Plan: <Title>

## Overview
1-3 sentences: what this feature does and why it's needed.

## Problem
What's wrong today / what's missing.

## User Experience (optional)
ASCII wireframes, workflow steps, before/after comparisons.

## Solution
Numbered list of changes, organized by file or component.
Include rationale for key design decisions (e.g., "Why X over Y?").

## Files to Modify
| File | Change |
|------|--------|

## Task Log
| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | ... | ⬜ | ... |

## Verification
- How to test the changes (commands, manual steps).
```

---

## Execution Log Structure (`FEATURE_REQUEST_EXECUTION_*.md`)

```markdown
# Feature Request Execution: <Title>

## Overview
Brief summary of what was implemented.

## Task Log
| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | ... | ✅ Done | What was done, artifacts created |
```

**Status icons:**
- `⬜` — not started
- `✅ Done` — completed

**For larger features**, group tasks under stage headings:
```markdown
### Stage 1: <Name>
| # | Task | Status | Details |
### Stage 2: <Name>
| # | Task | Status | Details |
```

---

## Combined Plan+Execution (smaller features)

For features that fit in a single file, use `FEATURE_REQUEST_<NAME>.md` with both the plan
sections (Overview, Problem, Solution) and the Task Log updated with completion status.

---

## Naming Conventions

- Plan files: `FEATURE_REQUEST_PLAN_<NAME>.md`
- Execution logs: `FEATURE_REQUEST_EXECUTION_<NAME>.md`
- Combined: `FEATURE_REQUEST_<NAME>.md`
- Simplification/refactor: `FEATURE_REQUEST_SIMPLIFICATION_<N>.md`
- All completed files go in `done/`

---

## Known Issues

Track pre-existing test failures, tech debt, and unresolved bugs here so they don't surprise us
during feature work. Remove entries once resolved.

| Issue | Location | Since | Notes |
|-------|----------|-------|-------|
| *(none)* | | | |

---

## Key Principles

1. **Task Log is the single source of truth** — update status as work progresses
2. **Details column** captures what was actually done, not just what was planned
3. **Verification section** lists concrete test commands and manual checks
4. **Pre-existing failures** are noted but not counted against the feature
