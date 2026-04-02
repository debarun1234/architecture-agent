"""
Agent Orchestrator — coordinates the 6-step architecture review workflow.
"""
from __future__ import annotations

import io
from typing import Any

from agent.steps.step1_extract import extract_context
from agent.steps.step2_retrieve import retrieve_knowledge
from agent.steps.step3_detect import detect_bottlenecks
from agent.steps.step4_propose import propose_improvements
from agent.steps.step5_artifacts import generate_artifacts
from agent.steps.step6_verify import verify_and_cite
from agent.pii_redactor import PIIRedactor
from vertexai.generative_models import GenerativeModel


def _parse_document(content: bytes, ext: str) -> str:
    """Extract plain text from uploaded document bytes."""
    if ext in (".txt", ".md"):
        return content.decode("utf-8", errors="replace")

    if ext == ".pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except Exception as e:
            return f"[PDF parse error: {e}]"

    if ext in (".docx",):
        try:
            from docx import Document
            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            return f"[DOCX parse error: {e}]"

    # Fallback: try raw text decode
    return content.decode("utf-8", errors="replace")


class AgentOrchestrator:
    STEPS = [
        (1, "Extracting Context", 16),
        (2, "Retrieving Knowledge", 33),
        (3, "Detecting Bottlenecks", 50),
        (4, "Proposing Improvements", 66),
        (5, "Generating Artifacts", 83),
        (6, "Verifying & Citing", 99),
    ]

    def __init__(
        self,
        model: str,
        job_id: str,
        jobs: dict,
    ):
        self.model_name = model
        self.job_id = job_id
        self.jobs = jobs
        self.llm = GenerativeModel(model)

    def _update(self, step_num: int, label: str, progress: int, data: Any = None):
        job = self.jobs[self.job_id]
        job["progress"] = progress
        job["steps"][str(step_num)] = {
            "label": label,
            "status": "complete" if data is not None else "running",
            "data": data,
        }

    async def run(self, content: bytes, ext: str, filename: str) -> dict:
        # Parse document
        raw_doc_text = _parse_document(content, ext)

        # Step 0 — "Zero-Trust" Security: Local PII Redaction
        redactor = PIIRedactor()
        doc_text = redactor.redact(raw_doc_text)
        filename = redactor.redact(filename)
        
        # Explicit memory sweep to discard PII
        del raw_doc_text

        results: dict[str, Any] = {}

        # Step 1 — Extract Context
        self._update(1, "Extracting Context", 5)
        context = await extract_context(self.llm, doc_text, filename)
        self._update(1, "Extracting Context", 16, context)
        results["context"] = context

        # Step 2 — Retrieve Knowledge
        self._update(2, "Retrieving Knowledge", 20)
        guidelines = await retrieve_knowledge(context)
        self._update(2, "Retrieving Knowledge", 33, guidelines)
        results["retrieved_guidelines"] = guidelines

        # Step 3 — Detect Bottlenecks
        self._update(3, "Detecting Bottlenecks", 38)
        bottlenecks = await detect_bottlenecks(self.llm, context, guidelines)
        self._update(3, "Detecting Bottlenecks", 50, bottlenecks)
        results["bottlenecks"] = bottlenecks

        # Step 4 — Propose Improvements
        self._update(4, "Proposing Improvements", 55)
        proposals = await propose_improvements(self.llm, context, bottlenecks, guidelines)
        self._update(4, "Proposing Improvements", 66, proposals)
        results["proposed_changes"] = proposals

        # Step 5 — Generate Artifacts
        self._update(5, "Generating Artifacts", 70)
        artifacts = await generate_artifacts(self.llm, context, bottlenecks, proposals)
        self._update(5, "Generating Artifacts", 83, artifacts)
        results["artifacts"] = artifacts

        # Step 6 — Verify & Cite
        self._update(6, "Verifying & Citing", 88)
        verified = await verify_and_cite(self.llm, results, guidelines)
        self._update(6, "Verifying & Citing", 99, verified["citations"])
        results["citations"] = verified["citations"]
        results["verification_notes"] = verified["notes"]

        return results
