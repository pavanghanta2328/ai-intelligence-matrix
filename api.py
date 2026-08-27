from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
import pymongo
import os

from scrapers import (
    get_github_ai_updates,
    get_huggingface_updates,
    get_arxiv_updates,
    get_pypi_updates,
    get_blog_updates,
    get_reddit_updates,
    get_producthunt_updates,
    get_course_updates,
    get_youtube_updates,
    get_mongo_client,
    save_updates_to_mongo,
    get_persisted_updates_from_mongo,
    enrich_updates_in_parallel
)

app = FastAPI(title="Enterprise AI Discovery API", docs_url=None)

# Enable CORS so browser extensions can query the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    standard_html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI"
    )
    custom_style = """
    <style>
        .swagger-ui .topbar {
            background-color: #090D16 !important;
            border-bottom: 2px solid #38BDF8 !important;
        }
    </style>
    """
    html_content = standard_html.body.decode("utf-8").replace("</head>", f"{custom_style}</head>")
    return HTMLResponse(content=html_content)

def load_mongo_uri():
    uri = os.environ.get("mongo_uri")
    if uri:
        return uri
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    if os.path.exists(secrets_path):
        with open(secrets_path, "r") as f:
            for line in f:
                if line.strip().startswith("mongo_uri"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip('"').strip("'")
    return None

def get_optional_db_client():
    uri = load_mongo_uri()
    if not uri or "YOUR_PASSWORD_HERE" in uri:
        return None
    try:
        return get_mongo_client(uri)
    except Exception as e:
        print(f"MongoDB fallback notice: {e}")
        return None

def fetch_all_live_updates():
    github_data = get_github_ai_updates()
    hf_data = get_huggingface_updates()
    arxiv_data = get_arxiv_updates()
    pypi_data = get_pypi_updates()
    blog_data = get_blog_updates()
    reddit_data = get_reddit_updates()
    ph_data = get_producthunt_updates()
    course_data = get_course_updates()
    yt_data = get_youtube_updates()
    
    all_list = (
        github_data + hf_data + arxiv_data + pypi_data + 
        blog_data + reddit_data + ph_data + course_data + yt_data
    )
    
    # Enrich all updates in parallel to get live PageTitle and PageDescription
    all_list = enrich_updates_in_parallel(all_list)
    
    # Re-group by category
    categories = {
        "GitHub Repo": [x for x in all_list if x["Type"] == "GitHub Repo"],
        "Hugging Face Model": [x for x in all_list if x["Type"] == "Hugging Face Model"],
        "arXiv Research Paper": [x for x in all_list if x["Type"] == "arXiv Research Paper"],
        "PyPI Release": [x for x in all_list if x["Type"] == "PyPI Release"],
        "Corporate Blog": [x for x in all_list if x["Type"] == "Corporate Blog"],
        "Reddit Discussion": [x for x in all_list if x["Type"] == "Reddit Discussion"],
        "Product Hunt Launch": [x for x in all_list if x["Type"] == "Product Hunt Launch"],
        "AI Course": [x for x in all_list if x["Type"] == "AI Course"],
        "YouTube Video": [x for x in all_list if x["Type"] == "YouTube Video"]
    }
    return categories, all_list

@app.get("/")
def read_root():
    return {"status": "online", "message": "Enterprise AI Discovery API is running."}

@app.get("/api/updates")
def get_updates():
    client = get_optional_db_client()
    
    categories = [
        "GitHub Repo",
        "Hugging Face Model",
        "arXiv Research Paper",
        "PyPI Release",
        "Corporate Blog",
        "Reddit Discussion",
        "Product Hunt Launch",
        "AI Course",
        "YouTube Video"
    ]
    
    response_data = {}
    has_persisted_data = False
    
    if client:
        try:
            for cat in categories:
                cat_updates = get_persisted_updates_from_mongo(client, cat)
                if cat_updates:
                    has_persisted_data = True
                response_data[cat] = cat_updates
        except Exception as e:
            print(f"Error querying database: {e}")
        finally:
            client.close()
            
    # Fallback to live scraping if Mongo is disconnected or has no data
    if not has_persisted_data:
        live_categories, _ = fetch_all_live_updates()
        return live_categories

    return response_data

@app.post("/api/sync")
def sync_updates():
    client = get_optional_db_client()
    try:
        live_categories, all_updates = fetch_all_live_updates()
        
        new_saved_count = 0
        if client and all_updates:
            new_saved_count = save_updates_to_mongo(client, all_updates)
            
        updated_data = {}
        categories = [
            "GitHub Repo",
            "Hugging Face Model",
            "arXiv Research Paper",
            "PyPI Release",
            "Corporate Blog",
            "Reddit Discussion",
            "Product Hunt Launch",
            "AI Course",
            "YouTube Video"
        ]
        
        if client:
            try:
                for cat in categories:
                    updated_data[cat] = get_persisted_updates_from_mongo(client, cat)
            except Exception as e:
                print(f"Error reading back from Mongo: {e}")
                updated_data = live_categories
            finally:
                client.close()
        else:
            updated_data = live_categories
            
        return {
            "status": "success",
            "mongo_connected": client is not None,
            "new_inserted": new_saved_count,
            "updates": updated_data
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error performing synchronisation: {str(e)}"
        )

