# DejaView — Retrospective 1

**Date:** 2026-02-26
**Scope:** Multi-threaded hashing + ETA progress display session

---

## Continue Doing

- **Clear problem statements.** You consistently describe the *why* before the *what*. "Users
  don't know when to come back" is far more useful than "add a timer." This lets me propose the
  right solution rather than just implement a spec blindly.

- **Challenging my assumptions.** Your question about thread blocking ("how are they not blocking
  each other?") caught a point I glossed over. That kind of scrutiny prevents subtle bugs from
  shipping.

- **The plan/execution convention.** It works remarkably well. Having a persistent artifact trail
  means we never lose context between sessions. The task log format
  (`| # | Task | Status | Details |`) is lightweight but effective.

- **Incremental scope.** You add features in sensible increments — multithreading first, *then*
  ETA on top of it. This keeps each change reviewable and testable.

---

## Do More Of

- **Acceptance criteria up front.** Sometimes requirements emerge mid-implementation (like "in
  seconds, minutes, hours, days format" and "in proper order, for human readable format" arriving
  after I'd already written the plan). If you stated the display format expectations in the
  initial request, the first plan draft would nail it. A quick "it should look like X" sketch
  saves a round-trip.

- **Flag pre-existing failures earlier.** We have that `test_regression_wf6` `hash_only` failure
  sitting in the codebase. It's unrelated to our work, but it's noise in every test run. Tagging
  known failures (e.g., `@pytest.mark.xfail`) or fixing them between features would keep the test
  suite clean and trustworthy.

- **Batch related requests.** The multithreading + ETA were conceptually one feature ("make
  scanning faster and show how long it'll take"). If scoped together from the start, I could have
  designed them as one coherent change instead of layering ETA on top after the fact. The result
  was fine, but upfront bundling saves planning overhead.

---

## Do Less Of

- **Re-entering plan mode for small additions.** The ETA feature was a ~40-line change to one file
  plus i18n strings. Full plan mode with Explore agents, Plan agents, and a 5-phase workflow added
  significant overhead for what was essentially "add a timer to the status label." For changes
  this small, a quick confirmation ("Add ETA to the status label using `time.monotonic` — sound
  good?") would be faster than the full ceremony.

---

## Process Improvement Ideas

1. **Size-gate the planning process.** Small changes (1 file, < 50 lines, clear scope) could skip
   formal plan mode. Reserve it for multi-file or architecturally ambiguous work.

2. **Add a "known issues" section to CONVENTIONS.md.** Track pre-existing test failures and tech
   debt so they don't surprise us repeatedly. *(Done — added during this session.)*

3. **Consider a CHANGELOG.md.** The work logs capture *how* things were built, but a user-facing
   changelog captures *what changed* for release notes. You're approaching distribution-readiness,
   and this would help.
