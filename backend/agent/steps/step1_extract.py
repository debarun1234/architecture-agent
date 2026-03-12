"""
Step 1 — Extract Context
Parses a design document and extracts structured architectural context using Gemini.
"""
from __future__ import annotations

import json
import re
from typing import Any

SYSTEM_PROMPT = """You are an expert enterprise architect. Analyze the following design document and extract a comprehensive structured architectural context.

Return ONLY valid JSON with this exact schema:
{
  "document_title": "string",
  "document_type": "PRD|HLD|LLD|unknown",
  "system_name": "string",
  "components": [
    {"name": "string", "type": "service|database|cache|queue|gateway|frontend|external", "description": "string", "technology": "string"}
  ],
  "services_and_apis": [
    {"name": "string", "type": "REST|gRPC|GraphQL|WebSocket|event", "endpoint": "string", "operations": ["string"], "consumers": ["string"]}
  ],
  "data_stores": [
    {"name": "string", "type": "RDBMS|NoSQL|cache|object_storage|search|time_series|graph", "technology": "string", "purpose": "string", "data_sensitivity": "high|medium|low"}
  ],
  "traffic_expectations": {
    "peak_qps": "string",
    "avg_qps": "string",
    "throughput_mbps": "string",
    "concurrent_users": "string",
    "data_volume": "string",
    "growth_rate": "string"
  },
  "reliability_requirements": {
    "slo": "string",
    "sla": "string",
    "rpo": "string",
    "rto": "string",
    "availability_target": "string"
  },
  "security_mechanisms": [
    {"mechanism": "string", "description": "string", "coverage": "string"}
  ],
  "architectural_patterns": ["string"],
  "deployment_model": "cloud|on-prem|hybrid|multi-cloud|unknown",
  "cloud_provider": "string",
  "regions": ["string"],
  "notable_gaps": ["string"]
}

If information is not present in the document, use "Not specified" as the value.
Return ONLY the JSON object, no markdown fences or explanation."""


def _clean_json(raw: str) -> str:
    """Strip markdown code fences and extract the JSON blob."""
    raw = raw.strip()
    # Remove ```json ... ``` or ``` ... ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


from vertexai.generative_models import GenerationConfig

async def extract_context(llm, doc_text: str, filename: str) -> dict[str, Any]:
    prompt = f"{SYSTEM_PROMPT}\n\n--- DOCUMENT: {filename} ---\n\n{doc_text[:30000]}"
    try:
        response = await llm.generate_content_async(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json")
        )
        raw = response.text or ""
        return json.loads(_clean_json(raw))
    except Exception as e:
        # Return partial context with raw text preserved
        return {
            "document_title": filename,
            "document_type": "unknown",
            "system_name": "Unknown System",
            "raw_extraction": str(e),
            "parse_error": "LLM output was not valid JSON or API error occurred.",
            "notable_gaps": ["Full structured extraction failed — manual review recommended"],
        }
