from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
from pydantic import BaseModel

# Add parent directory to path so we can import agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import run_agent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    goal: str
    api_key: str

@app.post("/api/chat")
async def chat(req: ChatRequest):
    os.environ["GEMINI_API_KEY"] = req.api_key
    
    logs = []
    def capture_print(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        logs.extend(text.splitlines())
    
    try:
        run_agent(req.goal, print_fn=capture_print)
        
        # Extract final answer if present
        final_answer = ""
        in_final = False
        final_lines = []
        for line in logs:
            if "[FINAL ANSWER]" in line:
                in_final = True
                continue
            if in_final:
                final_lines.append(line)
                
        if final_lines:
            final_answer = "\n".join(final_lines)
        else:
            final_answer = "Agent stopped without a final answer. Check logs."
            
        return {"answer": final_answer, "logs": logs}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "logs": logs})
