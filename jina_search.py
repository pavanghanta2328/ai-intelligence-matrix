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
    "Corporate Blog": "site:openai.com/blog OR site:deepmind.google/discover/blog OR site:anthropic.com/news",
    "Medium & Dev Community": "site:medium.com OR site:dev.to",
    "Reddit Discussion": "site:reddit.com/r/MachineLearning OR site:reddit.com/r/artificial",
    "Product Hunt Launch": "site:producthunt.com",
    "AI Course": "site:coursera.org OR site:udemy.com OR site:classcentral.com",
    "YouTube Video": "site:youtube.com",
    "Prompt & Guardrail Templates": "site:github.com prompt OR site:github.com guardrail"
}

def _get_jina_api_key():
    key = os.environ.get("JINA_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("JINA_API_KEY")
        except Exception:
            pass
    return key

def get_jina_resources_without_llm(problem_statement: str):
    """
    Fetches results directly from a natural language problem statement using 
    Jina AI's search endpoint for all 12 predefined categories.
    """
    api_key = _get_jina_api_key()
    
    # CRITICAL FIX 1: Ask Jina to return structured JSON payloads
    headers = {
        "Accept": "application/json" 
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    results = {}
    
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[ 429, 500, 502, 503, 504 ])
    
    # CRITICAL FIX 2: Increase pool_maxsize to match or exceed max_workers (12)
    adapter = HTTPAdapter(max_retries=retries, pool_connections=15, pool_maxsize=15)
    session.mount('https://', adapter)
    
    def _fetch_category(category, operator):
        combined_query = f"{problem_statement} {operator}"
        encoded_query = urllib.parse.quote(combined_query)
        url = f"https://s.jina.ai/{encoded_query}"
        
        try:
            response = session.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                try:
                    data = response.json().get("data", [])
                    return category, data
                except Exception:
                    return category, "Error: Invalid JSON response from Jina"
            else:
                return category, f"Error: Status code {response.status_code}"
        except Exception as e:
            return category, f"Failed to fetch: {str(e)}"
            
    # Fetch in parallel for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(_fetch_category, cat, op): cat for cat, op in JINA_CATEGORY_MAPPING.items()}
        for future in concurrent.futures.as_completed(futures):
            cat, result_text = future.result()
            results[cat] = result_text

    return results
