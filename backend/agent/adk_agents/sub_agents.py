"""
ADK Sub-Agents
Each of the 6 review pipeline steps is wrapped as a Google ADK LlmAgent.
Agents communicate strictly via session state — no shared globals.
"""
from __future__ import annotations

import json

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from agent.steps.step2_retrieve import retrieve_knowledge
from agent.steps.step3_detect import detect_bottlenecks
from agent.steps.step4_propose import propose_improvements
from agent.steps.step5_artifacts import generate_artifacts
from agent.steps.step6_verify import verify_and_cite
from agent.steps.step1_extract import extract_context

# ─── Tool wrappers ────────────────────────────────────────────────────────────
# Each tool pulls its inputs from session state, runs computation, writes back.

async def _tool_extract(doc_text: str, filename: str) -> str:
    """Extract structured architectural context from architecture document text."""
    from vertexai.generative_models import GenerativeModel
    import os
    model_name = os.getenv("ADK_MODEL", "gemini-2.0-flash-001")
    llm = GenerativeModel(model_name)
    result = await extract_context(llm, doc_text, filename)
    return json.dumps(result)


async def _tool_retrieve(context_json: str) -> str:
    """Query AlloyDB pgvector knowledge base and return relevant architecture guidelines."""
    context = json.loads(context_json)
    guidelines = await retrieve_knowledge(context)
    return json.dumps(guidelines)


async def _tool_detect(context_json: str, guidelines_json: str) -> str:
    """Detect architectural bottlenecks by cross-referencing context against guidelines."""
    from vertexai.generative_models import GenerativeModel
    import os
    model_name = os.getenv("ADK_MODEL", "gemini-2.0-flash-001")
    llm = GenerativeModel(model_name)
    context = json.loads(context_json)
    guidelines = json.loads(guidelines_json)
    result = await detect_bottlenecks(llm, context, guidelines)
    return json.dumps(result)


async def _tool_propose(context_json: str, bottlenecks_json: str, guidelines_json: str) -> str:
    """Propose concrete architectural improvements for each detected bottleneck."""
    from vertexai.generative_models import GenerativeModel
    import os
    model_name = os.getenv("ADK_MODEL", "gemini-2.0-flash-001")
    llm = GenerativeModel(model_name)
    context = json.loads(context_json)
    bottlenecks = json.loads(bottlenecks_json)
    guidelines = json.loads(guidelines_json)
    result = await propose_improvements(llm, context, bottlenecks, guidelines)
    return json.dumps(result)


async def _tool_artifacts(context_json: str, bottlenecks_json: str, proposals_json: str) -> str:
    """Generate Mermaid diagram, OpenAPI spec, and markdown review summary."""
    from vertexai.generative_models import GenerativeModel
    import os
    model_name = os.getenv("ADK_MODEL", "gemini-2.0-flash-001")
    llm = GenerativeModel(model_name)
    context = json.loads(context_json)
    bottlenecks = json.loads(bottlenecks_json)
    proposals = json.loads(proposals_json)
    result = await generate_artifacts(llm, context, bottlenecks, proposals)
    return json.dumps(result)


async def _tool_verify(results_json: str, guidelines_json: str) -> str:
    """Cross-check every finding against guidelines; mark unsupported claims as Not in Evidence."""
    from vertexai.generative_models import GenerativeModel
    import os
    model_name = os.getenv("ADK_MODEL", "gemini-2.0-flash-001")
    llm = GenerativeModel(model_name)
    results = json.loads(results_json)
    guidelines = json.loads(guidelines_json)
    verified = await verify_and_cite(llm, results, guidelines)
    return json.dumps(verified)


# ─── Sub-Agent definitions ────────────────────────────────────────────────────

extract_agent = LlmAgent(
    name="ContextExtractionAgent",
    description=(
        "Parses architecture/requirement documents and extracts structured context: "
        "components, traffic expectations, reliability targets, security mechanisms, "
        "data stores, architectural patterns, and notable gaps."
    ),
    instruction=(
        "You receive a document via the 'doc_text' and 'filename' fields in the session state. "
        "Call the extract tool with those values. "
        "Store the JSON result in session state under the key 'context'."
    ),
    tools=[FunctionTool(func=_tool_extract)],
    output_key="context",
)

retrieve_agent = LlmAgent(
    name="KnowledgeRetrievalAgent",
    description=(
        "Queries the AlloyDB pgvector knowledge base using semantic embeddings to retrieve "
        "the most relevant architecture guidelines, design patterns, anti-patterns, "
        "security policies, and cloud reference architectures."
    ),
    instruction=(
        "Read 'context' from session state. "
        "Call the retrieve tool with the context JSON. "
        "Store the resulting guidelines JSON under 'retrieved_guidelines'."
    ),
    tools=[FunctionTool(func=_tool_retrieve)],
    output_key="retrieved_guidelines",
)

detect_agent = LlmAgent(
    name="BottleneckDetectionAgent",
    description=(
        "Analyses the extracted system context against the retrieved guidelines to identify "
        "architectural bottlenecks, single points of failure, security gaps, scalability risks, "
        "and operational deficiencies — each with severity and supporting evidence."
    ),
    instruction=(
        "Read 'context' and 'retrieved_guidelines' from session state. "
        "Call the detect tool. "
        "Store the result under 'bottlenecks'."
    ),
    tools=[FunctionTool(func=_tool_detect)],
    output_key="bottlenecks",
)

propose_agent = LlmAgent(
    name="ImprovementProposalAgent",
    description=(
        "Generates concrete, prioritised architectural improvement proposals for each bottleneck. "
        "Includes impact analysis (cost/performance/ops/security), tradeoffs, effort estimate, "
        "quick wins, and a phased implementation roadmap."
    ),
    instruction=(
        "Read 'context', 'bottlenecks', and 'retrieved_guidelines' from session state. "
        "Call the propose tool. "
        "Store the result under 'proposed_changes'."
    ),
    tools=[FunctionTool(func=_tool_propose)],
    output_key="proposed_changes",
)

artifacts_agent = LlmAgent(
    name="ArtifactGenerationAgent",
    description=(
        "Produces three review artifacts: a Mermaid sequence diagram of component interactions, "
        "a complete OpenAPI 3.1 specification, and a formal Markdown architecture review summary."
    ),
    instruction=(
        "Read 'context', 'bottlenecks', and 'proposed_changes' from session state. "
        "Call the artifacts tool. "
        "Store the result under 'artifacts'."
    ),
    tools=[FunctionTool(func=_tool_artifacts)],
    output_key="artifacts",
)

verify_agent = LlmAgent(
    name="VerificationAndCitationAgent",
    description=(
        "Audits every finding and proposal against the retrieved knowledge base guidelines. "
        "Assigns verification_status (verified / partially_verified / not_in_evidence) "
        "and confidence scores to each citation. Strict evidence-based reasoning only."
    ),
    instruction=(
        "Read all keys from session state and assemble a 'results' dict containing "
        "'bottlenecks' and 'proposed_changes'. Also read 'retrieved_guidelines'. "
        "Call the verify tool. "
        "Store the result under 'verification'."
    ),
    tools=[FunctionTool(func=_tool_verify)],
    output_key="verification",
)
