import requests
import sys

# Configure standard output to support UTF-8 encoding on Windows console
sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Exactly 5 logical OR operators
q = 'ai OR llm OR agent OR "machine learning" OR "deep learning" OR nlp stars:>10'
params = {
    "q": q,
    "sort": "updated",
    "order": "desc",
    "per_page": 20
}

url = "https://api.github.com/search/repositories"
r = requests.get(url, headers=headers, params=params)
print("Status Code:", r.status_code)
if r.status_code == 200:
    items = r.json().get('items', [])
    print("Found items:")
    for item in items:
        print("  -", item['full_name'], "pushed at:", item.get('pushed_at'))
        print("    Description:", item.get('description') or "No description provided.")
else:
    print("Response:", r.text[:500])
