"""
safety.py — all safety guardrails for the agent.

Features:
  1. Hard caps: max iterations + max total tokens
  2. Human approval before risky tool calls (write_file, delete, etc.)
  3. Per-tool call timeout (default 30 s)
  4. Loop detection: stops if the same (tool, input) appears 3+ times
  5. JSON-lines logging to logs/<run-id>.jsonl
"""

import json
import signal
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 1. Hard caps
# ─────────────────────────────────────────────────────────────────────────────
MAX_ITERATIONS = 10          # absolute ceiling on agent loop iterations
MAX_TOTAL_TOKENS = 50_000   # cumulative input+output tokens before forced stop

# ─────────────────────────────────────────────────────────────────────────────
# 2. Risky tools that require human approval
# ─────────────────────────────────────────────────────────────────────────────
RISKY_TOOLS = {"write_file", "delete_file", "send_email", "execute_code"}

def require_approval(tool_name: str, tool_input: dict) -> bool:
    """
    Print the proposed call and ask the user y/n.
    Returns True (approved) or False (denied).
    Defaults to denied if stdin is not a TTY (e.g. CI).
    """
    if not sys.stdin.isatty():
        print(f"[SAFETY] Non-interactive mode — auto-denying risky tool '{tool_name}'.")
        return False

    print(f"\n⚠️  RISKY TOOL: {tool_name}")
    print(f"   Input: {json.dumps(tool_input, indent=2)}")
    try:
        answer = input("   Approve? [y/N] ").strip().lower()
    except EOFError:
        answer = "n"
    approved = answer == "y"
    if not approved:
        print(f"   → Denied by user.")
    return approved

# ─────────────────────────────────────────────────────────────────────────────
# 3. Tool call timeout (POSIX + Windows fallback)
# ─────────────────────────────────────────────────────────────────────────────
TOOL_TIMEOUT_SECONDS = 30

class ToolTimeoutError(Exception):
    pass

def run_with_timeout(fn, inp: dict, seconds: int = TOOL_TIMEOUT_SECONDS):
    """
    Run fn(inp) and raise ToolTimeoutError if it doesn't finish in time.
    Uses SIGALRM on Unix; falls back to thread-based timeout on Windows.
    """
    if hasattr(signal, "SIGALRM"):
        # ── Unix path ────────────────────────────────────────────────────────
        def _handler(signum, frame):
            raise ToolTimeoutError(f"Tool timed out after {seconds}s")
        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
        try:
            return fn(inp)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    else:
        # ── Windows path (threading) ─────────────────────────────────────────
        import threading
        result_box = [None]
        error_box  = [None]

        def _target():
            try:
                result_box[0] = fn(inp)
            except Exception as e:
                error_box[0] = e

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout=seconds)
        if t.is_alive():
            raise ToolTimeoutError(f"Tool timed out after {seconds}s")
        if error_box[0] is not None:
            raise error_box[0]
        return result_box[0]

# ─────────────────────────────────────────────────────────────────────────────
# 4. Loop detection
# ─────────────────────────────────────────────────────────────────────────────
LOOP_THRESHOLD = 3   # stop if the same (tool, serialised-input) appears ≥ this many times

class LoopDetector:
    def __init__(self):
        self._counts: Counter = Counter()

    def record(self, tool_name: str, tool_input: dict) -> bool:
        """Record a call. Returns True if a loop is detected."""
        key = (tool_name, json.dumps(tool_input, sort_keys=True))
        self._counts[key] += 1
        return self._counts[key] >= LOOP_THRESHOLD

# ─────────────────────────────────────────────────────────────────────────────
# 5. JSON-lines logger
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = (Path(__file__).parent / "logs").resolve()

class RunLogger:
    def __init__(self, run_id: str):
        LOG_DIR.mkdir(exist_ok=True)
        self._path = LOG_DIR / f"{run_id}.jsonl"
        self._f = self._path.open("a", encoding="utf-8")
        print(f"[logger]  writing to {self._path}")

    def log(self, event: str, **kwargs):
        record = {
            "ts":    datetime.now(timezone.utc).isoformat(),
            "event": event,
            **kwargs,
        }
        self._f.write(json.dumps(record) + "\n")
        self._f.flush()

    def close(self):
        self._f.close()
