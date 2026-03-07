# DejaView v1.1.0 — Release Notes

**Release Date:** March 7, 2026

---

## New Features

- **Sharing detection UX** — Improved user experience for detecting shared/duplicate images across directories
- **Help function** — Added in-app help for user guidance
- **JSON compression** — Scan data is now compressed, reducing storage and improving build efficiency
- **Advanced planning** — Enhanced plan review with more sophisticated duplicate resolution strategies
- **DB migration system** — Introduced database versioning (`PRAGMA user_version`) with automatic migration on upgrade (v1.0.2 schema)

## Improvements

- **Similarity view performance** — Significant speed improvement when browsing similar image groups
- **Similarity selection** — Better UX for selecting and acting on similar images
- **Duplicate handling UX** — Refined workflow for reviewing and resolving duplicates
- **Results browsing** — Fixed and improved thumbnail browsing in results view
- **Performance monitoring** — Fixed and enhanced performance tracking
- **Codebase cleanup** — General housekeeping and removal of unused executables
- **SonarQube remediation** — Fixed all critical and blocker findings from static analysis

## Bug Fixes

- Fixed progress indicator reliability (multiple iterations)
- Fixed app data directory reference
- Fixed various UI issues in the results and thumbnail views

## Infrastructure

- **React + pywebview foundation** — Scaffolded the v2.0 frontend architecture (Vite + React 19 + TypeScript + Tailwind CSS 4) with pywebview backend integration
- **Application hardening** — Improved error handling and resilience

---

*Version bump: 1.0.0 → 1.1.0 (new features + bug fixes = minor version increment per semver)*
