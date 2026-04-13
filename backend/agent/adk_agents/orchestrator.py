"""
ADK Orchestrator — SequentialAgent coordinating all 6 sub-agents.
Exposed via the A2A (Agent-to-Agent) protocol as a FastAPI sub-application.

A2A routes mounted at /a2a:
  GET  /a2a/                 → Agent Card  (describes capabilities + skills)
  POST /a2a/run              → Synchronous full-pipeline run
  POST /a2a/run_streaming    → SSE-streaming run (progress events)

A2A message format (request body):
  {
    "id": "<uuid>",
    "method": "tasks/send",
    "params": {
      "message": {
        "parts": [{"text": "<document text or Jira story JSON>"}]
      },
      "metadata": {
        "filename": "PROJ-123.jira",
        "model": "gemini-2.0-flash-001"
      }
    }
  }
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agent.adk_agents.sub_agents import (
    artifacts_agent,
    detect_agent,
    extract_agent,
    propose_agent,
    retrieve_agent,
    verify_agent,
)
from agent.pii_redactor import PIIRedactor

# ─── Orchestrator ─────────────────────────────────────────────────────────────

orchestrator = SequentialAgent(
    name="ArchitectureReviewOrchestrator",
    description=(
        "End-to-end enterprise architecture review pipeline. "
        "Accepts architecture documents (PRD / HLD / LLD) or Jira story payloads "
        "and produces: bottleneck analysis, improvement proposals, Mermaid diagram, "
        "OpenAPI spec, review summary, and evidence-backed citations."
    ),
    sub_agents=[
        extract_agent,      # Step 1 — context extraction
        retrieve_agent,     # Step 2 — RAG knowledge retrieval
        detect_agent,       # Step 3 — bottleneck detection
        propose_agent,      # Step 4 — improvement proposals
        artifacts_agent,    # Step 5 — artifact generation
        verify_agent,       # Step 6 — verification & citation
    ],
)

_session_service = InMemorySessionService()
_runner = Runner(
    agent=orchestrator,
    app_name="arch_review_a2a",
    session_service=_session_service,
)

APP_NAME = "arch_review_a2a"


# ─── A2A Agent Card ───────────────────────────────────────────────────────────

AGENT_CARD: dict[str, Any] = {
    "name": "ArchitectureReviewOrchestrator",
    "description": orchestrator.description,
    "url": os.getenv("A2A_PUBLIC_URL", "https://architecture-review-agent-vtqsnscssq-uc.a.run.app/a2a"),
    "version": "1.0.0",
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "architecture_review",
            "name": "Architecture Review",
            "description": (
                "Full 6-step review pipeline: context extraction, RAG knowledge retrieval, "
                "bottleneck detection, improvement proposals, artifact generation, "
                "and evidence-backed verification."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "examples": [
                "Review this HLD for scalability and security gaps",
                "Analyse this Jira story for architectural risks",
            ],
        }
    ],
    "defaultInputMode": "text",
    "defaultOutputMode": "text",
}


# ─── Runner helpers ───────────────────────────────────────────────────────────

async def _run_pipeline(doc_text: str, filename: str, model: str) -> dict:
    """Run the full sequential pipeline and return the assembled results dict."""
    redactor = PIIRedactor()
    # Redact PII before any data leaves the local process
    clean_doc_text = redactor.redact(doc_text)
    clean_filename = redactor.redact(filename)
    # Explicitly discard unredacted copies
    del doc_text
    del filename

    session_id = str(uuid.uuid4())
    user_id = "a2a_caller"

    session = await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={
            "doc_text": clean_doc_text,
            "filename": clean_filename,
            "model": model,
        },
    )

    from google.adk.events import Event
    from google.genai.types import Part, Content

    initial_message = Content(
        role="user",
        parts=[Part(text=f"Review the architecture document: {filename}")]
    )

    final_response_text = ""
    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=initial_message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response_text = event.content.parts[0].text or ""

    # Collect results from session state
    updated_session = await _session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    state = updated_session.state if updated_session else {}

    verification = state.get("verification", {})
    return {
        "context": _safe_json(state.get("context")),
        "retrieved_guidelines": _safe_json(state.get("retrieved_guidelines")),
        "bottlenecks": _safe_json(state.get("bottlenecks")),
        "proposed_changes": _safe_json(state.get("proposed_changes")),
        "artifacts": _safe_json(state.get("artifacts")),
        "citations": _safe_json(verification).get("citations", []),
        "verification_notes": _safe_json(verification).get("notes", {}),
    }


async def _stream_pipeline(
    doc_text: str, filename: str, model: str
) -> AsyncIterator[str]:
    """Yield SSE-formatted A2A progress events during pipeline execution."""
    redactor = PIIRedactor()
    clean_doc_text = redactor.redact(doc_text)
    clean_filename = redactor.redact(filename)
    del doc_text
    del filename

    session_id = str(uuid.uuid4())
    user_id = "a2a_stream_caller"

    await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={"doc_text": clean_doc_text, "filename": clean_filename, "model": model},
    )

    from google.genai.types import Part, Content

    initial_message = Content(
        role="user",
        parts=[Part(text=f"Review the architecture document: {clean_filename}")]
    )

    step_map = {
        "ContextExtractionAgent":        ("Extracting Context",      16),
        "KnowledgeRetrievalAgent":       ("Retrieving Knowledge",    33),
        "BottleneckDetectionAgent":      ("Detecting Bottlenecks",   50),
        "ImprovementProposalAgent":      ("Proposing Improvements",  66),
        "ArtifactGenerationAgent":       ("Generating Artifacts",    83),
        "VerificationAndCitationAgent":  ("Verifying & Citing",      99),
    }

    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=initial_message,
    ):
        author = getattr(event, "author", None)
        if author and author in step_map:
            label, progress = step_map[author]
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "tasks/sendSubscribeResponse",
                "params": {
                    "taskId": session_id,
                    "status": {"state": "working", "progress": progress, "label": label},
                },
            })
            yield f"data: {payload}\n\n"

        if event.is_final_response():
            updated = await _session_service.get_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
            state = updated.state if updated else {}
            verification = _safe_json(state.get("verification", {}))
            result = {
                "context": _safe_json(state.get("context")),
                "retrieved_guidelines": _safe_json(state.get("retrieved_guidelines")),
                "bottlenecks": _safe_json(state.get("bottlenecks")),
                "proposed_changes": _safe_json(state.get("proposed_changes")),
                "artifacts": _safe_json(state.get("artifacts")),
                "citations": verification.get("citations", []) if isinstance(verification, dict) else [],
                "verification_notes": verification.get("notes", {}) if isinstance(verification, dict) else {},
            }
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "tasks/sendSubscribeResponse",
                "params": {
                    "taskId": session_id,
                    "status": {"state": "completed"},
                    "artifact": {"parts": [{"text": json.dumps(result)}]},
                },
            })
            yield f"data: {payload}\n\n"


def _safe_json(value: Any) -> Any:
    """Parse JSON string → dict/list if needed; return as-is otherwise."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value or {}


# ─── A2A FastAPI sub-application ──────────────────────────────────────────────

a2a_app = FastAPI(title="A2A — ArchitectureReviewOrchestrator")


@a2a_app.get("/")
async def agent_card():
    """Return the A2A Agent Card describing this agent's skills and capabilities."""
    return JSONResponse(AGENT_CARD)


@a2a_app.post("/run")
async def a2a_run(request: Request):
    """
    Synchronous A2A endpoint (tasks/send).
    Runs the full pipeline and returns the complete result when done.
    """
    body = await request.json()
    params = body.get("params", {})
    message = params.get("message", {})
    metadata = params.get("metadata", {})

    parts = message.get("parts", [])
    doc_text = next((p.get("text", "") for p in parts if "text" in p), "")
    filename = metadata.get("filename", "document.txt")
    model = metadata.get("model", os.getenv("ADK_MODEL", "gemini-2.0-flash-001"))

    if not doc_text:
        return JSONResponse(
            status_code=400,
            content={"error": "message.parts must contain at least one text part"},
        )

    task_id = body.get("id", str(uuid.uuid4()))
    try:
        result = await _run_pipeline(doc_text, filename, model)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": task_id,
            "result": {
                "id": task_id,
                "status": {"state": "completed"},
                "artifacts": [{"parts": [{"text": json.dumps(result)}]}],
            },
        })
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": task_id,
                "error": {"code": -32603, "message": str(exc)},
            },
        )


@a2a_app.post("/run_streaming")
async def a2a_run_streaming(request: Request):
    """
    Streaming A2A endpoint (tasks/sendSubscribe).
    Returns an SSE stream of progress events; final event contains the full result.
    """
    body = await request.json()
    params = body.get("params", {})
    message = params.get("message", {})
    metadata = params.get("metadata", {})

    parts = message.get("parts", [])
    doc_text = next((p.get("text", "") for p in parts if "text" in p), "")
    filename = metadata.get("filename", "document.txt")
    model = metadata.get("model", os.getenv("ADK_MODEL", "gemini-2.0-flash-001"))

    if not doc_text:
        return JSONResponse(
            status_code=400,
            content={"error": "message.parts must contain at least one text part"},
        )

    return StreamingResponse(
        _stream_pipeline(doc_text, filename, model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
