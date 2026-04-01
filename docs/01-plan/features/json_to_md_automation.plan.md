---
title: "Plan: JSON to Markdown Conversion Automation"
created: "2026-02-08 12:11"
---

# Plan: JSON to Markdown Conversion Automation

> **Goal**: Automate the generation of Markdown (.md) reports from scraped JSON data for various SNS scrapers.

## 1. Requirement Analysis

### 1.1 Core Requirements

- **Shared Module**: Create a reusable Python module (`json_to_md.py`) to handle JSON-to-Markdown conversion.
- **Automation**: Integrate this module into existing scrapers to automatically generate `.md` files immediately after saving the "full" JSON version.
- **Scope**: Apply only to "full" version files (exclude "update" or temporary files).
- **Targets**:
  1. `substack_scrap_by_user.py`
  2. `linkedin_scrap_by_user.py`
  3. `threads_scrap.py`
  4. `linkedin_scrap.py`
  5. `total_scrap.py`

### 1.2 Output Format (Markdown)

- **Header**: Title, Subtitle (if any), Author, Date, URL.
- **Body**: Text content (handling `body_text` or `full_text`).
- **Images**: Embed images using Markdown syntax `![alt](url)`.
- **Layout**: Clear separation between posts (e.g., horizontal rules `---`).

---

## 2. Architecture Design

### 2.1 Shared Module (`utils/json_to_md.py`)

- **Function**: `convert_json_to_md(json_path, output_path=None)`
- **Logic**:
  1. Load JSON data.
  2. Identify the structure (usually `{ "posts": [...] }`).
  3. Iterate through posts and format them into a single Markdown string.
  4. Save to `output_path` (defaulting to `json_path` with `.md` extension).
  5. Handle encoding (UTF-8) and special characters.

### 2.2 Integration Points

- **substack_scrap_by_user.py**: In `update_full_version()` method, after `save_json(full_file, ...)`.
- **linkedin_scrap_by_user.py**: Identify "full" file saving block and append conversion call.
- **threads_scrap.py**: Identify `threads_py_simple_full_*.json` saving block and append conversion call.
- **linkedin_scrap.py**: Identify full file saving logic (likely `linkedin_py_full_...json`) and append.
- **total_scrap.py**: Identify total integration file saving and append.

---

## 3. Implementation Steps

1. **Create Shared Module**: Implement `utils/json_to_md.py`.
2. **Refactor Scrapers**:
   - Import the module in target scripts.
   - Locate the `save_json` call for the FULL version.
   - Add `json_to_md.convert_json_to_md(full_file_path)` immediately after.
3. **Verification**:
   - Run each scraper (in test/limit mode) to ensure `.md` files are generated.
   - Check the content of generated Markdown files.

## 4. Verification Plan

- **Substack**: Run for `edwardhan99` (limit 1) -> Check `output_substack/edwardhan99/...full...md`.
- **LinkedIn**: Run for a test user -> Check `output_linkedin_user/...full...md`.
- **Threads**: Run in update mode -> Check `output_threads/python/...full...md`.
- **General**: Verify `total_scrap.py` output.

---

## 5. PDCA Tracking

- **Plan**: Created `docs/01-plan/features/json_to_md_automation.plan.md`.
- **Design**: Will detail the Markdown template and module interface.
- **Do**: Implementation of module and scraper updates.
- **Check**: Validation of MD generation.
- **Act**: Final adjustments.
