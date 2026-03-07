# DejaView — Feature Request Plan: DB Versioning & Migration System

## Overview

Introduce a structured database versioning and migration system so that upgraded app versions can detect stale databases, migrate them safely with rollback support, validate the result, and prompt users about breaking changes before proceeding.

## Problem

DejaView currently has no explicit versioning. The database schema evolves via ad-hoc column/table existence checks in `_migrate()` (db.py:198-386). There is no schema version stored anywhere — migrations are inferred from `PRAGMA table_info` and `sqlite_master` queries each time. The app version "1.0.0" only exists in `installer.iss`. This makes it impossible to:
- Detect version mismatches between app and DB
- Run structured, ordered migrations with rollback
- Prompt users about breaking changes that require a rescan
- Validate that a migration completed successfully
- Protect against running an older app on a newer DB

## Solution

### 1. App Version — Single Source of Truth

Create `dejaview/version.py`:
```python
APP_VERSION = "1.0.0"
```
Imported by `main.py` and `backend/api.py`. Referenced manually by `installer.iss` and `frontend/package.json`.

### 2. DB Schema Version — `PRAGMA user_version`

Use SQLite's built-in `PRAGMA user_version` (32-bit integer stored in the DB file header).
- Starts at `0` for all existing and new databases (SQLite default)
- Incremented to `1` as the baseline when this feature lands
- Simple linear integers (1, 2, 3, ...) — no semver for schema versions

**Why `PRAGMA user_version` over a table?**
- Survives even if all tables are dropped
- Atomic, no extra DDL needed
- Built into SQLite, zero overhead

### 3. Migration Registry

Migrations are a list of `Migration` dataclass instances in `data/db.py` (all SQL stays in one module per ownership rules):

```python
@dataclass(frozen=True)
class Migration:
    version: int                          # Target version after this runs
    description: str                      # Human-readable label
    sql: str | None = None                # Simple DDL (ALTER TABLE, etc.)
    migrate_fn: Callable | None = None    # Complex logic
    breaking: bool = False                # Requires rescan / data loss
    breaking_reason: str = ""             # i18n key explaining impact

_MIGRATIONS: list[Migration] = [
    Migration(version=1, description="Baseline schema (v1.0.0)", migrate_fn=_migrate_v1),
    # Future: Migration(version=2, ...),
]
LATEST_SCHEMA_VERSION = _MIGRATIONS[-1].version
```

**Rules:** Append only; never reorder or remove. Each version = previous + 1. Simple column additions use `sql`; complex logic uses `migrate_fn`. If both set, `sql` runs first.

### 4. Migration Execution

Replace `_migrate()` with `_run_migrations()` in `Database.open()`:

1. Read `PRAGMA user_version` → `current`
2. If `current == LATEST_SCHEMA_VERSION` → no-op
3. **Downgrade protection:** If `current > LATEST_SCHEMA_VERSION` → raise error ("DB from newer app version — please update DejaView")
4. Collect `pending = [m for m in _MIGRATIONS if m.version > current]`
5. If any pending migration has `breaking=True` → return `MigrationResult(needs_user_confirmation=True)`, do NOT apply yet
6. Otherwise, execute all pending migrations sequentially
7. Each migration: run `sql` → `migrate_fn` → `PRAGMA user_version = N` → `commit()`. On failure: `rollback()`, raise `MigrationError`

**Result dataclass:**
```python
@dataclass
class MigrationResult:
    migrated: bool
    from_version: int
    to_version: int
    breaking_migrations: list[Migration] = field(default_factory=list)
    needs_user_confirmation: bool = False
    backup_path: str = ""
    validation_errors: list[str] = field(default_factory=list)
```

### 5. Pre-Migration Backup

In `main.py` (not db.py — no disk I/O rule):
- Before `db.open()`, if DB file exists, read `PRAGMA user_version` via a temporary connection
- If version < LATEST, copy `library.db` → `library.db.v{N}.bak`
- Clean up older `.bak` files after successful migration (keep only most recent)

### 6. Breaking Change Flow

When pending migrations include `breaking=True`:
1. `db.open()` returns `MigrationResult(needs_user_confirmation=True)` without applying
2. `main.py` passes result to API bridge
3. Frontend calls `get_migration_status()` on startup
4. **MigrationGate** component renders a blocking modal showing:
   - What will change (i18n keys from `breaking_reason`)
   - Backup file location
   - "Update Database" / "Exit" buttons
5. User confirms → frontend calls `confirm_migration()` → backend runs pending migrations + validation
6. User cancels → app exits

### 7. Post-Migration Validation

After all migrations complete, `_validate_schema()` introspects the DB against an `_EXPECTED_SCHEMA` dict:
- All expected **tables** exist with all expected **columns**
- All expected **views** exist
- All expected **indexes** exist

This does NOT rely on version strings — it checks actual DB structure. Validation errors are logged as warnings and included in `MigrationResult`.

### 8. Transition from Current State

- The existing `_DDL` already creates the full schema via `CREATE TABLE IF NOT EXISTS` — it stays as-is
- The old `_migrate()` method (lines 198-386) is **removed entirely**
- Migration v1 (`_migrate_v1`) is a **no-op** — `_DDL` already produces the correct schema for new DBs, and old `_migrate()` has already been applied to all existing DBs in the field
- v1 just stamps `PRAGMA user_version = 1`

### 9. Frontend Integration

**New API methods** (`backend/api.py`):
- `get_migration_status() -> dict` — migration need, breaking changes, backup path, app version
- `confirm_migration() -> dict` — runs pending migrations, returns success + validation errors
- `get_app_version() -> str` — returns APP_VERSION

**New TypeScript types** (`frontend/src/types/api.ts`):
- `MigrationStatus`, `BreakingChange` interfaces

**New component** (`frontend/src/components/MigrationGate.tsx`):
- Wraps the app, blocks UI if migration confirmation needed

**New i18n keys** (`en.json`, `hu.json`):
- `migration.title`, `migration.description`, `migration.breaking_warning`, `migration.backup_notice`, `migration.confirm`, `migration.cancel`, `migration.success`, `migration.error`

### 10. Additional Suggestions

- **Downgrade protection:** Detect `user_version > LATEST_SCHEMA_VERSION` → show "Please update DejaView" error
- **Migration logging:** Log each step at INFO level for user-reported issue diagnostics
- **Version in Settings:** Display APP_VERSION + schema version in Settings screen
- **Backup cleanup:** Auto-remove old `.bak` files after successful migration

## Files to Modify

| File | Change |
|------|--------|
| `dejaview/version.py` | **CREATE** — `APP_VERSION = "1.0.0"` |
| `dejaview/data/db.py` | Add Migration/MigrationResult/MigrationError classes, `_MIGRATIONS` registry, `_EXPECTED_SCHEMA`, replace `_migrate()` with `_run_migrations()` + `_execute_migrations()` + `confirm_breaking_migrations()` + `_validate_schema()` |
| `dejaview/main.py` | Import version, add `_backup_database()` + `_read_user_version()`, pass migration_result to API |
| `dejaview/backend/api.py` | Add `get_migration_status()`, `confirm_migration()`, `get_app_version()` |
| `dejaview/frontend/src/types/api.ts` | Add MigrationStatus/BreakingChange types, new API methods |
| `dejaview/frontend/src/components/MigrationGate.tsx` | **CREATE** — blocking modal for breaking migrations |
| `dejaview/frontend/src/App.tsx` | Wrap routes in MigrationGate |
| `dejaview/frontend/src/i18n/en.json` | Add migration.* keys |
| `dejaview/frontend/src/i18n/hu.json` | Add migration.* keys |
| `dejaview/tests/unit/test_migrations.py` | **CREATE** — full test suite (~20 tests) |
| `dejaview/tests/unit/test_api_bridge.py` | Add new API methods to EXPECTED_METHODS |

## Task Log

### Stage 1: Core Infrastructure
| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Create `version.py` | ✅ Done | APP_VERSION constant |
| 1.2 | Add Migration/MigrationResult/MigrationError dataclasses to db.py | ✅ Done | Frozen dataclass for registry entries, result/error types |
| 1.3 | Add `_MIGRATIONS` registry and `LATEST_SCHEMA_VERSION` | ✅ Done | v1 baseline migration (no-op) |
| 1.4 | Add `_EXPECTED_SCHEMA` dict | ✅ Done | All 12 tables, views, indexes |
| 1.5 | Implement `_run_migrations()` | ✅ Done | Version check, downgrade protection, breaking detection |
| 1.6 | Implement `_execute_migrations()` | ✅ Done | Per-step commit/rollback, version stamping |
| 1.7 | Implement `confirm_breaking_migrations()` | ✅ Done | Called after user confirms breaking changes |
| 1.8 | Implement `_validate_schema()` | ✅ Done | Introspect tables/columns/views/indexes |
| 1.9 | Remove old `_migrate()` method | ✅ Done | Lines 198-386, replaced by new system |
| 1.10 | Update `Database.open()` to use new system | ✅ Done | Call `_run_migrations()`, return MigrationResult |

### Stage 2: App Startup Integration
| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Add `_read_user_version()` to main.py | ✅ Done | Quick PRAGMA read via temporary connection |
| 2.2 | Add `_backup_database()` to main.py | ✅ Done | Copy .db to .bak before migration |
| 2.3 | Update startup flow to handle MigrationResult | ✅ Done | Pass result to API, handle downgrade error |

### Stage 3: API Bridge
| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Add `get_migration_status()` to api.py | ✅ Done | Returns migration need, breaking changes, backup path |
| 3.2 | Add `confirm_migration()` to api.py | ✅ Done | Runs pending migrations, returns validation result |
| 3.3 | Add `get_app_version()` to api.py | ✅ Done | Returns APP_VERSION string |

### Stage 4: Frontend
| # | Task | Status | Details |
|---|------|--------|---------|
| 4.1 | Add TypeScript types to api.ts | ✅ Done | MigrationStatus, BreakingChange interfaces |
| 4.2 | Create MigrationGate.tsx | ✅ Done | Blocking modal component |
| 4.3 | Wrap App.tsx with MigrationGate | ✅ Done | Gate renders before main UI |
| 4.4 | Add i18n keys (EN) | ✅ Done | migration.* keys in en.json |
| 4.5 | Add i18n keys (HU) | ✅ Done | migration.* keys in hu.json |

### Stage 5: Testing
| # | Task | Status | Details |
|---|------|--------|---------|
| 5.1 | Create test_migrations.py | ✅ Done | ~20 tests: registry, execution, breaking, validation, backward compat |
| 5.2 | Update test_api_bridge.py | ✅ Done | Add new methods to EXPECTED_METHODS |
| 5.3 | Run full test suite | ✅ Done | Verify no regressions |
| 5.4 | Run TypeScript type-check | ✅ Done | `npx tsc --noEmit` |

## Verification

- **Unit tests:** `python -m pytest tests/unit/test_migrations.py -v`
- **Full test suite:** `python -m pytest tests/unit/ tests/e2e/test_e2e_headless_api.py -m "not e2e or headless_e2e" --no-cov -q`
- **TypeScript check:** `cd frontend && npx tsc --noEmit`
- **Manual — fresh install:** Delete library.db, start app → DB at LATEST version, no prompt
- **Manual — upgrade:** Existing v0 DB → auto-migrates to v1, no prompt (non-breaking)
- **Manual — breaking (future):** Add test v2 breaking migration → modal appears, confirm/cancel works
- **Manual — downgrade:** Set user_version > LATEST → error message shown
