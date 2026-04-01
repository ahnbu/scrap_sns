---
title: "Design: JSON to Markdown Conversion Automation"
created: "2026-02-08 12:12"
---

# Design: JSON to Markdown Conversion Automation

> **Description**: Detailed design for the `json_to_md` shared module and its integration into SNS scrapers.

## 1. Shared Module: `utils/json_to_md.py`

### 1.1 Interface
```python
def convert_json_to_md(json_path: str, output_path: str = None) -> str:
    """
    Converts a standard SNS scraper JSON output to a Markdown file.
    
    Args:
        json_path: Path to the source JSON file.
        output_path: Optional custom path for the output .md file. 
                     If None, replaces .json with .md in json_path.
                     
    Returns:
        The path to the generated Markdown file.
    """
```

### 1.2 Markdown Format Template
```markdown
# {Title} (or "No Title")

> **Author**: {Subtitle/Author}
> **Date**: {Created At}
> **Link**: [Original Post]({Post URL})

---

{Body Text}

![Image]({Image URL})
...

---
```
- **Encoding**: UTF-8 (No BOM)
- **Error Handling**: Gracefully handle missing fields (use defaults).

### 1.3 Logic Flow
1. **Validation**: Check if `json_path` exists.
2. **Load**: Read JSON using `json.load`. Handle both list-at-root and dict-at-root (`{"posts": [...]}`) formats.
3. **Iterate**: Loop through posts.
4. **Format**:
    - Title: Use `title` or fallback to `code`.
    - Body: Use `body_text` (Substack) or `full_text` (Threads/LinkedIn).
    - Images: Iterate `images` list.
5. **Write**: Save to `.md` file.

---

## 2. Integration Points

### 2.1 `substack_scrap_by_user.py`
- **Location**: Inside `update_full_version` method.
- **Trigger**: Immediately after `save_json(full_file, full_data)`.
- **Code**:
  ```python
  from utils.json_to_md import convert_json_to_md
  # ...
  convert_json_to_md(full_file)
  print(f"📄 Markdown 변환 완료: {full_file.replace('.json', '.md')}")
  ```

### 2.2 `linkedin_scrap_by_user.py`
- **Location**: Inside `update_full_version` method.
- **Trigger**: After saving `linkedin_{USER_ID}_full_...json`.

### 2.3 `threads_scrap.py`
- **Location**: Inside `run` function, block `[2] Simple 버전 업데이트` (for update mode) and `else` block (for all mode).
- **Target**: `simple_filename` (which is the full file for this script).

### 2.4 `linkedin_scrap.py`
- **Location**: Inside `update_full_version` method.
- **Trigger**: After `save_json(full_file, full_data)`.

### 2.5 `total_scrap.py`
- **Location**: Inside `save_total` function.
- **Trigger**: After saving `total_filename`.

---

## 3. Directory Structure
```
D:\vibe-coding\scrap_sns
├── utils
│   ├── __init__.py
│   └── json_to_md.py  <-- NEW
├── substack_scrap_by_user.py
├── linkedin_scrap_by_user.py
├── threads_scrap.py
├── linkedin_scrap.py
└── total_scrap.py
```

## 4. Verification Plan (Checklist)
- [ ] `json_to_md.py` creates valid Markdown from sample JSON.
- [ ] `substack_scrap_by_user.py` generates `.md` on run.
- [ ] `threads_scrap.py` generates `.md` on run.
- [ ] `linkedin_scrap.py` generates `.md` on run.
- [ ] `total_scrap.py` generates `.md` on run.
