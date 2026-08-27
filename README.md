# 🌌 AI Intelligence Matrix

![AI Intelligence Matrix](https://img.shields.io/badge/Status-Active-success.svg) 
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg) 
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg) 
![MongoDB](https://img.shields.io/badge/Database-MongoDB-47A248.svg)

**AI Intelligence Matrix** is a powerful, autonomous reconnaissance engine designed to aggregate, enrich, and unify real-time AI developments across the global web. 

Instead of manually checking dozens of platforms, this matrix engine actively hunts for cutting-edge AI breakthroughs, open-source repositories, research papers, and discussions, consolidating them into a single, high-performance executive dashboard.

---

## 🚀 Enterprise-Grade Features

*   **Omni-Channel Intelligence Gathering:** Continuously scrapes and parses data from the industry's most critical sources:
    *   **GitHub** (Trending AI Repositories)
    *   **arXiv** (Latest Machine Learning Research)
    *   **PyPI** (New Python AI/ML Packages)
    *   **Hugging Face** (Trending Models & Datasets)
    *   **Product Hunt** (New AI Startup Launches)
    *   **Reddit** (Discussions from r/MachineLearning, r/LocalLLaMA, etc.)
    *   **Corporate Blogs** (OpenAI, Google DeepMind, Anthropic, etc.)
    *   **YouTube & Courses** (Latest educational content)
*   **Deep Metadata Enrichment:** Automatically resolves OpenGraph images, extracts page outlines, and generates pure-CSS branded fallbacks for platforms that block standard scrapers.
*   **Executive Dashboard:** A stunning, real-time Streamlit UI featuring vibrant visual analytics, paginated data rendering, and advanced keyword filtering.
*   **Browser Integration:** Includes a custom Chrome Extension that allows you to trigger on-demand scraping and view intelligence updates directly from your browser toolbar.
*   **Persistent Storage:** Backed by MongoDB for robust, scalable data persistence.

## 🛠️ Technology Stack

*   **Core Engine:** Python 3.10+
*   **Frontend UI:** Streamlit (with Altair for visual analytics)
*   **Database:** MongoDB Atlas
*   **Web Scraping:** Requests, BeautifulSoup4, Regex (Configured with advanced DOM parsing and deep `<head>` extraction).
*   **Extension:** Vanilla JavaScript, HTML5, CSS3

## ⚡ Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/pavanghanta2328/ai-intelligence-matrix.git
cd ai-intelligence-matrix
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Set up your MongoDB connection string inside `.streamlit/secrets.toml`:
```toml
MONGO_URI = "mongodb+srv://<username>:<password>@cluster..."
```

### 4. Launch the Engine
Start the FastAPI backend and the Streamlit dashboard:
```bash
# Terminal 1: Run the API
python -m uvicorn api:app --reload

# Terminal 2: Run the Dashboard
streamlit run Gather_updates.py
```

## 🌐 Deployment
This architecture is completely cloud-native and designed to be deployed seamlessly on **Streamlit Community Cloud**, Render, or AWS. The backend API can be hosted on Heroku or Railway, providing real-time data flow to the dashboard.

---
*Built to capture the pulse of the AI revolution.*
