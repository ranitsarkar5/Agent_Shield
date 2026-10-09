"""
Minimal Gemini agent — tools: get_time, read_file, write_file, web_search.
Usage: python agent.py "Search the web for the Anthropic founding year and save it to notes.txt"
"""

import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# pyrefly: ignore [missing-import]
from google import genai
from google.genai import types

from tools import GEMINI_TOOLS                       # ← all tools live here
from prompts import SYSTEM_PROMPT                  # ← edit prompts.py to tune behaviour
from safety import (                               # ← all guardrails live here
    MAX_ITERATIONS, MAX_TOTAL_TOKENS,
    RISKY_TOOLS, require_approval,
    run_with_timeout, LoopDetector, RunLogger,
)

load_dotenv()  # reads GEMINI_API_KEY from .env

# ── Agent loop ────────────────────────────────────────────────────────────────
def run_agent(goal: str):
    client = genai.Client()

    # ── Safety state (all guardrails) ────────────────────────────────────────────
    run_id       = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger       = RunLogger(run_id)
    total_tokens = 0
    loop_det     = LoopDetector()
    logger.log("run_start", goal=goal)

    try:
        # Initialize Gemini chat with tools
        chat = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=GEMINI_TOOLS,
                temperature=0.0
            )
        )

        current_message = goal

        for iteration in range(1, MAX_ITERATIONS + 1):
            print(f"\n{'─'*50}")
            print(f"  Iteration {iteration}/{MAX_ITERATIONS}  →  calling Gemini…")
            print(f"{'─'*50}")
            logger.log("iteration_start", n=iteration)

            # ── Call the model ────────────────────────────────────────────────────
            response = chat.send_message(current_message)

            # ── 1. Token cap ───────────────────────────────────────────────────────────
            used = 0
            if response.usage_metadata:
                used = response.usage_metadata.total_token_count
                
            # Gemini usage is cumulative per chat if not careful, but total_token_count
            # is usually the total so far for the turn. 
            total_tokens = used if used > 0 else total_tokens + 100
            
            logger.log("model_response", tokens_this_call=used, total_tokens=total_tokens)
            print(f"[tokens]       total={total_tokens}/{MAX_TOTAL_TOKENS}")

            if total_tokens >= MAX_TOTAL_TOKENS:
                print(f"\n[STOPPED] Token cap ({MAX_TOTAL_TOKENS}) reached.")
                logger.log("stopped", reason="token_cap", total_tokens=total_tokens)
                return

            # ── Case 1: model is done, return plain text ──────────────────────────
            if not response.function_calls:
                final = response.text or ""
                print(f"\n[FINAL ANSWER]\n{final}")
                logger.log("final_answer", text=final)
                return

            # ── Case 2: model wants to call one or more tools ─────────────────────
            tool_results = []
            for call in response.function_calls:
                block_name = call.name
                # Gemini returns args as a structure that dict() can cast, or it's already a dict
                block_input = dict(call.args) if call.args else {}

                print(f"[tool_use]     {block_name}({json.dumps(block_input)})")

                # ── 4. Loop detection ───────────────────────────────────────────────
                if loop_det.record(block_name, block_input):
                    print(f"[STOPPED] Loop detected: '{block_name}' repeated 3+ times.")
                    logger.log("stopped", reason="loop_detected", tool=block_name)
                    return

                # ── 2. Human approval for risky tools ──────────────────────────────
                if block_name in RISKY_TOOLS:
                    if not require_approval(block_name, block_input):
                        result   = "Tool call denied by user."
                        is_error = True
                        logger.log("tool_denied", tool=block_name)
                        tool_results.append(types.Part.from_function_response(
                            name=block_name,
                            response={"error": result}
                        ))
                        continue

                # ── 3. Run tool with timeout + error handling ──────────────────────────
                is_error = False
                try:
                    fn = next((t for t in GEMINI_TOOLS if t.__name__ == block_name), None)
                    if fn is None:
                        raise ValueError(f"No implementation for tool '{block_name}'")
                    
                    # Run with timeout; unpack kwargs into fn
                    def _wrapper(_):
                        return fn(**block_input)
                        
                    result = run_with_timeout(_wrapper, None)
                except Exception as exc:
                    result   = f"ERROR: {exc}"
                    is_error = True

                status = "[ERROR]" if is_error else "[tool_result]"
                print(f"{status}  {result}")
                logger.log("tool_result", tool=block_name, is_error=is_error,
                           result=str(result)[:300])

                resp_dict = {"error": result} if is_error else {"result": result}
                tool_results.append(types.Part.from_function_response(
                    name=block_name,
                    response=resp_dict
                ))

            # Provide the results to Gemini on the next loop
            current_message = tool_results

        print(f"\n[STOPPED] Reached {MAX_ITERATIONS} iterations without a final answer.")
        logger.log("stopped", reason="max_iterations")

    finally:
        logger.close()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python agent.py "your goal here"')
        sys.exit(1)

    run_agent(goal=" ".join(sys.argv[1:]))
