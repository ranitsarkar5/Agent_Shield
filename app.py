"""
app.py — Streamlit web UI for the AI agent.
Run with:  streamlit run app.py

Strategy
--------
* agent.py is NEVER modified — we simply import run_agent() from it.
* stdout is redirected via a ThreadLocalStdout so every print() from the agent
  (iterations, tool calls, results) is captured safely per-thread.
* The main thread drains the queue in a tight loop and updates Streamlit
  placeholders live — no page reload needed.
* safety.py's require_approval() is monkey-patched with a thread-aware wrapper.
"""

import sys
import json
import queue
import threading
from pathlib import Path

import streamlit as st
from agent import run_agent  # imported once at the top

# ── Thread-local safety & stdout ──────────────────────────────────────────────
class ThreadLocalStdout:
    def __init__(self, fallback):
        self.fallback = fallback
        self.local = threading.local()

    def write(self, s):
        if hasattr(self.local, 'stream'):
            self.local.stream.write(s)
        else:
            self.fallback.write(s)

    def flush(self):
        if hasattr(self.local, 'stream'):
            self.local.stream.flush()
        else:
            self.fallback.flush()

if not isinstance(sys.stdout, ThreadLocalStdout):
    sys.stdout = ThreadLocalStdout(sys.stdout)

import safety as _safety
_orig_approve = _safety.require_approval

def _thread_aware_approve(tool_name: str, tool_input: dict) -> bool:
    local = sys.stdout.local
    if hasattr(local, 'web_auto_approve'):
        if local.web_auto_approve:
            print(f"[AUTO-APPROVED] {tool_name}")
            return True
        print(f"[AUTO-DENIED]   {tool_name}  (enable 'Auto-approve' in sidebar to allow)")
        return False
    return _orig_approve(tool_name, tool_input)

_safety.require_approval = _thread_aware_approve

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS (minimal — keeps things readable) ──────────────────────────────
st.markdown("""
<style>
  .step-card   { background:#1e1e2e; border-radius:8px; padding:10px 14px;
                 margin:4px 0; font-family:monospace; font-size:0.85rem; }
  .iter-header { color:#cba6f7; font-weight:700; }
  .tool-call   { color:#89dceb; }
  .tool-ok     { color:#a6e3a1; }
  .tool-err    { color:#f38ba8; }
  .token-line  { color:#6c7086; font-size:0.78rem; }
  .stop-line   { color:#fab387; font-weight:600; }
  .warn-line   { color:#f9e2af; }
  .info-line   { color:#89b4fa; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️  Settings")

    auto_approve = st.toggle(
        "Auto-approve risky tools",
        value=False,
        help="write_file and similar tools require approval. Enable to skip the prompt.",
    )

    st.divider()
    st.subheader("🧠 Memory")
    mem_path = Path(__file__).parent / "memory.json"

    def _show_memory():
        if mem_path.exists():
            mem = json.loads(mem_path.read_text(encoding="utf-8"))
            if mem:
                for k, v in mem.items():
                    st.markdown(f"**`{k}`** → {v}")
            else:
                st.caption("Memory is empty.")
        else:
            st.caption("No memory file yet.")

    _show_memory()

    if st.button("🗑  Clear memory", use_container_width=True):
        if mem_path.exists():
            mem_path.unlink()
        st.rerun()

    st.divider()
    st.caption("Logs are saved to `./logs/` as JSON lines.")

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🤖 AI Agent")
st.caption("Powered by **Claude** via the Anthropic SDK")

goal = st.text_area(
    "Goal",
    placeholder=(
        "e.g. Search the web for who founded Anthropic "
        "and save a 3-sentence summary to workspace/anthropic.md"
    ),
    height=110,
    label_visibility="collapsed",
)

run_btn = st.button(
    "▶  Run Agent",
    type="primary",
    disabled=not goal.strip(),
    use_container_width=True,
)

# ── Line → structured card ────────────────────────────────────────────────────
def _card(css_class: str, icon: str, text: str) -> str:
    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_icon = icon.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<div class="step-card {css_class}">{safe_icon} {safe_text}</div>'

def _render_line(line: str) -> str | None:
    """Convert one agent output line into an HTML card. Returns None to skip."""
    l = line.strip()
    if not l or set(l) == {"─"}:
        return None
    if "Iteration" in l and "calling Claude" in l:
        return _card("iter-header", "🔄", l)
    if l.startswith("[tool_use]"):
        return _card("tool-call", "🔧", l.removeprefix("[tool_use]").strip())
    if l.startswith("[tool_result]"):
        return _card("tool-ok", "✅", l.removeprefix("[tool_result]").strip())
    if l.startswith("[ERROR]"):
        return _card("tool-err", "❌", l.removeprefix("[ERROR]").strip())
    if l.startswith("[tokens]"):
        return _card("token-line", "📊", l.removeprefix("[tokens]").strip())
    if l.startswith("[stop_reason]"):
        return _card("info-line", "⏹", l.removeprefix("[stop_reason]").strip())
    if l.startswith("[STOPPED]"):
        return _card("stop-line", "⛔", l.removeprefix("[STOPPED]").strip())
    if l.startswith("[WARN]"):
        return _card("warn-line", "⚠️", l.removeprefix("[WARN]").strip())
    if l.startswith("[logger]") or l.startswith("[SAFETY]") or l.startswith("[AUTO"):
        return _card("info-line", "ℹ️", l)
    if l.startswith("[FINAL ANSWER]"):
        return None  # handled separately
    # Generic text (planning sentences, etc.)
    return _card("info-line", "💬", l)

# ── Agent runner ──────────────────────────────────────────────────────────────
if run_btn and goal.strip():

    output_q: queue.Queue[str | None] = queue.Queue()
    done_event = threading.Event()

    # ── stdout redirector ─────────────────────────────────────────────────────
    class _Capture:
        def __init__(self):
            self._buf = ""
        def write(self, text: str):
            self._buf += text
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                output_q.put(line)
        def flush(self):
            pass

    # ── Thread target ─────────────────────────────────────────────────────────
    def _thread_target(is_auto_approve: bool):
        sys.stdout.local.stream = _Capture()
        sys.stdout.local.web_auto_approve = is_auto_approve
        try:
            run_agent(goal)
        except Exception as exc:
            output_q.put(f"[ERROR] Unhandled exception: {exc}")
        finally:
            if hasattr(sys.stdout.local, 'stream'):
                del sys.stdout.local.stream
            if hasattr(sys.stdout.local, 'web_auto_approve'):
                del sys.stdout.local.web_auto_approve
            done_event.set()

    t = threading.Thread(target=_thread_target, args=(auto_approve,), daemon=True)
    t.start()

    # ── Live log area ─────────────────────────────────────────────────────────
    st.divider()
    col_log, col_ans = st.columns([3, 2])

    with col_log:
        st.subheader("📋 Live Log")
        log_ph = st.empty()

    with col_ans:
        st.subheader("💡 Final Answer")
        ans_ph = st.empty()
        ans_ph.info("Waiting for agent to finish…")

    html_cards: list[str] = []
    final_lines: list[str] = []
    in_final = False

    # Drain queue until agent is done and queue is empty
    while not done_event.is_set() or not output_q.empty():
        try:
            line = output_q.get(timeout=0.1)
        except queue.Empty:
            continue

        # Track final-answer block
        if "[FINAL ANSWER]" in line:
            in_final = True
            continue
        if in_final:
            final_lines.append(line)
            ans_ph.success("\n\n".join(final_lines))
            continue

        card = _render_line(line)
        if card:
            html_cards.append(card)
            log_ph.markdown("\n".join(html_cards), unsafe_allow_html=True)

    # ── Post-run ──────────────────────────────────────────────────────────────
    if not final_lines:
        stopped = next(
            (c for c in html_cards if "⛔" in c or "⚠️" in c),
            None,
        )
        if stopped:
            ans_ph.warning("Agent stopped before producing a final answer. See log.")
        else:
            ans_ph.warning("No final answer received.")

    st.toast("Agent finished!", icon="✅")
    # Refresh sidebar memory panel
    st.rerun()
