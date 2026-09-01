import streamlit as st
import pandas as pd
from scrapers import (
    get_github_ai_updates,
    get_huggingface_updates,
    get_huggingface_dataset_updates,
    get_arxiv_updates,
    get_pypi_updates,
    get_blog_updates,
    get_medium_dev_community_updates,
    get_reddit_updates,
    get_producthunt_updates,
    get_course_updates,
    get_youtube_updates,
    get_prompt_template_updates,
    get_mongo_client,
    save_updates_to_mongo,
    get_persisted_updates_from_mongo,
    get_db_stats,
    clear_mongo_db,
    fetch_all_updates_dict
)



# ----------------------------------------------------
# 📡 Embed REST API Endpoint directly into Streamlit Web Server
# ----------------------------------------------------
def _inject_streamlit_api_route():
    try:
        from streamlit.web.server.server import Server
        import tornado.web
        import tornado.routing
        import json
        import os

        if getattr(Server, "_api_patched", False):
            return
        Server._api_patched = True

        orig_create_app = Server._create_app

        def patched_create_app(self):
            app = orig_create_app(self)

            class ApiUpdatesHandler(tornado.web.RequestHandler):
                def set_default_headers(self):
                    self.set_header("Access-Control-Allow-Origin", "*")
                    self.set_header("Access-Control-Allow-Headers", "*")
                    self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.set_header("Content-Type", "application/json")

                def options(self):
                    self.set_status(204)
                    self.finish()

                def get(self):
                    categories = [
                        "GitHub Repo", "Hugging Face Model", "Hugging Face Dataset",
                        "arXiv Research Paper", "PyPI Release", "Corporate Blog",
                        "Medium & Dev Community", "Reddit Discussion",
                        "Product Hunt Launch", "AI Course", "YouTube Video",
                        "Prompt & Guardrail Templates"
                    ]
                    mongo_uri = os.environ.get("mongo_uri")
                    if not mongo_uri:
                        try:
                            import streamlit as st
                            mongo_uri = st.secrets.get("mongo_uri")
                        except Exception:
                            mongo_uri = None

                    resp_data = {}
                    if mongo_uri and "YOUR_PASSWORD_HERE" not in mongo_uri:
                        from scrapers import get_mongo_client, fetch_all_updates_dict
                        c = get_mongo_client(mongo_uri)
                        if c:
                            try:
                                resp_data = fetch_all_updates_dict(c)
                            finally:
                                c.close()
                    self.write(json.dumps(resp_data))

            class ApiRecommendHandler(tornado.web.RequestHandler):
                def set_default_headers(self):
                    self.set_header("Access-Control-Allow-Origin", "*")
                    self.set_header("Access-Control-Allow-Headers", "*")
                    self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.set_header("Content-Type", "application/json")

                def options(self):
                    self.set_status(204)
                    self.finish()

                def post(self):
                    try:
                        body = json.loads(self.request.body)
                        scenario = body.get("scenario", "")
                        top_k = body.get("top_k", 5)

                        mongo_uri = os.environ.get("mongo_uri")
                        if not mongo_uri:
                            try:
                                import streamlit as st
                                mongo_uri = st.secrets.get("mongo_uri")
                            except Exception:
                                mongo_uri = None

                        from scrapers import get_mongo_client, fetch_all_updates_dict, fetch_live_category_fallback
                        c = get_mongo_client(mongo_uri) if mongo_uri else None
                        all_data = fetch_all_updates_dict(c)
                        if c: c.close()

                        from usecase_matcher import scenario_matcher
                        result = scenario_matcher.match_scenario(scenario, all_data, top_k=top_k)

                        for cat in result.get("low_confidence_categories", []):
                            live_items = fetch_live_category_fallback(cat, scenario)
                            if live_items:
                                scored_items = []
                                for item in live_items:
                                    score, matched_kw, tip = scenario_matcher.score_item(item, result["keywords"])
                                    item_copy = dict(item)
                                    item_copy["MatchScore"] = score
                                    item_copy["MatchedKeywords"] = matched_kw or result["keywords"][:2]
                                    item_copy["IntegrationTip"] = tip
                                    scored_items.append(item_copy)
                                if scored_items:
                                    result["recommendations"][cat] = scored_items[:top_k]

                        self.write(json.dumps(result))
                    except Exception as e:
                        self.set_status(500)
                        self.write(json.dumps({"error": str(e)}))

            rule1 = tornado.routing.Rule(tornado.routing.PathMatches(r"/api/updates"), ApiUpdatesHandler)
            rule2 = tornado.routing.Rule(tornado.routing.PathMatches(r"/api/recommend"), ApiRecommendHandler)
            app.wildcard_router.rules.insert(0, rule1)
            app.wildcard_router.rules.insert(0, rule2)
            return app

        Server._create_app = patched_create_app
    except Exception as e:
        print(f"API Route Injection Notice: {e}")

_inject_streamlit_api_route()


# ----------------------------------------------------
# 🔍 Rich Pylance Hover Tooltip Helper
# ----------------------------------------------------
def generate_pylance_preview(item, category, domain_host):
    title = item.get('Title', 'Untitled')
    desc = item.get('Description', 'No description provided.')
    link = item.get('Link', '#')
    
    # Retrieve enriched metadata (fall back to scraped title/description if not enriched yet)
    page_title = item.get('PageTitle', title)
    page_description = item.get('PageDescription', desc)
    page_image = item.get('PageImage', '')
    page_outline = item.get('PageOutline', [])
    if not page_image and category == "YouTube Video" and link:
        try:
            if "youtube.com/watch" in link:
                import urllib.parse
                parsed = urllib.parse.urlparse(link)
                qs = urllib.parse.parse_qs(parsed.query)
                if 'v' in qs:
                    video_id = qs['v'][0]
                    page_image = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            elif "youtu.be/" in link:
                video_id = link.split("youtu.be/")[1].split("?")[0]
                page_image = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        except:
            pass
            
    # Clean up signature
    clean_sig = category.replace(" ", "")

    # Ensure page_image is absolute; otherwise discard it
    if page_image and not page_image.startswith("http"):
        page_image = ""

    # Image block — uses native image if available, else a beautiful pure CSS branded fallback
    if page_image:
        img_block = f'<img src="{page_image}" onerror="this.style.display=\'none\';" style="width:calc(100% + 28px); margin: -14px -14px 14px -14px; height:160px; object-fit:cover; border-top-left-radius:8px; border-top-right-radius:8px; display:block;" />'
    else:
        # Pure CSS fallback using category theme colors
        cat_colors_fallback = {
            "GitHub Repo": ("#1e293b", "#0f172a"),
            "Hugging Face Model": ("#ffca28", "#f57c00"),
            "arXiv Research Paper": ("#b31b1b", "#5a0e0e"),
            "PyPI Release": ("#3775a9", "#1d405e"),
            "Corporate Blog": ("#10b981", "#047857"),
            "Reddit Discussion": ("#ff4500", "#992900"),
            "Product Hunt Launch": ("#da552f", "#80301a"),
            "AI Course": ("#f59e0b", "#b45309"),
            "YouTube Video": ("#dc2626", "#7f1d1d")
        }
        c1, c2 = cat_colors_fallback.get(category, ("#1e293b", "#020617"))
        
        short_name = {
            "arXiv Research Paper": "arXiv",
            "PyPI Release": "PyPI",
            "Reddit Discussion": "Reddit",
            "Product Hunt Launch": "Product Hunt",
            "Corporate Blog": "Tech Blog",
            "Hugging Face Model": "Hugging Face"
        }.get(category, domain_host.split(".")[0].capitalize())
        
        img_block = f"""
        <div style="width:calc(100% + 28px); margin: -14px -14px 14px -14px; height:140px; background:linear-gradient(135deg, {c1} 0%, {c2} 100%); border-top-left-radius:8px; border-top-right-radius:8px; display:flex; align-items:center; justify-content:center; box-shadow:inset 0 -10px 20px rgba(0,0,0,0.2);">
            <div style="background:rgba(0,0,0,0.2); padding:12px 28px; border-radius:12px; border:1px solid rgba(255,255,255,0.1);">
                <span style="font-size:1.8rem; font-weight:800; color:rgba(255,255,255,0.95); letter-spacing:2px; font-family:sans-serif;">{short_name}</span>
            </div>
        </div>"""
    
    # Render topics as colorful chip tags instead of a bullet list
    chips_html = ""
    if page_outline:
        chip_colors = ["#f97316","#a855f7","#38BDF8","#34D399","#fb7185","#facc15","#60a5fa"]
        chips = ""
        for i, heading in enumerate(page_outline[:6]):
            color = chip_colors[i % len(chip_colors)]
            chips += f'<span style="display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.72rem; font-weight:600; color:{color}; border:1px solid {color}; margin:2px 3px 2px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:180px;">{heading}</span>'
        chips_html = f'<div style="margin-bottom:10px; line-height:2;">{chips}</div>'

    # Build header bar styles based on whether image is available
    header_border_top = "border-top-left-radius:8px; border-top-right-radius:8px;" if not page_image else ""

    raw_html = f"""<div class="preview-popover">
{img_block}
<div style="background: linear-gradient(90deg, #7c2d12 0%, #581c87 60%, #1e1b4b 100%); padding: 10px 14px; margin: 0 -14px 14px -14px; {header_border_top} font-family: Consolas, monospace; font-size: 0.82rem; display: flex; justify-content: space-between; align-items: center;">
<div>
<span style="color:#fbbf24; font-weight:600; font-size:0.7rem; letter-spacing:1px; text-transform:uppercase;">{category}</span>
<span style="color: #e2e8f0; font-weight:600; margin-left:6px; font-size:0.82rem;">→ {title[:35]}</span>
</div>
<span style="background: rgba(251,191,36,0.15); color: #fbbf24; border:1px solid rgba(251,191,36,0.4); padding: 2px 8px; border-radius: 12px; font-size: 0.65rem; font-weight:600; flex-shrink:0; margin-left:8px;">{domain_host}</span>
</div>
<div style="padding: 4px 0 8px 0;">
<div style="font-size:1rem; font-weight:700; color:#f1f5f9; line-height:1.35; margin-bottom:6px;">{page_title[:100]}</div>
<div style="font-size:0.83rem; color:#cbd5e1; line-height:1.5; margin-bottom:{"10px" if chips_html else "0"};">{page_description[:200]}{"…" if len(page_description) > 200 else ""}</div>
{chips_html}
</div>
<div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 8px; margin-top:4px;">
<a class="popover-btn" href="{link}" target="_blank" style="display:block; text-align:center; background: linear-gradient(90deg, #f97316, #a855f7); color:#ffffff !important; font-size:0.82rem; font-weight:700; padding:8px 12px; border-radius:6px; text-decoration:none; letter-spacing:0.3px;">
🚀 Open Full Resource →
</a>
</div>
</div>"""

    # Strip all leading spaces per line to prevent markdown preformatted block parsing
    return "\n".join(line.strip() for line in raw_html.splitlines())

# ----------------------------------------------------
# 🎨 UI Configuration & Styling
# ----------------------------------------------------
st.set_page_config(
    page_title="Enterprise AI Discovery Hub",
    page_icon="🤖",
    layout="wide"
)

# Inject custom styling for card view & st.markdown(
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    /* Global styling overrides */
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Card Container style that adapts perfectly to both Light & Dark themes */
    .resource-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        transition: all 0.25s ease-in-out;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.03);
    }
    
    .resource-card:hover {
        transform: translateY(-2px);
        border-color: var(--primary-color);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    }
    
    /* Category Left Border Accents */
    .card-github { border-left: 5px solid #6e5494 !important; }
    .card-hf { border-left: 5px solid #ffca28 !important; }
    .card-arxiv { border-left: 5px solid #b31b1b !important; }
    .card-pypi { border-left: 5px solid #3775a9 !important; }
    .card-blog { border-left: 5px solid #10b981 !important; }
    .card-reddit { border-left: 5px solid #ff4500 !important; }
    .card-ph { border-left: 5px solid #da552f !important; }
    .card-course { border-left: 5px solid #f59e0b !important; }
    .card-yt { border-left: 5px solid #dc2626 !important; }

    /* High-contrast Title Link using the primary theme color */
    .resource-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: var(--primary-color) !important;
        text-decoration: none !important;
        margin-bottom: 8px;
        display: inline-block;
    }
    
    .resource-title:hover {
        text-decoration: underline !important;
        opacity: 0.85;
    }
    
    /* High contrast description that uses the current Streamlit theme's text color */
    .resource-desc {
        font-size: 0.95rem;
        color: var(--text-color);
        line-height: 1.6;
        margin: 0;
        font-weight: 400;
    }
    
    /* Custom High-Contrast Solid Badges */
    .resource-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 10px;
        letter-spacing: 0.5px;
    }
    
    .badge-github { background: #6e5494; color: #ffffff !important; }
    .badge-hf { background: #ffca28; color: #000000 !important; }
    .badge-arxiv { background: #b31b1b; color: #ffffff !important; }
    .badge-pypi { background: #3775a9; color: #ffffff !important; }
    .badge-blog { background: #10b981; color: #ffffff !important; }
    .badge-reddit { background: #ff4500; color: #ffffff !important; }
    .badge-ph { background: #da552f; color: #ffffff !important; }
    .badge-course { background: #f59e0b; color: #ffffff !important; }
    .badge-yt { background: #dc2626; color: #ffffff !important; }

    /* Theme-Adaptive Executive Metric Cards */
    [data-testid="stMetric"] {
        background: var(--secondary-background-color) !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        border-radius: 14px !important;
        padding: 16px 20px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03) !important;
        transition: all 0.2s ease-in-out !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px) !important;
        border-color: var(--primary-color) !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08) !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        color: var(--text-color) !important;
    }
    [data-testid="stMetricLabel"] p {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: var(--text-color) !important;
        opacity: 0.8;
    }

    /* Tab Custom Styling to Look Like Premium SaaS */
    div[data-baseweb="tab-list"] button {
        font-size: 1.02rem !important;
        font-weight: 600 !important;
        padding: 12px 18px !important;
        transition: all 0.2s ease-in-out !important;
    }

    /* Executive Domain Pill */
    .domain-pill {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--text-color);
        background: rgba(128, 128, 128, 0.15);
        padding: 4px 10px;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.25);
    }

    /* Executive Link Hover Preview Popover Styling */
    .link-wrapper {
        position: relative;
        display: inline-block;
    }

    .preview-popover {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        bottom: 100%; /* No gap so hovering over the popup stays within the container */
        left: 0;
        width: 440px;
        background: linear-gradient(145deg, #1a0533 0%, #0f1f4d 50%, #0a2040 100%);
        color: #F8FAFC;
        border: 2px solid;
        border-image: linear-gradient(135deg, #a855f7, #38BDF8, #34D399) 1;
        border-radius: 10px;
        padding: 14px;
        box-shadow: 0 12px 40px rgba(168, 85, 247, 0.3), 0 0 0 1px rgba(56, 189, 248, 0.15), inset 0 1px 0 rgba(255,255,255,0.05);
        z-index: 999;
        transition: opacity 0.15s ease-in-out, transform 0.15s ease-in-out, visibility 0.15s ease-in-out;
        transform: translateY(4px);
        pointer-events: auto; /* Enable mouse clicks inside the preview */
    }

    .preview-popover::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 20px;
        border-width: 6px;
        border-style: solid;
        border-color: #a855f7 transparent transparent transparent;
    }

    .link-wrapper:hover .preview-popover {
        visibility: visible;
        opacity: 1;
        transform: translateY(0);
    }

    .popover-btn {
        display: block;
        text-align: center;
        background: #252526;
        border: 1px solid #454545;
        color: #9CDCFE !important;
        font-size: 0.8rem;
        font-family: Consolas, monospace;
        font-weight: 600;
        padding: 8px 12px;
        border-radius: 4px;
        text-decoration: none !important;
        transition: all 0.2s ease;
    }

    .popover-btn:hover {
        background: #37373D;
        color: #4FC1FF !important;
        border-color: #007ACC;
        text-decoration: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ----------------------------------------------------
# 🔐 Executive Sidebar & Radar Controls
# ----------------------------------------------------
st.sidebar.markdown("## ⌘ Intelligence Core")

import os
# Auto-detect URI in background silently
mongo_uri = os.environ.get("mongo_uri")
if not mongo_uri:
    try:
        mongo_uri = st.secrets.get("mongo_uri")
    except Exception:
        mongo_uri = None

client = None
if mongo_uri and "YOUR_PASSWORD_HERE" not in mongo_uri:
    client = get_mongo_client(mongo_uri)

# Executive Stream Status Badge
if client:
    st.sidebar.success("🟢 Live Cloud Sync Active")
else:
    st.sidebar.info("🟠 Direct Stream Mode")

st.sidebar.markdown("---")

# Main Call-to-Action Button for Executives
fetch_btn = st.sidebar.button("⚡ Initiate Global Sweep", width="stretch", type="primary")

st.sidebar.markdown("---")

# Collapsed Developer / Database Management Console at the bottom
with st.sidebar.expander("⚙️ System Configuration", expanded=False):
    if client:
        stats = get_db_stats(client)
        total_records = sum(stats.values())
        st.markdown(f"**Cloud Status**: Connected (Atlas)")
        st.markdown(f"**Indexed Records**: `{total_records}` total")
        st.markdown("---")
        if st.button("🗑️ Clear Indexed History", width="stretch"):
            if clear_mongo_db(client):
                st.success("Database history cleared!")
                st.rerun()
    else:
        st.warning("Cloud Database Offline (Running in Live Scraper Mode)")
        st.info("Set `mongo_uri` in `.streamlit/secrets.toml` to persist history.")

# 🚀 Streamlit Main Dashboard UI

if not client and not fetch_btn and "live_updates" not in st.session_state:
    st.info("💡 MongoDB is disconnected or unreachable. Click **'Fetch Live AI Updates'** in the sidebar to scrape live updates directly, or enter valid MongoDB credentials to save & load history.")
else:
    # Action: Scrape & Save / Load
    if fetch_btn:
        with st.spinner("⚡ Scanning all 12 AI intelligence sources in parallel (GitHub · HF Models · HF Datasets · arXiv · PyPI · Blogs · Medium/Dev · Reddit · Product Hunt · Courses · YouTube · Prompts)..."):
            import concurrent.futures
            from scrapers import ALL_12_CATEGORIES
            scraper_tasks = {
                "github": get_github_ai_updates,
                "hf": get_huggingface_updates,
                "hf_ds": get_huggingface_dataset_updates,
                "arxiv": get_arxiv_updates,
                "pypi": get_pypi_updates,
                "blog": get_blog_updates,
                "medium": get_medium_dev_community_updates,
                "reddit": get_reddit_updates,
                "ph": get_producthunt_updates,
                "course": get_course_updates,
                "yt": get_youtube_updates,
                "prompt": get_prompt_template_updates,
            }
            results = {}
            # Run all 12 scrapers concurrently — total time ≈ slowest single scraper
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                future_map = {executor.submit(fn): name for name, fn in scraper_tasks.items()}
                for future in concurrent.futures.as_completed(future_map):
                    name = future_map[future]
                    try:
                        results[name] = future.result()
                    except Exception as e:
                        print(f"Scraper '{name}' failed: {e}")
                        results[name] = []

            all_updates = (
                results.get("github", []) + results.get("hf", []) + results.get("hf_ds", []) +
                results.get("arxiv", []) + results.get("pypi", []) + results.get("blog", []) +
                results.get("medium", []) + results.get("reddit", []) + results.get("ph", []) +
                results.get("course", []) + results.get("yt", []) + results.get("prompt", [])
            )
            
            # Enrich all updates in parallel to get live PageTitle and PageDescription
            from scrapers import enrich_updates_in_parallel
            all_updates = enrich_updates_in_parallel(all_updates)
            
            if all_updates:
                if client:
                    new_saved = save_updates_to_mongo(client, all_updates)
                    st.success(f"✅ Scan complete! Found {len(all_updates)} total resources, inserted {new_saved} new entries into MongoDB Atlas.")
                    st.rerun()
                else:
                    st.session_state["live_updates"] = {cat: [x for x in all_updates if x["Type"] == cat] for cat in ALL_12_CATEGORIES}
                    st.success(f"✅ Live fetch complete! Loaded {len(all_updates)} resources across all categories.")
            else:
                st.error("No updates found. Please check internet connection and try again.")


    # Read Persisted Data from MongoDB or Session State
    if client:
        raw_categories_data = fetch_all_updates_dict(client)
    elif "live_updates" in st.session_state:
        lu = st.session_state["live_updates"]
        from scrapers import ALL_12_CATEGORIES
        raw_categories_data = {cat: lu.get(cat, []) for cat in ALL_12_CATEGORIES}
    else:
        from scrapers import ALL_12_CATEGORIES
        raw_categories_data = {cat: [] for cat in ALL_12_CATEGORIES}
    
    total_raw_count = sum(len(lst) for lst in raw_categories_data.values())

    if total_raw_count > 0:
        import re

        def matches_search(item, query):
            if not query:
                return True
            q = query.strip()
            pattern = r'\b' + re.escape(q) + r'\b'
            title = item.get('Title', '')
            desc = item.get('Description', '')
            if re.search(pattern, title, re.IGNORECASE) or re.search(pattern, desc, re.IGNORECASE):
                return True
            if len(q) > 4 and (q.lower() in title.lower() or q.lower() in desc.lower()):
                return True
            return False

        # Constant items per page (dropdown removed)
        items_per_page = 10

        # ----------------------------------------------------
        # 1️⃣ Centered Executive Hero Header Banner (Creative & Attractive)
        # ----------------------------------------------------
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #7f1d1d 0%, #831843 30%, #4c1d95 70%, #1e3a5f 100%);
                border-radius: 20px;
                padding: 38px 32px;
                text-align: center;
                margin-bottom: 28px;
                box-shadow: 0 20px 60px rgba(131, 24, 67, 0.4), 0 0 80px rgba(249, 115, 22, 0.1), inset 0 1px 0 rgba(255,255,255,0.1);
                position: relative;
                overflow: hidden;
            ">
                <!-- Warm glow orbs -->
                <div style="
                    position: absolute;
                    top: -40%; left: -20%; width: 60%; height: 180%;
                    background: radial-gradient(ellipse, rgba(251, 113, 133, 0.18) 0%, transparent 65%);
                    pointer-events: none;
                "></div>
                <div style="
                    position: absolute;
                    top: -20%; right: -10%; width: 50%; height: 140%;
                    background: radial-gradient(ellipse, rgba(168, 85, 247, 0.15) 0%, transparent 60%);
                    pointer-events: none;
                "></div>
                <!-- Subtle dot grid -->
                <div style="
                    position: absolute;
                    top: 0; left: 0; right: 0; bottom: 0;
                    background-image: radial-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px);
                    background-size: 22px 22px;
                    pointer-events: none;
                "></div>
                <div style="position: relative; z-index: 1;">
                    <div style="display: inline-block; padding: 5px 18px; background: linear-gradient(90deg, rgba(251,113,133,0.3), rgba(251,191,36,0.25)); border: 1px solid rgba(251, 191, 36, 0.5); border-radius: 20px; font-size: 0.75rem; font-weight: 700; color: #fcd34d; letter-spacing: 1.5px; margin-bottom: 14px; text-transform: uppercase;">
                        ⚡ Autonomous AI Tracking
                    </div>
                    <h1 style="font-size: 2.8rem; font-weight: 800; background: linear-gradient(90deg, #ffffff, #e2e8f0); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0 0 12px 0; letter-spacing: -0.5px; filter: drop-shadow(0 0 25px rgba(255, 255, 255, 0.2));">
                        Intelligence Matrix
                    </h1>
                    <p style="font-size: 1.1rem; color: #cbd5e1; margin: 0; font-weight: 400; max-width: 600px; margin: 0 auto; line-height: 1.6; opacity: 0.9;">
                        Monitoring the bleeding edge of global AI development.
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Mode Selection
        view_mode = st.radio(
            "Select View Mode:",
            ["🎯 360° Use-Case AI Advisor", "📡 All Scanned Intelligence Feeds"],
            horizontal=True,
            key="platform_view_mode"
        )
        
        if view_mode == "🎯 360° Use-Case AI Advisor":
            st.markdown("### 💡 Universal 360° AI Developer Advisor")
            st.markdown("Describe ANY project scenario or engineering requirement below. Our engine automatically matches and suggests actionable tools across all 12 categories.")
            
            # Scenario Input
            scenario_text = st.text_area(
                "Project Scenario / Use Case Description",
                value=st.session_state.get("active_scenario", ""),
                placeholder="Describe your project requirement, tech stack, or engineering scenario...",
                height=100,
                key="scenario_text_input"
            )
            
            active_prompt = scenario_text.strip()
            if active_prompt:
                st.markdown(f"#### 🎯 Recommended AI Stack for: *\"{active_prompt}\"*")
                with st.spinner("Analyzing scenario & querying all 12 categories..."):
                    from usecase_matcher import scenario_matcher
                    from scrapers import fetch_live_category_fallback
                    
                    rec_result = scenario_matcher.match_scenario(active_prompt, raw_categories_data, top_k=5)
                    
                    # Handle low-confidence category fallbacks
                    for low_cat in rec_result.get("low_confidence_categories", []):
                        live_items = fetch_live_category_fallback(low_cat, active_prompt)
                        if live_items:
                            scored = []
                            for it in live_items:
                                sc, kw, tip = scenario_matcher.score_item(it, rec_result["keywords"])
                                it_copy = dict(it)
                                it_copy["MatchScore"] = sc
                                it_copy["MatchedKeywords"] = kw or rec_result["keywords"][:2]
                                it_copy["IntegrationTip"] = tip
                                scored.append(it_copy)
                            rec_result["recommendations"][low_cat] = scored[:5]

                    # Render 12 category accordions
                    recs = rec_result.get("recommendations", {})
                    for cat_name, items in recs.items():
                        match_count = len(items)
                        with st.expander(f"📦 {cat_name} ({match_count} Top Recommendations)", expanded=(match_count > 0)):
                            if not items:
                                st.info(f"No specific matches found for {cat_name}.")
                            for item in items:
                                score = item.get("MatchScore", 0.0)
                                tip = item.get("IntegrationTip", "")
                                link = item.get("Link", "#")
                                title = item.get("Title", "Untitled")
                                desc = item.get("Description", "")
                                
                                st.markdown(f"""
                                <div style="background: #1e293b; border: 1px solid #334155; border-left: 5px solid #0284c7; border-radius: 12px; padding: 18px 22px; margin-bottom: 16px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;">
                                        <a href="{link}" target="_blank" style="color: #38bdf8; font-size: 1.15rem; font-weight: 700; text-decoration: none; display: flex; align-items: center; gap: 6px;">
                                            🔗 {title}
                                        </a>
                                        <span style="background: #0284c7; color: #ffffff; padding: 4px 14px; border-radius: 20px; font-weight: 800; font-size: 0.85rem; letter-spacing: 0.5px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                                            🎯 {score}% Match
                                        </span>
                                    </div>
                                    <p style="color: #f1f5f9; font-size: 0.95rem; line-height: 1.6; margin-bottom: 12px; font-weight: 400;">
                                        {desc}
                                    </p>
                                    <div style="background: #0f172a; border-left: 4px solid #f59e0b; padding: 10px 14px; border-radius: 6px; margin-top: 8px;">
                                        <span style="color: #fbbf24; font-weight: 700; font-size: 0.88rem; display: block; margin-bottom: 2px;">
                                            💡 Solution Architect Tip & Integration Guide:
                                        </span>
                                        <span style="color: #f8fafc; font-size: 0.88rem; line-height: 1.5; font-weight: 500;">
                                            {tip}
                                        </span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
            else:
                st.info("💡 Type any project description above to generate a tailored 12-category developer recommendation!")

        else:
            # Full raw feed viewer mode
            # Retrieve active search query from session state
            search_query = st.session_state.get("exec_search_input", "")

            # Dynamically filter dataset based on active search query
            all_categories_data = {}
            for cat, items in raw_categories_data.items():
                all_categories_data[cat] = [it for it in items if matches_search(it, search_query)]

            filtered_total_count = sum(len(lst) for lst in all_categories_data.values())

            # ----------------------------------------------------
            # 2️⃣ Hero Executive Stats Banner (Placed Exactly after Heading at Top)
            # ----------------------------------------------------
            active_cats_with_items = [(cat, items) for cat, items in all_categories_data.items() if len(items) > 0]
            if active_cats_with_items:
                top_cat_name, top_cat_items = max(active_cats_with_items, key=lambda x: len(x[1]))
                top_cat_count = len(top_cat_items)
            else:
                top_cat_name, top_cat_count = "None", 0

            friendly_kpi_names = {
                "GitHub Repo": "GitHub Repos",
                "Hugging Face Model": "Hugging Face",
                "Hugging Face Dataset": "HF Datasets",
                "arXiv Research Paper": "arXiv Papers",
                "PyPI Release": "PyPI Packages",
                "Corporate Blog": "Tech Blogs",
                "Medium & Dev Community": "Medium Articles",
                "Reddit Discussion": "Reddit Topics",
                "Product Hunt Launch": "Product Hunt",
                "AI Course": "AI Courses",
                "YouTube Video": "YouTube Videos",
                "Prompt & Guardrail Templates": "Prompt Templates",
                "None": "N/A"
            }
            top_display_name = friendly_kpi_names.get(top_cat_name, top_cat_name)

            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("📊 All Intelligence Records", f"{filtered_total_count} Items", delta=f"Filtered from {total_raw_count}" if search_query else f"{total_raw_count} total across all scans")
            kpi2.metric("📡 Active Scanned Sources", f"{len(active_cats_with_items)} Channels")
            kpi3.metric("🔥 Top Trending Sector", top_display_name, f"{top_cat_count} Items" if top_cat_count > 0 else None)

            st.markdown("---")

            # ----------------------------------------------------
            # 3️⃣ Executive Visual Analytics (Category Breakdown)
            # ----------------------------------------------------
            with st.expander("📊 Executive Visual Analytics (Category Distribution)", expanded=True):
                import altair as alt
                chart_data = pd.DataFrame({
                    "Category": list(all_categories_data.keys()),
                    "Resources": [len(lst) for lst in all_categories_data.values()]
                })
                
                # Create a vibrant, premium bar chart using Altair
                chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                    x=alt.X('Category:N', sort='-y', axis=alt.Axis(labelAngle=-45, title=None, labelFontSize=12)),
                    y=alt.Y('Resources:Q', title="Total Items", axis=alt.Axis(grid=True, gridOpacity=0.1, labelFontSize=12)),
                    color=alt.Color('Category:N', legend=None, scale=alt.Scale(scheme='category10')),
                    tooltip=['Category', 'Resources']
                ).properties(height=380)
                
                st.altair_chart(chart, width="stretch")

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # ----------------------------------------------------
            # 4️⃣ Compact Search Filter Toolbar (Placed AFTER Visualization)
            # ----------------------------------------------------
            filter_col1, filter_col2, filter_col3 = st.columns([2.2, 1.3, 0.5])
            with filter_col1:
                def on_search_change():
                    st.session_state["exec_search_input"] = st.session_state["exec_search_widget"]

                st.text_input(
                    "🔍 Executive Keyword Filter",
                    value=search_query,
                    placeholder="Search LLM, Agent, DeepSeek, Vision, RAG, Llama...",
                    key="exec_search_widget",
                    on_change=on_search_change
                )
            
            with filter_col2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                export_rows = []
                for cat, items in all_categories_data.items():
                    for item in items:
                        export_rows.append({
                            "Category": cat,
                            "Title": item.get("Title", ""),
                            "Description": item.get("Description", ""),
                            "Link": item.get("Link", "")
                        })
                if export_rows:
                    df_export = pd.DataFrame(export_rows)
                    csv_data = df_export.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Briefing (CSV)",
                        data=csv_data,
                        file_name="executive_ai_intelligence_report.csv",
                        mime="text/csv",
                        width="stretch"
                    )

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

            # ----------------------------------------------------
            # 5️⃣ Smart Paginated Rendering Helper (Pagination AT BOTTOM)
            # ----------------------------------------------------
            def render_paginated_category(category_name, items, badge_class, badge_label, tab_id):
                if not items:
                    if search_query:
                        st.info(f"No {category_name} items match search query '{search_query}'.")
                    else:
                        st.info(f"No {category_name} updates available.")
                    return

                total_filtered = len(items)
                total_pages = max(1, (total_filtered + items_per_page - 1) // items_per_page)
                
                page_key = f"page_idx_{tab_id}"
                if page_key not in st.session_state:
                    st.session_state[page_key] = 1
                    
                if st.session_state[page_key] > total_pages:
                    st.session_state[page_key] = 1
                    
                current_page = st.session_state[page_key]

                # Slice current page items
                start_idx = (current_page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                page_items = items[start_idx:end_idx]

                from urllib.parse import urlparse

                def get_domain(url):
                    try:
                        netloc = urlparse(url).netloc
                        return netloc.replace("www.", "") if netloc else "external"
                    except Exception:
                        return "source link"

                # Render resource cards list
                card_class = badge_class.replace("badge-", "card-")
                for item in page_items:
                    link_url = item.get('Link', '#')
                    title_text = item.get('Title', 'Untitled Intelligence')
                    desc_text = item.get('Description', 'No summary provided.')
                    domain_host = get_domain(link_url)
                    timestamp = item.get('Timestamp', '')
                    
                    timestamp_html = f'<span style="color: #10b981; font-size: 0.75rem; font-weight: 600; background: rgba(16,185,129,0.1); padding: 4px 10px; border-radius: 12px; border: 1px solid rgba(16,185,129,0.2);">🕒 {timestamp}</span>' if timestamp else ''
                    
                    # Safe HTML escaping to prevent string breaks
                    safe_title = title_text.replace('"', '&quot;').replace("'", "&#39;")
                    safe_desc = desc_text.replace('"', '&quot;').replace("'", "&#39;")

                    st.markdown(
                        f"""
<div class="resource-card {card_class}">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
<span class="resource-badge {badge_class}">{badge_label}</span>
<div style="display: flex; align-items: center; gap: 8px;">
{timestamp_html}
<span class="domain-pill">🌐 {domain_host}</span>
</div>
</div>
<div class="link-wrapper">
<a class="resource-title" href="{link_url}" target="_blank">{title_text}</a>
{generate_pylance_preview(item, category_name, domain_host)}
</div>
<p class="resource-desc">{desc_text}</p>
</div>
                        """,
                        unsafe_allow_html=True
                    )

                # Render Bottom Pagination Bar (Standard Web Application UX)
                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                p_col1, p_col2, p_col3 = st.columns([1.5, 3, 1.5])
                with p_col1:
                    if st.button("⬅️ Previous", key=f"prev_{tab_id}", disabled=(current_page == 1)):
                        st.session_state[page_key] = max(1, current_page - 1)
                        st.rerun()
                with p_col2:
                    st.markdown(
                        f"<div style='text-align: center; padding-top: 6px; font-weight: 600; color: var(--text-color);'>"
                        f"Page {current_page} of {total_pages} &nbsp;•&nbsp; ({total_filtered} items)"
                        f"</div>", 
                        unsafe_allow_html=True
                    )
                with p_col3:
                    if st.button("Next ➡️", key=f"next_{tab_id}", disabled=(current_page >= total_pages)):
                        st.session_state[page_key] = min(total_pages, current_page + 1)
                        st.rerun()

            # ----------------------------------------------------
            # 6️⃣ Executive Content Tabs (Dynamic Header Counts)
            # ----------------------------------------------------
            f_github = all_categories_data.get("GitHub Repo", [])
            f_hf = all_categories_data.get("Hugging Face Model", [])
            f_hf_ds = all_categories_data.get("Hugging Face Dataset", [])
            f_arxiv = all_categories_data.get("arXiv Research Paper", [])
            f_pypi = all_categories_data.get("PyPI Release", [])
            f_blog = all_categories_data.get("Corporate Blog", [])
            f_medium = all_categories_data.get("Medium & Dev Community", [])
            f_reddit = all_categories_data.get("Reddit Discussion", [])
            f_ph = all_categories_data.get("Product Hunt Launch", [])
            f_course = all_categories_data.get("AI Course", [])
            f_yt = all_categories_data.get("YouTube Video", [])
            f_prompt = all_categories_data.get("Prompt & Guardrail Templates", [])

            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
                f"💻 GitHub ({len(f_github)})", 
                f"🤗 HF Models ({len(f_hf)})", 
                f"📊 HF Datasets ({len(f_hf_ds)})", 
                f"🔬 arXiv ({len(f_arxiv)})",
                f"📦 PyPI ({len(f_pypi)})",
                f"📰 Blogs ({len(f_blog)})",
                f"✍️ Medium/Dev ({len(f_medium)})",
                f"💬 Reddit ({len(f_reddit)})",
                f"🚀 ProdHunt ({len(f_ph)})",
                f"🎓 Courses ({len(f_course)})",
                f"📺 Videos ({len(f_yt)})",
                f"🛡️ Prompts ({len(f_prompt)})"
            ])

            with tab1:
                render_paginated_category("GitHub Repo", f_github, "badge-github", "GitHub Repo", "tab_gh")
            with tab2:
                render_paginated_category("Hugging Face Model", f_hf, "badge-hf", "Hugging Face Model", "tab_hf")
            with tab3:
                render_paginated_category("Hugging Face Dataset", f_hf_ds, "badge-hf", "Hugging Face Dataset", "tab_hf_ds")
            with tab4:
                render_paginated_category("arXiv Research Paper", f_arxiv, "badge-arxiv", "arXiv Research Paper", "tab_arxiv")
            with tab5:
                render_paginated_category("PyPI Release", f_pypi, "badge-pypi", "PyPI Release", "tab_pypi")
            with tab6:
                render_paginated_category("Corporate Blog", f_blog, "badge-blog", "AI Blog", "tab_blog")
            with tab7:
                render_paginated_category("Medium & Dev Community", f_medium, "badge-blog", "Medium / Dev", "tab_medium")
            with tab8:
                render_paginated_category("Reddit Discussion", f_reddit, "badge-reddit", "Reddit Discussion", "tab_reddit")
            with tab9:
                render_paginated_category("Product Hunt Launch", f_ph, "badge-ph", "Product Hunt Launch", "tab_ph")
            with tab10:
                render_paginated_category("AI Course", f_course, "badge-course", "AI Course", "tab_course")
            with tab11:
                render_paginated_category("YouTube Video", f_yt, "badge-yt", "YouTube Video", "tab_yt")
            with tab12:
                render_paginated_category("Prompt & Guardrail Templates", f_prompt, "badge-course", "Prompt Template", "tab_prompt")
    else:
        st.info("💡 The cloud database is currently empty. Click **Fetch New AI Updates** in the sidebar to perform your first sync!")

