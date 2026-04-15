"""
Core data models for the Banking Analytics Prompt Library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PromptInput:
    """Represents one input variable used by a prompt template."""
    name: str
    description: str


@dataclass
class PromptRecord:
    """Represents one prompt entry in the library."""

    id: int
    name: str
    category: str
    tags: List[str]
    prompt_objective: str
    prompt_template: str
    required_inputs: List[PromptInput]
    optional_inputs: List[PromptInput]
    expected_result: str

    # ── Ratings ──────────────────────────────────────────────────────────────
    ratings: List[int] = field(default_factory=list)
    # Parallel list: which session submitted each rating (for dedup later)
    rating_sessions: List[str] = field(default_factory=list)

    # ── Comments ─────────────────────────────────────────────────────────────
    comments: List[str] = field(default_factory=list)
    # ISO-format timestamps, parallel to comments
    comment_timestamps: List[str] = field(default_factory=list)
    # Session IDs, parallel to comments
    comment_sessions: List[str] = field(default_factory=list)
