"""
Central application configuration.
All settings can be overridden via environment variables, making the app
portable across local, staging, and cloud deployments.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    # ── Prompt source ────────────────────────────────────────────────────────
    # Can be overridden when a user uploads a file via the sidebar uploader.
    default_excel_path: str = os.environ.get("EXCEL_FILE_PATH", "prompt_guide.xlsx")

    # ── Feedback store ───────────────────────────────────────────────────────
    # Feedback is decoupled from the prompt source so that uploading a new
    # prompt file never wipes existing ratings and comments.
    feedback_excel_path: str = os.environ.get("FEEDBACK_FILE_PATH", "feedback.xlsx")

    # ── Sheet names ──────────────────────────────────────────────────────────
    prompts_sheet: str = os.environ.get("PROMPTS_SHEET", "Sheet2")
    ratings_sheet: str = os.environ.get("RATINGS_SHEET", "Ratings")
    comments_sheet: str = os.environ.get("COMMENTS_SHEET", "Comments")
    history_sheet: str = os.environ.get("HISTORY_SHEET", "History")

    # ── Feature flags ────────────────────────────────────────────────────────
    # ENABLE_SEED_DATA: set to "true" ONLY in development / demo environments.
    # In production, a missing or empty Excel file should show a clear
    # "no data loaded" message rather than silently serving fake data.
    enable_seed_data: bool = (
        os.environ.get("ENABLE_SEED_DATA", "false").lower() == "true"
    )

    # AUDIT_ENABLED: when "true", runs a full data-quality audit on each load
    # and writes findings to the log. Disable in production to save startup time.
    audit_enabled: bool = (
        os.environ.get("AUDIT_ENABLED", "false").lower() == "true"
    )

    # ── UI / pagination ──────────────────────────────────────────────────────
    page_size: int = int(os.environ.get("PAGE_SIZE", "20"))

    # ── Validation limits ────────────────────────────────────────────────────
    max_comment_length: int = 1_000
    min_prompt_length: int = 20


# Single shared instance imported by all modules
APP_CONFIG = AppConfig()
