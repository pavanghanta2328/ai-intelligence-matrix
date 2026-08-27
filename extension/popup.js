const API_BASES = ["http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:8080", "http://localhost:8080"];
let activeBase = "http://127.0.0.1:8000";
let cachedData = null;
let currentCategory = "GitHub Repo";
let searchQuery = "";
let categoryPages = {}; // Store current page per category
const ITEMS_PER_PAGE = 5;

// DOM Elements
let loadingEl, errorEl, noDataEl, listEl, countEl, tabButtons, syncBtn;
let searchInputEl, paginationBarEl, prevPageBtn, nextPageBtn, pageIndicatorEl;

// Init
document.addEventListener("DOMContentLoaded", () => {
  loadingEl = document.getElementById("loading");
  errorEl = document.getElementById("error");
  noDataEl = document.getElementById("no-data");
  listEl = document.getElementById("updates-list");
  countEl = document.getElementById("record-count");
  tabButtons = document.querySelectorAll(".tab-btn");
  syncBtn = document.getElementById("sync-btn");
  
  searchInputEl = document.getElementById("search-input");
  paginationBarEl = document.getElementById("pagination-bar");
  prevPageBtn = document.getElementById("prev-page-btn");
  nextPageBtn = document.getElementById("next-page-btn");
  pageIndicatorEl = document.getElementById("page-indicator");

  initPreviewOverlay();  // Create shared overlay panel once
  setupTabListeners();
  setupSyncListener();
  setupSearchListener();
  setupPaginationListeners();
  fetchUpdates();
});


// Setup search listener
function setupSearchListener() {
  if (!searchInputEl) return;
  searchInputEl.addEventListener("input", (e) => {
    searchQuery = e.target.value.toLowerCase().trim();
    // Reset page to 1 on search change for all categories
    categoryPages = {};
    updateTabHeaderCounts();
    renderCurrentCategory();
  });
}

// Word boundary regex matching (matches Python backend logic)
function matchesSearch(item, query) {
  if (!query) return true;
  const q = query.trim();
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`\\b${escaped}\\b`, 'i');
  const title = item.Title || item.title || "";
  const desc = item.Description || item.description || "";
  
  if (regex.test(title) || regex.test(desc)) return true;
  if (q.length > 4 && (title.toLowerCase().includes(q.toLowerCase()) || desc.toLowerCase().includes(q.toLowerCase()))) return true;
  return false;
}

// Setup pagination listeners
function setupPaginationListeners() {
  if (prevPageBtn) {
    prevPageBtn.addEventListener("click", () => {
      let currentPage = categoryPages[currentCategory] || 1;
      if (currentPage > 1) {
        categoryPages[currentCategory] = currentPage - 1;
        renderCurrentCategory();
      }
    });
  }

  if (nextPageBtn) {
    nextPageBtn.addEventListener("click", () => {
      let currentPage = categoryPages[currentCategory] || 1;
      categoryPages[currentCategory] = currentPage + 1;
      renderCurrentCategory();
    });
  }
}

// Setup tab navigation click listeners
function setupTabListeners() {
  if (!tabButtons) return;
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      tabButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentCategory = btn.getAttribute("data-category");
      renderCurrentCategory();
    });
  });
}

// Dynamically update tab headers with filtered item counts
function updateTabHeaderCounts() {
  if (!tabButtons || !cachedData) return;
  
  let totalFilteredAll = 0;
  let totalRawAll = 0;

  tabButtons.forEach(btn => {
    const cat = btn.getAttribute("data-category");
    const rawList = cachedData[cat] || [];
    totalRawAll += rawList.length;

    const filteredList = rawList.filter(item => matchesSearch(item, searchQuery));
    totalFilteredAll += filteredList.length;

    const friendlyLabel = getShortCategoryIconLabel(cat, filteredList.length);
    btn.textContent = friendlyLabel;
  });

  if (countEl) {
    if (searchQuery) {
      countEl.textContent = `${totalFilteredAll} items found (filtered from ${totalRawAll})`;
    } else {
      countEl.textContent = `${totalRawAll} resources synced`;
    }
  }
}

function getShortCategoryIconLabel(cat, count) {
  if (cat === "GitHub Repo") return `💻 GitHub (${count})`;
  if (cat === "Hugging Face Model") return `🤗 HF Models (${count})`;
  if (cat === "arXiv Research Paper") return `🔬 arXiv (${count})`;
  if (cat === "PyPI Release") return `📦 PyPI (${count})`;
  if (cat === "Corporate Blog") return `📰 Blogs (${count})`;
  if (cat === "Reddit Discussion") return `💬 Reddit (${count})`;
  if (cat === "Product Hunt Launch") return `🚀 ProdHunt (${count})`;
  if (cat === "AI Course") return `🎓 Courses (${count})`;
  if (cat === "YouTube Video") return `📺 Videos (${count})`;
  return `${cat} (${count})`;
}

// Find working backend API URL
async function getWorkingApiUrl(endpoint) {
  for (const base of API_BASES) {
    try {
      const res = await fetch(`${base}/`, { method: "GET", cache: "no-store" });
      if (res.ok) {
        activeBase = base;
        return `${base}${endpoint}`;
      }
    } catch (e) {
      // Ignore connection error and try next candidate
    }
  }
  return `${activeBase}${endpoint}`;
}

// Fetch updates from FastAPI
async function fetchUpdates() {
  showLoading(true);
  showError(null);

  try {
    const url = await getWorkingApiUrl("/api/updates");
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    cachedData = await response.json();
    showLoading(false);

    updateTabHeaderCounts();
    renderCurrentCategory();
  } catch (err) {
    showLoading(false);
    showError("Could not connect to the API. Make sure your FastAPI server is running (`python -m uvicorn api:app --reload`).");
    console.error(err);
  }
}

// Render items for selected category with pagination & search
function renderCurrentCategory() {
  if (!listEl || !noDataEl) return;
  listEl.innerHTML = "";
  noDataEl.style.display = "none";
  if (paginationBarEl) paginationBarEl.style.display = "none";

  if (!cachedData || !cachedData[currentCategory]) {
    noDataEl.style.display = "block";
    return;
  }

  let items = cachedData[currentCategory];
  if (!Array.isArray(items) || items.length === 0) {
    noDataEl.style.display = "block";
    return;
  }

  // Filter items using word boundary matching
  if (searchQuery) {
    items = items.filter(item => matchesSearch(item, searchQuery));
  }

  if (items.length === 0) {
    noDataEl.textContent = searchQuery ? `No items found matching "${searchQuery}"` : "No updates found.";
    noDataEl.style.display = "block";
    return;
  }

  // Pagination calculation
  const totalCount = items.length;
  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE);
  let currentPage = categoryPages[currentCategory] || 1;

  if (currentPage > totalPages) currentPage = totalPages;
  if (currentPage < 1) currentPage = 1;
  categoryPages[currentCategory] = currentPage;

  // Show pagination bar if multiple pages exist
  if (paginationBarEl && totalPages > 1) {
    paginationBarEl.style.display = "flex";
    if (pageIndicatorEl) pageIndicatorEl.textContent = `Page ${currentPage} of ${totalPages} (${totalCount} items)`;
    if (prevPageBtn) prevPageBtn.disabled = (currentPage <= 1);
    if (nextPageBtn) nextPageBtn.disabled = (currentPage >= totalPages);
  }

  // Slice page items
  const startIdx = (currentPage - 1) * ITEMS_PER_PAGE;
  const pageItems = items.slice(startIdx, startIdx + ITEMS_PER_PAGE);

  // Define badges CSS mapping
  const badgeMap = {
    "GitHub Repo": "badge-github",
    "Hugging Face Model": "badge-hf",
    "arXiv Research Paper": "badge-arxiv",
    "PyPI Release": "badge-pypi",
    "Corporate Blog": "badge-blog",
    "Reddit Discussion": "badge-reddit",
    "Product Hunt Launch": "badge-ph",
    "AI Course": "badge-course",
    "YouTube Video": "badge-yt"
  };

  const badgeClass = badgeMap[currentCategory] || "badge-blog";
  const badgeText = getFriendlyBadgeText(currentCategory);

  pageItems.forEach(item => {
    const card = document.createElement("div");
    card.className = "card";

    const link = item.Link || item.link || "#";
    const title = item.Title || item.title || "No Title";
    const description = item.Description || item.description || "No description provided.";
    
    let domainHost = "source";
    try {
      const u = new URL(link);
      domainHost = u.hostname.replace("www.", "");
    } catch (e) {
      domainHost = "link";
    }

    card.innerHTML = `
      <div style="margin-bottom: 6px;">
        <span class="card-badge ${badgeClass}">${badgeText}</span>
        <span class="domain-pill">🌐 ${escapeHtml(domainHost)}</span>
      </div>
      <div class="link-wrapper">
        <a class="card-title" href="${escapeHtml(link)}" target="_blank">${escapeHtml(title)}</a>
      </div>
      <p class="card-desc">${escapeHtml(description)}</p>
    `;

    // Attach JS hover events to show shared overlay (avoids CSS overflow clipping)
    const titleLink = card.querySelector(".card-title");
    if (titleLink) {
      titleLink.addEventListener("mouseenter", () => {
        showPreviewOverlay(item, currentCategory, domainHost);
      });
      titleLink.addEventListener("mouseleave", (e) => {
        // Keep open if moving into the overlay itself
        const overlay = document.getElementById("preview-overlay");
        if (overlay && !overlay.contains(e.relatedTarget)) {
          hidePreviewOverlay();
        }
      });
    }

    listEl.appendChild(card);
  });
}

function getFriendlyBadgeText(cat) {
  if (cat === "GitHub Repo") return "GitHub";
  if (cat === "Hugging Face Model") return "Hugging Face";
  if (cat === "arXiv Research Paper") return "arXiv Paper";
  if (cat === "PyPI Release") return "PyPI Package";
  if (cat === "Corporate Blog") return "Blog";
  if (cat === "Reddit Discussion") return "Reddit";
  if (cat === "Product Hunt Launch") return "Product Hunt";
  if (cat === "AI Course") return "Course";
  if (cat === "YouTube Video") return "Video";
  return "AI Release";
}

// Helper to escape HTML and prevent injection issues
function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showLoading(show) {
  if (loadingEl) loadingEl.style.display = show ? "block" : "none";
}

function showError(msg) {
  if (!errorEl || !listEl) return;
  if (msg) {
    errorEl.textContent = msg;
    errorEl.style.display = "block";
    listEl.innerHTML = "";
  } else {
    errorEl.style.display = "none";
  }
}

// Setup sync listener
function setupSyncListener() {
  if (syncBtn) {
    syncBtn.addEventListener("click", () => {
      syncUpdates();
    });
  }
}

// Sync latest updates from scrapers via FastAPI
async function syncUpdates() {
  if (!syncBtn) return;

  syncBtn.disabled = true;
  syncBtn.classList.add("spinning");

  if (loadingEl) loadingEl.textContent = "Syncing latest updates from web sources... This may take a moment.";
  showLoading(true);
  showError(null);

  try {
    const url = await getWorkingApiUrl("/api/sync");
    const response = await fetch(url, {
      method: "POST",
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    if (data.status === "success" && data.updates) {
      cachedData = data.updates;
      updateTabHeaderCounts();
      renderCurrentCategory();
    } else {
      throw new Error("Invalid sync response structure");
    }
  } catch (err) {
    console.error(err);
    showError("Could not sync updates. Make sure your local API server is running.");
  } finally {
    showLoading(false);
    if (loadingEl) loadingEl.textContent = "Loading updates from cloud...";
    syncBtn.disabled = false;
    syncBtn.classList.remove("spinning");
  }
}

function generatePylancePreview(item, category, domainHost) {
  const title = item.Title || item.title || "Untitled";
  const desc = item.Description || item.description || "No description provided.";
  const link = item.Link || item.link || "#";

  const pageTitle = item.PageTitle || item.page_title || title;
  const pageDescription = item.PageDescription || item.page_description || desc;
  const pageImage = item.PageImage || item.page_image || "";
  const pageOutline = item.PageOutline || item.page_outline || [];

  // Image block — full-width banner, hidden if broken via onerror
  let imgBlock = "";
  if (pageImage) {
    imgBlock = `<img src="${escapeHtml(pageImage)}"
      onerror="this.style.display='none'; var hdr=this.nextElementSibling; hdr.style.borderTopLeftRadius='8px'; hdr.style.borderTopRightRadius='8px';"
      style="width:calc(100% + 24px); margin:-10px -12px 0 -12px; height:150px; object-fit:cover; border-top-left-radius:8px; border-top-right-radius:8px; display:block;" />`;
  }

  // Header bar border radius — rounded on top only when no image
  const headerRadius = pageImage ? "" : "border-top-left-radius:8px; border-top-right-radius:8px;";

  // Colorful chip tags for topics
  const chipColors = ["#f97316","#a855f7","#38BDF8","#34D399","#fb7185","#facc15","#60a5fa"];
  let chipsHtml = "";
  if (pageOutline && pageOutline.length > 0) {
    let chips = "";
    pageOutline.slice(0, 6).forEach((heading, i) => {
      const color = chipColors[i % chipColors.length];
      chips += `<span style="display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.7rem; font-weight:600; color:${color}; border:1px solid ${color}; margin:2px 3px 2px 0; max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(heading)}</span>`;
    });
    chipsHtml = `<div style="margin-bottom:10px; line-height:2.1;">${chips}</div>`;
  }

  const descMargin = chipsHtml ? "10px" : "0";
  const truncDesc = pageDescription.length > 200 ? pageDescription.slice(0, 200) + "…" : pageDescription;
  const truncTitle = pageTitle.length > 100 ? pageTitle.slice(0, 100) : pageTitle;

  return `
    <div class="preview-popover">
      ${imgBlock}
      <div style="background: linear-gradient(90deg, #7c2d12 0%, #581c87 60%, #1e1b4b 100%); padding: 8px 12px; margin: 0 -12px 12px -12px; ${headerRadius} font-family: Consolas, monospace; font-size: 0.8rem; display: flex; justify-content: space-between; align-items: center; gap: 6px;">
        <div style="overflow:hidden; flex:1; min-width:0;">
          <span style="color:#fbbf24; font-weight:700; font-size:0.68rem; letter-spacing:1px; text-transform:uppercase;">${escapeHtml(category)}</span>
          <span style="color:#e2e8f0; font-weight:600; margin-left:5px; font-size:0.78rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:inline-block; max-width:160px; vertical-align:middle;">→ ${escapeHtml(title.slice(0, 35))}</span>
        </div>
        <span style="background:rgba(251,191,36,0.15); color:#fbbf24; border:1px solid rgba(251,191,36,0.4); padding:2px 7px; border-radius:12px; font-size:0.63rem; font-weight:600; flex-shrink:0;">${escapeHtml(domainHost)}</span>
      </div>

      <div style="padding: 2px 0 8px 0;">
        <div style="font-size:0.95rem; font-weight:700; color:#f1f5f9; line-height:1.35; margin-bottom:6px;">${escapeHtml(truncTitle)}</div>
        <div style="font-size:0.8rem; color:#cbd5e1; line-height:1.5; margin-bottom:${descMargin};">${escapeHtml(truncDesc)}</div>
        ${chipsHtml}
      </div>

      <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 8px; margin-top: 4px;">
        <a href="${escapeHtml(link)}" target="_blank"
          style="display:block; text-align:center; background:linear-gradient(90deg,#f97316,#a855f7); color:#ffffff !important; font-size:0.8rem; font-weight:700; padding:8px 12px; border-radius:6px; text-decoration:none; letter-spacing:0.3px;">
          🚀 Open Full Resource →
        </a>
      </div>
    </div>
  `;
}

// -------------------------------------------------------
// Shared preview overlay — appended once to body so it
// is never clipped by any parent overflow or scroll area
// -------------------------------------------------------
function initPreviewOverlay() {
  if (document.getElementById("preview-overlay")) return;
  const overlay = document.createElement("div");
  overlay.id = "preview-overlay";
  overlay.style.cssText = `
    display: none;
    position: fixed;
    left: 8px;
    right: 8px;
    bottom: 52px;
    max-height: 370px;
    overflow-y: auto;
    background: linear-gradient(145deg, #1a0533 0%, #0f1f4d 50%, #0a2040 100%);
    color: #F8FAFC;
    border: 2px solid #a855f7;
    border-radius: 10px;
    padding: 10px 12px;
    box-shadow: 0 -8px 40px rgba(168,85,247,0.35), 0 0 0 1px rgba(56,189,248,0.12);
    z-index: 9999;
    font-family: 'Outfit', sans-serif;
    scrollbar-width: thin;
    scrollbar-color: rgba(168,85,247,0.5) transparent;
    transition: opacity 0.15s ease;
  `;
  // Hide when mouse leaves the overlay itself
  overlay.addEventListener("mouseleave", hidePreviewOverlay);
  document.body.appendChild(overlay);
}

function showPreviewOverlay(item, category, domainHost) {
  const overlay = document.getElementById("preview-overlay");
  if (!overlay) return;
  overlay.innerHTML = buildPreviewInner(item, category, domainHost);
  overlay.style.display = "block";
  overlay.style.opacity = "1";
}

function hidePreviewOverlay() {
  const overlay = document.getElementById("preview-overlay");
  if (overlay) overlay.style.display = "none";
}

function buildPreviewInner(item, category, domainHost) {
  const title = item.Title || item.title || "Untitled";
  const desc = item.Description || item.description || "No description provided.";
  const link = item.Link || item.link || "#";
  const pageTitle = item.PageTitle || item.page_title || title;
  const pageDescription = item.PageDescription || item.page_description || desc;
  let pageImage = item.PageImage || item.page_image || "";
  const pageOutline = item.PageOutline || item.page_outline || [];

  if (!pageImage && category === "YouTube Video" && link) {
    let videoId = "";
    if (link.includes("youtube.com/watch")) {
      try {
        const urlParams = new URLSearchParams(link.split("?")[1]);
        videoId = urlParams.get("v");
      } catch (e) {}
    } else if (link.includes("youtu.be/")) {
      videoId = link.split("youtu.be/")[1]?.split("?")[0];
    }
    if (videoId) {
      pageImage = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
    }
  }

  // Full-width image banner
  let imgBlock = "";
  if (pageImage && pageImage.startsWith("http")) {
    imgBlock = `<img src="${escapeHtml(pageImage)}"
      onerror="this.style.display='none';"
      style="width:calc(100% + 24px); margin:-10px -12px 0 -12px; height:140px; object-fit:cover; border-top-left-radius:8px; border-top-right-radius:8px; display:block;" />`;
  } else {
    // Pure CSS fallback using category theme colors
    const catColorsFallback = {
        "GitHub Repo": ["#1e293b", "#0f172a"],
        "Hugging Face Model": ["#ffca28", "#f57c00"],
        "arXiv Research Paper": ["#b31b1b", "#5a0e0e"],
        "PyPI Release": ["#3775a9", "#1d405e"],
        "Corporate Blog": ["#10b981", "#047857"],
        "Reddit Discussion": ["#ff4500", "#992900"],
        "Product Hunt Launch": ["#da552f", "#80301a"],
        "AI Course": ["#f59e0b", "#b45309"],
        "YouTube Video": ["#dc2626", "#7f1d1d"]
    };
    
    const [c1, c2] = catColorsFallback[category] || ["#1e293b", "#020617"];
    
    const shortNames = {
        "arXiv Research Paper": "arXiv",
        "PyPI Release": "PyPI",
        "Reddit Discussion": "Reddit",
        "Product Hunt Launch": "Product Hunt",
        "Corporate Blog": "Tech Blog",
        "Hugging Face Model": "Hugging Face"
    };
    
    let domainStr = "Link";
    try { domainStr = new URL(link).hostname.replace("www.", "").split(".")[0]; } catch(e){}
    const shortName = shortNames[category] || (domainStr.charAt(0).toUpperCase() + domainStr.slice(1));

    imgBlock = `
    <div style="width:calc(100% + 24px); margin:-10px -12px 0 -12px; height:120px; background:linear-gradient(135deg, ${c1} 0%, ${c2} 100%); border-top-left-radius:8px; border-top-right-radius:8px; display:flex; align-items:center; justify-content:center; box-shadow:inset 0 -10px 20px rgba(0,0,0,0.2);">
        <div style="background:rgba(0,0,0,0.2); padding:10px 24px; border-radius:12px; border:1px solid rgba(255,255,255,0.1);">
            <span style="font-size:1.5rem; font-weight:800; color:rgba(255,255,255,0.95); letter-spacing:1.5px; font-family:sans-serif;">${shortName}</span>
        </div>
    </div>`;
  }

  const headerRadius = pageImage ? "" : "border-top-left-radius:8px; border-top-right-radius:8px;";

  // Colorful chip tags
  const chipColors = ["#f97316","#a855f7","#38BDF8","#34D399","#fb7185","#facc15","#60a5fa"];
  let chipsHtml = "";
  if (pageOutline && pageOutline.length > 0) {
    let chips = "";
    pageOutline.slice(0, 5).forEach((heading, i) => {
      const color = chipColors[i % chipColors.length];
      chips += `<span style="display:inline-block; padding:2px 9px; border-radius:20px; font-size:0.68rem; font-weight:600; color:${color}; border:1px solid ${color}; margin:2px 3px 2px 0; max-width:155px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(heading)}</span>`;
    });
    chipsHtml = `<div style="margin-bottom:8px; line-height:2;">${chips}</div>`;
  }

  const truncDesc = pageDescription.length > 200 ? pageDescription.slice(0, 200) + "…" : pageDescription;
  const truncTitle = pageTitle.length > 100 ? pageTitle.slice(0, 100) : pageTitle;
  const descMargin = chipsHtml ? "8px" : "0";

  return `
    ${imgBlock}
    <div style="background:linear-gradient(90deg,#7c2d12 0%,#581c87 60%,#1e1b4b 100%); padding:8px 12px; margin:0 -12px 12px -12px; ${headerRadius} font-family:Consolas,monospace; font-size:0.78rem; display:flex; justify-content:space-between; align-items:center; gap:6px;">
      <div style="overflow:hidden; flex:1; min-width:0;">
        <span style="color:#fbbf24; font-weight:700; font-size:0.67rem; letter-spacing:1px; text-transform:uppercase;">${escapeHtml(category)}</span>
        <span style="color:#e2e8f0; font-weight:600; margin-left:5px; font-size:0.76rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:inline-block; max-width:150px; vertical-align:middle;">→ ${escapeHtml(title.slice(0, 35))}</span>
      </div>
      <span style="background:rgba(251,191,36,0.15); color:#fbbf24; border:1px solid rgba(251,191,36,0.4); padding:2px 7px; border-radius:12px; font-size:0.62rem; font-weight:600; flex-shrink:0;">${escapeHtml(domainHost)}</span>
    </div>
    <div style="padding:2px 0 6px 0;">
      <div style="font-size:0.92rem; font-weight:700; color:#f1f5f9; line-height:1.35; margin-bottom:5px;">${escapeHtml(truncTitle)}</div>
      <div style="font-size:0.78rem; color:#cbd5e1; line-height:1.5; margin-bottom:${descMargin};">${escapeHtml(truncDesc)}</div>
      ${chipsHtml}
    </div>
    <div style="border-top:1px solid rgba(255,255,255,0.1); padding-top:7px; margin-top:3px;">
      <a href="${escapeHtml(link)}" target="_blank"
        style="display:block; text-align:center; background:linear-gradient(90deg,#f97316,#a855f7); color:#fff !important; font-size:0.78rem; font-weight:700; padding:7px 12px; border-radius:6px; text-decoration:none; letter-spacing:0.3px;">
        🚀 Open Full Resource →
      </a>
    </div>
  `;
}






