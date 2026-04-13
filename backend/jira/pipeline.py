"""
Jira Pipeline — Architecture Review Lifecycle
──────────────────────────────────────────────
Shared logic module that drives the full architecture review lifecycle for
Jira stories.  Called by the Jira poller (jira/poller.py).

There is NO webhook dependency here.  The poller discovers stories and
comments by polling the Jira REST API directly.

Two entry points:
  _trigger_pipeline(issue, jobs, model)
      Initial analysis for a newly detected story.
      Lifecycle: → In Progress → 6-step analysis → comment posted → In Review

  _trigger_rereview(issue_key, original_story_text, comment_text,
                    comment_author, prev_results, run_num, jobs, model)
      Re-analysis triggered by a new user comment on an already-reviewed story.
      Lifecycle: → In Progress → re-analysis (evidence-anchored) → comment → In Review / Done

Comment structure posted to Jira (ADF-formatted rich text):
  - Header: run number, timestamp, model
  - Executive summary + evidence quality score
  - Bottlenecks grouped by severity (High → Medium → Low)
    Each entry: area, risk level, description, affected components, evidence citation
  - Proposed improvements with tradeoffs and implementation notes
  - 3-phase implementation roadmap
  - Gap resolution table (re-reviews only) — quotes the user comment addressed
  - "Claims Without Evidence" table for any Not in Evidence findings
  - Anti-hallucination footer

Anti-hallucination contract (enforced in re-review documents):
  1. Address ONLY gaps the user raised in the new comment.
  2. Every claim MUST cite evidence from the original story document.
  3. Unverifiable claims → "Not in Evidence" (never guessed).
  4. No new bottlenecks unless explicitly evidenced by the original document.

Configuration (environment variables):
  JIRA_BASE_URL    — e.g. https://your-org.atlassian.net/
  JIRA_USER_EMAIL  — service-account email; comments from this address are
                     treated as bot output and never trigger re-review loops.
  ADK_MODEL        — Gemini model for the analysis pipeline.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from jira import client as jira_client

logger = logging.getLogger(__name__)

JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "")

# Email of the service account that posts comments.
# Used by the poller to skip bot-authored comments when scanning for new user input.
_BOT_EMAIL: str = os.getenv("JIRA_USER_EMAIL", "").lower()

# IDs of comments posted by this bot — poller uses this set as a secondary guard.
_bot_comment_ids: set[str] = set()


# ─── ADF → plain text ─────────────────────────────────────────────────────────

def _adf_to_text(node: Any) -> str:
    """
    Recursively converts an Atlassian Document Format (ADF) node tree to plain text.
    Handles: doc, paragraph, blockquote, heading, bulletList, orderedList,
    codeBlock, hardBreak, and inline text nodes.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node

    node_type = node.get("type", "")
    content = node.get("content", [])

    if node_type == "text":
        return node.get("text", "")

    if node_type in ("paragraph", "blockquote"):
        return "".join(_adf_to_text(c) for c in content) + "\n"

    if node_type == "heading":
        inner = "".join(_adf_to_text(c) for c in content)
        level = node.get("attrs", {}).get("level", 1)
        return f"{'#' * level} {inner}\n"

    if node_type == "bulletList":
        lines = []
        for item in content:
            item_text = "".join(_adf_to_text(c) for c in item.get("content", []))
            lines.append(f"- {item_text.strip()}")
        return "\n".join(lines) + "\n"

    if node_type == "orderedList":
        lines = []
        for i, item in enumerate(content, 1):
            item_text = "".join(_adf_to_text(c) for c in item.get("content", []))
            lines.append(f"{i}. {item_text.strip()}")
        return "\n".join(lines) + "\n"

    if node_type == "codeBlock":
        lang = node.get("attrs", {}).get("language", "")
        code = "".join(c.get("text", "") for c in content)
        return f"```{lang}\n{code}\n```\n"

    if node_type == "hardBreak":
        return "\n"

    if node_type == "doc":
        return "".join(_adf_to_text(c) for c in content)

    # Fallback: recurse into children
    return "".join(_adf_to_text(c) for c in content)


def _extract_description(description: Any) -> str:
    """
    Convert a Jira field value (ADF dict, plain string, or None) to plain text.
    Used for both story descriptions and comment bodies.
    """
    if not description:
        return "No description provided."
    if isinstance(description, str):
        return description
    if isinstance(description, dict):
        return _adf_to_text(description).strip() or "No description provided."
    return "No description provided."


# ─── Format Jira story as architecture input document ─────────────────────────

def _format_story_as_document(issue: dict) -> tuple[str, str]:
    """
    Convert a Jira issue payload into a structured plain-text document
    that the Step 1 context-extraction agent can parse like a PRD/HLD.

    Returns (doc_text, filename).
    Input: the raw issue dict from the Jira REST API (GET /rest/api/3/issue/{key}
    or from a search result).  No file upload involved.
    """
    fields = issue.get("fields", {})
    key = issue.get("key", "UNKNOWN")
    summary = fields.get("summary", "Untitled Story")
    description = _extract_description(fields.get("description"))

    issue_type = fields.get("issuetype", {}).get("name", "Story")
    priority = fields.get("priority", {}).get("name", "Medium")
    labels = fields.get("labels", [])
    components = [c.get("name", "") for c in fields.get("components", [])]
    reporter = fields.get("reporter", {}).get("displayName", "Unknown")
    assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")

    parent = fields.get("parent") or fields.get("epic") or {}
    epic_key = parent.get("key", "")
    epic_summary = (parent.get("fields") or {}).get("summary", "")
    project_key = fields.get("project", {}).get("key", "")
    issue_url = f"{JIRA_BASE_URL}/browse/{key}"

    doc_text = f"""# Architecture Requirements: {summary}

## Document Metadata
- **Jira Issue**: [{key}]({issue_url})
- **Issue Type**: {issue_type}
- **Priority**: {priority}
- **Reporter**: {reporter}
- **Assignee**: {assignee}
- **Epic**: {epic_key} — {epic_summary}
- **Project**: {project_key}
- **Labels**: {', '.join(labels) if labels else 'None'}
- **Components**: {', '.join(components) if components else 'None'}

## Requirements Description

{description}

## Architecture Review Scope

This document captures the requirements from Jira story {key} under Epic {epic_key}.
The architecture review should assess:
- Technical feasibility and design implications
- Scalability, reliability, and security requirements
- Integration points with existing system components
- Potential architectural bottlenecks or risks
- Recommended implementation patterns and best practices
"""
    return doc_text, f"{key}.jira.md"


# ─── Re-review input document ─────────────────────────────────────────────────

def _build_rereview_document(
    issue_key: str,
    original_story_text: str,
    prev_results: dict,
    comment_text: str,
    comment_author: str,
    run_num: int,
) -> str:
    """
    Assemble the structured re-review document passed to the pipeline.

    The document contains four sections:
      1. AGENT INSTRUCTIONS — explicit anti-hallucination rules
      2. New User Feedback  — the comment that triggered this re-review
      3. Previous Results   — compact summary of prior bottlenecks & proposals
      4. Original Story     — the full story title + description text

    The agent is instructed to address ONLY what the user raised, cite
    evidence from the original story for every claim, and mark any
    unverifiable claim as "Not in Evidence".
    """
    prev_bottlenecks = prev_results.get("bottlenecks", {})
    prev_proposals = prev_results.get("proposed_changes", {})
    prev_summary = prev_bottlenecks.get("summary", {})

    bn_lines = []
    for bn in prev_bottlenecks.get("bottlenecks", [])[:20]:
        bn_lines.append(
            f"- [{bn.get('severity', '?').upper()}] {bn.get('id', '?')}: "
            f"{bn.get('title', '?')} | Area: {bn.get('area', '?')} | "
            f"Evidence: {bn.get('supporting_evidence', 'Not in Evidence')}"
        )
    bn_section = "\n".join(bn_lines) if bn_lines else "- No bottlenecks recorded."

    prop_lines = []
    for p in prev_proposals.get("proposals", [])[:20]:
        prop_lines.append(
            f"- [{p.get('priority', '?').upper()}] {p.get('id', '?')}: "
            f"{p.get('title', '?')} (Effort: {p.get('effort', '?')})"
        )
    prop_section = "\n".join(prop_lines) if prop_lines else "- No proposals recorded."

    total = prev_summary.get('total_issues', 0)
    high = prev_summary.get('high_severity', 0)
    medium = prev_summary.get('medium_severity', 0)
    low = prev_summary.get('low_severity', 0)

    return f"""# Architecture Re-Review: {issue_key} (Run #{run_num})

## AGENT INSTRUCTIONS — READ BEFORE ANALYSIS
This is a re-review. You MUST follow these rules to avoid hallucination:
1. Address ONLY the concerns the user raised in the "New User Feedback" section below.
2. Every claim you make MUST cite evidence from the "Original Story Requirements" section.
3. If a previous bottleneck has been resolved by information in the new comment, mark it RESOLVED.
4. If you cannot find document evidence for a claim, write "Not in Evidence" — do NOT guess.
5. Do NOT introduce new bottlenecks unless they are explicitly evidenced by the original document.
6. Stay strictly within the scope of the original story and the new comment.

---

## New User Feedback (by {comment_author}) — Requires Re-Evaluation

{comment_text}

---

## Previous Architecture Review Results (Run #{run_num - 1})

**Summary**: {total} issues — {high} High, {medium} Medium, {low} Low

### Previously Detected Bottlenecks
{bn_section}

### Previously Proposed Changes
{prop_section}

---

## Original Story Requirements

{original_story_text}
"""


# ─── Format analysis results as Jira comment ──────────────────────────────────

def _format_results_comment(
    results: dict,
    run_num: int,
    model: str = "",
    addressed_comment: str | None = None,
    addressed_by: str | None = None,
) -> str:
    """
    Convert the full pipeline results dict into a markdown string suitable for
    posting as a Jira comment (will be ADF-converted by client.add_comment).

    Sections:
      Header → Executive Summary → Bottlenecks (by severity) →
      Proposed Improvements → Implementation Roadmap →
      Gap Resolution (re-reviews) → Claims Without Evidence → Footer
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run_label = "Initial Analysis" if run_num == 1 else f"Re-Review #{run_num}"
    model_label = f" | **Model**: {model}" if model else ""

    lines: list[str] = [
        f"# Architecture Review — {run_label}",
        f"**Analysis Date**: {now}{model_label}",
        "",
        "---",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────────────
    notes = results.get("verification_notes", {})
    overall_confidence = notes.get("overall_confidence", "N/A")
    verified_count = notes.get("verified_count", "?")
    nie_count = notes.get("not_in_evidence_count", "?")
    reviewer_notes = notes.get("reviewer_notes", "")

    lines += [
        "## Executive Summary",
        reviewer_notes or "_No summary generated._",
        "",
        f"**Evidence Quality**: {str(overall_confidence).upper()} | "
        f"**Verified Claims**: {verified_count} | "
        f"**Not in Evidence**: {nie_count}",
        "",
        "---",
        "",
    ]

    # ── Bottlenecks ──────────────────────────────────────────────────────────
    bottlenecks_data = results.get("bottlenecks", {})
    bottlenecks = bottlenecks_data.get("bottlenecks", [])
    summary = bottlenecks_data.get("summary", {})

    total = summary.get("total_issues", len(bottlenecks))
    high = summary.get("high_severity", 0)
    medium = summary.get("medium_severity", 0)
    low = summary.get("low_severity", 0)
    critical_area = summary.get("most_critical_area", "N/A")

    lines += [
        "## Detected Bottlenecks",
        f"**Total**: {total} | **High**: {high} | **Medium**: {medium} | "
        f"**Low**: {low} | **Critical Area**: {critical_area}",
        "",
    ]

    for sev in ("high", "medium", "low"):
        sev_items = [b for b in bottlenecks if b.get("severity") == sev]
        if not sev_items:
            continue
        lines.append(f"### {sev.upper()} Severity")
        for bn in sev_items:
            affected = ", ".join(bn.get("affected_components", [])) or "N/A"
            evidence = bn.get("supporting_evidence", "Not in Evidence")
            lines += [
                f"**{bn.get('id', '?')}: {bn.get('title', '?')}**",
                f"- **Area**: {bn.get('area', '?')} | "
                f"**Risk**: {bn.get('risk_probability', '?')} probability / "
                f"{bn.get('risk_impact', '?')} impact",
                f"- {bn.get('description', '')}",
                f"- **Affected**: {affected}",
                f"- **Evidence**: _{evidence}_",
                "",
            ]

    if not bottlenecks:
        lines += ["_No bottlenecks detected._", ""]

    lines += ["---", ""]

    # ── Proposed Improvements ────────────────────────────────────────────────
    proposals_data = results.get("proposed_changes", {})
    proposals = proposals_data.get("proposals", [])
    quick_wins = proposals_data.get("quick_wins", [])

    lines += ["## Proposed Improvements", ""]

    if quick_wins:
        lines.append("### Quick Wins (implement immediately)")
        for qw in quick_wins:
            lines.append(f"- {qw}")
        lines.append("")

    for prop in proposals:
        changes = prop.get("recommended_changes", [])
        pros = prop.get("tradeoffs", {}).get("pros", [])
        cons = prop.get("tradeoffs", {}).get("cons", [])
        lines += [
            f"### {prop.get('id', '?')}: {prop.get('title', '?')}",
            f"**Addresses**: {prop.get('addresses_bottleneck', '?')} | "
            f"**Priority**: {prop.get('priority', '?')} | "
            f"**Effort**: {prop.get('effort', '?')}",
            "",
            prop.get("rationale", ""),
            "",
        ]
        if changes:
            lines.append("**Recommended Changes**:")
            for ch in changes:
                lines.append(
                    f"- _{ch.get('component', '?')}_ ({ch.get('change_type', '?')}): "
                    f"{ch.get('description', '?')}"
                )
                if ch.get("implementation_notes"):
                    lines.append(f"  - Notes: {ch['implementation_notes']}")
            lines.append("")
        if pros or cons:
            lines.append(
                f"**Pros**: {'; '.join(pros) or 'None'} | "
                f"**Cons**: {'; '.join(cons) or 'None'}"
            )
            lines.append("")

    if not proposals:
        lines += ["_No proposals generated._", ""]

    lines += ["---", ""]

    # ── Implementation Roadmap ───────────────────────────────────────────────
    roadmap = proposals_data.get("roadmap", {})
    p1 = roadmap.get("phase_1_immediate", [])
    p2 = roadmap.get("phase_2_short_term", [])
    p3 = roadmap.get("phase_3_long_term", [])

    if p1 or p2 or p3:
        lines.append("## Implementation Roadmap")
        if p1:
            lines.append("### Phase 1 — Immediate")
            for item in p1:
                lines.append(f"- {item}")
            lines.append("")
        if p2:
            lines.append("### Phase 2 — Short-term")
            for item in p2:
                lines.append(f"- {item}")
            lines.append("")
        if p3:
            lines.append("### Phase 3 — Long-term")
            for item in p3:
                lines.append(f"- {item}")
            lines.append("")
        lines += ["---", ""]

    # ── Gap Resolution (re-reviews only) ────────────────────────────────────
    if run_num > 1 and addressed_comment:
        author_label = f"by **{addressed_by}**" if addressed_by else ""
        lines += [
            "## Gaps Addressed in This Re-Review",
            f"User comment {author_label}:",
            "",
            f"> {addressed_comment[:1500]}{'…' if len(addressed_comment) > 1500 else ''}",
            "",
            "The analysis above re-evaluates all previously identified bottlenecks "
            "in light of the above feedback. Resolved items are reflected in the "
            "updated bottleneck count.",
            "",
            "---",
            "",
        ]

    # ── Claims Without Evidence ──────────────────────────────────────────────
    citations = results.get("citations", [])
    nie_cites = [c for c in citations if c.get("verification_status") == "not_in_evidence"]

    if nie_cites:
        lines += [
            "## Claims Without Evidence",
            "_The following findings could not be verified against the knowledge base:_",
            "",
        ]
        for c in nie_cites:
            lines.append(
                f"- **{c.get('finding_id', '?')}** ({c.get('finding_title', '?')}): "
                f"{c.get('claim', '?')}"
            )
        lines += ["", "---", ""]

    # ── Footer ───────────────────────────────────────────────────────────────
    lines += [
        "_Generated by Architecture Review Agent — "
        f"Run #{run_num} | {now} | "
        "All claims are evidence-backed against retrieved architecture guidelines. "
        "Claims without document/guideline evidence are explicitly marked "
        "\"Not in Evidence\" and should be validated manually._",
    ]

    return "\n".join(lines)


def _format_error_comment(issue_key: str, error: str, run_num: int = 1) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"# Architecture Review — Run #{run_num} FAILED\n\n"
        f"**Issue**: {issue_key} | **Date**: {now}\n\n"
        "The architecture review pipeline encountered an error and could not complete.\n\n"
        f"**Error**:\n```\n{error[:2000]}\n```\n\n"
        "Please check the backend logs and retry.\n\n"
        "_Generated by Architecture Review Agent_"
    )


# ─── Job store helper ─────────────────────────────────────────────────────────

def _get_latest_completed_job(issue_key: str, jobs: dict) -> tuple[dict | None, int]:
    """
    Return (results_dict, run_number) for the most recently completed job for
    the given Jira issue key.  Returns (None, 0) if no completed job exists.
    """
    def _run_num(j: dict) -> int:
        try:
            return int(j.get("run", 0))
        except (TypeError, ValueError):
            return 0

    matching = [
        j for j in jobs.values()
        if j.get("source") == "jira"
        and j.get("jira_key") == issue_key
        and j.get("status") == "complete"
    ]
    if not matching:
        return None, 0
    latest = max(matching, key=_run_num)
    return latest.get("results"), _run_num(latest)


# ─── Initial analysis pipeline ────────────────────────────────────────────────

async def _trigger_pipeline(issue: dict, jobs: dict, model: str) -> None:
    """
    Run the initial 6-step architecture review for a newly detected Jira story.

    Input:  Jira issue dict (from REST API search or get_issue).
            The story title + description are used directly — no file upload.
    Output: Full structured results posted as a Jira comment (ADF-formatted).

    Lifecycle:
      → In Progress  (immediately, before the pipeline starts)
      → pipeline runs (extract → retrieve → detect → propose → artifacts → verify)
      → results comment posted
      → In Review
      → In Progress / To Do on error (with error comment)
    """
    from agent.adk_agents.orchestrator import _run_pipeline

    key = issue.get("key", "UNKNOWN")
    doc_text, filename = _format_story_as_document(issue)

    job_id = f"jira-{key}-run1-{uuid.uuid4().hex[:8]}"
    jobs[job_id] = {
        "id": job_id,
        "source": "jira",
        "jira_key": key,
        "run": 1,
        "status": "running",
        "progress": 0,
        "steps": {},
        "results": None,
        "error": None,
    }
    logger.info("Jira initial analysis: %s (job=%s)", key, job_id)

    try:
        await jira_client.set_in_progress(key)
    except Exception as exc:
        logger.warning("Could not transition %s to In Progress: %s", key, exc)

    try:
        result = await _run_pipeline(doc_text, filename, model)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["results"] = result
        jobs[job_id]["progress"] = 100

        comment_text = _format_results_comment(result, run_num=1, model=model)
        comment_id = await jira_client.add_comment(key, comment_text)
        _bot_comment_ids.add(comment_id)
        jobs[job_id]["bot_comment_id"] = comment_id

        await jira_client.set_in_review(key)
        logger.info("Jira initial analysis complete: %s → In Review", key)

    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        logger.exception("Jira initial analysis failed for %s: %s", key, exc)
        try:
            ecid = await jira_client.add_comment(key, _format_error_comment(key, str(exc)))
            _bot_comment_ids.add(ecid)
            await jira_client.set_to_do(key)
        except Exception as post_exc:
            logger.warning("Could not post error comment for %s: %s", key, post_exc)


# ─── Re-review pipeline ───────────────────────────────────────────────────────

async def _trigger_rereview(
    issue_key: str,
    original_story_text: str,
    comment_text: str,
    comment_author: str,
    prev_results: dict,
    run_num: int,
    jobs: dict,
    model: str,
) -> None:
    """
    Re-run the 6-step pipeline in response to a new user comment on an
    already-reviewed Jira story.

    The re-review document embeds the original story, the prior findings, and
    the new comment, with explicit anti-hallucination instructions.

    Lifecycle:
      → In Progress  (immediately)
      → pipeline re-runs (evidence-anchored, gap-focused)
      → updated results comment posted (includes gap resolution section)
      → Done  if no High/Medium bottlenecks remain
      → In Review  otherwise
    """
    from agent.adk_agents.orchestrator import _run_pipeline

    doc_text = _build_rereview_document(
        issue_key, original_story_text, prev_results,
        comment_text, comment_author, run_num,
    )
    filename = f"{issue_key}-rereview-{run_num}.jira.md"

    job_id = f"jira-{issue_key}-run{run_num}-{uuid.uuid4().hex[:8]}"
    jobs[job_id] = {
        "id": job_id,
        "source": "jira",
        "jira_key": issue_key,
        "run": run_num,
        "status": "running",
        "progress": 0,
        "steps": {},
        "results": None,
        "error": None,
    }
    logger.info("Jira re-review #%s: %s (job=%s)", run_num, issue_key, job_id)

    try:
        await jira_client.set_in_progress(issue_key)
    except Exception as exc:
        logger.warning("Could not transition %s to In Progress: %s", issue_key, exc)

    try:
        result = await _run_pipeline(doc_text, filename, model)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["results"] = result
        jobs[job_id]["progress"] = 100

        comment_out = _format_results_comment(
            result,
            run_num=run_num,
            model=model,
            addressed_comment=comment_text,
            addressed_by=comment_author,
        )
        cid = await jira_client.add_comment(issue_key, comment_out)
        _bot_comment_ids.add(cid)
        jobs[job_id]["bot_comment_id"] = cid

        # Move to Done only when no High or Medium bottlenecks remain.
        bn_summary = result.get("bottlenecks", {}).get("summary", {})
        remaining_critical = (
            bn_summary.get("high_severity", 1) + bn_summary.get("medium_severity", 1)
        )
        if remaining_critical == 0:
            await jira_client.set_done(issue_key)
            logger.info("Jira re-review #%s complete: %s → Done", run_num, issue_key)
        else:
            await jira_client.set_in_review(issue_key)
            logger.info(
                "Jira re-review #%s complete: %s → In Review (%s critical remaining)",
                run_num, issue_key, remaining_critical,
            )

    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        logger.exception("Jira re-review #%s failed for %s: %s", run_num, issue_key, exc)
        try:
            ecid = await jira_client.add_comment(
                issue_key, _format_error_comment(issue_key, str(exc), run_num)
            )
            _bot_comment_ids.add(ecid)
            await jira_client.set_in_review(issue_key)
        except Exception as post_exc:
            logger.warning("Could not post error comment for %s: %s", issue_key, post_exc)
