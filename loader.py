"""
Excel loader: converts a spreadsheet into PromptRecord objects.

The data-quality audit is guarded by config.audit_enabled so it only runs
during development and never adds startup latency in production.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd

from config import APP_CONFIG, AppConfig
from models import PromptInput, PromptRecord

logger = logging.getLogger("prompt_library.loader")

REQUIRED_COLUMNS: List[str] = [
    "Prompt ID",
    "Prompt Name",
    "Category",
    "Tags/Labels",
    "Prompt Objective",
    "Prompt",
    "Required Inputs",
    "Sample Output",
]


class PromptExcelLoader:
    """Converts an Excel table into a list of PromptRecord objects."""

    @classmethod
    def load_from_excel(
        cls,
        file_path: str,
        config: AppConfig = APP_CONFIG,
    ) -> List[PromptRecord]:
        path = Path(file_path)
        if not path.exists():
            logger.warning("Excel file not found: %s", path.resolve())
            return []

        df = pd.read_excel(path, sheet_name=config.prompts_sheet)
        df.columns = [str(c).strip() for c in df.columns]
        logger.info(
            "Loaded sheet '%s': %d rows, %d columns",
            config.prompts_sheet, len(df), len(df.columns),
        )

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        # Audit is intentionally gated — never runs in production
        if config.audit_enabled:
            cls._audit_dataframe(df, config)

        records: List[PromptRecord] = []
        skipped = 0
        for row_num, (_, row) in enumerate(df.iterrows(), start=2):
            record = cls._row_to_record(row, row_num)
            if record:
                records.append(record)
            else:
                skipped += 1

        logger.info("Loaded %d records, skipped %d rows", len(records), skipped)
        return records

    # ── Audit ─────────────────────────────────────────────────────────────────

    @classmethod
    def _audit_dataframe(cls, df: pd.DataFrame, config: AppConfig) -> None:
        total = len(df)
        if total == 0:
            logger.warning("Audit: sheet is empty")
            return

        logger.info("=== Data audit: %d rows ===", total)

        # 1. Fill-rate per column
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                continue
            filled = df[col].apply(
                lambda v: pd.notna(v) and str(v).strip() != ""
            ).sum()
            pct = filled / total * 100
            level = (
                logging.INFO if pct >= 90
                else logging.WARNING if pct >= 50
                else logging.ERROR
            )
            logger.log(level, "  '%s': %.1f%% filled (%d/%d)", col, pct, filled, total)

        # 2. Duplicate IDs
        id_series = df["Prompt ID"].dropna()
        dup_ids = id_series[id_series.duplicated(keep=False)]
        if not dup_ids.empty:
            logger.error(
                "  Duplicate Prompt IDs: %s", sorted(dup_ids.unique().tolist())
            )
        else:
            logger.info("  Duplicate Prompt IDs: none")

        # 3. Per-row template quality
        ph_re = re.compile(r"\{[^}]+\}")
        short_rows, mismatch_rows = [], []

        for excel_row, (_, row) in enumerate(df.iterrows(), start=2):
            prompt = str(row.get("Prompt", "") or "").strip()
            inputs = str(row.get("Required Inputs", "") or "").strip()
            if prompt and len(prompt) < config.min_prompt_length:
                short_rows.append(excel_row)
            if inputs and prompt and not ph_re.search(prompt):
                mismatch_rows.append(excel_row)

        if short_rows:
            logger.warning(
                "  Short prompts (<%d chars) at rows: %s",
                config.min_prompt_length, short_rows,
            )
        if mismatch_rows:
            logger.warning(
                "  Inputs listed but no {placeholder} in prompt at rows: %s",
                mismatch_rows,
            )

        logger.info("=== Audit complete ===")

    # ── Row parsing ───────────────────────────────────────────────────────────

    @classmethod
    def _row_to_record(
        cls, row: pd.Series, row_index: int
    ) -> Optional[PromptRecord]:
        prompt_id   = cls._safe_int(row.get("Prompt ID"))
        prompt_name = cls._safe_text(row.get("Prompt Name"))

        if prompt_id is None or not prompt_name:
            logger.warning(
                "Row %d skipped: missing Prompt ID (%s) or Prompt Name (%r)",
                row_index, prompt_id, prompt_name,
            )
            return None

        required, optional = cls._parse_inputs(
            cls._safe_text(row.get("Required Inputs"))
        )

        return PromptRecord(
            id=prompt_id,
            name=prompt_name,
            category=cls._safe_text(row.get("Category")) or "Uncategorized",
            tags=cls._parse_tags(row.get("Tags/Labels")),
            prompt_objective=cls._safe_text(row.get("Prompt Objective")),
            prompt_template=cls._safe_text(row.get("Prompt")),
            required_inputs=required,
            optional_inputs=optional,
            expected_result=cls._safe_text(row.get("Sample Output")),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_text(value: Any) -> str:
        return "" if pd.isna(value) else str(value).strip()

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(value) if pd.notna(value) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_tags(value: Any) -> List[str]:
        text = PromptExcelLoader._safe_text(value)
        if not text:
            return []
        for sep in [";", "|", "/"]:
            text = text.replace(sep, ",")
        return [t.strip() for t in text.split(",") if t.strip()]

    @staticmethod
    def _parse_inputs(
        value: str,
    ) -> Tuple[List[PromptInput], List[PromptInput]]:
        """
        Parses the 'Required Inputs' cell into two lists.
        Supports:
          - one item per line
          - comma-separated
          - "Required: a, b" / "Optional: c, d" prefixes
          - markdown bullets (-, *, •)
        """
        if not value:
            return [], []

        required: List[PromptInput] = []
        optional: List[PromptInput] = []

        lines = [ln.strip() for ln in value.splitlines() if ln.strip()]
        if not lines:
            lines = [item.strip() for item in value.split(",") if item.strip()]

        bucket = required
        for raw in lines:
            line  = raw.lstrip("-*• ").strip()
            lower = line.lower()

            if lower.startswith("required:"):
                for item in line.split(":", 1)[1].split(","):
                    item = item.strip()
                    if item:
                        required.append(PromptInput(item, "Provided by user"))
                bucket = required
                continue

            if lower.startswith("optional:"):
                for item in line.split(":", 1)[1].split(","):
                    item = item.strip()
                    if item:
                        optional.append(PromptInput(item, "Optional user input"))
                bucket = optional
                continue

            bucket.append(PromptInput(line, "Provided by user"))

        return required, optional
