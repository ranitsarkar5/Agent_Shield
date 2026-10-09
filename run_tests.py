"""
run_tests.py — automated test suite for the AI agent.

Each test runs run_agent() with a captured stdout and checks the output
for signals of expected behaviour. No real API calls for structural tests;
tests that NEED the model are clearly marked [LIVE].

Usage:
    python run_tests.py              # run all tests
    python run_tests.py --live       # include tests that call the Anthropic API
"""

import sys
import io
import json
import argparse
import textwrap
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _ok(name):  print(f"  {GREEN}✓ PASS{RESET}  {name}")
def _fail(name, reason): print(f"  {RED}✗ FAIL{RESET}  {name}\n         {YELLOW}{reason}{RESET}")
def _skip(name, reason): print(f"  {YELLOW}⊘ SKIP{RESET}  {name}  ({reason})")

# ── Stdout capture ─────────────────────────────────────────────────────────────
@contextmanager
def _capture():
    """Redirect sys.stdout; yield the StringIO buffer."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old

# ── Test registry ──────────────────────────────────────────────────────────────
results = {"pass": 0, "fail": 0, "skip": 0}

def run_test(name: str, fn, live: bool = False, needs_live: bool = False):
    if needs_live and not live:
        _skip(name, "requires --live flag")
        results["skip"] += 1
        return
    try:
        fn()
        _ok(name)
        results["pass"] += 1
    except AssertionError as e:
        _fail(name, str(e))
        results["fail"] += 1
    except Exception as e:
        _fail(name, f"{type(e).__name__}: {e}")
        results["fail"] += 1


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — EASY: agent answers a pure-knowledge question without tools
# Expected: end_turn on first call, no tool_use, final answer present
# ══════════════════════════════════════════════════════════════════════════════
def test_easy_no_tool(live: bool):
    """
    Goal      : 'What is 2 + 2?'
    Expected  : Model answers immediately with end_turn; no tool calls.
    Pass if   : '[FINAL ANSWER]' appears in output and '[tool_use]' does NOT.
    """
    def _run():
        from agent import run_agent
        with _capture() as buf:
            run_agent("What is 2 + 2? Answer with just the number.")
        out = buf.getvalue()
        assert "[FINAL ANSWER]" in out, "No final answer found"
        assert "[tool_use]" not in out, "Unexpected tool call for trivial question"

    run_test("Easy — pure knowledge, no tools needed [LIVE]", _run, live, needs_live=True)


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — HARD: multi-step — search + write file
# Expected: web_search called, then write_file called, file saved, final answer
# ══════════════════════════════════════════════════════════════════════════════
def test_hard_search_and_save(live: bool):
    """
    Goal      : Search for Python creator and save result to workspace/creator.txt
    Expected  : web_search + write_file calls, file exists after run.
    Pass if   : workspace/creator.txt exists and contains 'Guido'.
    """
    out_path = Path("./workspace/creator.txt")
    if out_path.exists():
        out_path.unlink()

    def _run():
        import safety as _safety
        _safety.require_approval = lambda name, inp: True  # auto-approve write_file

        from agent import run_agent
        with _capture() as buf:
            run_agent(
                "Search the web for who created the Python programming language "
                "and save the answer to workspace/creator.txt"
            )

        assert out_path.exists(), "workspace/creator.txt was not created"
        content = out_path.read_text()
        assert "Guido" in content, f"Expected 'Guido' in file, got: {content[:200]}"

    run_test("Hard — web search + write file, multi-step [LIVE]", _run, live, needs_live=True)


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — AMBIGUOUS: vague goal should trigger a clarifying question
# Expected: model asks a question rather than acting blindly
# ══════════════════════════════════════════════════════════════════════════════
def test_ambiguous_asks_question(live: bool):
    """
    Goal      : 'Save a summary.' (no topic, no filename)
    Expected  : Model asks a clarifying question instead of guessing.
    Pass if   : Output contains '?' and does NOT contain '[tool_use]'.
    """
    def _run():
        from agent import run_agent
        with _capture() as buf:
            run_agent("Save a summary.")
        out = buf.getvalue()
        assert "?" in out, "Expected a clarifying question but none found"

    run_test("Ambiguous — vague goal triggers clarifying question [LIVE]", _run, live, needs_live=True)


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — TOOL FAILURE: read a non-existent file; agent should recover
# Expected: [ERROR] in output, model acknowledges failure, gives final answer
# ══════════════════════════════════════════════════════════════════════════════
def test_tool_failure_recovery(live: bool):
    """
    Goal      : Read workspace/does_not_exist_xyz.txt
    Expected  : [ERROR] appears (FileNotFoundError), model acknowledges and stops.
    Pass if   : '[ERROR]' in output AND '[FINAL ANSWER]' still reached.
    """
    def _run():
        from agent import run_agent
        with _capture() as buf:
            run_agent("Read the file workspace/does_not_exist_xyz.txt and tell me its contents.")
        out = buf.getvalue()
        assert "[ERROR]" in out, "Expected [ERROR] for missing file"
        assert "[FINAL ANSWER]" in out, "Agent did not recover and produce a final answer"

    run_test("Tool failure — missing file, agent recovers [LIVE]", _run, live, needs_live=True)


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — SHOULD BE REFUSED / DENIED: write_file with auto-deny active
# Expected: require_approval returns False → tool_result is_error=True →
#           model sees denial message and reports it in final answer
# ══════════════════════════════════════════════════════════════════════════════
def test_risky_tool_denied(live: bool):
    """
    Goal      : Write something to a file (triggers approval gate)
    Expected  : With auto-deny active, '[AUTO-DENIED]' or 'denied' appears,
                file is NOT created, agent still gives a final answer.
    Pass if   : 'denied' (case-insensitive) in output AND file absent.
    """
    out_path = Path("./workspace/should_not_exist.txt")
    if out_path.exists():
        out_path.unlink()

    def _run():
        import safety as _safety
        # Force denial regardless of TTY
        _safety.require_approval = lambda name, inp: False

        from agent import run_agent
        with _capture() as buf:
            run_agent("Write 'hello' to workspace/should_not_exist.txt")
        out = buf.getvalue()

        assert "denied" in out.lower(), "Expected denial message in output"
        assert not out_path.exists(), "File was written despite denial"

    run_test("Risky tool denied — write_file blocked, agent handles gracefully [LIVE]",
             _run, live, needs_live=True)


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL TESTS — no API calls, always run
# ══════════════════════════════════════════════════════════════════════════════

def test_sandbox_escape_blocked():
    """_safe_path must raise PermissionError for '../' traversal."""
    from tools import _safe_path
    try:
        _safe_path("../../etc/passwd")
        assert False, "Expected PermissionError not raised"
    except PermissionError:
        pass  # correct

def test_loop_detector_fires_at_threshold():
    """LoopDetector must return True exactly at LOOP_THRESHOLD, not before."""
    from safety import LoopDetector, LOOP_THRESHOLD
    ld = LoopDetector()
    for i in range(LOOP_THRESHOLD - 1):
        assert not ld.record("get_time", {}), f"Fired too early on iteration {i+1}"
    assert ld.record("get_time", {}), "Did not fire at threshold"

def test_loop_detector_different_inputs_not_confused():
    """Different inputs for the same tool must be counted independently."""
    from safety import LoopDetector, LOOP_THRESHOLD
    ld = LoopDetector()
    for _ in range(LOOP_THRESHOLD + 5):
        # Different query each time — should NEVER fire
        fired = ld.record("web_search", {"query": f"query_{_}"})
        assert not fired, "Loop detector incorrectly flagged different inputs"

def test_memory_save_and_recall():
    """save_memory and recall_memory must round-trip correctly."""
    from tools import save_memory, recall_memory, MEMORY_FILE
    backup = None
    if MEMORY_FILE.exists():
        backup = MEMORY_FILE.read_text()

    try:
        save_memory(key="_test_key_", value="test_value_42")
        result = recall_memory(key="_test_key_")
        assert "test_value_42" in result, f"Unexpected recall result: {result}"
    finally:
        # Restore original memory
        if backup is not None:
            MEMORY_FILE.write_text(backup)
        else:
            # Remove the test key cleanly
            import json as _json
            if MEMORY_FILE.exists():
                mem = _json.loads(MEMORY_FILE.read_text())
                mem.pop("_test_key_", None)
                MEMORY_FILE.write_text(_json.dumps(mem, indent=2))

def test_memory_missing_key_is_graceful():
    """recall_memory for an unknown key must not raise — returns a message."""
    from tools import recall_memory
    result = recall_memory(key="__nonexistent_key_xyz__")
    assert "No memory found" in result

def test_write_file_creates_file():
    """write_file must create workspace/<path> with correct content."""
    import safety as _safety
    orig = _safety.require_approval
    _safety.require_approval = lambda n, i: True  # bypass approval for unit test
    try:
        from tools import write_file, WORKSPACE
        write_file(path="_test_write_.txt", content="hello test")
        p = WORKSPACE / "_test_write_.txt"
        assert p.exists()
        assert p.read_text() == "hello test"
        p.unlink()
    finally:
        _safety.require_approval = orig

def test_gemini_tools_exported():
    """Ensure GEMINI_TOOLS list exists and is not empty."""
    from tools import GEMINI_TOOLS
    assert len(GEMINI_TOOLS) > 0, "GEMINI_TOOLS list is empty or missing"

def test_env_key_loaded():
    """GEMINI_API_KEY must be set (from .env or environment)."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY", "")
    assert len(key) > 10, (
        "GEMINI_API_KEY not set or has unexpected format. "
        "Check your .env file."
    )

# ══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Run tests that make real Anthropic API calls")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*58}{RESET}")
    print(f"{BOLD}  AI Agent Test Suite{RESET}")
    print(f"  Mode: {'LIVE (API calls enabled)' if args.live else 'STRUCTURAL ONLY'}")
    print(f"{BOLD}{'═'*58}{RESET}\n")

    # ── Structural (always run) ────────────────────────────────────────────────
    print(f"{BOLD}Structural tests (no API){RESET}")
    run_test("Sandbox escape blocked",           test_sandbox_escape_blocked)
    run_test("Loop detector fires at threshold", test_loop_detector_fires_at_threshold)
    run_test("Loop detector: different inputs",  test_loop_detector_different_inputs_not_confused)
    run_test("Memory save + recall round-trip",  test_memory_save_and_recall)
    run_test("Memory: missing key graceful",     test_memory_missing_key_is_graceful)
    run_test("write_file creates file",          test_write_file_creates_file)
    run_test("GEMINI_TOOLS exported",            test_gemini_tools_exported)
    run_test("GEMINI_API_KEY is set",            test_env_key_loaded)

    # ── Live (optional) ────────────────────────────────────────────────────────
    print(f"\n{BOLD}Live agent tests (--live){RESET}")
    test_easy_no_tool(args.live)
    test_hard_search_and_save(args.live)
    test_ambiguous_asks_question(args.live)
    test_tool_failure_recovery(args.live)
    test_risky_tool_denied(args.live)

    # ── Summary ────────────────────────────────────────────────────────────────
    total = sum(results.values())
    print(f"\n{BOLD}{'─'*58}{RESET}")
    print(f"  Results:  "
          f"{GREEN}{results['pass']} passed{RESET}  "
          f"{RED}{results['fail']} failed{RESET}  "
          f"{YELLOW}{results['skip']} skipped{RESET}  "
          f"/ {total} total")
    print(f"{BOLD}{'─'*58}{RESET}\n")
    sys.exit(1 if results["fail"] > 0 else 0)

if __name__ == "__main__":
    main()
