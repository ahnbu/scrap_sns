import json
import os
from collections import defaultdict

# Load JSON data
file_path = r'd:\vibe-coding\scrap_sns\output_total\total_full_20260201.json'

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle list or dict wrapping
    posts = data if isinstance(data, list) else data.get('posts', [])
    
    total_count = len(posts)
    missing_date_count = 0
    missing_by_platform = defaultdict(int)
    total_by_platform = defaultdict(int)
    
    for post in posts:
        platform = post.get('sns_platform', 'unknown')
        total_by_platform[platform] += 1
        
        # Check if created_at is missing or null
        created_at = post.get('created_at')
        if not created_at:
            missing_date_count += 1
            missing_by_platform[platform] += 1
            
    print(f"=== Date Field Analysis Report ===")
    print(f"Total Posts: {total_count}")
    print(f"Posts with Missing 'created_at': {missing_date_count} ({missing_date_count/total_count*100:.1f}%)")
    print("-" * 30)
    print("Missing Count by Platform:")
    for platform, count in total_by_platform.items():
        missing = missing_by_platform[platform]
        percentage = (missing / count * 100) if count > 0 else 0
        print(f"  - {platform}: {missing}/{count} ({percentage:.1f}% missing)")

except Exception as e:
    print(f"Error analyzing file: {e}")
