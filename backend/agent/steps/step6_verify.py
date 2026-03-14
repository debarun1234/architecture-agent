"""
Step 6 — Verify and Cite
Cross-checks every claim against retrieved guidelines; marks unsupported claims "Not in Evidence".
"""
from __future__ import annotations

import json
import re
from typing import Any

from vertexai.generative_models import GenerationConfig

VERIFY_PROMPT = """You are a rigorous enterprise architecture auditor. Review all findings and verify them against the retrieved architecture guidelines.

FULL ANALYSIS RESULTS:
{results}

AVAILABLE GUIDELINES:
{guidelines}

For each bottleneck and proposal, verify that it has supporting evidence from the retrieved guidelines.
Create a citations list and identify unverified claims.

Return ONLY valid JSON with this exact schema:
{{
  "citations": [
    {{
      "finding_id": "BN-001 or PROP-001",
      "finding_title": "Title of the finding",
      "claim": "The specific claim being cited",
      "source_id": "guideline source_id",
      "section_reference": "section reference",
      "guideline_summary": "relevant guideline text",
      "verification_status": "verified|not_in_evidence|partially_verified",
      "confidence": "high|medium|low"
    }}
  ],
  "notes": {{
    "verified_count": 0,
    "not_in_evidence_count": 0,
    "overall_confidence": "high|medium|low",
    "reviewer_notes": "Overall assessment of evidence quality"
  }}
}}

Return ONLY the JSON object."""


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _format_guidelines(guidelines: list[dict]) -> str:
    return "\n".join(
        f"[{g['source_id']}] ({g.get('collection','')}) {g.get('guideline_summary','')}"
        for g in guidelines[:25]
    )


async def verify_and_cite(
    llm,
    results: dict,
    guidelines: list[dict],
) -> dict[str, Any]:
    # Prepare a summary of results for verification
    review_data = {
        "bottlenecks": results.get("bottlenecks", {}).get("bottlenecks", []),
        "proposals": results.get("proposed_changes", {}).get("proposals", []),
    }
    res_str = json.dumps(review_data, indent=2)[:12000]
    guide_str = _format_guidelines(guidelines)

    prompt = VERIFY_PROMPT.format(
        results=res_str,
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
    except Exception:
        # Build minimal citations from available data
        citations = []
        for bn in review_data.get("bottlenecks", []):
            for gid in bn.get("related_guidelines", [])[:2]:
                matching = next(
                    (g for g in guidelines if g["source_id"] == gid), None
                )
                citations.append({
                    "finding_id": bn.get("id", "BN-?"),
                    "finding_title": bn.get("title", ""),
                    "claim": bn.get("description", ""),
                    "source_id": gid,
                    "section_reference": matching.get("section_reference", "N/A") if matching else "N/A",
                    "guideline_summary": matching.get("guideline_summary", "Not in Evidence") if matching else "Not in Evidence",
                    "verification_status": "partially_verified" if matching else "not_in_evidence",
                    "confidence": "low",
                })
        return {
            "citations": citations,
            "notes": {
                "verified_count": 0,
                "not_in_evidence_count": len(citations),
                "overall_confidence": "low",
                "reviewer_notes": "Automated citation fallback — LLM output parse error.",
            },
        }
