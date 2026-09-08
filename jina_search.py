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
                {"role": "system", "content": "You are an expert search query optimizer. Extract exactly 3 to 5 of the most important single-word keywords (technologies or concepts) from the user's problem statement. Output ONLY these words separated by spaces. NO PHRASES. MAXIMUM 5 WORDS TOTAL."},
                {"role": "user", "content": problem_statement}
            ]
        }
        # Use a short timeout so the UI doesn't hang forever if OpenRouter is slow
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=8)
        if response.status_code == 200:
            extracted = response.json()['choices'][0]['message']['content'].strip()
            # Hard limit to 5 words to prevent Jina 422 errors
            return " ".join(extracted.split()[:5])
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
    DuckDuckGo Search, optimized via OpenRouter keyword extraction.
    """
    import time
    import random
    try:
        from ddgs import DDGS
    except ImportError:
        return {"Error": "Please run 'pip install ddgs' to use the free DuckDuckGo search backend."}
        
    results = {}
    
    # CRITICAL HYBRID FIX: Use OpenRouter once to extract intelligent keywords for free
    optimized_query = extract_keywords_with_openrouter(problem_statement)
    
    def _fetch_category(category, operator):
        # Jitter to prevent massive 12-request spike triggering DDG anti-bot
        time.sleep(random.uniform(0.1, 0.8))
        
        combined_query = f"{optimized_query} {operator}"
        
        try:
            category_data = []
            with DDGS() as ddgs:
                # max_results=5 to mimic the original Jina payload size
                for r in ddgs.text(combined_query, max_results=5):
                    # Map DDG keys to Jina expected keys to prevent UI breakages
                    category_data.append({
                        "title": r.get("title", "Untitled"),
                        "url": r.get("href", "#"),
                        "description": r.get("body", "No summary provided.")
                    })
            return category, category_data
            
        except Exception as e:
            # Simple fallback/graceful degradation if temporary rate limit is hit
            time.sleep(random.uniform(1.0, 2.5))
            try:
                category_data = []
                with DDGS() as ddgs:
                    for r in ddgs.text(combined_query, max_results=3):
                        category_data.append({
                            "title": r.get("title", "Untitled"),
                            "url": r.get("href", "#"),
                            "description": r.get("body", "No summary provided.")
                        })
                return category, category_data
            except Exception as e2:
                return category, f"Rate limited/Failed to fetch: {str(e2)}"
            
    # Fetch in parallel for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(_fetch_category, cat, op): cat for cat, op in JINA_CATEGORY_MAPPING.items()}
        for future in concurrent.futures.as_completed(futures):
            cat, result_data = future.result()
            results[cat] = result_data

    return results
