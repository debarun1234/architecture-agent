"""
Step 4 — Propose Improvements
Generates actionable architectural recommendations for each detected bottleneck.
"""
from __future__ import annotations

import json
import re
from typing import Any

PROMPT_TEMPLATE = """You are an expert enterprise architect. Based on the bottlenecks identified in a system design review, propose detailed architectural improvements.

SYSTEM CONTEXT:
{context}

DETECTED BOTTLENECKS:
{bottlenecks}

RELEVANT GUIDELINES:
{guidelines}

For each bottleneck, propose one or more concrete improvements.

Return ONLY valid JSON with this exact schema:
{{
  "proposals": [
    {{
      "id": "PROP-001",
      "addresses_bottleneck": "BN-001",
      "title": "Short action title",
      "rationale": "Why this change is needed and what problem it solves",
      "recommended_changes": [
        {{
          "component": "affected component name",
          "change_type": "add|modify|replace|remove",
          "description": "Specific change description",
          "implementation_notes": "Key implementation considerations"
        }}
      ],
      "alternative_patterns": ["Alternative pattern 1", "Alternative pattern 2"],
      "tradeoffs": {{
        "pros": ["Pro 1", "Pro 2"],
        "cons": ["Con 1", "Con 2"]
      }},
      "impact_analysis": {{
        "cost": "increase|decrease|neutral",
        "cost_detail": "Explanation",
        "performance": "increase|decrease|neutral",
        "performance_detail": "Explanation",
        "operations": "increase|decrease|neutral",
        "operations_detail": "Explanation",
        "security": "increase|decrease|neutral",
        "security_detail": "Explanation"
      }},
      "effort": "low|medium|high",
      "priority": "immediate|short_term|long_term"
    }}
  ],
  "quick_wins": ["Description of quick wins that can be done immediately"],
  "roadmap": {{
    "phase_1_immediate": ["Action items"],
    "phase_2_short_term": ["Action items"],
    "phase_3_long_term": ["Action items"]
  }}
}}

Return ONLY the JSON object. Be specific and actionable."""


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _format_guidelines(guidelines: list[dict]) -> str:
    return "\n".join(
        f"[{g['source_id']}] {g['guideline_summary']}"
        for g in guidelines[:15]
    )


from vertexai.generative_models import GenerationConfig

async def propose_improvements(
    llm,
    context: dict,
    bottlenecks: dict,
    guidelines: list[dict],
) -> dict[str, Any]:
    ctx_str = json.dumps(context, indent=2)[:6000]
    bn_str = json.dumps(bottlenecks, indent=2)[:8000]
    guide_str = _format_guidelines(guidelines)

    prompt = PROMPT_TEMPLATE.format(
        context=ctx_str,
        bottlenecks=bn_str,
        guidelines=guide_str,
    )
    
    try:
        response = await llm.generate_content_async(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json")
        )
        raw = response.text or ""
        return json.loads(_clean_json(raw))
    except Exception as e:
        return {
            "proposals": [],
            "quick_wins": [],
            "roadmap": {
                "phase_1_immediate": [],
                "phase_2_short_term": [],
                "phase_3_long_term": [],
            },
            "parse_error": str(e),
        }
