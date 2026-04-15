# Banking Analytics Prompt Library

A modular, production-ready Streamlit application for managing, searching, and using reusable AI prompts in banking analytics workflows.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [File Reference](#file-reference)
4. [Setup & Installation](#setup--installation)
5. [Configuration](#configuration)
6. [Excel File Format](#excel-file-format)
7. [Feature Guide](#feature-guide)
8. [Data Flow](#data-flow)
9. [Extending the App](#extending-the-app)
10. [Changelog](#changelog)

---

## Overview

The Prompt Library gives banking analytics teams a single, governed place to store, discover, and use AI prompt templates. Users can search and filter the library, fill in placeholder variables interactively, rate prompts, leave comments, and export results — all without touching the underlying Excel files directly.

**Key design principles:**

- **Separation of concerns** — each Python file owns exactly one responsibility
- **No cache-clearing on feedback** — ratings and comments update in-memory without reloading the entire dataset
- **Feedback decoupled from prompt source** — uploading a new prompt library never overwrites existing ratings or comments
- **Production-safe defaults** — seed data, audit logging, and debug flags are all off unless explicitly enabled

---

## Architecture

```
app.py                  ← Streamlit UI (presentation only)
│
├── ui_helpers.py       ← Reusable UI components (stars, chips, builder, copy button)
│
├── service.py          ← Business logic (detail assembly, feedback, export, history)
│   ├── repository.py   ← In-memory data store (search, sort, paginate, mutate)
│   ├── feedback.py     ← Feedback persistence (ratings, comments, history → Excel)
│   └── models.py       ← Data models (PromptRecord, PromptInput)
│
├── loader.py           ← Excel → PromptRecord objects (with optional audit)
└── config.py           ← Centralised settings (env-overridable dataclass)
```

### Layer responsibilities

| Layer | File | Allowed to import |
|---|---|---|
| Presentation | `app.py` | `service`, `repository`, `ui_helpers`, `config` |
| UI components | `ui_helpers.py` | `streamlit` only |
| Business logic | `service.py` | `repository`, `feedback`, `models`, `config` |
| Data store | `repository.py` | `models` only |
| Persistence | `feedback.py` | `config` only |
| Loading | `loader.py` | `models`, `config` |
| Models | `models.py` | nothing (pure dataclasses) |
| Config | `config.py` | `os` only |

---

## File Reference

### `config.py`

Central application configuration. All settings are plain Python dataclass fields that default to environment variable reads, making the app portable across environments without code changes.

```python
APP_CONFIG = AppConfig()   # single shared instance imported by all modules
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `default_excel_path` | `str` | `prompt_guide.xlsx` | Prompt source when no file is uploaded |
| `feedback_excel_path` | `str` | `feedback.xlsx` | Where ratings, comments, and history are written |
| `prompts_sheet` | `str` | `Sheet2` | Sheet name for the prompt table |
| `ratings_sheet` | `str` | `Ratings` | Sheet name for stored ratings |
| `comments_sheet` | `str` | `Comments` | Sheet name for stored comments |
| `history_sheet` | `str` | `History` | Sheet name for filled-prompt history |
| `enable_seed_data` | `bool` | `false` | Show sample prompts when no Excel file is found |
| `audit_enabled` | `bool` | `false` | Run data-quality checks on load |
| `page_size` | `int` | `20` | Prompts shown per page |
| `max_comment_length` | `int` | `1000` | Character cap on user comments |
| `min_prompt_length` | `int` | `20` | Minimum chars for a non-stub prompt (audit only) |

---

### `models.py`

Pure dataclasses with no external dependencies.

#### `PromptInput`

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Variable name as it appears in the template, e.g. `portfolio_data` |
| `description` | `str` | Human-readable explanation shown in the UI |

#### `PromptRecord`

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Unique prompt identifier (from Excel) |
| `name` | `str` | Display name |
| `category` | `str` | Grouping label, e.g. `Risk Analytics` |
| `tags` | `List[str]` | Searchable labels |
| `prompt_objective` | `str` | One-sentence purpose statement |
| `prompt_template` | `str` | The full prompt text with `{placeholder}` variables |
| `required_inputs` | `List[PromptInput]` | Variables the user must supply |
| `optional_inputs` | `List[PromptInput]` | Variables that enrich but are not required |
| `expected_result` | `str` | Sample output shown to users |
| `ratings` | `List[int]` | Integer ratings 1–5 |
| `rating_sessions` | `List[str]` | Session IDs parallel to `ratings` |
| `comments` | `List[str]` | Free-text user comments |
| `comment_timestamps` | `List[str]` | ISO timestamps parallel to `comments` |
| `comment_sessions` | `List[str]` | Session IDs parallel to `comments` |

---

### `loader.py`

Reads the prompt Excel file and returns a list of `PromptRecord` objects.

#### `PromptExcelLoader.load_from_excel(file_path, config)`

1. Reads the sheet named `config.prompts_sheet`
2. Validates all required columns are present (raises `ValueError` if not)
3. Optionally runs `_audit_dataframe()` when `config.audit_enabled` is `True`
4. Converts each row to a `PromptRecord`, skipping rows missing ID or Name
5. Returns the list — feedback is merged by the caller

#### Audit checks (when `AUDIT_ENABLED=true`)

| Check | Log level |
|---|---|
| Column fill rate < 50% | ERROR |
| Column fill rate 50–90% | WARNING |
| Column fill rate ≥ 90% | INFO |
| Duplicate Prompt IDs | ERROR |
| Prompt text shorter than `min_prompt_length` | WARNING |
| Required inputs listed but no `{placeholder}` in template | WARNING |

#### Input cell parsing

The `Required Inputs` column supports several formats:

```
# One item per line
portfolio_data
time_period

# Comma-separated
portfolio_data, time_period, region

# Explicit Required / Optional prefixes
Required: portfolio_data, time_period
Optional: region, benchmark

# Markdown bullets
- portfolio_data
• time_period
```

---

### `feedback.py`

All feedback is written to a single dedicated file (`feedback.xlsx` by default), separate from the prompt source. This means:

- Uploading a new prompt library never loses ratings or comments
- The prompt source file can be read-only

#### Functions

| Function | Description |
|---|---|
| `ensure_feedback_file(path, config)` | Creates the workbook and sheets if they do not exist |
| `load_feedback(path, config)` | Returns `(ratings_map, comments_map)` dicts keyed by prompt ID |
| `load_history(path, config)` | Returns all history rows as a list of dicts |
| `append_rating(path, prompt_id, rating, session_id, config)` | Appends one rating row |
| `append_comment(path, prompt_id, comment, session_id, config)` | Appends one comment row |
| `append_history(path, prompt_id, prompt_name, filled_values, session_id, config)` | Appends one history row with filled values as JSON |

#### Sheet schemas

**Ratings**

| Column | Type | Notes |
|---|---|---|
| Prompt ID | int | Foreign key to the prompt |
| Rating | int | 1–5 |
| Session ID | str | Browser session UUID |
| Created At | str | ISO 8601 timestamp |

**Comments**

| Column | Type | Notes |
|---|---|---|
| Prompt ID | int | |
| Comment | str | Max 1000 characters |
| Session ID | str | |
| Created At | str | ISO 8601 timestamp |

**History**

| Column | Type | Notes |
|---|---|---|
| Prompt ID | int | |
| Prompt Name | str | Snapshot of the name at save time |
| Filled Values | str | JSON dict of `{placeholder: value}` pairs |
| Session ID | str | |
| Created At | str | ISO 8601 timestamp |

---

### `repository.py`

In-memory store. Intentionally has no knowledge of Streamlit, Excel, or feedback files — making it straightforward to swap the underlying storage for a database later.

#### `PromptRepository(seed_data)`

| Method | Signature | Description |
|---|---|---|
| `list_all` | `() → List[PromptRecord]` | All prompts, unsorted |
| `get_by_id` | `(id) → Optional[PromptRecord]` | Single prompt lookup |
| `categories` | `() → List[str]` | Sorted unique categories |
| `search` | `(text, categories, sort_by, page, page_size) → (List, int)` | Filtered, sorted, paginated results + total count |
| `add_rating` | `(id, rating, session_id) → bool` | Appends to in-memory ratings list |
| `add_comment` | `(id, comment, timestamp, session_id) → bool` | Appends to in-memory comments list |
| `duplicate_ids` | `List[int]` attribute | IDs that appeared more than once in the source data |

#### Search behaviour

Search is **fuzzy and token-based**:

1. The query is split on whitespace and common delimiters (`-`, `_`, `,`, `.`, `/`)
2. Every token must appear somewhere in the combined haystack of name + category + tags + objective + template + expected result
3. Order of tokens does not matter — `"risk credit"` and `"credit risk"` return the same results

#### Sort options

| Label | Behaviour |
|---|---|
| `Name A→Z` | Alphabetical ascending (case-insensitive) |
| `Name Z→A` | Alphabetical descending |
| `Highest Rated` | Descending mean rating; unrated prompts sort last |
| `Most Reviews` | Descending review count |

---

### `service.py`

Orchestrates between the repository, feedback layer, and UI. The UI should never call `repository` or `feedback` functions directly.

#### `PromptService(repository, config)`

| Method | Description |
|---|---|
| `get_prompt_detail(id)` | Assembles the full detail dict consumed by the UI, including formatted comments with relative timestamps |
| `submit_rating(id, rating, session_id)` | Updates in-memory repo and persists to Excel; returns a user-facing message string |
| `submit_comment(id, comment, session_id)` | Same pattern as `submit_rating` |
| `save_history(id, name, filled_values, session_id)` | Persists a filled-prompt usage to the history sheet |
| `get_history()` | Returns all history rows for the History tab |
| `export_filtered_csv(prompts)` | Serialises a list of `PromptRecord` objects to CSV bytes for `st.download_button` |

#### `get_prompt_detail` return keys

| Key | Type | Description |
|---|---|---|
| `name` | `str` | |
| `category` | `str` | |
| `tags` | `List[str]` | Raw list, rendered as chips by UI |
| `objective` | `str` | |
| `required_inputs` | `str` | Bullet-formatted string |
| `optional_inputs` | `str` | Bullet-formatted string |
| `expected_result` | `str` | Raw markdown, rendered by `st.markdown` |
| `rating_summary` | `str` | e.g. `"Average: 4.3 / 5 (6 reviews)"` |
| `avg_rating` | `Optional[float]` | `None` when no ratings exist |
| `rating_count` | `int` | |
| `comments` | `str` | Bullet-formatted with relative timestamps |
| `prompt_template` | `str` | Raw template for the view box |
| `copy_payload` | `str` | Full structured block for the copy-all button |

---

### `ui_helpers.py`

All components that emit HTML use `html.escape()` on user-supplied values before injection. No raw content from Excel or user input reaches the DOM unescaped.

#### `render_copy_button(text, button_label, element_id)`

Renders a button that copies `text` to the clipboard. The label changes to `Copied ✓` for 1.5 seconds on click.

#### `render_star_display(avg_rating, count)`

Renders filled (`★`) and empty (`☆`) Unicode stars in amber alongside a muted summary string. When `avg_rating` is `None`, renders "No ratings yet".

#### `render_tag_chips(tags, selected_tags, key_prefix)`

Renders each tag as a pill-shaped element. Selected tags are shown in blue. Returns the tag that was clicked this render cycle, or `None`.

#### `render_placeholder_builder(template, prompt_id)`

1. Scans the template for `{variable_name}` patterns using a regex
2. De-duplicates while preserving order
3. Renders one `st.text_input` per unique placeholder, arranged in up to two columns
4. Returns `(live_filled_prompt, filled_values_dict)` — unfilled placeholders are left as-is in the output

#### `field_box(label, value)`

Renders a labelled read-only display box. Both label and value are HTML-escaped.

---

### `app.py`

Thin presentation layer. All business logic lives in `service.py`.

#### Session state keys

| Key | Type | Initialised | Purpose |
|---|---|---|---|
| `_session_initialised` | `bool` | Once | Guard flag — prevents re-init on every rerun |
| `session_id` | `str` | Once | UUID identifying this browser session |
| `selected_prompt_id` | `Optional[int]` | Once | Currently viewed prompt |
| `current_page` | `int` | Once, reset on filter change | Pagination cursor |
| `search_text` | `str` | Once | Active search query |
| `selected_categories` | `List[str]` | Once | Active category filter |
| `sort_by` | `str` | Once | Active sort option |
| `active_tag_filters` | `List[str]` | Once | Tags selected via chip clicks |
| `uploaded_file_hash` | `Optional[int]` | Once | Detects new file uploads |
| `repo` | `Optional[PromptRepository]` | Built on first load | In-memory data store |

#### Repository lifecycle

The repository is stored in `st.session_state.repo` and rebuilt only when:

- The app starts for the first time in a session, or
- The user uploads a new file (detected by comparing `hash(file_bytes)`)

Ratings and comments mutate the existing repository objects in place — **no rebuild or cache clear is needed after feedback submission**.

#### Tabs

| Tab | Contents |
|---|---|
| Prompt Library | Search, filter, sort, view, builder, feedback |
| History | Table of all filled prompts saved this session; CSV export |
| About | Feature list, column reference, environment variable table, run instructions |

---

## Setup & Installation

### Prerequisites

- Python 3.9 or later
- pip

### Steps

```bash
# 1. Clone or copy the project files into a directory
cd prompt_library/

# 2. Install dependencies
pip install -r requirements.txt

# 3. Place your Excel file in the same directory
cp /path/to/your/prompt_guide.xlsx .

# 4. Run the app
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

### First run without an Excel file

If no Excel file is present and `ENABLE_SEED_DATA` is not set, the app displays a clear error message prompting you to upload a file or place one in the directory. No fake data is shown silently.

To run with sample data for a demo:

```bash
ENABLE_SEED_DATA=true streamlit run app.py
```

---

## Configuration

All settings can be overridden via environment variables. No code changes are needed between environments.

### Environment variables

| Variable | Default | When to change |
|---|---|---|
| `EXCEL_FILE_PATH` | `prompt_guide.xlsx` | Prompt file is in a different location |
| `FEEDBACK_FILE_PATH` | `feedback.xlsx` | Store feedback in a shared or mounted path |
| `PROMPTS_SHEET` | `Sheet2` | Your prompt table is on a differently named sheet |
| `RATINGS_SHEET` | `Ratings` | Customise the feedback sheet name |
| `COMMENTS_SHEET` | `Comments` | Customise the feedback sheet name |
| `HISTORY_SHEET` | `History` | Customise the history sheet name |
| `ENABLE_SEED_DATA` | `false` | Set to `true` in demo or development environments |
| `AUDIT_ENABLED` | `false` | Set to `true` during data onboarding to catch quality issues |
| `PAGE_SIZE` | `20` | Adjust for very large or very small libraries |

### Example: Streamlit Cloud deployment

In the Streamlit Cloud dashboard, add these under **App settings → Secrets** (or environment variables):

```toml
EXCEL_FILE_PATH = "data/prompts.xlsx"
FEEDBACK_FILE_PATH = "/mnt/shared/feedback.xlsx"
PAGE_SIZE = "30"
```

---

## Excel File Format

### Prompt source sheet (default: `Sheet2`)

| Column | Required | Type | Notes |
|---|---|---|---|
| `Prompt ID` | Yes | Integer | Must be unique across all rows |
| `Prompt Name` | Yes | String | Display name shown in the selector |
| `Category` | Yes | String | Used for filtering; defaults to `Uncategorized` if blank |
| `Tags/Labels` | No | String | Comma, semicolon, pipe, or slash-separated |
| `Prompt Objective` | No | String | One-sentence purpose statement |
| `Prompt` | Yes | String | The prompt template; use `{variable_name}` for placeholders |
| `Required Inputs` | No | String | See parsing rules in the loader section |
| `Sample Output` | No | String | Rendered as markdown in the UI |

### Placeholder syntax

Variables in the prompt template must use curly-brace syntax:

```
Analyse {portfolio_data} focusing on {time_period} trends.
```

The loader extracts matching entries from the `Required Inputs` column and displays them as named input fields in the interactive builder.

### Common formatting issues

| Issue | Symptom | Fix |
|---|---|---|
| Duplicate `Prompt ID` values | Warning banner in the UI; later row overwrites earlier | Assign unique IDs |
| `Prompt` column empty | Prompt view shows blank | Fill the cell |
| `Required Inputs` filled but no `{var}` in template | Audit warning (when enabled) | Add placeholders or clear the inputs cell |
| Tags not splitting correctly | All tags appear as one chip | Use comma, semicolon, or pipe as separator |

---

## Feature Guide

### Search

The search bar uses token-based fuzzy matching. Enter space-separated terms; all must appear somewhere in the prompt's name, category, tags, objective, template, or sample output.

```
# Finds prompts mentioning both "credit" and "portfolio"
credit portfolio

# Finds prompts in the fraud space related to mobile
fraud mobile

# Exact phrase works too
liquidity coverage
```

### Category filter

Select one or more categories from the multiselect. Leaving it empty shows all categories. Combine with search for precise filtering.

### Tag chips

Tags on the selected prompt are displayed as clickable pills. Clicking a tag sets the search bar to that tag and re-filters the library. Clicking the same tag again in a subsequent search clears it.

### Interactive builder

Below the raw prompt template, the builder automatically detects every `{placeholder}` and renders a text input for each one. As you type, the **Filled prompt** preview updates live. When all placeholders are filled:

1. Click **Copy filled prompt** to copy the ready-to-use prompt
2. Click **Save to History** to record the filled values in `feedback.xlsx`

### Ratings

Submit a rating using the 1–5 slider. Ratings are immediately reflected in the visual star display and persisted to the feedback file. Each rating is tagged with your session ID to support deduplication in future versions.

### Comments

Comments are appended with an ISO timestamp and displayed with a relative time label (e.g. `3h ago`, `2d ago`). They persist across sessions via the feedback file.

### Export

The **Export CSV** button downloads all prompts matching the current search and category filter — not just the current page. The CSV includes all metadata columns plus average rating and review count.

### History tab

Every time you click **Save to History**, a row is written to the `History` sheet in `feedback.xlsx`. The History tab shows all entries with their filled values, session ID, and timestamp. The tab also has its own **Export history CSV** button.

---

## Data Flow

### Startup

```
browser opens app
       │
       ▼
_init_session()          ← runs once; sets session_id, page, filters
       │
       ▼
_get_or_build_repo()     ← checks uploaded_file_hash
       │
       ├─ file uploaded? ─── write to temp ─── PromptExcelLoader.load_from_excel()
       │                                              │
       └─ default path? ──────────────────────────────┘
                                                       │
                                                       ▼
                                              load_feedback()   ← merges ratings/comments
                                                       │
                                                       ▼
                                              PromptRepository  ← stored in session_state
```

### Rating submission

```
user clicks Submit Rating
       │
       ▼
service.submit_rating(id, rating, session_id)
       │
       ├─ repo.add_rating()           ← in-memory update (instant UI refresh)
       │
       └─ feedback.append_rating()    ← writes to feedback.xlsx
```

No cache clearing. No full reload. The in-memory `PromptRecord` object is mutated directly, so the star display updates on the next render.

### File upload

```
user uploads new Excel file
       │
       ▼
hash(file_bytes) != session_state.uploaded_file_hash
       │
       ▼
write bytes → tempfile → load records → merge feedback → new PromptRepository
       │
       ▼
session_state.repo updated, page reset to 1
```

---

## Extending the App

### Swapping Excel for a database

The repository and feedback layers are isolated from all storage concerns. To replace Excel with SQLite:

1. Create a `SqliteFeedback` module implementing the same function signatures as `feedback.py`
2. Create a `SqliteLoader` implementing `load_from_db(connection) → List[PromptRecord]`
3. Update `_load_records_from_path` in `app.py` to call the new loader
4. Update `PromptService.__init__` to receive and use the new feedback module

No changes are needed in `repository.py`, `models.py`, `ui_helpers.py`, or `config.py`.

### Adding a new feedback type (e.g. bookmarks)

1. Add a `bookmarks` sheet to `ensure_feedback_file` in `feedback.py`
2. Add `append_bookmark` and `load_bookmarks` functions
3. Add a `bookmarks: List[str]` field to `PromptRecord` in `models.py`
4. Add a `toggle_bookmark` method to `PromptRepository`
5. Add `submit_bookmark` to `PromptService`
6. Add a bookmark button in `app.py`

### Adding a new sort option

1. Add the label string to `SORT_OPTIONS` in `repository.py`
2. Add the corresponding `elif` branch in `PromptRepository.search`

### Enabling multi-user feedback deduplication

Each rating and comment already records a `Session ID`. To prevent duplicate ratings from the same session:

In `PromptRepository.add_rating`, check whether `session_id` already appears in `prompt.rating_sessions` before appending.

---

## Changelog

### v2.0

**Performance**
- Removed `tracemalloc` (was running continuously in production)
- Replaced `@st.cache_resource` + `cache.clear()` pattern with session-state repository — no full reload on feedback submission
- Data-quality audit gated behind `AUDIT_ENABLED` flag

**UI enhancements**
- Interactive placeholder builder with live-filled preview
- Visual star rating display (★☆ Unicode)
- Clickable tag chips that set the search filter
- Sort dropdown: Name A→Z, Name Z→A, Highest Rated, Most Reviews
- Multi-category filter via `st.multiselect`

**New functionality**
- Sidebar Excel file uploader — no filesystem access required
- Token-based fuzzy search — space-separated terms all matched independently
- Comment timestamps displayed as relative time (`2h ago`, `3d ago`)
- Export filtered results to CSV
- History tab — records all filled prompts with their values and timestamps

**Code quality**
- `_init_session()` guarded with `_session_initialised` flag — runs once per session
- All HTML field boxes use `html.escape()` — XSS risk eliminated
- Configuration centralised in `AppConfig` dataclass with env-var overrides
- Pagination: `repo.search()` returns `(results, total_count)` with page/page_size parameters

**Data layer**
- Duplicate Prompt ID warning banner in the UI
- `Session ID` column added to Ratings and Comments sheets
- `feedback.xlsx` decoupled from prompt source — upload safety
- Seed data gated behind `ENABLE_SEED_DATA=true` — silent fallback removed
- History sheet for filled-prompt usage tracking

### v1.0

- Initial release: single-file Streamlit app with Excel integration, basic search, ratings, and comments