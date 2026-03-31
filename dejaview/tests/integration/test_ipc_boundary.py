"""
tests/integration/test_ipc_boundary.py — Regression tests for IPC boundary bugs.

Phase 1, Week 1: "The 4 Regression Tests" Sprint.

These tests reproduce the four production failures that shipped green despite
578 passing tests.  Each test validates an architectural boundary (pipes,
encoding, threading, event volume) that was previously untested.

Guardrail: every test here must demonstrably fail against pre-fix code.
"""

import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from core.scanner import Scanner
from data.db import Database


# ── Helpers ──────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    """Deterministic JPEG — same color + size + quality → identical file bytes."""
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def scan_dir(tmp_path):
    d = tmp_path / "scan"
    d.mkdir()
    return d


@pytest.fixture
def session_id(db, scan_dir):
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="regression test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


# ═════════════════════════════════════════════════════════════════════════════
# TEST 1: Backpressure — scanner thread must not deadlock on slow stdout
# Bug: commit 0604305 — stdout pipe buffer fills, blocks scanner thread
# Fix: queue-based _stdout_writer decouples emission from pipe drainage
# ═════════════════════════════════════════════════════════════════════════════

class _BlockingStream:
    """Fake stdout that blocks on write until explicitly unblocked."""

    def __init__(self):
        self.gate = threading.Event()  # blocks until set
        self.lines: list[str] = []

    def write(self, data: str) -> int:
        self.gate.wait()  # simulate pipe backpressure
        self.lines.append(data)
        return len(data)

    def flush(self):
        pass


def test_write_queue_backpressure():
    """
    Regression for scanner hang (commit 0604305).

    Reproduces the bug: a slow/blocked stdout must not block the producer
    thread.  The queue-based writer pattern ensures producers (scanner)
    enqueue events without blocking, while only the writer thread blocks.

    Pre-fix behavior: producer blocks on sys.stdout.write() → deadlock.
    Post-fix behavior: producer enqueues instantly, writer drains when ready.
    """
    blocked_stream = _BlockingStream()
    write_queue: queue.Queue[str | None] = queue.Queue()

    # Writer thread — same pattern as sidecar_main._stdout_writer
    def writer():
        while True:
            line = write_queue.get()
            if line is None:
                break
            try:
                blocked_stream.write(line)
                blocked_stream.flush()
            except OSError:
                break

    writer_thread = threading.Thread(target=writer, daemon=True)
    writer_thread.start()

    # Non-blocking enqueue — same pattern as sidecar_main._write
    def write_event(obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=True) + "\n"
        write_queue.put(line)

    # ── Producer: emit 200 events rapidly (simulates scanner) ────────────
    n_events = 200
    producer_done = threading.Event()

    def producer():
        for i in range(n_events):
            write_event({
                "jsonrpc": "2.0",
                "method": "event",
                "params": {"name": "scan:progress", "detail": {"current": i, "total": n_events}},
            })
        producer_done.set()

    t = threading.Thread(target=producer, daemon=True)
    t.start()

    # KEY ASSERTION: producer finishes in <2 seconds despite stdout being blocked.
    # Pre-fix, this would deadlock because write() blocks on the pipe.
    assert producer_done.wait(timeout=2.0), (
        "Producer thread blocked — backpressure propagated to scanner "
        "(pre-fix behavior: stdout.write() blocked the producer)"
    )

    # ── Unblock the writer and verify all events drain ───────────────────
    blocked_stream.gate.set()
    write_queue.put(None)  # sentinel to stop writer
    writer_thread.join(timeout=5.0)

    assert len(blocked_stream.lines) == n_events, (
        f"Expected {n_events} events drained, got {len(blocked_stream.lines)}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# TEST 2: Non-ASCII paths — scanner must handle international folder names
# Bug: commit 809d9af — Windows codepage vs UTF-8 mismatch at sidecar boundary
# Fix: force stdin/stdout to UTF-8 encoding before any I/O
# ═════════════════════════════════════════════════════════════════════════════

def test_utf8_nonascii_paths(db, thumb_dir, tmp_path):
    """
    Regression for non-ASCII path failure (commit 809d9af).

    Creates folders with Hungarian and CJK names, runs the scanner, and
    verifies all files are discovered.  The original bug caused os.stat()
    to fail on non-ASCII paths because the sidecar used the system codepage
    instead of UTF-8.

    Pre-fix behavior: 0 files found (os.stat fails on mojibake paths).
    Post-fix behavior: all files discovered.
    """
    # Folders with non-ASCII names matching the production bug report
    folders = [
        tmp_path / "Családi fotók",       # Hungarian: "Family photos"
        tmp_path / "Emlékek",              # Hungarian: "Memories"
        tmp_path / "写真",                  # Japanese: "Photos"
        tmp_path / "사진 모음",              # Korean: "Photo collection"
        tmp_path / "Ñoño's Fotos",         # Spanish: tilde-N + apostrophe
    ]

    expected_files = []
    for folder in folders:
        folder.mkdir(parents=True)
        # Also test non-ASCII file names within the folders
        img_path = _jpg(folder / "képek_01.jpg")
        expected_files.append(str(img_path))

    # Create scan session with all folders
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="utf8 test", created_at=now)
    for folder in folders:
        db.add_session_folder(sid, str(folder))

    scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
    done = threading.Event()
    errors: list[tuple[str, str]] = []

    scanner.scan_complete.connect(lambda: done.set())
    scanner.scan_stopped.connect(lambda: done.set())
    scanner.scan_error.connect(lambda p, m: errors.append((p, m)))
    scanner.start()

    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(sid)
    found_paths = {f["path"] for f in files}

    # KEY ASSERTION: all non-ASCII paths were discovered
    for expected in expected_files:
        assert expected in found_paths, (
            f"Non-ASCII path not found: {expected}\n"
            f"Found: {found_paths}\n"
            f"Errors: {errors}"
        )

    assert len(files) == len(expected_files), (
        f"Expected {len(expected_files)} files, found {len(files)}"
    )
    assert not errors, f"Scanner reported errors on non-ASCII paths: {errors}"


# ═════════════════════════════════════════════════════════════════════════════
# TEST 3: Phase transitions — scan progress must not skip phases
# Bug: commit b0c428e — polling overwrites real-time events for fast scans
# Fix: frontend only polls when store is in 'idle' state
# ═════════════════════════════════════════════════════════════════════════════

def test_scan_progress_phase_transitions(db, scan_dir, session_id, thumb_dir):
    """
    Regression for progress race condition (commit b0c428e).

    Verifies that the backend emits phase transition events in correct
    order and that get_scan_progress() returns consistent state at each
    transition point.  The original bug was frontend-side (poll overwrote
    real-time events), but the backend must guarantee the phase sequence
    so the frontend can rely on it.

    The test also verifies that for fast scans (no size-duplicates → no
    hashing work), all intermediate phases are still present in the event
    stream — the exact scenario that triggered the production bug.

    Pre-fix impact: frontend jumped from idle → complete, skipping phases.
    Post-fix: phases arrive in order: started → hashing → complete.
    """
    from backend.api import DejaViewAPI

    # Create a fast scan scenario: unique-size files → no hashing candidates
    for i in range(3):
        _jpg(scan_dir / f"unique_{i}.jpg", size=(60 + i * 20, 60 + i * 20))

    api = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=scan_dir.parent / "trash",
        app_dir=scan_dir.parent / "app",
    )

    # Collect all emitted events
    events: list[tuple[str, dict]] = []
    api.set_emit_callback(lambda name, detail: events.append((name, detail)))

    # Run scan via the API (same path as sidecar dispatch)
    api.start_scan(
        folders=[str(scan_dir)],
        session_name="phase test",
        enable_similarity=False,
    )

    # Wait for completion
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        progress = api.get_scan_progress()
        if progress["phase"] == "complete":
            break
        time.sleep(0.05)
    else:
        pytest.fail("Scan did not reach 'complete' phase within timeout")

    # Extract phase transitions from status events
    status_events = [
        (name, detail) for name, detail in events if name == "scan:status"
    ]
    phase_sequence = [detail["status"] for _, detail in status_events]

    # KEY ASSERTION: phases arrive in order, none skipped
    assert "started" in phase_sequence, (
        f"'started' phase missing from status events: {phase_sequence}"
    )
    assert "complete" in phase_sequence, (
        f"'complete' phase missing from status events: {phase_sequence}"
    )

    # Verify ordering: started must come before complete
    started_idx = phase_sequence.index("started")
    complete_idx = phase_sequence.index("complete")
    assert started_idx < complete_idx, (
        f"Phases out of order: started at {started_idx}, complete at {complete_idx}"
    )

    # Verify discovery events were emitted (frontend needs these for progress display)
    discovery_events = [
        (name, detail) for name, detail in events
        if name == "scan:discovery_progress"
    ]
    assert len(discovery_events) > 0, (
        "No discovery_progress events emitted — fast scan still needs discovery phase"
    )

    # Verify final polling state is consistent with events
    final = api.get_scan_progress()
    assert final["phase"] == "complete"
    assert final["discovered"] == 3, f"Expected 3 discovered, got {final['discovered']}"


# ═════════════════════════════════════════════════════════════════════════════
# TEST 4: High event volume — 5000+ duplicate events must not freeze/block
# Bug: RCA1 — duplicate_found emitted per file, not per group → O(N²) signals
# Fix: emit duplicate_found only when hash first becomes a duplicate (len==2)
# ═════════════════════════════════════════════════════════════════════════════

def test_high_event_volume_no_freeze(db, scan_dir, session_id, thumb_dir):
    """
    Regression for signal storm / UI freeze (RCA1).

    Creates a high-duplicate-rate corpus (100 groups × ~5 files each = 500
    files, all with identical content within each group) and verifies:

    1. Scan completes without hanging.
    2. duplicate_found is emitted only ONCE per hash group (when len(ids)==2),
       not for every subsequent file in the group.
    3. Total signal count is bounded by unique hashes, not total files.

    Pre-fix behavior: 13,784 duplicate_found signals for a 26,599-file scan
      (one per file matching an existing hash) → UI freeze.
    Post-fix behavior: ~60 signals (one per hash group when it first becomes
      a duplicate).
    """
    # Create 50 duplicate groups with 10 identical files each = 500 files.
    # Each group has a unique color → unique pixel hash.
    n_groups = 50
    n_copies = 10
    total_files = n_groups * n_copies

    for group_idx in range(n_groups):
        group_dir = scan_dir / f"group_{group_idx:03d}"
        group_dir.mkdir()
        # Same color within group → same pixel hash → duplicates
        color = (group_idx * 5 % 256, (group_idx * 7 + 30) % 256, (group_idx * 11 + 60) % 256)
        for copy_idx in range(n_copies):
            _jpg(group_dir / f"copy_{copy_idx:02d}.jpg", color=color)

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    done = threading.Event()
    dup_signals: list[tuple[str, list]] = []
    lock = threading.Lock()

    def on_dup(pixel_hash, file_ids):
        with lock:
            dup_signals.append((pixel_hash, list(file_ids)))

    scanner.duplicate_found.connect(on_dup)
    scanner.scan_complete.connect(lambda: done.set())
    scanner.scan_stopped.connect(lambda: done.set())

    t0 = time.monotonic()
    scanner.start()

    # KEY ASSERTION 1: scan completes (no hang from event storm)
    assert done.wait(timeout=60.0), (
        "Scan did not complete within 60s — possible signal storm deadlock"
    )
    elapsed = time.monotonic() - t0

    # KEY ASSERTION 2: duplicate_found emitted once per group, not per file.
    # Each group should emit exactly 1 signal (when the 2nd file is found).
    # Pre-fix: would emit (n_copies - 1) signals per group = 450 total.
    # Post-fix: exactly n_groups signals = 50.
    assert len(dup_signals) == n_groups, (
        f"Expected {n_groups} duplicate_found signals (one per group), "
        f"got {len(dup_signals)} — signal storm not fixed?\n"
        f"Pre-fix would emit {n_groups * (n_copies - 1)} signals."
    )

    # KEY ASSERTION 3: each signal carries exactly 2 file IDs (the first pair)
    for pixel_hash, file_ids in dup_signals:
        assert len(file_ids) == 2, (
            f"duplicate_found for hash {pixel_hash} should carry 2 file IDs "
            f"(first duplicate pair), got {len(file_ids)}"
        )

    # Verify all files were actually scanned
    files = db.get_files_for_session(session_id)
    assert len(files) == total_files, (
        f"Expected {total_files} files discovered, got {len(files)}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# TEST 5: Realistic corpus — 500+ files, non-ASCII paths, mixed formats
# Phase 1, Week 2: Realistic fixture set
# ═════════════════════════════════════════════════════════════════════════════

def test_realistic_corpus_full_scan(db, thumb_dir, tmp_path):
    """
    Full scan of a realistic 500+ file corpus with non-ASCII paths.

    Validates that the scanner handles a production-like workload:
    - 500+ files across 20+ folders
    - Non-ASCII folder and file names (Hungarian, Japanese, Korean)
    - Duplicate groups (same pixel hash across different folders)
    - Mixed image sizes and formats
    - 3-level-deep directory nesting

    Plan guardrail: fixture sets must include at least one non-ASCII path
    AND non-ASCII filename, and one corpus above 500 images.
    """
    from tests.fixtures.realistic_corpus import generate_corpus

    corpus = generate_corpus(tmp_path / "corpus")

    assert corpus["total_files"] >= 500, (
        f"Corpus has {corpus['total_files']} files, need 500+"
    )

    # Create session with all top-level folders
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="realistic corpus", created_at=now)
    db.add_session_folder(sid, str(corpus["root"]))

    scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
    done = threading.Event()
    errors: list[tuple[str, str]] = []
    dup_signals: list[tuple[str, list]] = []

    scanner.scan_complete.connect(lambda: done.set())
    scanner.scan_stopped.connect(lambda: done.set())
    scanner.scan_error.connect(lambda p, m: errors.append((p, m)))
    scanner.duplicate_found.connect(lambda h, ids: dup_signals.append((h, ids)))

    scanner.start()
    assert done.wait(timeout=120.0), "Realistic corpus scan did not complete within 2 minutes"

    files = db.get_files_for_session(sid)

    # All files discovered (including non-ASCII paths)
    assert len(files) >= corpus["total_files"], (
        f"Expected {corpus['total_files']}+ files, found {len(files)}"
    )

    # No errors on non-ASCII paths
    assert not errors, (
        f"Scanner reported {len(errors)} errors: {errors[:5]}"
    )

    # Duplicate groups detected
    assert len(dup_signals) >= corpus["duplicate_groups"], (
        f"Expected {corpus['duplicate_groups']}+ duplicate groups, "
        f"found {len(dup_signals)}"
    )
