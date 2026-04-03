import asyncio
import json
import os
import uuid
from pathlib import Path

import vertexai
from agent.orchestrator import AgentOrchestrator
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from agent.pii_redactor import PIIRedactor
from sse_starlette.sse import EventSourceResponse

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT",
                       "project-ef11010f-3538-4e0c-8f1")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

app = FastAPI(
    title="Enterprise Architecture Review Agent",
    description="AI-powered architecture review system for PRD/HLD/LLD documents",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    # Initialize Vertex AI on startup
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print(f"Vertex AI initialized for project {PROJECT_ID} in {LOCATION}")

    # Pre-warm local PII Redaction NLP pipeline
    PIIRedactor()
    print("PII Redaction NLP engine pre-warmed.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (production: use Redis)
jobs: dict[str, dict] = {}

# Frontend is hosted on Vercel. Root and all non-API paths redirect there.
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://arch-review-ai.vercel.app")


# Single source of truth for available models — both frontends fetch this.
MODELS = [
    {"value": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite", "badge": "Recommended"},
    {"value": "gemini-2.0-flash-001",           "label": "Gemini 2.0 Flash",      "badge": ""},
    {"value": "gemini-2.0-flash-lite-001",      "label": "Gemini 2.0 Flash Lite", "badge": "Fastest"},
    {"value": "gemini-1.5-pro-001",             "label": "Gemini 1.5 Pro",        "badge": "Highest Quality"},
]
DEFAULT_MODEL = MODELS[0]["value"]


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/models")
async def list_models():
    """Return the canonical list of supported Vertex AI models."""
    return {"models": MODELS, "default": DEFAULT_MODEL}


@app.post("/api/analyze")
async def analyze(
    document: UploadFile = File(...),
    model: str = Form(default=DEFAULT_MODEL),
):
    """Upload a design document and start the architecture review workflow."""
    job_id = str(uuid.uuid4())
    content = await document.read()

    # Detect file type and decode text
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

    # Run agent in background
    asyncio.create_task(
        run_agent(job_id, content, ext, filename, model)
    )

    return {"job_id": job_id, "status": "pending"}


async def run_agent(
    job_id: str,
    content: bytes,
    ext: str,
    filename: str,
    model: str,
):
    jobs[job_id]["status"] = "running"
    try:
        orchestrator = AgentOrchestrator(
            model=model,
            job_id=job_id,
            jobs=jobs,
        )
        result = await orchestrator.run(content, ext, filename)
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["results"] = result
        jobs[job_id]["progress"] = 100
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


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
            content={"status": job["status"],
                     "message": "Analysis still in progress"},
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
                    "data": json.dumps({
                        "status": status,
                        "error": job.get("error"),
                    }),
                }
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@app.get("/")
async def redirect_root():
    """Redirect browser traffic at root to the Vercel-hosted frontend."""
    return RedirectResponse(url=FRONTEND_URL, status_code=301)


@app.get("/{path:path}")
async def redirect_non_api(path: str):
    """Redirect any non-API path to the Vercel frontend (e.g. /about, /results)."""
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return RedirectResponse(url=f"{FRONTEND_URL}/{path}", status_code=301)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
