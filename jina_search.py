import urllib.parse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import concurrent.futures
import os

JINA_CATEGORY_MAPPING = {
    "GitHub Repo": "site:github.com",
    "Hugging Face Model": "site:huggingface.co/models",
    "Hugging Face Dataset": "site:huggingface.co/datasets",
    "arXiv Research Paper": "site:arxiv.org",
    "Packages (PyPI/NPM)": "site:pypi.org OR site:npmjs.com",
    "Engineering Blogs": "site:engineering.fb.com OR site:netflixtechblog.com OR site:blog.cloudflare.com OR site:aws.amazon.com/blogs/ OR site:cloud.google.com/blog",
    "Medium & Dev Community": "site:medium.com OR site:dev.to",
    "Reddit Discussion": "site:reddit.com",
    "Product Hunt Launch": "site:producthunt.com",
    "Online Course": "site:coursera.org OR site:udemy.com OR site:edx.org",
    "YouTube Video": "site:youtube.com",
    "Code Snippets & Gists": "site:gist.github.com OR site:stackoverflow.com"
}



def extract_keywords_with_openrouter(problem_statement: str) -> dict:
    """Uses OpenRouter's free models to extract optimal search keywords and relevant categories."""
    import json
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("OPENROUTER_API_KEY")
        except Exception:
            pass
            
    # Default fallback
    words = problem_statement.split()
    short_query = " ".join(words[:12])
    fallback_result = {
        "optimized_query": short_query[:100] if len(short_query) > 100 else short_query,
        "relevant_categories": list(JINA_CATEGORY_MAPPING.keys())
    }
            
    if not key:
        return fallback_result
        
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        valid_categories = list(JINA_CATEGORY_MAPPING.keys())
        system_prompt = f"""You are an expert Google Search query optimizer for software engineering and AI architectures.
Your goal is to act like a semantic search engine: you must understand the deep technical meaning of the user's problem and translate it into the most effective Google Search query possible to discover the best repositories, research papers, and tech blogs.

Follow these strict rules for flawless results:
1. TRIPLE DISTILLATION: Strip away all conversational noise. Translate the core problem into 3 to 5 broad, industry-standard architectural concepts. (e.g., If the user says "control remains in same state for days", translate it to the industry standard "long-running state management").
2. DO NOT OVER-CONSTRAIN: Never use more than 5 words. Google's algorithm works best with fewer, highly semantic terms. If you use too many keywords, Google will incorrectly filter out perfect matches.
3. CATEGORY SELECTION: Select exactly 2 or 3 of the most relevant categories to search from this list: {valid_categories}

You must output valid JSON in this exact format:
{{
  "optimized_query": "your 3-to-5 word google search query here",
  "relevant_categories": ["Category 1", "Category 2"]
}}"""

        data = {
            "model": "openrouter/free",
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": problem_statement}
            ]
        }
        # Use a short timeout so the UI doesn't hang forever if OpenRouter is slow
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            extracted = response.json()['choices'][0]['message']['content'].strip()
            return json.loads(extracted)
        else:
            print(f"OpenRouter Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"OpenRouter extraction failed: {e}")
        
    return fallback_result

def get_semantic_discovery_results(problem_statement: str):
    """
    Fetches results directly from a natural language problem statement using 
    Serper.dev (Google Search API), optimized via OpenRouter dynamic extraction.
    """
    import time
    import random
    
    results = {}
    
    serper_key = os.environ.get("SERPER_API_KEY")
    if not serper_key:
        try:
            import streamlit as st
            serper_key = st.secrets.get("SERPER_API_KEY")
        except Exception:
            pass
            
    if not serper_key:
        return {"Error": "Please add SERPER_API_KEY to your .streamlit/secrets.toml file to use the Google Search backend."}
    
    # CRITICAL HYBRID FIX: Use OpenRouter once to extract intelligent keywords for free
    extraction_data = extract_keywords_with_openrouter(problem_statement)
    optimized_query = extraction_data.get("optimized_query", problem_statement)
    relevant_categories = extraction_data.get("relevant_categories", list(JINA_CATEGORY_MAPPING.keys()))
    
    def _fetch_category(category, operator):
        # We can still add a small jitter just to play nice with our own thread pool
        time.sleep(random.uniform(0.1, 0.5))
        
        combined_query = f"{optimized_query} {operator}"
        url = "https://google.serper.dev/search"
        payload = {
            "q": combined_query,
            "num": 5
        }
        headers = {
            "X-API-KEY": serper_key,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                return category, f"Serper API Error: {response.status_code} - {response.text}"
                
            data = response.json()
            organic_results = data.get("organic", [])
            
            category_data = []
            for r in organic_results[:5]:
                # Map Serper keys to expected frontend keys to prevent UI breakages
                category_data.append({
                    "title": r.get("title", "Untitled"),
                    "url": r.get("link", "#"),
                    "description": r.get("snippet", "No summary provided.")
                })
            return category, category_data
            
        except Exception as e:
            return category, f"Failed to fetch from Serper: {str(e)}"
            
    # Fetch in parallel for speed, but ONLY for the relevant categories determined by the LLM
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {}
        for cat, op in JINA_CATEGORY_MAPPING.items():
            if cat in relevant_categories:
                futures[executor.submit(_fetch_category, cat, op)] = cat
            else:
                # If LLM deemed this category irrelevant, skip the API call to save Serper credits
                # We return an empty list so the Streamlit UI cleanly skips rendering a tab for it.
                results[cat] = []
                
        for future in concurrent.futures.as_completed(futures):
            cat, result_data = future.result()
            results[cat] = result_data

    return results
