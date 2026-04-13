import asyncio
import json
import logging
import os
import posixpath
import re
import uuid
from pathlib import Path

import vertexai
from agent.orchestrator import _parse_document
from agent.adk_agents.orchestrator import a2a_app, _run_pipeline
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from agent.pii_redactor import PIIRedactor
from sse_starlette.sse import EventSourceResponse

load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT",
                       "project-ef11010f-3538-4e0c-8f1")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

app = FastAPI(
    title="Enterprise Architecture Review Agent",
    description="AI-powered architecture review system for PRD/HLD/LLD documents",
    version="1.0.0",
)

# In-memory job store (production: use Redis)
# Shared between the HTTP handlers, the Jira poller, and (optionally) the webhook router.
jobs: dict[str, dict] = {}

_jira_poller_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup_event():
    global _jira_poller_task

    # Initialize Vertex AI (fast — just sets module-level config)
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        logger.info("Vertex AI initialized for project %s in %s", PROJECT_ID, LOCATION)
    except Exception as exc:
        logger.warning("Vertex AI init warning (non-fatal): %s", exc)

    # Pre-warm PII Redaction engine in a background thread so it does NOT
    # block the event loop or delay the port from accepting connections.
    # spacy model loading can take 10-30s; Cloud Run health probe must not time out.
    def _prewarm_pii():
        try:
            PIIRedactor()
            logger.info("PII Redaction NLP engine pre-warmed.")
        except Exception as exc:
            logger.warning("PII Redactor pre-warm failed (non-fatal): %s", exc)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _prewarm_pii)

    # Start Jira poller if a project key is configured.
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "")
    if jira_project_key:
        from jira.poller import JiraPoller
        poller = JiraPoller(jobs)
        _jira_poller_task = asyncio.create_task(poller.run())
        logger.info("Jira poller started — monitoring project %s", jira_project_key)
    else:
        logger.info("Jira poller disabled (JIRA_PROJECT_KEY not set).")


@app.on_event("shutdown")
async def shutdown_event():
    if _jira_poller_task and not _jira_poller_task.done():
        _jira_poller_task.cancel()
        try:
            await _jira_poller_task
        except asyncio.CancelledError:
            pass

# CORS: explicit origins required when allow_credentials=True
# (browser rejects credentialed requests to wildcard origins per the CORS spec)
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "https://arch-review-ai.vercel.app,http://localhost:3000,http://localhost:8000",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount A2A sub-application at /a2a  (Agent-to-Agent strict protocol)
app.mount("/a2a", a2a_app)

# UI_ENABLED gates the file-upload endpoints and Vercel frontend redirects.
# Set UI_ENABLED=true to re-enable the web UI; Jira integration is always active.
_UI_ENABLED: bool = os.getenv("UI_ENABLED", "false").lower() in ("1", "true", "yes")

# Frontend is hosted on Vercel. Root and all non-API paths redirect there.
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://arch-review-ai.vercel.app")


# Single source of truth for available models — both frontends fetch this.
MODELS = [
    {"value": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite", "badge": "Recommended"},
    {"value": "gemini-2.0-flash-001", "label": "Gemini 2.0 Flash", "badge": ""},
    {"value": "gemini-2.0-flash-lite-001", "label": "Gemini 2.0 Flash Lite", "badge": "Fastest"},
    {"value": "gemini-1.5-pro-001", "label": "Gemini 1.5 Pro", "badge": "Highest Quality"},
]
DEFAULT_MODEL = MODELS[0]["value"]


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/models")
async def list_models():
    """Return the canonical list of supported Vertex AI models."""
    return {"models": MODELS, "default": DEFAULT_MODEL}


VALID_MODEL_VALUES = {m["value"] for m in MODELS}


# ─── UI endpoints (disabled by default — set UI_ENABLED=true to re-enable) ────
# Registered conditionally so FastAPI never parses multipart bodies unless UI is on.

if _UI_ENABLED:
    from fastapi import File, Form, UploadFile

    @app.post("/api/analyze")
    async def analyze(
        document: UploadFile = File(...),
        model: str = Form(default=DEFAULT_MODEL),
    ):
        """Upload a design document and start the architecture review workflow."""
        if model not in VALID_MODEL_VALUES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported model '{model}'. Valid options: {sorted(VALID_MODEL_VALUES)}",
            )
        job_id = str(uuid.uuid4())
        content = await document.read()
        filename = document.filename or "document.txt"
        ext = Path(filename).suffix.lower()
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "steps": {},
            "results": None,
            "error": None,
        }
        asyncio.create_task(run_agent(job_id, content, ext, filename, model))
        return {"job_id": job_id, "status": "pending"}

    @app.get("/api/status/{job_id}")
    async def get_status(job_id: str):
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs[job_id]
        return {
            "id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "steps": job["steps"],
            "error": job.get("error"),
        }

    @app.get("/api/results/{job_id}")
    async def get_results(job_id: str):
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs[job_id]
        if job["status"] != "complete":
            return JSONResponse(
                status_code=202,
                content={"status": job["status"], "message": "Analysis still in progress"},
            )
        return job["results"]

    @app.get("/api/stream/{job_id}")
    async def stream_progress(job_id: str):
        """SSE stream for real-time progress updates."""
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")

        async def event_generator():
            last_progress = -1
            while True:
                job = jobs.get(job_id)
                if not job:
                    break
                progress = job["progress"]
                status = job["status"]
                if progress != last_progress:
                    last_progress = progress
                    yield {
                        "event": "progress",
                        "data": json.dumps({
                            "progress": progress,
                            "status": status,
                            "steps": job["steps"],
                        }),
                    }
                if status in ("complete", "error"):
                    yield {
                        "event": "done",
                        "data": json.dumps({"status": status, "error": job.get("error")}),
                    }
                    break
                await asyncio.sleep(0.5)

        return EventSourceResponse(event_generator())


async def run_agent(job_id: str, content: bytes, ext: str, filename: str, model: str):
    jobs[job_id]["status"] = "running"
    try:
        doc_text = _parse_document(content, ext)
        result = await _run_pipeline(doc_text, filename, model)
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["results"] = result
        jobs[job_id]["progress"] = 100
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


@app.get("/")
async def redirect_root():
    """Root path: redirect to frontend if UI enabled, otherwise return service info."""
    if not _UI_ENABLED:
        return JSONResponse({"service": "Architecture Review Agent", "status": "running",
                             "jira": "active", "ui": "disabled"})
    return RedirectResponse(url=FRONTEND_URL, status_code=301)


@app.get("/{path:path}")
async def redirect_non_api(path: str):
    """Redirect any non-API path to the Vercel frontend (UI mode only)."""
    if not _UI_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    # Strip characters that are not safe URL path chars, then normalize to
    # collapse any dot-segments (e.g. ../api/health -> api/health).
    cleaned = re.sub(r'[^a-zA-Z0-9/_.-]', '', path)
    safe_path = posixpath.normpath('/' + cleaned).lstrip('/')
    # Re-check after normalization so dot-segment tricks cannot bypass the guard.
    if safe_path == "api" or safe_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return RedirectResponse(url=f"{FRONTEND_URL}/{safe_path}", status_code=301)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
