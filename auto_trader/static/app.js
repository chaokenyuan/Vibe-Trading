// vibe-auto-trader UI 共用 JS

const API = "/api";

async function fetchJson(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${text}`);
  }
  return resp.json();
}

function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind} show`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 200);
  }, 2500);
}

function fmt(value, kind) {
  if (value === null || value === undefined || value === "") return "—";
  if (kind === "decimal") {
    const n = parseFloat(value);
    if (isNaN(n)) return value;
    if (n === Math.floor(n)) return n.toString();
    return n.toFixed(8).replace(/\.?0+$/, "");
  }
  if (kind === "pct") {
    return (parseFloat(value) * 100).toFixed(2) + "%";
  }
  if (kind === "iso-time") {
    try { return new Date(value).toLocaleString(); }
    catch { return value; }
  }
  if (kind === "short") {
    return String(value).slice(0, 16) + (String(value).length > 16 ? "…" : "");
  }
  return String(value);
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null) continue;
    if (typeof c === "string" || typeof c === "number") {
      e.appendChild(document.createTextNode(c));
    } else {
      e.appendChild(c);
    }
  }
  return e;
}

// 設定當前 active 頁面
function setActivePage(page) {
  document.querySelectorAll("header nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === page);
  });
}
