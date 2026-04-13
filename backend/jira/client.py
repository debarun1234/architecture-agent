"""
Jira REST API v3 Client
────────────────────────
Thin async wrapper for the Jira operations the orchestrator needs:
  - Transition issue status
  - Post / update comments
  - Fetch issue + comment history

Configuration (environment variables):
  JIRA_BASE_URL      — e.g. https://your-org.atlassian.net
  JIRA_USER_EMAIL    — Atlassian account email (service account)
  JIRA_API_TOKEN     — Atlassian API token (not password)

Status transition IDs vary per Jira project.
Set these env vars to match your project's workflow:
  JIRA_TRANSITION_IN_PROGRESS  — default "21"
  JIRA_TRANSITION_IN_REVIEW    — default "31"
  JIRA_TRANSITION_DONE         — default "41"
  JIRA_TRANSITION_TO_DO        — default "11"  (used to reset on re-open)
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_ORG_ID = os.getenv("JIRA_ORG_ID", "")
JIRA_USER_EMAIL = os.getenv("JIRA_USER_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

# Workflow transition IDs — override in env if your project differs
TRANSITION_TO_DO = os.getenv("JIRA_TRANSITION_TO_DO", "11")
TRANSITION_IN_PROGRESS = os.getenv("JIRA_TRANSITION_IN_PROGRESS", "21")
TRANSITION_IN_REVIEW = os.getenv("JIRA_TRANSITION_IN_REVIEW", "31")
TRANSITION_DONE = os.getenv("JIRA_TRANSITION_DONE", "41")

_TIMEOUT = httpx.Timeout(30.0)


def _auth_headers() -> dict[str, str]:
    token = base64.b64encode(
        f"{JIRA_USER_EMAIL}:{JIRA_API_TOKEN}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─── Issue ────────────────────────────────────────────────────────────────────

async def get_issue(issue_key: str) -> dict[str, Any]:
    """Fetch a full issue including fields and comment list."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json()


# ─── Transitions ──────────────────────────────────────────────────────────────

async def get_transitions(issue_key: str) -> list[dict]:
    """Return available status transitions for an issue."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json().get("transitions", [])


async def transition_issue(issue_key: str, transition_id: str) -> bool:
    """
    Move issue to a new status via transition ID.
    Returns True on success, False if the transition is not available
    (e.g. issue already in that state).
    """
    # Verify the transition is available before attempting it
    available = await get_transitions(issue_key)
    available_ids = {t["id"] for t in available}
    if transition_id not in available_ids:
        logger.warning(
            "Transition %s not available for %s (available: %s)",
            transition_id, issue_key, available_ids,
        )
        return False

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions"
    body = {"transition": {"id": transition_id}}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, headers=_auth_headers(), json=body)
        if resp.status_code == 204:
            logger.info("Transitioned %s → transition=%s", issue_key, transition_id)
            return True
        logger.error(
            "Transition failed for %s: %s %s", issue_key, resp.status_code, resp.text
        )
        return False


# ─── Comments ─────────────────────────────────────────────────────────────────

def _text_to_adf(text: str) -> dict:
    """
    Convert plain markdown-style text to minimal ADF (Atlassian Document Format)
    so Jira renders it as formatted content.
    Handles: headings (#, ##, ###), bullet lists (- ), numbered lists (1. ),
    code blocks (```), horizontal rules (---), bold (**), and plain paragraphs.
    """
    import re
    content_nodes: list[dict] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Heading
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            content_nodes.append({
                "type": "heading",
                "attrs": {"level": min(level, 6)},
                "content": [{"type": "text", "text": heading_text}],
            })
            i += 1
            continue

        # Code block
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip() or "text"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            content_nodes.append({
                "type": "codeBlock",
                "attrs": {"language": lang},
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            })
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^---+$", line.strip()):
            content_nodes.append({"type": "rule"})
            i += 1
            continue

        # Bullet list — collect contiguous bullet items
        if re.match(r"^[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                item_text = re.sub(r"^[-*]\s+", "", lines[i])
                items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": _inline_nodes(item_text),
                    }],
                })
                i += 1
            content_nodes.append({"type": "bulletList", "content": items})
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": _inline_nodes(item_text),
                    }],
                })
                i += 1
            content_nodes.append({"type": "orderedList", "content": items})
            continue

        # Empty line — skip
        if not line.strip():
            i += 1
            continue

        # Default: paragraph
        content_nodes.append({
            "type": "paragraph",
            "content": _inline_nodes(line),
        })
        i += 1

    return {"type": "doc", "version": 1, "content": content_nodes}


def _inline_nodes(text: str) -> list[dict]:
    """Parse inline **bold** and `code` marks into ADF inline nodes."""
    import re
    nodes = []
    pattern = re.compile(r"(\*\*(.+?)\*\*|`(.+?)`)")
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            nodes.append({"type": "text", "text": text[last:m.start()]})
        if m.group(0).startswith("**"):
            nodes.append({
                "type": "text",
                "text": m.group(2),
                "marks": [{"type": "strong"}],
            })
        else:
            nodes.append({
                "type": "text",
                "text": m.group(3),
                "marks": [{"type": "code"}],
            })
        last = m.end()
    if last < len(text):
        nodes.append({"type": "text", "text": text[last:]})
    return nodes or [{"type": "text", "text": text}]


async def add_comment(issue_key: str, text: str) -> str:
    """
    Post a new comment to the issue.
    Returns the comment ID of the created comment.
    """
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    body = {"body": _text_to_adf(text)}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, headers=_auth_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        comment_id = data.get("id", "")
        logger.info("Posted comment %s on %s", comment_id, issue_key)
        return comment_id


async def update_comment(issue_key: str, comment_id: str, text: str) -> None:
    """Update an existing comment in-place."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment/{comment_id}"
    body = {"body": _text_to_adf(text)}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.put(url, headers=_auth_headers(), json=body)
        resp.raise_for_status()
        logger.info("Updated comment %s on %s", comment_id, issue_key)


async def get_comments(issue_key: str) -> list[dict]:
    """Return all comments on an issue, ordered by creation time ascending."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment?orderBy=created"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json().get("comments", [])


async def get_current_status(issue_key: str) -> str:
    """Return the current status name of an issue (e.g. 'In Progress')."""
    issue = await get_issue(issue_key)
    return issue.get("fields", {}).get("status", {}).get("name", "Unknown")


async def search_issues(
    jql: str,
    fields: str = "*all",
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """
    Search for Jira issues using JQL.
    Returns a list of raw issue dicts (same shape as get_issue()).
    """
    url = f"{JIRA_BASE_URL}/rest/api/3/search"
    params = {
        "jql": jql,
        "fields": fields,
        "maxResults": str(max_results),
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_auth_headers(), params=params)
        resp.raise_for_status()
        return resp.json().get("issues", [])


# ─── Convenience status helpers ───────────────────────────────────────────────

async def set_in_progress(issue_key: str) -> None:
    await transition_issue(issue_key, TRANSITION_IN_PROGRESS)

async def set_in_review(issue_key: str) -> None:
    await transition_issue(issue_key, TRANSITION_IN_REVIEW)

async def set_done(issue_key: str) -> None:
    await transition_issue(issue_key, TRANSITION_DONE)

async def set_to_do(issue_key: str) -> None:
    await transition_issue(issue_key, TRANSITION_TO_DO)
