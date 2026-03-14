"""
Step 3 — Detect Bottlenecks
Analyzes the extracted context against retrieved guidelines to identify architectural risks.
"""
from __future__ import annotations

import json
import re
from typing import Any

from vertexai.generative_models import GenerationConfig

PROMPT_TEMPLATE = """You are a senior enterprise architect conducting a critical architecture review.

EXTRACTED SYSTEM CONTEXT:
{context}

RETRIEVED ARCHITECTURE GUIDELINES:
{guidelines}

Analyze the system design and identify ALL architectural bottlenecks, risks, and vulnerabilities.

Return ONLY valid JSON with this exact schema:
{{
  "bottlenecks": [
    {{
      "id": "BN-001",
      "area": "scalability|reliability|data_consistency|security|operational|performance|cost",
      "severity": "high|medium|low",
      "title": "Short descriptive title",
      "description": "Detailed description of the issue",
      "supporting_evidence": "Specific quotes or observations from the design document",
      "related_guidelines": ["source_id of relevant guideline"],
      "affected_components": ["component names"],
      "risk_probability": "high|medium|low",
      "risk_impact": "high|medium|low"
    }}
  ],
  "summary": {{
    "total_issues": 0,
    "high_severity": 0,
    "medium_severity": 0,
    "low_severity": 0,
    "most_critical_area": "string"
  }}
}}

Be thorough. Check for:
- Single points of failure
- Missing circuit breakers or retry logic
- Lack of rate limiting
- Authentication/authorization gaps
- Missing data encryption at rest/transit
- No observability (metrics, logs, traces)
- Tight coupling between services
- Missing database indexing or query optimization
- No disaster recovery plan
- Hardcoded configuration
- Missing API versioning
- N+1 query problems
- Lack of idempotency

If evidence is missing for a claim, mark supporting_evidence as "Not in Evidence".
Return ONLY the JSON object."""


def _format_guidelines(guidelines: list[dict]) -> str:
    top = guidelines[:20]
    lines = []
    for g in top:
        lines.append(
            f"[{g['source_id']}] ({g['collection']}) {g['guideline_summary']}"
        )
    return "\n".join(lines)


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def detect_bottlenecks(
    llm, context: dict, guidelines: list[dict]
) -> dict[str, Any]:
    ctx_str = json.dumps(context, indent=2)[:12000]
    guide_str = _format_guidelines(guidelines)

    prompt = PROMPT_TEMPLATE.format(
        context=ctx_str,
        guidelines=guide_str,
    )

    try:
        response = await llm.generate_content_async(
            prompt,
            generation_config=GenerationConfig(
                response_mime_type="application/json")
        )
        raw = response.text or ""
        return json.loads(_clean_json(raw))
    except Exception as e:
        # Return structured fallback
        return {
            "bottlenecks": [{
                "id": "BN-001",
                "area": "operational",
                "severity": "high",
                "title": "Bottleneck detection parse error",
                "description": "LLM output could not be parsed as JSON or API error occurred.",
                "supporting_evidence": "Not in Evidence",
                "related_guidelines": [],
                "affected_components": [],
                "risk_probability": "medium",
                "risk_impact": "medium",
            }],
            "summary": {
                "total_issues": 1,
                "high_severity": 1,
                "medium_severity": 0,
                "low_severity": 0,
                "most_critical_area": "operational",
            },
            "raw": str(e),
        }
