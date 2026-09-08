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

def extract_keywords_with_openrouter(problem_statement: str) -> str:
    """Uses OpenRouter's free models to extract optimal search keywords, falling back to truncation."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("OPENROUTER_API_KEY")
        except Exception:
            pass
            
    if not key:
        words = problem_statement.split()
        short_query = " ".join(words[:12])
        return short_query[:100] if len(short_query) > 100 else short_query
        
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openai/gpt-4o-mini", # Extremely fast and reliable model on OpenRouter
            "messages": [
                {"role": "system", "content": "You are an expert search query optimizer. Extract the core 3-6 technologies, frameworks, or key concepts from the user's problem statement. Output ONLY the extracted keywords separated by spaces. Do not include introductory text or punctuation."},
                {"role": "user", "content": problem_statement}
            ]
        }
        # Use a short timeout so the UI doesn't hang forever if OpenRouter is slow
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=8)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"OpenRouter Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"OpenRouter extraction failed: {e}")
        
    # Fallback to truncation if OpenRouter fails or times out
    words = problem_statement.split()
    short_query = " ".join(words[:12])
    return short_query[:100] if len(short_query) > 100 else short_query

def get_jina_resources_without_llm(problem_statement: str):
    """
    Fetches results directly from a natural language problem statement using 
    Jina AI's search endpoint, optimized via OpenRouter keyword extraction.
    """
    api_key = _get_jina_api_key()
    
    headers = {
        "Accept": "application/json" 
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    results = {}
    
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[ 429, 500, 502, 503, 504 ])
    
    adapter = HTTPAdapter(max_retries=retries, pool_connections=15, pool_maxsize=15)
    session.mount('https://', adapter)
    
    # CRITICAL HYBRID FIX: Use OpenRouter once to extract intelligent keywords for free
    optimized_query = extract_keywords_with_openrouter(problem_statement)
    
    def _fetch_category(category, operator):
        combined_query = f"{optimized_query} {operator}"
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
