import json
import os

# Paths
json_path = r'd:\Vibe_Coding\scrap_sns\output_total\total_full_20260201.json'
js_output_path = r'd:\Vibe_Coding\scrap_sns\web_viewer\data.js'

print(f"Reading JSON from: {json_path}")

try:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # JSON 데이터를 JS 변수 할당문으로 변환
    js_content = f"const snsFeedData = {json.dumps(data, ensure_ascii=False, indent=2)};"
    
    with open(js_output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)
        
    print(f"Successfully created: {js_output_path}")
    print("Now you can use 'snsFeedData' variable in your script without fetch!")

except Exception as e:
    print(f"Error converting JSON to JS: {e}")
