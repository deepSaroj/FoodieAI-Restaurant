/* FoodieAI Restaurant -- customer frontend logic */
"use strict";

const CATEGORIES = ["All", "Pizza", "Burger", "Indian", "Chinese", "Beverages", "Desserts"];
const TAX_RATE = 0.05;

const state = {
  menu: [],            // last fetched menu items
  byId: {},            // id -> item
  cart: JSON.parse(localStorage.getItem("foodieai_cart") || "{}"), // {id: qty}
  category: "All",
  vegOnly: false,
  chatHistory: [],     // {role, content} for the AI API mode
};

/* ---------------- tiny helpers ---------------- */
const $ = (id) => document.getElementById(id);
const fmt = (n) => "₹" + Number(n).toFixed(n % 1 ? 2 : 0);

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2600);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* Very small markdown-lite: *bold* and line breaks (bot replies use these). */
function renderRich(text) {
  let h = escapeHtml(text);
  h = h.replace(/\*([^*]+)\*/g, "<b>$1</b>");
  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
  h = h.replace(/\n/g, "<br>");
  return h;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* ---------------- theme ---------------- */
function initTheme() {
  const saved = localStorage.getItem("foodieai_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  $("themeToggle").textContent = saved === "dark" ? "☀️" : "🌙";
  $("themeToggle").onclick = () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("foodieai_theme", next);
    $("themeToggle").textContent = next === "dark" ? "☀️" : "🌙";
  };
}

/* ---------------- menu ---------------- */
function renderChips() {
  $("categoryChips").innerHTML = CATEGORIES.map((c) =>
    `<button class="chip ${c === state.category ? "active" : ""}" data-cat="${c}">${c}</button>`
  ).join("");
  $("categoryChips").querySelectorAll(".chip").forEach((b) => {
    b.onclick = () => { state.category = b.dataset.cat; renderChips(); loadMenu(); };
  });
}

async function loadMenu() {
  const params = new URLSearchParams();
  if (state.category !== "All") params.set("category", state.category);
  const q = $("searchInput").value.trim();
  if (q) params.set("search", q);
  if (state.vegOnly) params.set("veg", "1");
  try {
    const data = await api("/api/menu?" + params.toString());
    state.menu = data.items;
    state.byId = Object.fromEntries(data.items.map((i) => [i.id, i]));
    renderMenu();
  } catch (e) {
    $("menuGrid").innerHTML = `<div class="empty-state">⚠️ Could not load menu: ${escapeHtml(e.message)}</div>`;
  }
}

function renderMenu() {
  const grid = $("menuGrid");
  if (!state.menu.length) {
    grid.innerHTML = `<div class="empty-state">😕 No dishes found. Try another search or category.</div>`;
    return;
  }
  grid.innerHTML = state.menu.map((it) => {
    const badge = it.is_veg
      ? `<span class="veg-badge veg">VEG</span>` : `<span class="veg-badge nonveg">NON-VEG</span>`;
    const action = it.is_available
      ? `<button class="btn btn-small" data-add="${it.id}">Add +</button>`
      : `<span class="soldout">Sold out</span>`;
    return `
      <div class="food-card">
        <div class="food-emoji">${escapeHtml(it.image || "🍽️")}</div>
        <div class="food-body">
          <h3>${badge} ${escapeHtml(it.name)}</h3>
          <p class="food-desc">${escapeHtml(it.description || "")}</p>
          <p class="food-meta">⭐ ${it.rating} • ${escapeHtml(it.category)}</p>
          <div class="price-row"><span class="price">${fmt(it.price)}</span>${action}</div>
        </div>
      </div>`;
  }).join("");
  grid.querySelectorAll("[data-add]").forEach((b) => {
    b.onclick = () => addToCart(Number(b.dataset.add), 1);
  });
}

/* ---------------- cart ---------------- */
function saveCart() {
  localStorage.setItem("foodieai_cart", JSON.stringify(state.cart));
  updateBadge();
}

function updateBadge() {
  $("cartCount").textContent = Object.values(state.cart).reduce((a, b) => a + b, 0);
}

function addToCart(id, qty) {
  const item = state.byId[id];
  if (!item || !item.is_available) { toast("Item not available"); return; }
  state.cart[id] = Math.min((state.cart[id] || 0) + qty, 20);
  saveCart(); renderCart();
  toast(`Added ${qty} × ${item.name}`);
}

function cartLines() {
  return Object.entries(state.cart)
    .map(([id, qty]) => ({ item: state.byId[Number(id)], qty }))
    .filter((l) => l.item);
}

function cartTotals() {
  const subtotal = cartLines().reduce((s, l) => s + l.item.price * l.qty, 0);
  const tax = +(subtotal * TAX_RATE).toFixed(2);
  return { subtotal, tax, total: +(subtotal + tax).toFixed(2) };
}

function renderCart() {
  const box = $("cartItems");
  const lines = cartLines();
  if (!lines.length) {
    box.innerHTML = `<div class="empty-state">Your cart is empty 🛒<br>Add something tasty!</div>`;
  } else {
    box.innerHTML = lines.map((l) => `
      <div class="cart-item">
        <div class="emoji">${escapeHtml(l.item.image || "🍽️")}</div>
        <div class="info"><b>${escapeHtml(l.item.name)}</b><br><small>${fmt(l.item.price)} each</small></div>
        <div class="qty-controls">
          <button class="qty-btn" data-dec="${l.item.id}">−</button>
          <b>${l.qty}</b>
          <button class="qty-btn" data-inc="${l.item.id}">+</button>
        </div>
        <button class="remove-link" data-rem="${l.item.id}">Remove</button>
      </div>`).join("");
    box.querySelectorAll("[data-inc]").forEach((b) => (b.onclick = () => {
      state.cart[b.dataset.inc] = Math.min(state.cart[b.dataset.inc] + 1, 20); saveCart(); renderCart();
    }));
    box.querySelectorAll("[data-dec]").forEach((b) => (b.onclick = () => {
      const id = b.dataset.dec;
      state.cart[id]--;
      if (state.cart[id] <= 0) delete state.cart[id];
      saveCart(); renderCart();
    }));
    box.querySelectorAll("[data-rem]").forEach((b) => (b.onclick = () => {
      delete state.cart[b.dataset.rem]; saveCart(); renderCart();
    }));
  }
  const t = cartTotals();
  $("cartSubtotal").textContent = fmt(t.subtotal);
  $("cartTax").textContent = fmt(t.tax);
  $("cartTotal").textContent = fmt(t.total);
  $("checkoutBtn").disabled = !lines.length;
}

function openCart() { $("cartDrawer").classList.add("open"); $("cartOverlay").classList.add("open"); }
function closeCart() { $("cartDrawer").classList.remove("open"); $("cartOverlay").classList.remove("open"); }

/* ---------------- checkout ---------------- */
function openCheckout() {
  const lines = cartLines();
  if (!lines.length) return;
  const t = cartTotals();
  $("coSummary").innerHTML =
    lines.map((l) => `<div class="totals-row"><span>${escapeHtml(l.item.name)} × ${l.qty}</span><span>${fmt(l.item.price * l.qty)}</span></div>`).join("") +
    `<div class="totals-row"><span>GST (5%)</span><span>${fmt(t.tax)}</span></div>` +
    `<div class="totals-row grand"><span>Total</span><span>${fmt(t.total)}</span></div>`;
  $("coError").textContent = "";
  closeCart();
  $("checkoutModal").classList.add("open");
}

async function placeOrder() {
  const btn = $("placeOrderBtn");
  const payload = {
    customer_name: $("coName").value.trim(),
    phone: $("coPhone").value.trim(),
    address: $("coAddress").value.trim(),
    items: cartLines().map((l) => ({ id: l.item.id, qty: l.qty })),
  };
  $("coError").textContent = "";
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>Placing order…`;
  try {
    const order = await api("/api/orders", { method: "POST", body: JSON.stringify(payload) });
    state.cart = {}; saveCart(); renderCart();
    $("checkoutModal").classList.remove("open");
    $("orderCode").textContent = order.order_code;
    $("successTotal").textContent = `Total: ${fmt(order.total)} (incl. GST) • Status: ${order.status}`;
    $("successModal").classList.add("open");
    $("trackFromSuccess").onclick = () => {
      $("successModal").classList.remove("open");
      $("trackCode").value = order.order_code;
      trackOrder();
      document.getElementById("track").scrollIntoView({ behavior: "smooth" });
    };
  } catch (e) {
    $("coError").textContent = e.message;   // real server validation errors
  } finally {
    btn.disabled = false;
    btn.textContent = "Place Order • Mock Payment";
  }
}

/* ---------------- track order ---------------- */
const STATUS_STEPS = ["Pending", "Confirmed", "Preparing", "Out for Delivery", "Delivered"];

async function trackOrder() {
  const code = $("trackCode").value.trim().toUpperCase();
  const box = $("trackResult");
  if (!code) { box.innerHTML = `<p class="form-error">Please enter an order code.</p>`; return; }
  box.innerHTML = `<p style="color:var(--muted)">Looking up ${escapeHtml(code)}…</p>`;
  try {
    const o = await api("/api/orders/" + encodeURIComponent(code));
    const idx = STATUS_STEPS.indexOf(o.status);
    const steps = STATUS_STEPS.map((s, i) => `
      <div class="timeline-step ${idx >= 0 && i <= idx ? "done" : ""}">
        <div><div class="timeline-dot">${i < idx || o.status === "Delivered" && i <= idx ? "✓" : i + 1}</div>${i < STATUS_STEPS.length - 1 ? '<div class="line"></div>' : ""}</div>
        <div class="timeline-label">${s}${i === idx ? " <small>current status</small>" : ""}</div>
      </div>`).join("");
    const items = o.items.map((it) => `${escapeHtml(it.item_name)} × ${it.quantity}`).join(", ");
    box.innerHTML = `
      <p style="margin-top:0.8rem"><b>Order ${escapeHtml(o.order_code)}</b> — <span class="pill">${escapeHtml(o.status)}</span></p>
      <p style="color:var(--muted);font-size:0.9rem">${items} • Total ${fmt(o.total)} • ${escapeHtml(o.created_at || "")}</p>
      ${o.status === "Cancelled" ? `<p class="form-error">This order was cancelled.</p>` : `<div class="timeline">${steps}</div>`}`;
  } catch (e) {
    box.innerHTML = `<p class="form-error">${escapeHtml(e.message)}</p>`;
  }
}

/* ---------------- chatbot ---------------- */
const QUICK = ["Show menu", "Under ₹200", "Veg options", "Recommend something", "Delivery info", "Timings"];

function addMsg(text, who, actions = []) {
  const box = $("chatMessages");
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.innerHTML = renderRich(text);
  if (actions.length && who === "bot") {
    const row = document.createElement("div");
    row.className = "confirm-row";
    actions.forEach((a) => {
      if (a.type === "add_to_cart") {
        const b = document.createElement("button");
        b.className = "btn btn-small btn-gold";
        b.textContent = `Yes, add ${a.qty} × ${a.item_name} (${fmt(a.price * a.qty)})`;
        b.onclick = () => {
          addToCart(a.item_id, a.qty);
          addMsg(`Yes, add ${a.qty} × ${a.item_name}`, "user");
          addMsg(`Done! ${a.qty} × *${a.item_name}* cart mein add ho gaya 🛒`, "bot");
          row.remove();
        };
        const no = document.createElement("button");
        no.className = "btn btn-small btn-outline";
        no.textContent = "No";
        no.onclick = () => { row.remove(); addMsg("No, rehne do", "user"); };
        row.append(b, no);
      }
    });
    div.appendChild(row);
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

async function sendChat(text) {
  const message = (text ?? $("chatInput").value).trim();
  if (!message) return;
  $("chatInput").value = "";
  addMsg(message, "user");
  state.chatHistory.push({ role: "user", content: message });

  const typing = document.createElement("div");
  typing.className = "msg bot typing";
  typing.textContent = "FoodieAI is typing…";
  $("chatMessages").appendChild(typing);

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, history: state.chatHistory.slice(-6) }),
    });
    typing.remove();
    addMsg(data.reply, "bot", data.actions || []);
    state.chatHistory.push({ role: "assistant", content: data.reply });
    if (data.mode) $("chatMode").textContent = data.mode === "ai" ? "online • AI mode ✨" : "online • rule-based mode";
  } catch (e) {
    typing.remove();
    addMsg("⚠️ " + e.message + " — thodi der baad try karein.", "bot");
  }
}

function initChat() {
  $("chatFab").onclick = () => $("chatPanel").classList.toggle("open");
  $("chatClose").onclick = () => $("chatPanel").classList.remove("open");
  $("chatSend").onclick = () => sendChat();
  $("chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
  $("quickChips").innerHTML = QUICK.map((q) => `<button class="qchip">${q}</button>`).join("");
  $("quickChips").querySelectorAll(".qchip").forEach((b) => (b.onclick = () => sendChat(b.textContent)));
  addMsg("Namaste! 🙏 Main *FoodieAI* hoon.\nMenu dekhna hai, budget mein khana hai, ya order track karna hai — bas poochhein!", "bot");
}

/* ---------------- boot ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  renderChips();
  loadMenu();
  renderCart();
  updateBadge();
  initChat();

  let debounce;
  $("searchInput").addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(loadMenu, 300);
  });
  $("searchBtn").onclick = loadMenu;
  $("searchInput").addEventListener("keydown", (e) => { if (e.key === "Enter") loadMenu(); });
  $("vegToggle").onchange = (e) => { state.vegOnly = e.target.checked; loadMenu(); };

  $("cartBtn").onclick = openCart;
  $("closeCart").onclick = closeCart;
  $("cartOverlay").onclick = closeCart;
  $("checkoutBtn").onclick = openCheckout;
  $("coCancel").onclick = () => $("checkoutModal").classList.remove("open");
  $("placeOrderBtn").onclick = placeOrder;
  $("successClose").onclick = () => $("successModal").classList.remove("open");
  $("trackBtn").onclick = trackOrder;
  $("trackCode").addEventListener("keydown", (e) => { if (e.key === "Enter") trackOrder(); });
});
