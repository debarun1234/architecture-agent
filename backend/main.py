import asyncio
import json
import os
import uuid
from pathlib import Path

import aiofiles
import vertexai
from agent.orchestrator import AgentOrchestrator
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        async with aiofiles.open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=await f.read())
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/analyze")
async def analyze(
    document: UploadFile = File(...),
    model: str = Form(default="gemini-3.1-flash-light-preview-preview"),
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
