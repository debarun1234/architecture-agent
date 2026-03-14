"""
Step 5 — Generate Artifacts
Produces: Mermaid sequence diagram, OpenAPI 3.1 spec, and architecture review summary.
"""
from __future__ import annotations

import json
import re
from typing import Any

MERMAID_PROMPT = """You are an expert enterprise architect. Based on the system context and proposed improvements, generate a Mermaid sequence diagram showing the key interactions between system components.

SYSTEM CONTEXT:
{context}

Rules:
- Use sequenceDiagram notation
- Include all major components and their interactions
- Show both happy path and error paths
- Use activate/deactivate for async operations
- Keep participant names short (no spaces, use CamelCase)
- Maximum 30 lines
- Return ONLY the raw Mermaid diagram code, starting with "sequenceDiagram"
- Do NOT include markdown fences"""

OPENAPI_PROMPT = """You are an API architect. Generate a complete OpenAPI 3.1.0 specification in YAML for the services identified in this system.

SYSTEM CONTEXT:
{context}

Rules:
- Use openapi: 3.1.0
- Include all identified services and their endpoints
- Add proper request/response schemas
- Include security schemes (Bearer token by default)
- Add meaningful descriptions and examples
- Return ONLY valid YAML, no markdown fences"""

SUMMARY_PROMPT = """You are a senior enterprise architect writing a formal architecture review report.

SYSTEM CONTEXT:
{context}

DETECTED BOTTLENECKS:
{bottlenecks}

PROPOSED IMPROVEMENTS:
{proposals}

Write a concise, professional architecture review summary report in Markdown format covering:

1. **Executive Summary** (2-3 sentences)
2. **Architecture Overview** (key components and patterns)
3. **Key Strengths** (2-4 bullet points)
4. **Critical Issues** (from bottleneck analysis, prioritized by severity)
5. **Top 5 Recommendations** (actionable, numbered)
6. **Risk Assessment** (overall risk level and rationale)
7. **Next Steps** (immediate actions)

Be direct and actionable. Use professional language."""


def _clean_mermaid(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:mermaid)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _clean_yaml(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:yaml|yml)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def generate_artifacts(
    llm,
    context: dict,
    bottlenecks: dict,
    proposals: dict,
) -> dict[str, Any]:
    ctx_str = json.dumps(context, indent=2)[:8000]
    bn_str = json.dumps(bottlenecks.get("bottlenecks", []), indent=2)[:4000]
    prop_str = json.dumps(proposals.get("proposals", []), indent=2)[:4000]

    # Generate all 3 artifacts in sequence (Gemini free tier has rate limits)
    artifacts: dict[str, Any] = {}

    # 1. Mermaid Diagram
    try:
        mermaid_resp = await llm.generate_content_async(
            MERMAID_PROMPT.format(context=ctx_str)
        )
        artifacts["mermaid_diagram"] = _clean_mermaid(mermaid_resp.text or "")
    except Exception as e:
        artifacts[
            "mermaid_diagram"] = f"sequenceDiagram\n    %% Error generating diagram: {e}"

    # 2. OpenAPI Spec
    try:
        openapi_resp = await llm.generate_content_async(
            OPENAPI_PROMPT.format(context=ctx_str)
        )
        artifacts["openapi_spec"] = _clean_yaml(openapi_resp.text or "")
    except Exception as e:
        artifacts["openapi_spec"] = f"# Error generating OpenAPI spec: {e}"

    # 3. Review Summary
    try:
        summary_resp = await llm.generate_content_async(
            SUMMARY_PROMPT.format(
                context=ctx_str,
                bottlenecks=bn_str,
                proposals=prop_str,
            )
        )
        artifacts["review_summary"] = summary_resp.text or ""
    except Exception as e:
        artifacts["review_summary"] = f"Error generating summary: {e}"

    # Validate Mermaid starts correctly
    mermaid = artifacts.get("mermaid_diagram", "")
    if not mermaid.startswith("sequenceDiagram"):
        # Attempt to extract the diagram block
        match = re.search(r"sequenceDiagram[\s\S]+", mermaid)
        if match:
            artifacts["mermaid_diagram"] = match.group(0)

    return artifacts
