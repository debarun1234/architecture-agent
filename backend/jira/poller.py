"""
Jira Story Poller
─────────────────
Polls Jira REST API for new Stories and for new user comments on already-analysed
Stories.  No webhook configuration required — works in any network environment.

Two input paths exist in this system:
  UI upload  → user uploads a PRD/HLD document via the frontend
  Jira path  → this poller reads story title + description + comments directly

Flow (every JIRA_POLL_INTERVAL seconds):
  1. Search Jira for Stories in the configured project / epic (JQL)
  2. For each Story NOT yet seen → queue initial architecture review
     a. Transition issue → In Progress
     b. Run 6-step pipeline using title + description as the input document
     c. Post structured results comment (ADF-formatted)
     d. Transition issue → In Review
  3. For each Story already processed → scan for new user (non-bot) comments
     a. If a new user comment is found → queue re-review
        • Transition → In Progress
        • Run pipeline with original story + prior findings + new comment
        • Post updated results comment
        • If no High/Medium bottlenecks remain → Done; else → In Review

State is kept in-process per story key:
  last_seen_user_comment_id — ID of last user comment we triggered re-review for.
  Baseline is set to the most recent user comment at the time we first discover
  the story (so pre-existing comments never generate spurious re-reviews).

After a server restart all state is lost and stories will be re-analysed.
This is intentional — each run is idempotent from Jira's perspective
(another comment is posted).

Configuration (environment variables):
  JIRA_PROJECT_KEY    — Jira project key to monitor (e.g. "ARCH").  Required.
  JIRA_EPIC_KEY       — Optional: only process stories under this epic key.
  JIRA_POLL_INTERVAL  — Seconds between poll cycles (default: 60).
  JIRA_MAX_STORIES    — Max stories fetched per poll cycle (default: 50).
  JIRA_USER_EMAIL     — Service-account email; comments from this email are
                        treated as bot output and skipped to prevent loops.
  ADK_MODEL           — Gemini model for the analysis pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from jira import client as jira_client

logger = logging.getLogger(__name__)

JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "")
JIRA_EPIC_KEY: str = os.getenv("JIRA_EPIC_KEY", os.getenv("JIRA_TRIGGER_EPIC_KEY", ""))
JIRA_POLL_INTERVAL: int = int(os.getenv("JIRA_POLL_INTERVAL", "60"))
JIRA_MAX_STORIES: int = int(os.getenv("JIRA_MAX_STORIES", "50"))

# Atlassian account email of the bot / service account posting comments.
# Comments authored by this email are skipped when scanning for new user input.
_BOT_EMAIL: str = os.getenv("JIRA_USER_EMAIL", "").lower()


class JiraPoller:
    """Background polling agent for the Jira → architecture review lifecycle."""

    def __init__(self, jobs: dict) -> None:
        self.jobs = jobs
        # Per-story state.
        # key: Jira issue key (e.g. "ARCH-42")
        # value: {
        #   "initial_triggered": bool,
        #   "last_seen_user_comment_id": str | None,
        # }
        self._state: dict[str, dict] = {}

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _is_in_flight(self, issue_key: str) -> bool:
        """Return True if a pipeline job is currently running for this issue."""
        return any(
            j.get("source") == "jira"
            and j.get("jira_key") == issue_key
            and j.get("status") == "running"
            for j in self.jobs.values()
        )

    def _latest_completed_job(self, issue_key: str) -> tuple[dict | None, int]:
        """Return (results, run_number) for the most recent completed job, or (None, 0)."""
        matching = sorted(
            [
                j for j in self.jobs.values()
                if j.get("source") == "jira"
                and j.get("jira_key") == issue_key
                and j.get("status") == "complete"
            ],
            key=lambda j: j["id"],
        )
        if not matching:
            return None, 0
        latest = matching[-1]
        return latest.get("results"), latest.get("run", len(matching))

    def _get_last_user_comment_id(self, story: dict) -> str | None:
        """
        Return the ID of the most recent non-bot comment on the story.
        Used to establish a baseline so pre-existing comments don't trigger
        re-review when the poller first discovers a story.
        """
        comments = story.get("fields", {}).get("comment", {}).get("comments", [])
        for comment in reversed(comments):
            author_email = (
                comment.get("author", {}).get("emailAddress") or ""
            ).lower()
            if _BOT_EMAIL and author_email == _BOT_EMAIL:
                continue
            return str(comment.get("id", ""))
        return None

    def _find_new_user_comment(
        self, story: dict, last_seen_id: str | None
    ) -> dict | None:
        """
        Return the first user (non-bot) comment that appears AFTER last_seen_id.

        If last_seen_id is None it means there were no user comments when we
        first discovered the story.  Any user comment that appears now is new.

        Algorithm:
          - Walk comments in chronological order.
          - Skip all comments until we've passed last_seen_id (if set).
          - Skip comments authored by the bot.
          - Return the first remaining user comment.

        This means bot-posted results comments are naturally skipped; the
        pointer (last_seen_id) only advances when we find and process a
        user comment, so multiple bot comments in sequence are handled cleanly.
        """
        comments = story.get("fields", {}).get("comment", {}).get("comments", [])
        if not comments:
            return None

        passed_cutoff = last_seen_id is None  # if no baseline, start from beginning

        for comment in comments:
            cid = str(comment.get("id", ""))

            if not passed_cutoff:
                if cid == last_seen_id:
                    passed_cutoff = True
                continue  # haven't reached the cutoff yet

            # We are past the last-seen comment — check if this is a user comment
            author_email = (
                comment.get("author", {}).get("emailAddress") or ""
            ).lower()
            if _BOT_EMAIL and author_email == _BOT_EMAIL:
                continue  # skip bot comments

            return comment

        return None

    # ─── Jira search ──────────────────────────────────────────────────────────

    def _build_jql(self) -> str:
        """Build a JQL query scoped to the configured project and optional epic."""
        parts = ["issuetype in (Story, \"User Story\")"]
        if JIRA_PROJECT_KEY:
            parts.append(f"project = {JIRA_PROJECT_KEY}")
        if JIRA_EPIC_KEY:
            # Support both next-gen (parent) and classic (Epic Link) projects
            parts.append(
                f"(parent = {JIRA_EPIC_KEY} OR \"Epic Link\" = {JIRA_EPIC_KEY})"
            )
        parts.append("ORDER BY created DESC")
        return " AND ".join(parts)

    # ─── Poll cycle ───────────────────────────────────────────────────────────

    async def _poll(self) -> None:
        if not JIRA_PROJECT_KEY:
            logger.debug("Jira poller: JIRA_PROJECT_KEY not set — skipping poll")
            return

        jql = self._build_jql()
        try:
            stories = await jira_client.search_issues(
                jql,
                fields=(
                    "summary,description,status,comment,"
                    "issuetype,priority,reporter,assignee,"
                    "labels,components,parent,project"
                ),
                max_results=JIRA_MAX_STORIES,
            )
        except Exception as exc:
            logger.warning("Jira poller: search failed: %s", exc)
            return

        model = os.getenv("ADK_MODEL", "gemini-2.0-flash-001")

        for story in stories:
            key = story.get("key", "")
            if not key:
                continue

            # Never start a new run while one is already in flight for this story
            if self._is_in_flight(key):
                continue

            state = self._state.get(key)

            if state is None:
                # First time we've seen this story.
                # Record the most recent existing user comment as baseline so
                # pre-existing comments don't generate spurious re-reviews.
                baseline = self._get_last_user_comment_id(story)
                self._state[key] = {
                    "initial_triggered": True,
                    "last_seen_user_comment_id": baseline,
                }
                asyncio.create_task(self._run_initial(story, model))
                continue

            # Story already known — look for a new user comment
            new_comment = self._find_new_user_comment(
                story, state["last_seen_user_comment_id"]
            )
            if new_comment:
                # Advance the pointer immediately so a second poll cycle
                # doesn't re-trigger the same comment while re-review is in flight.
                state["last_seen_user_comment_id"] = str(new_comment.get("id", ""))
                asyncio.create_task(self._run_rereview(story, new_comment, model))

    # ─── Initial analysis ─────────────────────────────────────────────────────

    async def _run_initial(self, story: dict, model: str) -> None:
        """
        Queue the initial 6-step architecture review for a newly-discovered story.
        The story title + description are used directly as the input document —
        no file upload required.
        Lifecycle: To Do → In Progress → (analysis) → comment posted → In Review
        """
        from jira.pipeline import _trigger_pipeline
        key = story.get("key", "?")
        logger.info("Jira poller: initial analysis → %s", key)
        await _trigger_pipeline(story, self.jobs, model)

    # ─── Re-review from user comment ──────────────────────────────────────────

    async def _run_rereview(
        self, story: dict, comment: dict, model: str
    ) -> None:
        """
        Queue a re-review triggered by a new user comment.
        Builds a structured document: original story + previous findings + new comment.
        Lifecycle: In Review → In Progress → (re-analysis) → comment posted → In Review / Done
        """
        from jira.pipeline import (
            _format_story_as_document,
            _trigger_rereview,
            _extract_description,
        )

        key = story.get("key", "?")
        prev_results, last_run = self._latest_completed_job(key)

        if prev_results is None:
            logger.warning(
                "Jira poller: no completed analysis for %s — skipping re-review; "
                "will retry after initial analysis completes.",
                key,
            )
            # Rewind the pointer so this comment is retried next poll cycle
            state = self._state.get(key, {})
            # Find the comment before this one to rewind
            comments = story.get("fields", {}).get("comment", {}).get("comments", [])
            cid = str(comment.get("id", ""))
            prev_ids = [
                str(c.get("id", "")) for c in comments if str(c.get("id", "")) < cid
            ]
            state["last_seen_user_comment_id"] = prev_ids[-1] if prev_ids else None
            return

        comment_body = _extract_description(comment.get("body"))
        author_name = comment.get("author", {}).get("displayName", "Unknown")

        # Fetch full issue to get the most up-to-date description
        try:
            full_issue = await jira_client.get_issue(key)
            original_story_text, _ = _format_story_as_document(full_issue)
        except Exception as exc:
            logger.warning("Could not fetch full issue %s: %s — using payload", key, exc)
            original_story_text, _ = _format_story_as_document(story)

        run_num = last_run + 1
        logger.info("Jira poller: re-review #%s → %s (author: %s)", run_num, key, author_name)

        await _trigger_rereview(
            key,
            original_story_text,
            comment_body,
            author_name,
            prev_results,
            run_num,
            self.jobs,
            model,
        )

    # ─── Main loop ────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Perpetual polling loop.  Started as an asyncio background task from main.py.
        Cancelled automatically when the FastAPI server shuts down.
        """
        if not JIRA_PROJECT_KEY:
            logger.warning(
                "Jira poller: JIRA_PROJECT_KEY is not set — poller will not run. "
                "Set JIRA_PROJECT_KEY in .env to enable automatic story monitoring."
            )
            return

        logger.info(
            "Jira poller started | project=%s | epic=%s | interval=%ss | max=%s stories",
            JIRA_PROJECT_KEY,
            JIRA_EPIC_KEY or "(all epics)",
            JIRA_POLL_INTERVAL,
            JIRA_MAX_STORIES,
        )

        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                logger.info("Jira poller stopped.")
                return
            except Exception as exc:
                logger.exception("Jira poller: unexpected error in poll cycle: %s", exc)

            await asyncio.sleep(JIRA_POLL_INTERVAL)
