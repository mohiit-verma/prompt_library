"""
In-memory repository.

Separated from all UI and persistence logic so the app can later be
upgraded to SQLite, Postgres, or a REST API with minimal changes.

Enhancements over the original:
  - Fuzzy / token-based search (all query tokens must appear in haystack)
  - Multi-category filtering
  - Sort by name, rating, or review count
  - Pagination (returns a page slice + total count)
  - Duplicate ID detection exposed to the UI layer
"""
from __future__ import annotations

import re
import statistics
from typing import Dict, List, Optional, Tuple

from models import PromptRecord

# ── Sort keys ─────────────────────────────────────────────────────────────────
SORT_OPTIONS = ["Name A→Z", "Name Z→A", "Highest Rated", "Most Reviews"]


class PromptRepository:
    """Holds all prompts in memory and exposes search / mutation operations."""

    def __init__(self, seed_data: Optional[List[PromptRecord]] = None):
        self._prompts: Dict[int, PromptRecord] = {}
        self.duplicate_ids: List[int] = []

        if seed_data:
            seen: Dict[int, bool] = {}
            for prompt in seed_data:
                if prompt.id in seen:
                    if prompt.id not in self.duplicate_ids:
                        self.duplicate_ids.append(prompt.id)
                else:
                    seen[prompt.id] = True
                # Last write wins but we still track duplicates
                self._prompts[prompt.id] = prompt

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_all(self) -> List[PromptRecord]:
        return list(self._prompts.values())

    def get_by_id(self, prompt_id: int) -> Optional[PromptRecord]:
        return self._prompts.get(prompt_id)

    def categories(self) -> List[str]:
        """Returns sorted list of all unique categories (no 'All' sentinel)."""
        return sorted({p.category for p in self._prompts.values()})

    def search(
        self,
        search_text: str = "",
        categories: Optional[List[str]] = None,
        sort_by: str = "Name A→Z",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[PromptRecord], int]:
        """
        Returns (page_results, total_matching_count).

        Args:
            search_text: Space-separated tokens; all must appear somewhere in
                         the combined name/category/tags/objective/template text.
            categories:  None or empty list → all categories.
            sort_by:     One of SORT_OPTIONS.
            page:        1-based page number.
            page_size:   Items per page.
        """
        results: List[PromptRecord] = []
        tokens = _tokenize(search_text)

        for prompt in self._prompts.values():
            # Category filter
            if categories and prompt.category not in categories:
                continue
            # Fuzzy text search
            if tokens and not _all_tokens_present(tokens, _build_haystack(prompt)):
                continue
            results.append(prompt)

        # Sort
        if sort_by == "Name A→Z":
            results.sort(key=lambda p: p.name.lower())
        elif sort_by == "Name Z→A":
            results.sort(key=lambda p: p.name.lower(), reverse=True)
        elif sort_by == "Highest Rated":
            results.sort(
                key=lambda p: -(statistics.mean(p.ratings) if p.ratings else 0)
            )
        elif sort_by == "Most Reviews":
            results.sort(key=lambda p: -len(p.ratings))

        total = len(results)
        start = (page - 1) * page_size
        return results[start : start + page_size], total

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_rating(
        self,
        prompt_id: int,
        rating: int,
        session_id: str = "",
    ) -> bool:
        prompt = self.get_by_id(prompt_id)
        if not prompt:
            return False
        prompt.ratings.append(rating)
        prompt.rating_sessions.append(session_id)
        return True

    def add_comment(
        self,
        prompt_id: int,
        comment: str,
        timestamp: str = "",
        session_id: str = "",
    ) -> bool:
        prompt = self.get_by_id(prompt_id)
        if not prompt:
            return False
        prompt.comments.append(comment)
        prompt.comment_timestamps.append(timestamp)
        prompt.comment_sessions.append(session_id)
        return True


# ── Search helpers ────────────────────────────────────────────────────────────

_SPLIT_RE = re.compile(r"[\s\-_,./]+")


def _tokenize(text: str) -> List[str]:
    """Lowercases and splits on common delimiters; ignores empty tokens."""
    return [t for t in _SPLIT_RE.split(text.lower().strip()) if t]


def _build_haystack(prompt: PromptRecord) -> str:
    return " ".join([
        prompt.name,
        prompt.category,
        " ".join(prompt.tags),
        prompt.prompt_objective or "",
        prompt.prompt_template or "",
        prompt.expected_result or "",
    ]).lower()


def _all_tokens_present(tokens: List[str], haystack: str) -> bool:
    """Returns True when every token appears somewhere in the haystack string."""
    return all(token in haystack for token in tokens)
