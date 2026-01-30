import json
import os

playwriter_path = 'output2/scraped_items_playwriter.json'
legacy_path = 'output/threads_saved_full_20260130.json'

try:
    with open(playwriter_path, 'r', encoding='utf-8') as f:
        playwriter_data = json.load(f)

    with open(legacy_path, 'r', encoding='utf-8') as f:
        legacy_full = json.load(f)
        if isinstance(legacy_full, dict) and 'posts' in legacy_full:
            legacy_posts = legacy_full['posts']
        else:
            legacy_posts = legacy_full

    report = ["# Scraped Data Comparison Report\n\n"]
    report.append("| Code | Playwriter (New, Cleaned) | Legacy (Old, Raw) | Analysis |\n")
    report.append("|---|---|---|---|\n")

    for p_item in playwriter_data:
        code = p_item.get('code')
        if not code: continue
        
        l_item = next((x for x in legacy_posts if x.get('code') == code), None)
        
        p_text = p_item.get('full_text', '').strip()
        # Truncate for display
        p_display = p_text.replace('\n', '<br>')
        if len(p_display) > 200: p_display = p_display[:200] + "..."
        
        if l_item:
            l_text = l_item.get('text', '').strip()
            l_display = l_text.replace('\n', '<br>')
            if len(l_display) > 200: l_display = l_display[:200] + "..."
            
            # Comparison Logic
            p_norm = p_text.replace('\n', '').replace(' ', '')
            l_norm = l_text.replace('\n', '').replace(' ', '')
            
            match_status = ""
            if p_text == l_text:
                match_status = "✅ Perfect Match"
            elif p_norm == l_norm:
                match_status = "✅ Content Match (Whitespace Diff)"
            elif p_text in l_text:
                match_status = "⚠️ New is Subset (Cleaned?)"
            elif l_text in p_text:
                match_status = "⚠️ Old is Subset"
            else:
                # Diff hint
                len_diff = len(p_text) - len(l_text)
                match_status = f"❌ Mismatch (Len Diff: {len_diff})"

            report.append(f"| {code} | {p_display} | {l_display} | {match_status} |\n")
        else:
            report.append(f"| {code} | {p_display} | (Not found) | 🆕 New Item |\n")

    with open('comparison_report.md', 'w', encoding='utf-8') as f:
        f.writelines(report)

    print("Report generated: comparison_report.md")

except Exception as e:
    print(f"Error: {e}")
