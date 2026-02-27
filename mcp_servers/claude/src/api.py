import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .client import send_message


class ClaudeRequest(BaseModel):
    prompt: str
    model: Optional[str] = None


class ClaudeResponse(BaseModel):
    content: str
    finish_reason: str


app = FastAPI(title="Claude Direct Proxy", version="1.0.0")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Simple health endpoint."""
    return {"status": "ok"}


@app.post("/api/claude/direct", response_model=ClaudeResponse, tags=["claude"])
async def claude_direct(request: ClaudeRequest) -> ClaudeResponse:
    """
    Proxy endpoint that sends a prompt to Claude.ai (web) using the direct
    streaming protocol and returns the final concatenated text.
    """
    try:
        content, finish_reason = await send_message(request.prompt, request.model)
        return ClaudeResponse(content=content, finish_reason=finish_reason)
    except Exception as exc:
        # Surface a concise error message to the client
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def run() -> None:
    """Convenience entrypoint for `python -m` or local dev."""
    import uvicorn

    uvicorn.run(
        "src.api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        reload=False,
    )

