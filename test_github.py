
import sys
sys.path.append('.')
from scrapers import enrich_item_metadata
item = {
    'Type': 'GitHub Repo',
    'Title': 'AI-Image-Web-Application',
    'Description': 'AI-powered web application for PPE detection...',
    'Link': 'https://github.com/shameek001/AI-Image-Web-Application'
}
import requests
url = item['Link']
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'text/html', 'Accept-Encoding': 'gzip, deflate'}
with requests.get(url, headers=headers, timeout=4, stream=True) as resp:
    raw_bytes = b''
    for chunk in resp.iter_content(chunk_size=8192):
        raw_bytes += chunk
        if len(raw_bytes) >= 24576:
            break
html = raw_bytes.decode('utf-8', errors='ignore')
print('HTML length:', len(html))
import re
pat = r'<meta\s+property=[\'\"]og:image[\'\"]\s+content=[\'\"](.*?)[\'\"]'
m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
print('Regex match:', m)

