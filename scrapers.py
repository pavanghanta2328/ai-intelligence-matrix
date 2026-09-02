import requests
import feedparser
import pandas as pd
import pymongo
import os
import json
import re

# Resolve base directory relative to scrapers.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cleanup legacy configurations
legacy_path = os.path.join(BASE_DIR, "youtube_rss_channels.json")
if os.path.exists(legacy_path):
    try:
        os.remove(legacy_path)
    except:
        pass

def _get_db_client():
    uri = os.environ.get("mongo_uri")
    if not uri:
        secrets_path = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            try:
                with open(secrets_path, "r") as f:
                    for line in f:
                        if line.strip().startswith("mongo_uri"):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                uri = parts[1].strip().strip('"').strip("'")
                                break
            except:
                pass
    if uri and "YOUR_PASSWORD_HERE" not in uri:
        try:
            return pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
        except:
            pass
    return None

# In-memory config cache — loaded once per process, reused by all parallel threads
_CONFIG_CACHE: dict = {}

def load_scraper_config(config_name):
    """
    Dynamically loads configuration from MongoDB or a local JSON file.
    Results are cached in memory after first load to avoid repeated DB hits
    when called from parallel scraper threads.
    """
    if config_name in _CONFIG_CACHE:
        return _CONFIG_CACHE[config_name]

    result = None
    client = _get_db_client()
    if client:
        try:
            db = client["ai_discovery"]
            col = db["configs"]
            doc = col.find_one({"_id": config_name})
            if doc and "data" in doc:
                result = doc["data"]
        except Exception as e:
            print(f"MongoDB config load error for {config_name}: {e}")
        finally:
            client.close()

    if result is None:
        # Fallback to local JSON
        try:
            # Check both the new config directory and the legacy root directory
            config_path = os.path.join(BASE_DIR, "config", f"{config_name}.json")
            legacy_path = os.path.join(BASE_DIR, f"{config_name}.json")
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
            elif os.path.exists(legacy_path):
                with open(legacy_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
        except Exception as e:
            print(f"JSON config load error for {config_name}: {e}")

    if result is None:
        print(f"Warning: Configuration {config_name} not found in MongoDB or local file.")

    _CONFIG_CACHE[config_name] = result
    return result

from datetime import datetime, timezone
from dateutil import parser

def time_ago(date_str):
    if not date_str:
        return ""
    try:
        dt = parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        seconds = diff.total_seconds()
        if seconds < 0:
            return "Just now"
            
        minutes = seconds / 60
        hours = minutes / 60
        days = hours / 24
        
        if minutes < 60:
            return f"{int(minutes)} mins ago"
        elif hours < 24:
            return f"{int(hours)} hours ago"
        elif days < 30:
            return f"{int(days)} days ago"
        else:
            return dt.strftime("%b %d, %Y")
    except Exception:
        return ""

# ----------------------------------------------------
# 🔌 API Fetching Methods
# ----------------------------------------------------

# 1. Fetch Trending GitHub AI Repos
def get_github_ai_updates():
    url = "https://api.github.com/search/repositories?q=topic:artificial-intelligence&sort=updated&order=desc"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    repos = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for item in data.get('items', []):
                repos.append({
                    "Type": "GitHub Repo",
                    "Title": item.get('name', 'Unknown'),
                    "Description": item.get('description') or "No description provided.",
                    "Link": item.get('html_url', 'https://github.com'),
                    "Timestamp": time_ago(item.get('updated_at', ''))
                })
    except Exception as e:
        print(f"Error fetching GitHub: {e}")
    return repos

# 2. Fetch Trending Hugging Face Models
def get_huggingface_updates():
    url = "https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=50"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    models = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for item in data:
                model_id = item.get('id', '')
                if model_id and ('llama' in model_id.lower() or 'ai' in model_id.lower() or 'mistral' in model_id.lower()):
                    models.append({
                        "Type": "Hugging Face Model",
                        "Title": model_id,
                        "Description": f"Author: {item.get('author', 'Unknown')} | Downloads: {item.get('downloads', 0)} | Likes: {item.get('likes', 0)}",
                        "Link": f"https://huggingface.co/{model_id}",
                        "Timestamp": time_ago(item.get('lastModified', ''))
                    })
    except Exception as e:
        print(f"Error fetching Hugging Face: {e}")
    return models

# 3. Fetch arXiv Research Papers
def get_arxiv_updates():
    url = "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=15"
    papers = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            papers.append({
                "Type": "arXiv Research Paper",
                "Title": entry.get('title', 'No Title').replace('\n', ' ').strip(),
                "Description": entry.get('summary', 'No abstract available.').replace('\n', ' ').strip()[:300] + "...",
                "Link": entry.get('link', '#'),
                "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
            })
    except Exception as e:
        print(f"Error fetching arXiv: {e}")
    return papers

# 4. Fetch PyPI Package Releases
def get_pypi_updates():
    url = "https://pypi.org/rss/updates.xml"
    packages = []
    try:
        feed = feedparser.parse(url)
        keywords = load_scraper_config("pypi_keywords") or []
        for entry in feed.entries:
            title = entry.get('title', '')
            desc = entry.get('summary', '')
            if any(k in title.lower() or k in desc.lower() for k in keywords):
                packages.append({
                    "Type": "PyPI Release",
                    "Title": title,
                    "Description": desc[:200] + "..." if desc else "New package release on PyPI.",
                    "Link": entry.get('link', 'https://pypi.org'),
                    "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
                })
        if not packages and feed.entries:
            for entry in feed.entries[:5]:
                packages.append({
                    "Type": "PyPI Release",
                    "Title": entry.get('title', 'Unknown Package'),
                    "Description": entry.get('summary', '')[:200] + "...",
                    "Link": entry.get('link', 'https://pypi.org'),
                    "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
                })
    except Exception as e:
        print(f"Error fetching PyPI: {e}")
    return packages

# 5. Fetch AI Blog and Research RSS Feeds (parallel per feed)
def get_blog_updates():
    feeds = load_scraper_config("blog_feeds") or []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def _fetch_feed(url):
        articles = []
        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                source_name = url.split('/')[2].replace('www.', '')
                for entry in feed.entries[:5]:
                    articles.append({
                        "Type": "Corporate Blog",
                        "Title": f"[{source_name.upper()}] {entry.get('title', 'No Title')}",
                        "Description": entry.get('summary', 'Click link to read')[:250] + "...",
                        "Link": entry.get('link', '#'),
                        "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
                    })
        except:
            pass
        return articles

    import concurrent.futures
    all_articles = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(feeds), 16)) as ex:
        results = ex.map(_fetch_feed, feeds)
    for batch in results:
        all_articles.extend(batch)
    return all_articles


# 6. Fetch Reddit AI Discussions
def get_reddit_updates():
    url = "https://www.reddit.com/r/MachineLearning/.rss"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 AI-Discovery-Hub/1.0"
    }
    posts = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:15]:
                posts.append({
                    "Type": "Reddit Discussion",
                    "Title": entry.get('title', 'No Title'),
                    "Description": f"Author: {entry.get('author', 'Unknown')}",
                    "Link": entry.get('link', 'https://reddit.com'),
                    "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
                })
    except Exception as e:
        print(f"Error fetching Reddit: {e}")
    return posts

# 7. Fetch Product Hunt AI Launches
def get_producthunt_updates():
    url = "https://www.producthunt.com/feed"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    launches = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            keywords = load_scraper_config("ph_keywords") or []
            for entry in feed.entries:
                title = entry.get('title', '')
                desc = entry.get('summary', '') or "New product launch on Product Hunt."
                if any(k in title.lower() or k in desc.lower() for k in keywords):
                    launches.append({
                        "Type": "Product Hunt Launch",
                        "Title": title,
                        "Description": desc[:250] + "...",
                        "Link": entry.get('link', 'https://producthunt.com'),
                        "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
                    })
    except Exception as e:
        print(f"Error fetching Product Hunt: {e}")
    return launches

# 8. Fetch AI Courses
def get_course_updates():
    url = "https://www.classcentral.com/report/feed/"
    courses = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            keywords = load_scraper_config("course_keywords") or []
            for entry in feed.entries:
                title = entry.get('title', '')
                desc = entry.get('summary', '') or "Educational resources and course news."
                if any(k in title.lower() or k in desc.lower() for k in keywords):
                    courses.append({
                        "Type": "AI Course",
                        "Title": title,
                        "Description": desc[:250] + "...",
                        "Link": entry.get('link', '#'),
                        "Timestamp": time_ago(entry.get('published') or entry.get('updated'))
                    })
    except:
        pass
    return courses

# 9. Fetch YouTube AI Videos dynamically via global search query (parallel per query)
def get_youtube_updates():
    queries = load_scraper_config("youtube_search_queries") or []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    import urllib.parse

    def _fetch_query(q):
        results = []
        encoded_query = urllib.parse.quote_plus(q)
        url = f"https://www.youtube.com/results?search_query={encoded_query}&sp=CAI%253D"
        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                matches = re.findall(r"var ytInitialData = ({.*?});</script>", response.text)
                if not matches:
                    matches = re.findall(r"window\[\"ytInitialData\"\] = ({.*?});</script>", response.text)
                if matches:
                    data = json.loads(matches[0])
                    section_list = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {})
                    count = 0
                    for section in section_list.get("contents", []):
                        item_section = section.get("itemSectionRenderer", {})
                        for item in item_section.get("contents", []):
                            video_renderer = item.get("videoRenderer", {})
                            lockup_model = item.get("lockupViewModel", {})
                            v_title = v_id = ""
                            v_channel = "YouTube"
                            v_desc = "Watch latest video on YouTube."
                            v_time = ""
                            if video_renderer:
                                v_title = video_renderer.get("title", {}).get("runs", [{}])[0].get("text", "")
                                v_id = video_renderer.get("videoId", "")
                                owner_runs = video_renderer.get("ownerText", {}).get("runs", [])
                                if owner_runs:
                                    v_channel = owner_runs[0].get("text", "YouTube")
                                desc_runs = video_renderer.get("detailedMetadataSnippets", [{}])[0].get("snippetText", {}).get("runs", [])
                                if desc_runs:
                                    v_desc = desc_runs[0].get("text", "Watch video on YouTube.")
                                else:
                                    desc_runs_fb = video_renderer.get("descriptionSnippet", {}).get("runs", [])
                                    if desc_runs_fb:
                                        v_desc = desc_runs_fb[0].get("text", "Watch video on YouTube.")
                            elif lockup_model:
                                v_title = lockup_model.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "")
                                v_id = lockup_model.get("contentId", "")
                                v_channel = lockup_model.get("shortBylineText", {}).get("runs", [{}])[0].get("text", "YouTube")
                            
                            # Fallback extraction for YouTube relative time text (e.g. '2 weeks ago')
                            if video_renderer:
                                v_time = video_renderer.get("publishedTimeText", {}).get("simpleText", "")
                            elif lockup_model:
                                v_time = lockup_model.get("metadata", {}).get("lockupMetadataViewModel", {}).get("metadata", {}).get("primaryMetadataViewModel", {}).get("publishedTimeText", {}).get("content", "")

                            if v_title and v_id:
                                results.append({
                                    "Type": "YouTube Video",
                                    "Title": f"[{v_channel.upper()}] {v_title}",
                                    "Description": v_desc[:250] + "..." if len(v_desc) > 250 else v_desc,
                                    "Link": f"https://www.youtube.com/watch?v={v_id}",
                                    "Timestamp": v_time
                                })
                                count += 1
                                if count >= 5:
                                    break
                        if count >= 5:
                            break
        except Exception as e:
            print(f"Error searching YouTube for {q}: {e}")
        return results

    import concurrent.futures
    videos = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(queries), 8)) as ex:
        for batch in ex.map(_fetch_query, queries):
            videos.extend(batch)
    return videos

# 10. Fetch Hugging Face Datasets
def get_huggingface_dataset_updates():
    url = "https://huggingface.co/api/datasets?sort=lastModified&direction=-1&limit=50"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    datasets = []
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for item in data:
                ds_id = item.get('id', '')
                if ds_id:
                    datasets.append({
                        "Type": "Hugging Face Dataset",
                        "Title": ds_id,
                        "Description": f"Author: {item.get('author', 'Unknown')} | Downloads: {item.get('downloads', 0)} | Likes: {item.get('likes', 0)}",
                        "Link": f"https://huggingface.co/datasets/{ds_id}",
                        "Timestamp": time_ago(item.get('lastModified', ''))
                    })
    except Exception as e:
        print(f"Error fetching Hugging Face Datasets: {e}")
    return datasets

# 11. Fetch Medium & Developer Community Articles (Medium, Dev.to, Hashnode, Hacker News)
def get_medium_dev_community_updates():
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # 1. Dev.to API (Multi-discipline developer tags)
    for tag in ["ai", "webdev", "devops", "testing", "python"]:
        try:
            res = requests.get(f"https://dev.to/api/articles?tag={tag}&per_page=5", headers=headers, timeout=5)
            if res.status_code == 200:
                for a in res.json():
                    articles.append({
                        "Type": "Medium & Dev Community",
                        "Title": f"[DEV.TO / {tag.upper()}] {a.get('title', '')}",
                        "Description": a.get('description', '') or "Developer community engineering post.",
                        "Link": a.get('url', '#'),
                        "Timestamp": time_ago(a.get('published_at', ''))
                    })
        except:
            pass
        
    # 2. Medium Tech RSS Feeds
    medium_feeds = [
        ("Towards Data Science", "https://medium.com/feed/towards-data-science"),
        ("Towards AI", "https://medium.com/feed/towards-artificial-intelligence"),
        ("ITNEXT", "https://medium.com/feed/itnext")
    ]
    for source_name, feed_url in medium_feeds:
        try:
            r = requests.get(feed_url, headers=headers, timeout=5)
            if r.status_code == 200:
                parsed = feedparser.parse(r.content)
                for entry in parsed.entries[:5]:
                    articles.append({
                        "Type": "Medium & Dev Community",
                        "Title": f"[{source_name.upper()}] {entry.get('title', '')}",
                        "Description": (entry.get('summary', '') or "Tech engineering guide")[:250] + "...",
                        "Link": entry.get('link', '#'),
                        "Timestamp": time_ago(entry.get('published', ''))
                    })
        except:
            pass
            
    return articles

# 12. Fetch System Prompt & Guardrail Templates dynamically from GitHub API
def get_prompt_template_updates():
    templates = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    url = "https://api.github.com/search/repositories?q=prompt+guardrail+system-prompt+sort:updated&per_page=15"
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            for item in res.json().get('items', []):
                templates.append({
                    "Type": "Prompt & Guardrail Templates",
                    "Title": f"[PROMPT / GUARDRAIL] {item.get('name', 'Template')}",
                    "Description": item.get('description') or "Production system prompt repository or safety guardrail specification.",
                    "Link": item.get('html_url', '#'),
                    "Timestamp": time_ago(item.get('updated_at', ''))
                })
    except Exception as e:
        print(f"Error fetching dynamic prompt templates: {e}")
    return templates

def extract_fallback_subqueries(query_text, category_name=""):
    if not query_text:
        return ["ai"]
    from usecase_matcher import ENGLISH_STOPWORDS, scenario_matcher
    
    # 1. Dynamically extract the Primary Subject Anchor from scenario text
    subject_anchor = scenario_matcher.extract_subject_anchor(query_text)
    
    # 2. Extract Action Clauses & Modifiers
    clauses = re.split(r'[,;\.\n]| and | that | with | for ', query_text.lower())
    generic_unigrams = {"ai", "driven", "data", "web", "online", "tool", "system", "app", "application", "thought", "think", "build", "using", "create", "looking", "help", "need", "want"}
    
    subqueries = []
    anchor_clean = ""
    
    if subject_anchor:
        anchor_clean = "+".join([w for w in subject_anchor.split() if w not in ENGLISH_STOPWORDS and w not in generic_unigrams])
        if anchor_clean:
            subqueries.append(anchor_clean)
            
    for clause in clauses:
        words = [w.strip() for w in re.findall(r'\b[a-zA-Z0-9\-]+\b', clause) if w.strip() not in ENGLISH_STOPWORDS and w.strip() not in generic_unigrams and len(w.strip()) > 2]
        if words:
            phrase_str = "+".join(words[:2])
            if anchor_clean and anchor_clean not in phrase_str:
                anchored_query = f"{anchor_clean}+{phrase_str}"
            else:
                anchored_query = phrase_str
                
            if anchored_query and anchored_query not in subqueries:
                subqueries.append(anchored_query)
                
    return subqueries[:3] or ["ai"]

# Live Fallback Handler for ALL 12 categories dynamically
def fetch_live_category_fallback(category_name, query=""):
    import urllib.parse
    subqueries = extract_fallback_subqueries(query, category_name)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    results = []
    seen_links = set()
    
    try:
        for q_str in subqueries:
            if category_name == "GitHub Repo":
                # Relevance-based search (no sort=stars bias)
                url = f"https://api.github.com/search/repositories?q={q_str}&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    for item in res.json().get('items', []):
                        link = item.get('html_url', '#')
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "GitHub Repo",
                                "Title": item.get('name', 'Unknown'),
                                "Description": item.get('description') or "No description provided.",
                                "Link": link,
                                "Timestamp": time_ago(item.get('updated_at', ''))
                            })
            elif category_name == "Hugging Face Model":
                url = f"https://huggingface.co/api/models?search={q_str}&sort=downloads&direction=-1&limit=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    for m in res.json():
                        link = f"https://huggingface.co/{m.get('id', '')}"
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "Hugging Face Model",
                                "Title": m.get('id', ''),
                                "Description": f"Author: {m.get('author', 'Unknown')} | Downloads: {m.get('downloads', 0)}",
                                "Link": link,
                                "Timestamp": time_ago(m.get('lastModified', ''))
                            })
            elif category_name == "Hugging Face Dataset":
                url = f"https://huggingface.co/api/datasets?search={q_str}&sort=downloads&direction=-1&limit=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    for d in res.json():
                        link = f"https://huggingface.co/datasets/{d.get('id', '')}"
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "Hugging Face Dataset",
                                "Title": d.get('id', ''),
                                "Description": f"Author: {d.get('author', 'Unknown')} | Downloads: {d.get('downloads', 0)}",
                                "Link": link,
                                "Timestamp": time_ago(d.get('lastModified', ''))
                            })
            elif category_name == "arXiv Research Paper":
                url = f"https://export.arxiv.org/api/query?search_query=all:{q_str}&start=0&max_results=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    entries = re.findall(r'<entry>(.*?)</entry>', res.text, re.DOTALL)
                    for entry in entries:
                        t_m = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                        l_m = re.search(r'<id>(.*?)</id>', entry, re.DOTALL)
                        d_m = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                        p_m = re.search(r'<published>(.*?)</published>', entry, re.DOTALL)
                        
                        title = re.sub(r'\s+', ' ', t_m.group(1)).strip() if t_m else "Research Paper"
                        link = l_m.group(1).strip() if l_m else "#"
                        desc = re.sub(r'\s+', ' ', d_m.group(1)).strip() if d_m else "No abstract available."
                        pub = p_m.group(1).strip() if p_m else ""
                        
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "arXiv Research Paper",
                                "Title": title,
                                "Description": desc[:250] + "..." if len(desc) > 250 else desc,
                                "Link": link,
                                "Timestamp": time_ago(pub)
                            })
            elif category_name == "PyPI Release":
                            seen_links.add(link)
                            desc_text = descs[i].strip() if i < len(descs) else "Python library on PyPI."
                            results.append({
                                "Type": "PyPI Release",
                                "Title": name,
                                "Description": desc_text,
                                "Link": link,
                                "Timestamp": "Recent Release"
                            })
            elif category_name == "Corporate Blog":
                url = f"https://dev.to/api/articles?tag={q_str}&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    for a in res.json():
                        link = a.get('url', '#')
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "Corporate Blog",
                                "Title": f"[BLOG] {a.get('title', '')}",
                                "Description": a.get('description', '') or "Corporate tech blog post.",
                                "Link": link,
                                "Timestamp": time_ago(a.get('published_at', ''))
                            })
            elif category_name == "Medium & Dev Community":
                url = f"https://dev.to/api/articles?tag={q_str.replace('+', '-')}&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    for a in res.json():
                        title = a.get('title', '')
                        desc = a.get('description', '') or ""
                        # Content Verification: Ensure article contains query terms, reject silent trending fallbacks
                        q_words = [w for w in q_str.split('+') if len(w) > 2]
                        if any(w.lower() in (title + " " + desc).lower() for w in q_words):
                            link = a.get('url', '#')
                            if link not in seen_links:
                                seen_links.add(link)
                                results.append({
                                    "Type": "Medium & Dev Community",
                                    "Title": f"[DEV.TO] {title}",
                                    "Description": desc or "Developer community article.",
                                    "Link": link,
                                    "Timestamp": time_ago(a.get('published_at', ''))
                                })
            elif category_name == "Reddit Discussion":
                url = f"https://www.reddit.com/search.json?q={q_str}&sort=relevance&limit=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    data = res.json().get('data', {}).get('children', [])
                    for child in data:
                        d = child.get('data', {})
                        link = f"https://www.reddit.com{d.get('permalink', '')}"
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "Reddit Discussion",
                                "Title": f"[r/{d.get('subreddit', 'all')}] {d.get('title', '')}",
                                "Description": (d.get('selftext', '') or "Reddit community discussion.")[:250] + "...",
                                "Link": link,
                                "Timestamp": time_ago(pd.to_datetime(d.get('created_utc', 0), unit='s').isoformat())
                            })
            elif category_name == "Product Hunt Launch":
                url = f"https://api.github.com/search/repositories?q={q_str}+topic:product-hunt&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200 and res.json().get('items'):
                    for item in res.json().get('items', []):
                        link = item.get('html_url', '#')
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "Product Hunt Launch",
                                "Title": f"[LAUNCH] {item.get('name', '')}",
                                "Description": item.get('description') or "Product launch and developer tool specification.",
                                "Link": link,
                                "Timestamp": time_ago(item.get('updated_at', ''))
                            })
            elif category_name == "AI Course":
                url = f"https://api.github.com/search/repositories?q={q_str}+course+learning&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200:
                    for item in res.json().get('items', []):
                        link = item.get('html_url', '#')
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "AI Course",
                                "Title": f"[COURSE] {item.get('name', '')}",
                                "Description": item.get('description') or "Interactive engineering course and hands-on repository.",
                                "Link": link,
                                "Timestamp": time_ago(item.get('updated_at', ''))
                            })
            elif category_name == "YouTube Video":
                url = f"https://api.github.com/search/repositories?q={q_str}+topic:demo+topic:tutorial&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200 and res.json().get('items'):
                    for item in res.json().get('items', []):
                        link = item.get('html_url', '#')
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "YouTube Video",
                                "Title": f"[DEMO] {item.get('name', '')}",
                                "Description": item.get('description') or "Technical implementation video walkthrough and demo.",
                                "Link": link,
                                "Timestamp": time_ago(item.get('updated_at', ''))
                            })
            elif category_name == "Prompt & Guardrail Templates":
                primary_term = q_str.split('+')[0]
                url = f"https://api.github.com/search/repositories?q={primary_term}+guardrail&per_page=5"
                res = requests.get(url, headers=headers, timeout=6)
                if res.status_code == 200 and res.json().get('items'):
                    for item in res.json().get('items', []):
                        link = item.get('html_url', '#')
                        if link not in seen_links:
                            seen_links.add(link)
                            results.append({
                                "Type": "Prompt & Guardrail Templates",
                                "Title": f"[GUARDRAIL / PROMPT] {item.get('name', '')}",
                                "Description": item.get('description') or "System prompt & guardrail template repository.",
                                "Link": link,
                                "Timestamp": time_ago(item.get('updated_at', ''))
                            })
                else:
                    # Fallback query using prompt templates
                    url2 = f"https://api.github.com/search/repositories?q=system-prompt+{primary_term}&per_page=5"
                    res2 = requests.get(url2, headers=headers, timeout=6)
                    if res2.status_code == 200:
                        for item in res2.json().get('items', []):
                            link = item.get('html_url', '#')
                            if link not in seen_links:
                                seen_links.add(link)
                                results.append({
                                    "Type": "Prompt & Guardrail Templates",
                                    "Title": f"[GUARDRAIL / PROMPT] {item.get('name', '')}",
                                    "Description": item.get('description') or "System prompt & guardrail template repository.",
                                    "Link": link,
                                    "Timestamp": time_ago(item.get('updated_at', ''))
                                })
    except Exception as e:
        print(f"Error fetching live fallback for {category_name}: {e}")
        
    return results

# ----------------------------------------------------
# 🔍 Direct Link Metadata Enricher (Crawls actual page title/meta description)
# ----------------------------------------------------
def enrich_item_metadata(item):
    """
    Fetches only the first 24KB of the target page (enough to get all <head> meta tags)
    instead of downloading the full HTML — much faster for pages that can be 500KB+.
    """
    url = item.get("Link", "")
    if not url or url == "#" or "youtube.com" in url:
        item["PageTitle"] = item.get("Title")
        item["PageDescription"] = item.get("Description")
        item["PageImage"] = ""
        item["PageOutline"] = []
        return item

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
            "Accept-Encoding": "gzip, deflate",
        }
        # Stream=True + read only first 100KB — some sites place meta tags deep in <head>
        with requests.get(url, headers=headers, timeout=5, stream=True) as resp:
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")
            raw_bytes = b""
            for chunk in resp.iter_content(chunk_size=8192):
                raw_bytes += chunk
                if len(raw_bytes) >= 102400:  # 100KB is enough for modern <head>
                    break
        html = raw_bytes.decode("utf-8", errors="ignore")

        # 1. Title
        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        p_title = re.sub(r"\s+", " ", title_match.group(1).strip()) if title_match else ""

        # 2. Meta Description (name or og:description)
        p_desc = ""
        for pat in [
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']',
            r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\']',
            r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:description["\']',
        ]:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                p_desc = re.sub(r"\s+", " ", m.group(1).strip())
                break
        if p_desc and len(p_desc) > 250:
            p_desc = p_desc[:250] + "..."

        # 3. og:image / twitter:image — trust the URL, let browser onerror handle broken ones
        p_img = ""
        for pat in [
            r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']',
            r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:image["\']',
            r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\'](.*?)["\']',
            r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']twitter:image["\']',
        ]:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                p_img = m.group(1).strip()
                if p_img.startswith("/") and not p_img.startswith("//"):
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(url)
                    p_img = f"{parsed_url.scheme}://{parsed_url.netloc}{p_img}"
                break

        # 4. Headings for chip tags (from partial HTML, best-effort)
        headings = []
        for h_type in ["h1", "h2", "h3"]:
            for h_text in re.findall(rf"<{h_type}[^>]*>(.*?)</{h_type}>", html, re.IGNORECASE | re.DOTALL):
                h_clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h_text).strip())
                if h_clean and 5 < len(h_clean) < 70 and h_clean not in headings:
                    headings.append(h_clean)
                    if len(headings) >= 3:
                        break
            if len(headings) >= 3:
                break

        item["PageTitle"] = p_title or item.get("Title")
        item["PageDescription"] = p_desc or item.get("Description")
        item["PageImage"] = p_img
        item["PageOutline"] = headings
        return item

    except Exception:
        pass

    item["PageTitle"] = item.get("Title")
    item["PageDescription"] = item.get("Description")
    item["PageImage"] = ""
    item["PageOutline"] = []
    return item

def enrich_updates_in_parallel(updates_list):
    """
    Crawls target links in parallel to enrich the items with actual page titles and summaries.
    Uses 24 workers for maximum throughput.
    """
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executor:
        enriched = list(executor.map(enrich_item_metadata, updates_list))
    return enriched


# ----------------------------------------------------
# 🔑 MongoDB Helpers
# ----------------------------------------------------
def get_mongo_client(uri):
    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client
    except Exception as e:
        print(f"MongoDB connection check failed: {e}")
        return None

def save_updates_to_mongo(client, updates_list):
    if not client:
        return 0
    db = client["ai_discovery"]
    collection = db["updates"]
    
    new_count = 0
    for item in updates_list:
        doc = {
            "_id": item["Link"],
            "type": item["Type"],
            "title": item["Title"],
            "description": item["Description"],
            "page_title": item.get("PageTitle", item["Title"]),
            "page_description": item.get("PageDescription", item["Description"]),
            "page_image": item.get("PageImage", ""),
            "page_outline": item.get("PageOutline", []),
            "timestamp": item.get("Timestamp", ""),
            "fetched_at": pd.Timestamp.now().isoformat()
        }
        try:
            result = collection.replace_one({"_id": item["Link"]}, doc, upsert=True)
            if result.upserted_id is not None:
                new_count += 1
        except Exception as e:
            print(f"Error upserting document: {e}")
            pass
    return new_count

def get_persisted_updates_from_mongo(client, update_type):
    if not client:
        return []
    db = client["ai_discovery"]
    collection = db["updates"]
    
    results = []
    try:
        # Load ALL records for this type, sorted alphabetically by title
        cursor = collection.find(
            {"type": update_type}
        ).sort("title", 1).limit(500)  # 500 per category max
        
        for doc in cursor:
            results.append({
                "Type": doc["type"],
                "Title": doc["title"],
                "Description": doc["description"],
                "PageTitle": doc.get("page_title", doc["title"]),
                "PageDescription": doc.get("page_description", doc["description"]),
                "PageImage": doc.get("page_image", ""),
                "PageOutline": doc.get("page_outline", []),
                "Timestamp": doc.get("timestamp", ""),
                "Link": doc["_id"]
            })
    except Exception as e:
        print(f"Error loading persisted data for {update_type}: {e}")
    return results

def get_db_stats(client):
    if not client:
        return {}
    db = client["ai_discovery"]
    collection = db["updates"]
    stats = {}
    try:
        pipeline = [
            {"$group": {"_id": "$type", "count": {"$sum": 1}}}
        ]
        groups = collection.aggregate(pipeline)
        for g in groups:
            stats[g["_id"]] = g["count"]
    except Exception as e:
        print(f"Error gathering stats: {e}")
    return stats

def clear_mongo_db(client):
    if not client:
        return False
    try:
        db = client["ai_discovery"]
        db["updates"].drop()
        return True
    except Exception as e:
        print(f"Error dropping database collection: {e}")
        return False

ALL_12_CATEGORIES = [
    "GitHub Repo",
    "Hugging Face Model",
    "Hugging Face Dataset",
    "arXiv Research Paper",
    "PyPI Release",
    "Corporate Blog",
    "Medium & Dev Community",
    "Reddit Discussion",
    "Product Hunt Launch",
    "AI Course",
    "YouTube Video",
    "Prompt & Guardrail Templates"
]

def fetch_all_updates_dict(client=None):
    data = {}
    if client:
        try:
            for cat in ALL_12_CATEGORIES:
                items = get_persisted_updates_from_mongo(client, cat)
                if items:
                    data[cat] = items
        except Exception as e:
            print(f"Error fetching persisted data: {e}")
            
    # Live fallback if data is incomplete or client is None
    if not data:
        data = {
            "GitHub Repo": get_github_ai_updates(),
            "Hugging Face Model": get_huggingface_updates(),
            "Hugging Face Dataset": get_huggingface_dataset_updates(),
            "arXiv Research Paper": get_arxiv_updates(),
            "PyPI Release": get_pypi_updates(),
            "Corporate Blog": get_blog_updates(),
            "Medium & Dev Community": get_medium_dev_community_updates(),
            "Reddit Discussion": get_reddit_updates(),
            "Product Hunt Launch": get_producthunt_updates(),
            "AI Course": get_course_updates(),
            "YouTube Video": get_youtube_updates(),
            "Prompt & Guardrail Templates": get_prompt_template_updates()
        }
    else:
        # Fill missing keys if any
        if "Hugging Face Dataset" not in data:
            data["Hugging Face Dataset"] = get_huggingface_dataset_updates()
        if "Medium & Dev Community" not in data:
            data["Medium & Dev Community"] = get_medium_dev_community_updates()
        if "Prompt & Guardrail Templates" not in data:
            data["Prompt & Guardrail Templates"] = get_prompt_template_updates()
            
    return data

