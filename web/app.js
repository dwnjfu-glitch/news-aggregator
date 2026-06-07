(function () {
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  const searchInput = document.getElementById("search");
  const filtersEl = document.getElementById("filters");
  const updatedEl = document.getElementById("updated");

  let allArticles = [];
  let activeSource = null;
  let activeCategory = null;

  // --- Load ---

  async function load() {
    status.textContent = "Loading...";
    status.className = "status";
    grid.innerHTML = "";

    try {
      const [indexResp, statsResp] = await Promise.allSettled([
        fetch("data/index.json"),
        fetch("data/stats.json"),
      ]);

      if (indexResp.status === "rejected" || !indexResp.value.ok) {
        throw new Error("Failed to load data/index.json");
      }

      allArticles = await indexResp.value.json();

      if (statsResp.status === "fulfilled" && statsResp.value.ok) {
        const stats = await statsResp.value.json();
        if (stats.updated) {
          const d = new Date(stats.updated);
          updatedEl.textContent = `Last updated: ${d.toLocaleString()}`;
        }
      }

      if (!allArticles.length) {
        status.textContent = "No articles yet. Check back after the first fetch.";
        status.className = "status";
        return;
      }

      status.textContent = "";
      status.className = "status hidden";

      buildFilters();
      render();
    } catch (err) {
      status.textContent = "Could not load news data. Is data/index.json present?";
      status.className = "status";
      console.error(err);
    }
  }

  // --- Filters ---

  function buildFilters() {
    const sources = [...new Set(allArticles.map((a) => a.source))].sort();
    const categories = [...new Set(allArticles.map((a) => a.category))].sort();

    filtersEl.innerHTML = "";

    // "All" button
    const allBtn = document.createElement("button");
    allBtn.className = "filter-btn active";
    allBtn.textContent = "All";
    allBtn.addEventListener("click", () => {
      activeSource = null;
      activeCategory = null;
      document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
      allBtn.classList.add("active");
      render();
    });
    filtersEl.appendChild(allBtn);

    // Source buttons
    sources.forEach((src) => {
      const btn = document.createElement("button");
      btn.className = "filter-btn";
      btn.textContent = src;
      btn.addEventListener("click", () => {
        activeCategory = null;
        activeSource = activeSource === src ? null : src;
        updateFilterUI();
        render();
      });
      filtersEl.appendChild(btn);
    });

    // Category buttons
    categories.forEach((cat) => {
      const btn = document.createElement("button");
      btn.className = "filter-btn";
      btn.textContent = cat;
      btn.addEventListener("click", () => {
        activeSource = null;
        activeCategory = activeCategory === cat ? null : cat;
        updateFilterUI();
        render();
      });
      filtersEl.appendChild(btn);
    });
  }

  function updateFilterUI() {
    document.querySelectorAll(".filter-btn").forEach((btn) => {
      const txt = btn.textContent;
      const isAll = txt === "All";
      const isSourceActive = activeSource && txt === activeSource;
      const isCatActive = activeCategory && txt === activeCategory;
      btn.classList.toggle("active", isAll ? !activeSource && !activeCategory : isSourceActive || isCatActive);
    });
  }

  // --- Render ---

  function render() {
    const query = searchInput.value.toLowerCase().trim();

    let filtered = allArticles;

    if (activeSource) {
      filtered = filtered.filter((a) => a.source === activeSource);
    }
    if (activeCategory) {
      filtered = filtered.filter((a) => a.category === activeCategory);
    }
    if (query) {
      filtered = filtered.filter(
        (a) =>
          a.title.toLowerCase().includes(query) ||
          (a.summary && a.summary.toLowerCase().includes(query)) ||
          a.source.toLowerCase().includes(query)
      );
    }

    if (!filtered.length) {
      grid.innerHTML = '<div class="empty">No articles match your filter.</div>';
      return;
    }

    grid.innerHTML = filtered
      .map((a) => {
        const time = a.pubDate ? timeAgo(a.pubDate) : "";
        return `
            <article class="card" data-url="${esc(a.link)}">
              <div class="card-title"><a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a></div>
              ${a.summary ? `<div class="card-summary">${esc(a.summary)}</div>` : ""}
              <div class="card-meta">
                <span class="tag source">${esc(a.source)}</span>
                ${a.category ? `<span class="tag">${esc(a.category)}</span>` : ""}
                ${time ? `<span class="card-time">${time}</span>` : ""}
              </div>
            </article>`;
      })
      .join("");

    // Click card (not link) → open article
    grid.querySelectorAll(".card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.tagName === "A") return;
        window.open(card.dataset.url, "_blank", "noopener");
      });
    });
  }

  // --- Helpers ---

  function esc(s) {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return String(s).replace(/[&<>"']/g, (c) => map[c]);
  }

  function timeAgo(dateStr) {
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return "";
      const now = new Date();
      const diff = Math.max(0, now - d);
      const mins = Math.floor(diff / 60000);
      if (mins < 60) return `${mins}m ago`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `${hours}h ago`;
      const days = Math.floor(hours / 24);
      if (days < 30) return `${days}d ago`;
      return d.toLocaleDateString();
    } catch {
      return "";
    }
  }

  // --- Events ---

  searchInput.addEventListener("input", render);
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      searchInput.focus();
    }
  });

  // --- Init ---

  load();
})();
