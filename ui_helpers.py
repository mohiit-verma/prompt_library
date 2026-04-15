"""
Reusable Streamlit UI components.

All HTML injected into the page is explicitly escaped to prevent XSS.
"""
from __future__ import annotations

import html
import re
from typing import Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components


# ── Copy button ───────────────────────────────────────────────────────────────

def render_copy_button(text: str, button_label: str, element_id: str) -> None:
    """
    Renders a clipboard copy button.
    After clicking the label changes to 'Copied' for 1.5 s, then resets.
    """
    escaped_text  = html.escape(text or "")
    escaped_label = html.escape(button_label)

    components.html(
        f"""
        <div style="margin: 0.25rem 0 1rem 0;">
            <button
                id="{element_id}"
                onclick="
                    navigator.clipboard.writeText(
                        document.getElementById('{element_id}_payload').innerText
                    );
                    const btn = document.getElementById('{element_id}');
                    btn.innerText = 'Copied ✓';
                    btn.disabled = true;
                    setTimeout(() => {{
                        btn.innerText = '{escaped_label}';
                        btn.disabled  = false;
                    }}, 1500);
                "
                style="
                    background: white;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    padding: 0.45rem 0.85rem;
                    font-size: 13px;
                    cursor: pointer;
                    transition: background 0.15s;
                "
                onmouseover="this.style.background='#f3f4f6'"
                onmouseout="this.style.background='white'"
            >
                {escaped_label}
            </button>
            <div id="{element_id}_payload" style="display:none;">{escaped_text}</div>
        </div>
        """,
        height=52,
    )


# ── Star rating display ───────────────────────────────────────────────────────

def render_star_display(avg_rating: Optional[float], count: int) -> None:
    """
    Renders a visual star rating row using inline HTML.
    Uses filled (★) and empty (☆) Unicode stars.
    """
    if avg_rating is None:
        st.markdown(
            '<span style="color:#9ca3af;font-size:0.9rem">No ratings yet</span>',
            unsafe_allow_html=True,
        )
        return

    filled  = round(avg_rating)
    empty   = 5 - filled
    stars   = "★" * filled + "☆" * empty
    summary = html.escape(f"{avg_rating:.1f} / 5  ({count} review{'s' if count != 1 else ''})")

    st.markdown(
        f'<span style="color:#f59e0b;font-size:1.3rem;letter-spacing:2px">{stars}</span>'
        f'&nbsp;&nbsp;<span style="color:#6b7280;font-size:0.85rem">{summary}</span>',
        unsafe_allow_html=True,
    )


# ── Tag chips ─────────────────────────────────────────────────────────────────

def render_tag_chips(
    tags: List[str],
    selected_tags: List[str],
    key_prefix: str = "tag",
) -> Optional[str]:
    """
    Renders tags as small pill buttons.
    Returns the tag that was clicked this render cycle, or None.
    Selected tags are highlighted.
    """
    if not tags:
        return None

    clicked: Optional[str] = None
    cols = st.columns(min(len(tags), 8))

    for idx, tag in enumerate(tags):
        col = cols[idx % len(cols)]
        is_selected = tag in selected_tags
        bg    = "#1d4ed8" if is_selected else "#eff6ff"
        color = "#ffffff"  if is_selected else "#1d4ed8"

        with col:
            # Streamlit buttons styled via markdown trick
            st.markdown(
                f"""
                <div style="
                    display:inline-block;
                    background:{bg};
                    color:{color};
                    border:1px solid #bfdbfe;
                    border-radius:999px;
                    padding:0.2rem 0.65rem;
                    font-size:0.78rem;
                    font-weight:500;
                    cursor:pointer;
                    margin-bottom:4px;
                    white-space:nowrap;
                ">{html.escape(tag)}</div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                tag,
                key=f"{key_prefix}_{tag}",
                help=f"Filter by tag: {tag}",
                use_container_width=False,
            ):
                clicked = tag

    return clicked


# ── Placeholder builder ───────────────────────────────────────────────────────

_PH_RE = re.compile(r"\{(\w+)\}")


def render_placeholder_builder(
    template: str,
    prompt_id: int,
) -> Tuple[str, Dict[str, str]]:
    """
    Detects {placeholder} variables in the template, renders one text input per
    unique placeholder, and returns (live_filled_prompt, filled_values_dict).

    If the user hasn't filled a placeholder the original {name} token is kept,
    making it obvious what still needs replacing.
    """
    placeholders = list(dict.fromkeys(_PH_RE.findall(template)))  # unique, ordered

    if not placeholders:
        return template, {}

    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#6b7280;margin-bottom:0.4rem">'
        "Fill placeholders</div>",
        unsafe_allow_html=True,
    )

    filled: Dict[str, str] = {}
    col_count = min(len(placeholders), 2)
    cols = st.columns(col_count)

    for idx, ph in enumerate(placeholders):
        with cols[idx % col_count]:
            value = st.text_input(
                label=ph,
                key=f"ph_{prompt_id}_{ph}",
                placeholder=f"Enter {ph}…",
                label_visibility="visible",
            )
            filled[ph] = value

    # Build live preview
    filled_prompt = template
    for ph, value in filled.items():
        if value.strip():
            filled_prompt = filled_prompt.replace(f"{{{ph}}}", value.strip())

    return filled_prompt, filled


# ── Field box helper ──────────────────────────────────────────────────────────

def field_box(label: str, value: str) -> None:
    """
    Renders a labelled read-only field box.
    All user-supplied content is HTML-escaped before injection.
    """
    safe_label = html.escape(label)
    safe_value = html.escape(value or "—")
    st.markdown(
        f'<div class="field-label">{safe_label}</div>'
        f'<div class="field-box">{safe_value}</div>',
        unsafe_allow_html=True,
    )
