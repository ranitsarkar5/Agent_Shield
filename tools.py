"""
tools.py — all tool implementations + schemas for the Gemini agent.
"""

import json
import requests
import threading
from datetime import datetime
from pathlib import Path

# ── Sandbox root for all file operations ─────────────────────────────────────
WORKSPACE = (Path(__file__).parent / "workspace").resolve()
WORKSPACE.mkdir(exist_ok=True)   # create it if it doesn't exist

# ── Persistent memory file (agent infrastructure, lives next to agent.py) ─────
MEMORY_FILE = (Path(__file__).parent / "memory.json").resolve()

_memory_lock = threading.Lock()

def _load_memory() -> dict:
    with _memory_lock:
        if MEMORY_FILE.exists():
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return {}

def _save_memory(data: dict):
    with _memory_lock:
        MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def _safe_path(filename: str) -> Path:
    """Resolve filename inside WORKSPACE; raise if it escapes the sandbox."""
    target = (WORKSPACE / filename).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise PermissionError(f"Access denied: '{filename}' is outside ./workspace/")
    return target

# ── Tool implementations ───────────────────────────────────────────────────────

def get_time() -> str:
    """Returns the current local date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_file(path: str) -> str:
    """Read a text file from the ./workspace/ folder. Provide a filename like 'notes.txt'"""
    target = _safe_path(path)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {path}")
    content = target.read_text(encoding="utf-8")
    if len(content) > 50_000:
        return content[:50_000] + "\n\n...[truncated at 50 KB]"
    return content


def write_file(path: str, content: str) -> str:
    """Write text content to a file inside the ./workspace/ folder. Provide a filename like 'summary.md' and the full text."""
    if len(content) > 500_000:
        raise ValueError("Content too large (>500 KB)")
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to workspace/{path}"


def web_search(query: str) -> str:
    """Search the web for a query using DuckDuckGo and return a short answer."""
    resp = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    answer = data.get("AbstractText", "").strip()
    if not answer and data.get("RelatedTopics"):
        first = data["RelatedTopics"][0]
        answer = first.get("Text", "").strip() if isinstance(first, dict) else ""
    return answer or f"No Instant Answer found for '{query}'. Try a different query."


def save_memory(key: str, value: str) -> str:
    """Save a fact to long-term memory under a short key. Use snake_case keys (e.g. 'user_name'). Overwrites the key if it already exists."""
    key = key.strip()
    if not key:
        raise ValueError("key must be a non-empty string")
    mem = _load_memory()
    mem[key] = value
    _save_memory(mem)
    return f"Memory saved: '{key}' = {json.dumps(value)}"


def recall_memory(key: str) -> str:
    """Look up a previously saved fact by key. Returns the value, or a message saying the key was not found."""
    key = key.strip()
    mem = _load_memory()
    if key not in mem:
        return f"No memory found for key '{key}'."
    return f"{key}: {json.dumps(mem[key])}"

# ── Exported Tools ────────────────────────────────────────────────────────────
GEMINI_TOOLS = [
    get_time,
    read_file,
    write_file,
    web_search,
    save_memory,
    recall_memory
]
