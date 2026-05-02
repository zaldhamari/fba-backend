const API = "/api";

// Tab navigation
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.panel).classList.add("active");
  });
});

// ---- UTILS ----

function loading(btnEl, spinnerEl, on) {
  btnEl.disabled = on;
  spinnerEl.style.display = on ? "inline-block" : "none";
}

function showError(container, msg) {
  container.innerHTML = `<div class="error-msg">⚠ ${msg}</div>`;
}

function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {});
}

async function post(endpoint, body) {
  const res = await fetch(API + endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}

// ---- PHASE 1: PRODUCT RESEARCH ----

document.getElementById("research-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("research-btn");
  const spinner = document.getElementById("research-spinner");
  const out = document.getElementById("research-results");

  const keyword = document.getElementById("keyword").value.trim();
  const category = document.getElementById("category").value;
  if (!keyword) return;

  loading(btn, spinner, true);
  out.innerHTML = `<div class="empty-state"><div class="spinner" style="width:32px;height:32px;margin:0 auto"></div><p style="margin-top:16px">Searching Amazon & Google Trends…</p></div>`;

  try {
    const data = await post("/research/amazon", { keyword, category });
    renderResearch(data, out);
  } catch (err) {
    showError(out, err.message);
  } finally {
    loading(btn, spinner, false);
  }
});

function renderResearch(data, container) {
  const { products, trends, keyword } = data;
  let html = "";

  // Trends section
  if (trends && !trends.error) {
    const dir = trends.trend_direction;
    const dirClass = dir === "Rising" ? "trend-rising" : dir === "Declining" ? "trend-declining" : "trend-stable";
    const dirIcon = dir === "Rising" ? "↑" : dir === "Declining" ? "↓" : "→";

    html += `<div class="card">
      <h2>Google Trends — "${keyword}"</h2>
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
        <div class="trend-box ${dirClass}">${dirIcon} ${dir}</div>
        <div class="stat">Avg Interest: <span>${trends.interest_score ?? "N/A"}/100</span></div>
      </div>`;

    if (trends.monthly_interest?.length) {
      const max = Math.max(...trends.monthly_interest.map(m => m.value), 1);
      html += `<div class="interest-chart">` +
        trends.monthly_interest.map(m => `<div class="bar" title="${m.month}: ${m.value}" style="height:${Math.max(4, (m.value / max) * 100)}%"></div>`).join("") +
        `</div>`;
    }

    if (trends.related_queries?.length) {
      html += `<div style="margin-top:12px"><label>Related searches</label>
        <div class="tag-list">` +
        trends.related_queries.map(q => `<span class="tag">${q}</span>`).join("") +
        `</div></div>`;
    }
    html += `</div>`;
  }

  // Products
  const goodProducts = products.filter(p => !p.error);
  const errors = products.filter(p => p.error);

  if (errors.length) {
    html += `<div class="error-msg">⚠ ${errors[0].error}</div>`;
  }

  if (goodProducts.length === 0) {
    html += `<div class="empty-state"><div class="icon">🔍</div><p>No products found. Try a different keyword.</p></div>`;
  } else {
    html += `<h3 style="margin:16px 0 8px;color:var(--text-muted);font-size:0.85rem">${goodProducts.length} products found</h3>
      <div class="results-grid">`;

    goodProducts.forEach(p => {
      const oppClass = p.opportunity === "Good" ? "badge-green" : p.opportunity === "Moderate" ? "badge-yellow" : "badge-red";
      const compClass = p.competition === "Low" ? "badge-green" : p.competition === "Medium" ? "badge-yellow" : "badge-red";

      html += `<div class="product-card">
        ${p.image ? `<img src="${p.image}" alt="product" onerror="this.style.display='none'">` : ""}
        <div class="title">${p.title}</div>
        <div class="meta-row">
          <span class="price">${p.price ? "$" + p.price.toFixed(2) : "N/A"}</span>
          <span class="badge ${oppClass}">${p.opportunity}</span>
        </div>
        <div class="stats-row">
          <div class="stat">⭐ <span>${p.rating ?? "N/A"}</span></div>
          <div class="stat">Reviews: <span>${p.review_count ?? "N/A"}</span></div>
          <div class="stat">Competition: <span class="badge ${compClass}" style="font-size:0.7rem">${p.competition}</span></div>
        </div>
        ${p.url ? `<a href="${p.url}" target="_blank" style="display:block;margin-top:10px;color:#2196f3;font-size:0.8rem">View on Amazon →</a>` : ""}
      </div>`;
    });

    html += `</div>`;
  }

  container.innerHTML = html;
}

// ---- PHASE 2: SUPPLIER SEARCH ----

document.getElementById("supplier-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("supplier-btn");
  const spinner = document.getElementById("supplier-spinner");
  const out = document.getElementById("supplier-results");

  const product = document.getElementById("supplier-product").value.trim();
  const max_price = parseFloat(document.getElementById("max-price").value) || null;
  if (!product) return;

  loading(btn, spinner, true);
  out.innerHTML = `<div class="empty-state"><div class="spinner" style="width:32px;height:32px;margin:0 auto"></div><p style="margin-top:16px">Searching Alibaba for suppliers…</p></div>`;

  try {
    const data = await post("/research/suppliers", { product, max_price });
    renderSuppliers(data, out);
  } catch (err) {
    showError(out, err.message);
  } finally {
    loading(btn, spinner, false);
  }
});

function renderSuppliers(data, container) {
  const { suppliers } = data;
  const good = suppliers.filter(s => !s.error);
  const errors = suppliers.filter(s => s.error);

  let html = "";
  if (errors.length) html += `<div class="error-msg">⚠ ${errors[0].error}</div>`;

  if (good.length === 0) {
    html += `<div class="empty-state"><div class="icon">🏭</div><p>No suppliers found. Try a broader search term.</p></div>`;
  } else {
    html += `<h3 style="margin:0 0 16px;color:var(--text-muted);font-size:0.85rem">${good.length} suppliers found</h3>
      <div style="display:flex;flex-direction:column;gap:12px">`;

    good.forEach(s => {
      html += `<div class="supplier-card">
        ${s.image ? `<img src="${s.image}" alt="product" onerror="this.style.display='none'">` : `<div style="width:80px;height:80px;background:var(--surface);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem">🏭</div>`}
        <div class="supplier-info">
          <div class="name">${s.title}</div>
          <div class="price">${s.price_display}</div>
          <div class="moq">MOQ: ${s.moq}</div>
          ${s.supplier !== "N/A" ? `<div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px">${s.supplier}</div>` : ""}
          ${s.url ? `<a href="${s.url}" target="_blank">View on Alibaba →</a>` : ""}
        </div>
      </div>`;
    });

    html += `</div>`;
  }

  container.innerHTML = html;
}

// ---- PHASE 3: FBA CALCULATOR ----

document.getElementById("calc-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("calc-btn");
  const spinner = document.getElementById("calc-spinner");
  const out = document.getElementById("calc-results");

  const body = {
    product_name: document.getElementById("calc-product").value.trim() || "Product",
    selling_price: parseFloat(document.getElementById("selling-price").value),
    supplier_cost: parseFloat(document.getElementById("supplier-cost").value),
    weight_lbs: parseFloat(document.getElementById("weight").value),
    dimensions: {
      length: parseFloat(document.getElementById("length").value),
      width: parseFloat(document.getElementById("width").value),
      height: parseFloat(document.getElementById("height").value),
    },
    category: document.getElementById("calc-category").value,
  };

  if (isNaN(body.selling_price) || isNaN(body.supplier_cost) || isNaN(body.weight_lbs)) return;

  loading(btn, spinner, true);
  try {
    const data = await post("/calculate/fba", body);
    renderCalc(data, out);
  } catch (err) {
    showError(out, err.message);
  } finally {
    loading(btn, spinner, false);
  }
});

function renderCalc(d, container) {
  const profitColor = d.profit > 0 ? "var(--green)" : "var(--red)";
  const verdictClass = d.verdict === "Excellent" ? "badge-green" : d.verdict === "Good" ? "badge-green" : d.verdict === "Marginal" ? "badge-yellow" : "badge-red";

  container.innerHTML = `
    <div class="fee-breakdown">
      <div>
        <div class="card">
          <h2>Fee Breakdown</h2>
          <div class="fee-row"><span>Selling Price</span><span class="amount">$${d.selling_price.toFixed(2)}</span></div>
          <div class="fee-row"><span>Supplier Cost</span><span class="amount" style="color:var(--red)">-$${d.supplier_cost.toFixed(2)}</span></div>
          <div class="fee-row"><span>Referral Fee</span><span class="amount" style="color:var(--red)">-$${d.fees.referral_fee.toFixed(2)}</span></div>
          <div class="fee-row"><span>FBA Fulfillment</span><span class="amount" style="color:var(--red)">-$${d.fees.fulfillment_fee.toFixed(2)}</span></div>
          <div class="fee-row"><span>Storage (monthly)</span><span class="amount" style="color:var(--red)">-$${d.fees.monthly_storage.toFixed(2)}</span></div>
          <div class="fee-row total"><span>Net Profit</span><span class="amount" style="color:${profitColor}">$${d.profit.toFixed(2)}</span></div>
        </div>
        <div class="card" style="margin-top:0">
          <h3>Product Details</h3>
          <div class="fee-row"><span>Size Tier</span><span>${d.size_tier.replace("_", " ")}</span></div>
          <div class="fee-row"><span>Billable Weight</span><span>${d.billable_weight_lbs} lbs</span></div>
          <div class="fee-row"><span>Total Fees</span><span>$${d.fees.total_fees.toFixed(2)}</span></div>
        </div>
      </div>

      <div>
        <div class="profit-display card">
          <div class="profit-num" style="color:${profitColor}">$${d.profit.toFixed(2)}</div>
          <div class="profit-label">Profit per unit</div>
          <div class="verdict" style="margin-top:16px">
            <span class="badge ${verdictClass}" style="font-size:0.9rem;padding:6px 16px">${d.verdict}</span>
          </div>
          <div class="stats-row" style="justify-content:center;margin-top:16px">
            <div class="stat">Margin: <span>${d.margin_pct}%</span></div>
            <div class="stat">ROI: <span>${d.roi_pct}%</span></div>
          </div>
          ${d.viable ? `<p style="margin-top:16px;font-size:0.85rem;color:var(--green)">✓ Meets the 25%+ margin threshold</p>` : `<p style="margin-top:16px;font-size:0.85rem;color:var(--red)">✗ Below the recommended 25% margin</p>`}
        </div>
      </div>
    </div>`;
}

// ---- PHASE 4: BRAND CREATION ----

let currentBrand = null;

document.getElementById("brand-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("brand-btn");
  const spinner = document.getElementById("brand-spinner");
  const out = document.getElementById("brand-results");

  const product_type = document.getElementById("brand-product").value.trim();
  const style = document.getElementById("brand-style").value;
  if (!product_type) return;

  loading(btn, spinner, true);
  out.innerHTML = "";

  try {
    const data = await post("/brand/create", { product_type, keywords: [], style });
    currentBrand = data;
    renderBrand(data, out);
  } catch (err) {
    showError(out, err.message);
  } finally {
    loading(btn, spinner, false);
  }
});

function renderBrand(data, container) {
  const { brand_name, name_options, tagline, logo_svg, listing, generated_keywords } = data;

  container.innerHTML = `
    <div class="card brand-output">
      <h2>Your Brand</h2>

      <div class="section">
        <label>Name Options — click to select</label>
        <div class="brand-names">
          ${name_options.map((n, i) => `<div class="brand-name-chip ${i === 0 ? 'selected' : ''}" onclick="selectName(this, '${n}')">${n}</div>`).join("")}
        </div>
        <div style="font-size:0.85rem;color:var(--text-muted);margin-top:8px">"${tagline}"</div>
      </div>

      ${generated_keywords?.length ? `
      <div class="section" style="margin-top:20px">
        <label>Auto-Generated Keywords (${generated_keywords.length})</label>
        <div class="tag-list" style="margin-top:10px">
          ${generated_keywords.map(k => `<span class="tag" style="color:var(--text)">${k}</span>`).join("")}
        </div>
      </div>` : ""}

      <div class="section" style="margin-top:20px">
        <label>Logo Preview</label>
        <div class="logo-preview">${logo_svg}</div>
        <button class="btn btn-outline" style="font-size:0.8rem;padding:6px 14px" onclick="downloadLogo()">Download SVG</button>
      </div>
    </div>

    <div class="card">
      <h2>Amazon Listing Copy</h2>
      <div class="listing-copy">
        <div class="section">
          <label>Product Title <button class="btn btn-outline copy-btn" onclick="copyText(\`${listing.title.replace(/`/g, '\\`')}\`)">Copy</button></label>
          <div class="copy-text">${listing.title}</div>
        </div>
        <div class="section">
          <label>Bullet Points</label>
          <ul class="bullet-list">
            ${listing.bullet_points.map(b => `<li>${b}</li>`).join("")}
          </ul>
        </div>
        <div class="section">
          <label>Product Description <button class="btn btn-outline copy-btn" onclick="copyText(\`${listing.description.replace(/`/g, '\\`')}\`)">Copy</button></label>
          <div class="copy-text">${listing.description}</div>
        </div>
        <div class="section">
          <label>Backend Keywords</label>
          <div class="tag-list">${listing.backend_keywords.map(k => `<span class="tag">${k}</span>`).join("")}</div>
        </div>
      </div>
    </div>`;
}

function selectName(el, name) {
  document.querySelectorAll(".brand-name-chip").forEach(c => c.classList.remove("selected"));
  el.classList.add("selected");
}

function downloadLogo() {
  if (!currentBrand) return;
  const blob = new Blob([currentBrand.logo_svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${currentBrand.brand_name}-logo.svg`;
  a.click();
  URL.revokeObjectURL(url);
}
