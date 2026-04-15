"""
Service layer: business logic between the UI and the repository / feedback layer.
"""
from __future__ import annotations

import io
import statistics
import textwrap
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import APP_CONFIG, AppConfig
from feedback import (
    append_comment,
    append_history,
    append_rating,
    load_history,
)
from models import PromptRecord
from repository import PromptRepository


class PromptService:
    """Orchestrates reads, writes, and data transformations."""

    def __init__(
        self,
        repository: PromptRepository,
        config: AppConfig = APP_CONFIG,
    ):
        self.repository = repository
        self.config = config

    # ── Prompt detail ─────────────────────────────────────────────────────────

    def get_prompt_detail(self, prompt_id: int) -> Dict[str, Any]:
        """Returns a fully-rendered detail dict for the UI layer."""
        prompt = self.repository.get_by_id(prompt_id)
        if not prompt:
            return _empty_detail()

        avg_rating = (
            round(statistics.mean(prompt.ratings), 2) if prompt.ratings else None
        )

        required_inputs = (
            "\n".join(f"• {i.name}: {i.description}" for i in prompt.required_inputs)
            or "None"
        )
        optional_inputs = (
            "\n".join(f"• {i.name}: {i.description}" for i in prompt.optional_inputs)
            or "None"
        )

        # Build comment lines with timestamps
        comment_lines = []
        for idx, comment in enumerate(prompt.comments):
            ts = (
                prompt.comment_timestamps[idx]
                if idx < len(prompt.comment_timestamps)
                else ""
            )
            pretty_ts = _format_timestamp(ts) if ts else ""
            line = f"• {comment}"
            if pretty_ts:
                line += f"  [{pretty_ts}]"
            comment_lines.append(line)
        comments_text = "\n".join(comment_lines) or "No comments yet"

        rating_summary = (
            f"Average: {avg_rating}/5 from {len(prompt.ratings)} review(s)"
            if avg_rating is not None
            else "No ratings yet"
        )

        return {
            "name":            prompt.name,
            "category":        prompt.category,
            "tags":            prompt.tags,           # list, not string
            "objective":       prompt.prompt_objective,
            "required_inputs": required_inputs,
            "optional_inputs": optional_inputs,
            "expected_result": prompt.expected_result,
            "rating_summary":  rating_summary,
            "avg_rating":      avg_rating,
            "rating_count":    len(prompt.ratings),
            "comments":        comments_text,
            "prompt_template": (prompt.prompt_template or "").strip(),
            "copy_payload":    _build_copy_payload(prompt),
        }

    # ── Feedback ──────────────────────────────────────────────────────────────

    def submit_rating(
        self,
        prompt_id: int,
        rating: int,
        session_id: str = "",
    ) -> str:
        if not prompt_id:
            return "Please select a prompt before rating."
        if not (1 <= rating <= 5):
            return "Rating must be between 1 and 5."

        ok = self.repository.add_rating(prompt_id, rating, session_id)
        if not ok:
            return "Unable to submit rating: prompt not found."

        try:
            append_rating(
                self.config.feedback_excel_path, prompt_id, rating, session_id, self.config
            )
        except Exception as exc:
            return f"Rating saved in session but could not persist to file: {exc}"

        return "Rating submitted successfully."

    def submit_comment(
        self,
        prompt_id: int,
        comment: str,
        session_id: str = "",
    ) -> str:
        if not prompt_id:
            return "Please select a prompt before commenting."
        if not comment or not comment.strip():
            return "Comment cannot be empty."
        if len(comment) > self.config.max_comment_length:
            return (
                f"Comment is too long "
                f"({len(comment)}/{self.config.max_comment_length} characters)."
            )

        ts = datetime.now().isoformat(timespec="seconds")
        ok = self.repository.add_comment(prompt_id, comment.strip(), ts, session_id)
        if not ok:
            return "Unable to add comment: prompt not found."

        try:
            append_comment(
                self.config.feedback_excel_path,
                prompt_id, comment.strip(), session_id, self.config,
            )
        except Exception as exc:
            return f"Comment saved in session but could not persist to file: {exc}"

        return "Comment added successfully."

    # ── History ───────────────────────────────────────────────────────────────

    def save_history(
        self,
        prompt_id: int,
        prompt_name: str,
        filled_values: Dict[str, str],
        session_id: str = "",
    ) -> str:
        try:
            append_history(
                self.config.feedback_excel_path,
                prompt_id, prompt_name, filled_values, session_id, self.config,
            )
            return "Saved to history."
        except Exception as exc:
            return f"Could not save history: {exc}"

    def get_history(self) -> List[Dict[str, Any]]:
        return load_history(self.config.feedback_excel_path, self.config)

    # ── Export ────────────────────────────────────────────────────────────────

    def export_filtered_csv(self, prompts: List[PromptRecord]) -> bytes:
        """Serialises a list of prompts to CSV bytes for st.download_button."""
        rows = []
        for p in prompts:
            avg = (
                round(statistics.mean(p.ratings), 2) if p.ratings else ""
            )
            rows.append({
                "Prompt ID":        p.id,
                "Prompt Name":      p.name,
                "Category":         p.category,
                "Tags":             ", ".join(p.tags),
                "Objective":        p.prompt_objective,
                "Prompt Template":  p.prompt_template,
                "Required Inputs":  ", ".join(i.name for i in p.required_inputs),
                "Optional Inputs":  ", ".join(i.name for i in p.optional_inputs),
                "Sample Output":    p.expected_result,
                "Avg Rating":       avg,
                "Review Count":     len(p.ratings),
            })
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        return buf.getvalue()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty_detail() -> Dict[str, Any]:
    return {
        "name": "", "category": "", "tags": [], "objective": "",
        "required_inputs": "None", "optional_inputs": "None",
        "expected_result": "", "rating_summary": "No ratings yet",
        "avg_rating": None, "rating_count": 0,
        "comments": "No comments yet",
        "prompt_template": "", "copy_payload": "",
    }


def _build_copy_payload(prompt: PromptRecord) -> str:
    """Generates a structured, copy-ready block for end users."""
    req_help = (
        "\n".join(f"  • {i.name}: {i.description}" for i in prompt.required_inputs)
        or "  • None"
    )
    opt_help = (
        "\n".join(f"  • {i.name}: {i.description}" for i in prompt.optional_inputs)
        or "  • None"
    )
    return textwrap.dedent(f"""
        Prompt ID      : {prompt.id}
        Prompt Name    : {prompt.name}
        Category       : {prompt.category}
        Tags           : {', '.join(prompt.tags)}
        Objective      : {prompt.prompt_objective}

        Required Inputs:
        {req_help}

        Optional Inputs:
        {opt_help}

        Prompt Template:
        {prompt.prompt_template}

        Sample Output:
        {prompt.expected_result}
    """).strip()


def _format_timestamp(ts: str) -> str:
    """Returns a human-friendly relative time string."""
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now()
        diff = now - dt
        if diff.days >= 1:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours >= 1:
            return f"{hours}h ago"
        minutes = diff.seconds // 60
        return f"{max(minutes, 1)}m ago"
    except (ValueError, TypeError):
        return ts
