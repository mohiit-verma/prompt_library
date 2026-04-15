"""
Banking Analytics Prompt Library — Streamlit application.

Enhancements over v1:
  UI       — interactive placeholder builder, clickable tag chips,
             visual star ratings, sort dropdown, multi-category filter
  Func     — Excel file uploader, fuzzy search, comment timestamps,
             export filtered results to CSV
  Code     — HTML-escaped field boxes, type-safe config, guarded session
             init, pagination for large libraries
  Data     — duplicate ID warnings, session-tracked feedback,
             filled-prompt history tab, seed data behind a flag
"""
from __future__ import annotations

import html
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

import streamlit as st

from config import APP_CONFIG
from feedback import load_feedback
from loader import PromptExcelLoader
from models import PromptRecord
from repository import SORT_OPTIONS, PromptRepository
from service import PromptService
from ui_helpers import (
    field_box,
    render_copy_button,
    render_placeholder_builder,
    render_star_display,
    render_tag_chips,
)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("prompt_library")

# ── Page config (must be first Streamlit call) ────────────────────────────────

st.set_page_config(
    page_title="Banking Analytics Prompt Library",
    page_icon="📚",
)

# ── Global styles ─────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .main .block-container { max-width: 1100px; padding-top: 2rem; padding-bottom: 2rem; }

    .app-note    { color: #6b7280; font-size: 0.95rem; margin-bottom: 1rem; }
    .field-label { font-size: 0.82rem; font-weight: 600; color: #6b7280; margin-bottom: 0.25rem; }
    .field-box   {
        border: 1px solid #e5e7eb; border-radius: 8px;
        padding: 0.75rem 0.9rem; background: #ffffff;
        margin-bottom: 0.85rem; white-space: pre-wrap;
    }

    /* Hide the Streamlit label for tag chip buttons */
    div[data-testid="stButton"] > button[kind="secondary"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Seed data (dev / demo only) ───────────────────────────────────────────────

def _get_seed_prompts() -> List[PromptRecord]:
    from models import PromptInput
    return [
        PromptRecord(
            id=1,
            name="Credit Risk Summary Generator",
            category="Risk Analytics",
            tags=["credit-risk", "portfolio", "summary"],
            prompt_objective="Summarize credit portfolio performance and surface management actions.",
            prompt_template=(
                "You are a banking analytics expert. Analyse the following credit portfolio data: "
                "{portfolio_data}. Focus on delinquency trends, segment concentration, early warning "
                "signals, and recommended risk actions for management."
            ),
            required_inputs=[PromptInput("portfolio_data", "Portfolio snapshot and delinquency measures.")],
            optional_inputs=[
                PromptInput("time_period", "Reporting month or quarter."),
                PromptInput("region", "Geography or branch segmentation."),
            ],
            expected_result="A concise risk summary with trends, red flags, and management recommendations.",
            ratings=[5, 4],
            rating_sessions=["demo", "demo"],
            comments=["Very useful for portfolio review meetings."],
            comment_timestamps=["2024-01-15T09:00:00"],
            comment_sessions=["demo"],
        ),
        PromptRecord(
            id=2,
            name="Fraud Pattern Investigation",
            category="Fraud Analytics",
            tags=["fraud", "transactions", "anomaly"],
            prompt_objective="Identify suspicious transaction patterns and prioritise investigation.",
            prompt_template=(
                "Review the transaction anomaly data: {transaction_data}. Identify suspicious patterns, "
                "possible fraud typologies, customer segments impacted, and the likely next investigation steps."
            ),
            required_inputs=[PromptInput("transaction_data", "Transaction records and anomaly scores.")],
            optional_inputs=[
                PromptInput("historical_baseline", "Normal transaction behaviour benchmark."),
                PromptInput("channel", "ATM, card, mobile, branch, or online."),
            ],
            expected_result="A structured fraud analysis highlighting patterns, risk severity, and investigation priorities.",
            ratings=[4, 4, 5],
            rating_sessions=["demo", "demo", "demo"],
            comments=["Good for first-level fraud reviews."],
            comment_timestamps=["2024-01-16T10:30:00"],
            comment_sessions=["demo"],
        ),
        PromptRecord(
            id=3,
            name="Customer Churn Insight Builder",
            category="Customer Analytics",
            tags=["churn", "retention", "segmentation"],
            prompt_objective="Explain attrition drivers and suggest segment-level retention actions.",
            prompt_template=(
                "Using this customer attrition dataset: {customer_data}, identify the top churn drivers, "
                "high-risk segments, and personalised retention strategies a retail bank can deploy."
            ),
            required_inputs=[PromptInput("customer_data", "Customer profile, usage, and attrition indicators.")],
            optional_inputs=[
                PromptInput("campaign_history", "Previous retention campaigns and outcomes."),
                PromptInput("lifecycle_stage", "New, growth, or mature customer stage."),
            ],
            expected_result="Churn driver analysis with segment-level action recommendations.",
            ratings=[5],
            rating_sessions=["demo"],
            comments=[],
            comment_timestamps=[],
            comment_sessions=[],
        ),
        PromptRecord(
            id=4,
            name="Liquidity Dashboard Narrative",
            category="Treasury Analytics",
            tags=["liquidity", "treasury", "dashboard", "narrative"],
            prompt_objective="Convert treasury metrics into an executive liquidity narrative.",
            prompt_template=(
                "Turn the following treasury metrics into an executive narrative: {liquidity_metrics}. "
                "Comment on coverage, funding stability, short-term stress points, and actions needed."
            ),
            required_inputs=[PromptInput("liquidity_metrics", "Treasury ratios and funding data.")],
            optional_inputs=[PromptInput("stress_scenarios", "Scenario assumptions and stress-test outputs.")],
            expected_result="An executive-ready treasury narrative summarising the liquidity position.",
            ratings=[],
            rating_sessions=[],
            comments=[],
            comment_timestamps=[],
            comment_sessions=[],
        ),
    ]


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_records_from_path(excel_path: str) -> List[PromptRecord]:
    """Loads records from an Excel file and merges feedback from the feedback store."""
    try:
        records = PromptExcelLoader.load_from_excel(excel_path, APP_CONFIG)
    except Exception as exc:
        st.sidebar.error(f"Failed to load prompts: {exc}")
        logger.error("Excel load error: %s", exc)
        records = []

    if not records:
        if APP_CONFIG.enable_seed_data:
            logger.info("No records from Excel; using seed data (ENABLE_SEED_DATA=true)")
            records = _get_seed_prompts()
        else:
            return []

    # Merge feedback
    try:
        ratings_map, comments_map = load_feedback(
            APP_CONFIG.feedback_excel_path, APP_CONFIG
        )
        for r in records:
            rb = ratings_map.get(r.id, {})
            r.ratings         = rb.get("ratings", [])
            r.rating_sessions = rb.get("sessions", [])
            cb = comments_map.get(r.id, {})
            r.comments           = cb.get("comments", [])
            r.comment_timestamps = cb.get("timestamps", [])
            r.comment_sessions   = cb.get("sessions", [])
    except Exception as exc:
        logger.error("Feedback merge error: %s", exc)

    return records


def _build_repo(records: List[PromptRecord]) -> PromptRepository:
    return PromptRepository(seed_data=records)


# ── Session state bootstrap ───────────────────────────────────────────────────

def _init_session() -> None:
    """
    Initialises all session-state keys exactly once per browser session.
    Guards against re-initialising on every Streamlit rerun.
    """
    if st.session_state.get("_session_initialised"):
        return

    st.session_state.session_id            = str(uuid.uuid4())
    st.session_state.selected_prompt_id    = None
    st.session_state.current_page          = 1
    st.session_state.search_text           = ""
    st.session_state.selected_categories   = []
    st.session_state.sort_by               = "Name A→Z"
    st.session_state.active_tag_filters    = []
    st.session_state.uploaded_file_hash    = None
    st.session_state.repo                  = None
    st.session_state._session_initialised  = True


def _get_or_build_repo(file_bytes: Optional[bytes] = None) -> PromptRepository:
    """
    Returns the cached in-memory repository.
    Rebuilds only when a new file is uploaded (hash changes) or on first load.
    """
    current_hash = hash(file_bytes) if file_bytes is not None else "default"

    if (
        st.session_state.repo is None
        or st.session_state.uploaded_file_hash != current_hash
    ):
        if file_bytes is not None:
            # Write uploaded bytes to a temp file, load, then delete
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                records = _load_records_from_path(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            records = _load_records_from_path(APP_CONFIG.default_excel_path)

        st.session_state.repo               = _build_repo(records)
        st.session_state.uploaded_file_hash = current_hash
        # Reset navigation state when source changes
        st.session_state.current_page     = 1
        st.session_state.selected_prompt_id = None

    return st.session_state.repo


# ── App entrypoint ────────────────────────────────────────────────────────────

_init_session()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("📂 Data source")
    uploaded_file = st.file_uploader(
        "Upload prompt library Excel",
        type=["xlsx"],
        help=(
            "Upload your prompt_guide.xlsx. The app will reload prompts from this file. "
            "Feedback (ratings, comments) is always stored in feedback.xlsx alongside the app."
        ),
    )
    file_bytes: Optional[bytes] = uploaded_file.read() if uploaded_file else None

    if uploaded_file:
        st.success(f"Using: {uploaded_file.name}")
    else:
        default_exists = Path(APP_CONFIG.default_excel_path).exists()
        if default_exists:
            st.info(f"Using: {APP_CONFIG.default_excel_path}")
        else:
            if APP_CONFIG.enable_seed_data:
                st.warning("No Excel file found — showing sample prompts.")
            else:
                st.error(
                    "No Excel file found. Upload a file above or place "
                    f"`{APP_CONFIG.default_excel_path}` next to this script."
                )

    st.divider()
    st.caption(f"Session: `{st.session_state.session_id[:8]}…`")

# ── Build repo and service ────────────────────────────────────────────────────

repo    = _get_or_build_repo(file_bytes)
service = PromptService(repo, APP_CONFIG)

# ── Duplicate ID warning ──────────────────────────────────────────────────────

if repo.duplicate_ids:
    st.warning(
        f"⚠️ Duplicate Prompt IDs detected in the source file: "
        f"`{repo.duplicate_ids}`. The last row for each duplicate ID was kept. "
        "Please fix the source file to avoid missing prompts."
    )

# ── Main title + tabs ─────────────────────────────────────────────────────────

st.title("Banking Analytics Prompt Library")

tab_library, tab_history, tab_about = st.tabs(["Prompt Library", "History", "About"])


# ════════════════════════════════════════════════════════════════════════════════
# TAB: About
# ════════════════════════════════════════════════════════════════════════════════

with tab_about:
    st.subheader("About this app")
    st.markdown(
        """
        ### Features
        - **Interactive placeholder builder** — fill `{variables}` live and copy a ready-to-use prompt
        - **Fuzzy search** — all search tokens must appear anywhere in the prompt content
        - **Clickable tag chips** — click any tag to filter the library instantly
        - **Visual star ratings** — filled / empty star display alongside the numeric summary
        - **Multi-category filter** — combine any number of categories
        - **Sort options** — by name, average rating, or review count
        - **Excel file uploader** — drag and drop a new prompt library without touching the filesystem
        - **Comment timestamps** — see when each comment was left
        - **Export to CSV** — download the current filtered results
        - **History tab** — review every prompt you have filled and copied this session
        - **Feedback persistence** — ratings and comments saved to `feedback.xlsx`

        ### Required Excel columns
        `Prompt ID` · `Prompt Name` · `Category` · `Tags/Labels` ·
        `Prompt Objective` · `Prompt` · `Required Inputs` · `Sample Output`

        ### Run locally
        ```bash
        pip install streamlit pandas openpyxl
        streamlit run app.py
        ```

        ### Environment variables
        | Variable | Default | Purpose |
        |---|---|---|
        | `EXCEL_FILE_PATH` | `prompt_guide.xlsx` | Default prompt source |
        | `FEEDBACK_FILE_PATH` | `feedback.xlsx` | Ratings / comments store |
        | `PROMPTS_SHEET` | `Sheet2` | Sheet name for prompts |
        | `ENABLE_SEED_DATA` | `false` | Show sample prompts when no file found |
        | `AUDIT_ENABLED` | `false` | Run data-quality audit on load |
        | `PAGE_SIZE` | `20` | Prompts per page |
        """
    )


# ════════════════════════════════════════════════════════════════════════════════
# TAB: History
# ════════════════════════════════════════════════════════════════════════════════

with tab_history:
    st.subheader("Filled prompt history")
    st.caption(
        "Every time you click **Save to History** in the builder, an entry is appended here "
        "and persisted to `feedback.xlsx`."
    )

    history_rows = service.get_history()
    if not history_rows:
        st.info("No history yet. Fill placeholders in a prompt and click 'Save to History'.")
    else:
        import pandas as pd
        hist_df = pd.DataFrame(history_rows)
        st.dataframe(
            hist_df,
            use_container_width=True,
            hide_index=True,
            column_order=["Prompt ID", "Prompt Name", "Filled Values", "Created At", "Session ID"],
        )
        csv_bytes = hist_df.to_csv(index=False).encode()
        st.download_button(
            "⬇ Export history CSV",
            data=csv_bytes,
            file_name="prompt_history.csv",
            mime="text/csv",
        )


# ════════════════════════════════════════════════════════════════════════════════
# TAB: Prompt Library
# ════════════════════════════════════════════════════════════════════════════════

with tab_library:

    if not repo.list_all():
        st.info(
            "No prompts loaded. Upload an Excel file in the sidebar or set "
            "`ENABLE_SEED_DATA=true` to see sample prompts."
        )
        st.stop()

    st.markdown(
        '<div class="app-note">'
        "A clean, searchable library of reusable prompts for banking analytics."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Search, sort, category row ────────────────────────────────────────────

    search_col, sort_col = st.columns([3, 1])
    with search_col:
        search_input = st.text_input(
            "Search",
            value=st.session_state.search_text,
            placeholder="Search name, tag, category, or prompt content (space-separated tokens)",
        )
    with sort_col:
        sort_by = st.selectbox(
            "Sort by",
            options=SORT_OPTIONS,
            index=SORT_OPTIONS.index(st.session_state.sort_by),
        )

    all_categories = repo.categories()
    selected_categories: List[str] = st.multiselect(
        "Filter by category",
        options=all_categories,
        default=st.session_state.selected_categories,
        placeholder="All categories",
    )

    # Sync search/filter state
    if search_input != st.session_state.search_text:
        st.session_state.search_text  = search_input
        st.session_state.current_page = 1
    if sorted(selected_categories) != sorted(st.session_state.selected_categories):
        st.session_state.selected_categories = selected_categories
        st.session_state.current_page = 1
    if sort_by != st.session_state.sort_by:
        st.session_state.sort_by      = sort_by
        st.session_state.current_page = 1

    # ── Search ────────────────────────────────────────────────────────────────

    page_results, total_count = repo.search(
        search_text=st.session_state.search_text,
        categories=st.session_state.selected_categories if st.session_state.selected_categories else None,
        sort_by=st.session_state.sort_by,
        page=st.session_state.current_page,
        page_size=APP_CONFIG.page_size,
    )

    # For export we need all matching results (not just the current page)
    all_results, _ = repo.search(
        search_text=st.session_state.search_text,
        categories=st.session_state.selected_categories if st.session_state.selected_categories else None,
        sort_by=st.session_state.sort_by,
        page=1,
        page_size=total_count or 1,
    )

    if not page_results:
        st.info("No prompts found for the current search / filter combination.")
        st.stop()

    # ── Prompt selector ───────────────────────────────────────────────────────

    prompt_choices = {
        f"{p.name}  [{p.category}]": p.id for p in page_results
    }
    current_ids = [p.id for p in page_results]

    if st.session_state.selected_prompt_id not in current_ids:
        st.session_state.selected_prompt_id = current_ids[0]

    selected_label = next(
        (label for label, pid in prompt_choices.items()
         if pid == st.session_state.selected_prompt_id),
        list(prompt_choices.keys())[0],
    )

    sel_col, export_col = st.columns([4, 1])
    with sel_col:
        chosen_label = st.selectbox(
            "Prompt",
            options=list(prompt_choices.keys()),
            index=list(prompt_choices.keys()).index(selected_label),
        )
    with export_col:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        csv_bytes = service.export_filtered_csv(all_results)
        st.download_button(
            "⬇ Export CSV",
            data=csv_bytes,
            file_name="filtered_prompts.csv",
            mime="text/csv",
            help=f"Export all {total_count} matching prompts to CSV",
        )

    st.session_state.selected_prompt_id = prompt_choices[chosen_label]

    # ── Pagination ────────────────────────────────────────────────────────────

    total_pages = max(1, -(-total_count // APP_CONFIG.page_size))
    if total_pages > 1:
        pg_info, pg_prev, pg_next = st.columns([3, 1, 1])
        with pg_info:
            start_item = (st.session_state.current_page - 1) * APP_CONFIG.page_size + 1
            end_item   = min(st.session_state.current_page * APP_CONFIG.page_size, total_count)
            st.caption(
                f"Showing {start_item}–{end_item} of {total_count} prompts  "
                f"(page {st.session_state.current_page} of {total_pages})"
            )
        with pg_prev:
            if st.button("← Prev", disabled=st.session_state.current_page <= 1):
                st.session_state.current_page -= 1
                st.rerun()
        with pg_next:
            if st.button("Next →", disabled=st.session_state.current_page >= total_pages):
                st.session_state.current_page += 1
                st.rerun()

    # ── Prompt detail ─────────────────────────────────────────────────────────

    selected_id     = st.session_state.selected_prompt_id
    selected_prompt = repo.get_by_id(selected_id)
    detail          = service.get_prompt_detail(selected_id)

    left_col, right_col = st.columns(2)

    # ── Left column: metadata ─────────────────────────────────────────────────

    with left_col:
        field_box("Name",     detail["name"])
        field_box("Category", detail["category"])

        # Tags — display as chips; clicking one adds it to the search
        st.markdown(
            '<div class="field-label">Tags</div>', unsafe_allow_html=True
        )
        if detail["tags"]:
            clicked_tag = render_tag_chips(
                detail["tags"],
                selected_tags=st.session_state.active_tag_filters,
                key_prefix=f"detail_tag_{selected_id}",
            )
            if clicked_tag:
                if clicked_tag in st.session_state.active_tag_filters:
                    st.session_state.active_tag_filters.remove(clicked_tag)
                else:
                    st.session_state.active_tag_filters.append(clicked_tag)
                # Apply tag as search token
                st.session_state.search_text  = clicked_tag
                st.session_state.current_page = 1
                st.rerun()
        else:
            st.markdown(
                '<div class="field-box">—</div>', unsafe_allow_html=True
            )

        field_box("Prompt Objective",  detail["objective"])
        field_box("Required Inputs",   detail["required_inputs"])
        field_box("Optional Inputs",   detail["optional_inputs"])

        # Sample output rendered as markdown
        st.markdown(
            '<div class="field-label">Sample Output</div>', unsafe_allow_html=True
        )
        st.markdown(
            '<div class="field-box">',
            unsafe_allow_html=True,
        )
        st.markdown(detail["expected_result"] or "—")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Right column: prompt view + builder ───────────────────────────────────

    with right_col:

        # Raw prompt template view
        st.markdown(
            '<div class="field-label">Prompt template</div>',
            unsafe_allow_html=True,
        )
        st.text_area(
            "Prompt template",
            value=detail["prompt_template"],
            height=220,
            key="prompt_view_area",
            label_visibility="collapsed",
        )
        render_copy_button(
            text=detail["prompt_template"],
            button_label="📋 Copy template",
            element_id=f"copy_view_{selected_id}",
        )

        st.divider()

        # Interactive placeholder builder
        st.markdown(
            '<div class="field-label">Interactive builder</div>',
            unsafe_allow_html=True,
        )

        if selected_prompt and selected_prompt.prompt_template:
            filled_prompt, filled_values = render_placeholder_builder(
                template=selected_prompt.prompt_template,
                prompt_id=selected_id,
            )

            # Live-filled preview
            st.text_area(
                "Filled prompt",
                value=filled_prompt,
                height=200,
                key="filled_prompt_area",
                label_visibility="visible",
            )

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                render_copy_button(
                    text=filled_prompt,
                    button_label="📋 Copy filled prompt",
                    element_id=f"copy_filled_{selected_id}",
                )
            with btn_col2:
                if st.button("💾 Save to History", key=f"save_hist_{selected_id}"):
                    msg = service.save_history(
                        selected_id,
                        detail["name"],
                        {k: v for k, v in filled_values.items() if v.strip()},
                        st.session_state.session_id,
                    )
                    st.success(msg)

        st.divider()

        # Full structured copy block
        st.markdown(
            '<div class="field-label">Full copy block</div>',
            unsafe_allow_html=True,
        )
        st.text_area(
            "Full copy block",
            value=detail["copy_payload"],
            height=200,
            key="copy_payload_area",
            label_visibility="collapsed",
        )
        render_copy_button(
            text=detail["copy_payload"],
            button_label="📋 Copy full block",
            element_id=f"copy_prompt_{selected_id}",
        )

    # ── Ratings + Comments ────────────────────────────────────────────────────

    st.divider()
    feedback_col, comments_col = st.columns(2)

    with feedback_col:
        st.markdown("#### Ratings")
        render_star_display(detail["avg_rating"], detail["rating_count"])

        with st.form(f"rating_form_{selected_id}", clear_on_submit=False):
            rating_value = st.slider(
                "Your rating", min_value=1, max_value=5, value=5, step=1
            )
            if st.form_submit_button("Submit rating"):
                msg = service.submit_rating(
                    selected_id, rating_value, st.session_state.session_id
                )
                st.success(msg)
                st.rerun()

    with comments_col:
        st.markdown("#### Comments")
        st.text_area(
            "Existing comments",
            value=detail["comments"],
            height=150,
            disabled=True,
            label_visibility="collapsed",
        )
        with st.form(f"comment_form_{selected_id}", clear_on_submit=True):
            comment_value = st.text_area(
                "Add a comment",
                placeholder="Share feedback or usage notes…",
                height=90,
            )
            if st.form_submit_button("Add comment"):
                msg = service.submit_comment(
                    selected_id, comment_value, st.session_state.session_id
                )
                if "successfully" in msg.lower():
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

    # ── Setup notes expander ──────────────────────────────────────────────────

    st.divider()
    with st.expander("Setup notes", expanded=False):
        st.markdown(
            """
            **Excel file**
            Place `prompt_guide.xlsx` in the same folder as `app.py`, or upload it
            using the sidebar uploader.

            **Feedback file**
            Ratings, comments, and history are stored in `feedback.xlsx` (created
            automatically on first use). This file is separate from the prompt source
            so uploading a new library never overwrites existing feedback.

            **Required Excel columns**
            `Prompt ID` · `Prompt Name` · `Category` · `Tags/Labels` ·
            `Prompt Objective` · `Prompt` · `Required Inputs` · `Sample Output`

            **Run locally**
            ```bash
            pip install streamlit pandas openpyxl
            streamlit run app.py
            ```
            """
        )
