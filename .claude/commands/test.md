# DejaView Test Suite Runner

Run the DejaView test suite. Accepts an optional argument to select which tests to run.

## Arguments

$ARGUMENTS — optional test selector:
- (empty): run ALL tests (unit + contract + headless integration)
- `unit`: run only Python unit tests (core logic, DB, selection, similarity, etc.)
- `contract`: run only API bridge contract tests (FE/BE surface, signal connections, event payloads, return shapes)
- `integration`: run only headless API integration tests (browse, plan, execute, bin, config flows)
- `typecheck`: run only TypeScript type-checking (catches FE/BE type drift)
- `all`: run everything including TypeScript type-check
- any pytest path or `-k` filter: passed directly to pytest

## Test Architecture

The test suite has 3 layers:

1. **Unit tests** (`tests/unit/`) — 500+ tests covering core logic (hasher, scanner, executor, selection, similarity, trash, DB, export, sync). Fast, no I/O.
2. **API contract tests** (`tests/unit/test_api_bridge.py`) — 58 tests verifying the pywebview API bridge: method surface completeness, DirectConnection on all signals, event payload shapes, return type contracts.
3. **Headless integration tests** (`tests/e2e/test_e2e_headless_api.py`) — 19 tests exercising the full Browse-Plan-Execute-Bin pipeline through `DejaViewAPI`, exactly as the React frontend would drive it.
4. **TypeScript type-check** (`npm run typecheck` in `frontend/`) — Catches any mismatch between `api.ts` types and actual usage in screens/stores.

## Execution

Run from the project root. Set PATH to include Node.js for TypeScript checks.

### Commands by selector

**Unit tests:**
```bash
cd dejaview && python -m pytest tests/unit/ --no-cov -q
```

**Contract tests only:**
```bash
cd dejaview && python -m pytest tests/unit/test_api_bridge.py --no-cov -v
```

**Integration tests only:**
```bash
cd dejaview && python -m pytest tests/e2e/test_e2e_headless_api.py -m headless_e2e --no-cov -v
```

**TypeScript type-check:**
```bash
cd dejaview && cd frontend && PATH="/c/Program Files/nodejs:$PATH" npx tsc --noEmit
```

**All Python tests:**
```bash
cd dejaview && python -m pytest tests/unit/ tests/e2e/test_e2e_headless_api.py -m "not e2e or headless_e2e" --no-cov -q
```

**Everything (Python + TypeScript):**
Run both the Python tests and the TypeScript type-check.

**Custom filter (passed as $ARGUMENTS):**
```bash
cd dejaview && python -m pytest $ARGUMENTS --no-cov -v
```

## After Testing

- Report pass/fail counts and any failures
- If contract tests fail: the API bridge is out of sync — check `api.py` method signatures vs `api.ts` types
- If integration tests fail: a full pipeline flow is broken — likely a DB query or API method regression
- If typecheck fails: TypeScript types don't match usage — check `frontend/src/types/api.ts`
- If unit tests fail: core logic regression — check the specific module
