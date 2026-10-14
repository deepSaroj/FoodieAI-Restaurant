/* FoodieAI Restaurant -- admin panel logic */
"use strict";

const $ = (id) => document.getElementById(id);
const CATEGORIES = ["Pizza", "Burger", "Indian", "Chinese", "Beverages", "Desserts"];
const STATUSES = ["Pending", "Confirmed", "Preparing", "Out for Delivery", "Delivered", "Cancelled"];
let editingId = null;

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2600);
}
const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
const fmt = (n) => "₹" + Number(n).toFixed(2);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { showLogin(); throw new Error("Session expired — please log in again."); }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* ---------------- auth ---------------- */
function showLogin() {
  $("loginCard").style.display = "block";
  $("dashboard").style.display = "none";
  $("logoutBtn").style.display = "none";
}
function showDashboard() {
  $("loginCard").style.display = "none";
  $("dashboard").style.display = "block";
  $("logoutBtn").style.display = "inline-block";
}

async function doLogin() {
  $("loginError").textContent = "";
  const btn = $("loginBtn");
  btn.disabled = true;
  try {
    await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ username: $("adminUser").value.trim(), password: $("adminPass").value }),
    });
    $("adminPass").value = "";
    showDashboard();
    loadMenuTable(); loadOrders(); loadStats();
    toast("Welcome back! 👋");
  } catch (e) {
    $("loginError").textContent = e.message;
  } finally { btn.disabled = false; }
}

/* ---------------- tabs ---------------- */
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".tab-btn").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tab-page").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $("tab-" + b.dataset.tab).classList.add("active");
    };
  });
}

/* ---------------- menu management ---------------- */
async function loadMenuTable() {
  try {
    const { items } = await api("/api/admin/menu");
    $("menuTable").innerHTML = `
      <tr><th>#</th><th>Item</th><th>Category</th><th>Price</th><th>Rating</th><th>Veg</th><th>Available</th><th>Actions</th></tr>` +
      items.map((it) => `
      <tr>
        <td>${it.id}</td>
        <td>${escapeHtml(it.image)} <b>${escapeHtml(it.name)}</b></td>
        <td>${escapeHtml(it.category)}</td>
        <td>${fmt(it.price)}</td>
        <td>⭐ ${it.rating}</td>
        <td>${it.is_veg ? "🟢" : "🔴"}</td>
        <td><input type="checkbox" data-avail="${it.id}" ${it.is_available ? "checked" : ""} title="Toggle availability" /></td>
        <td>
          <button class="btn btn-small btn-outline" data-edit="${it.id}">Edit</button>
          <button class="btn btn-small btn-danger" data-del="${it.id}">Delete</button>
        </td>
      </tr>`).join("");
    $("menuTable").querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => openItemModal(items.find((i) => i.id == b.dataset.edit))));
    $("menuTable").querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => deleteItem(Number(b.dataset.del))));
    $("menuTable").querySelectorAll("[data-avail]").forEach((c) => (c.onchange = () => toggleAvail(Number(c.dataset.avail), c.checked)));
  } catch (e) { toast(e.message); }
}

function openItemModal(item = null) {
  editingId = item ? item.id : null;
  $("itemModalTitle").textContent = item ? "Edit Menu Item" : "Add Menu Item";
  $("fCategory").innerHTML = CATEGORIES.map((c) => `<option ${item && item.category === c ? "selected" : ""}>${c}</option>`).join("");
  $("fName").value = item?.name || "";
  $("fPrice").value = item?.price ?? "";
  $("fRating").value = item?.rating ?? 4.0;
  $("fDesc").value = item?.description || "";
  $("fImage").value = item?.image || "";
  $("fVeg").checked = item ? !!item.is_veg : true;
  $("fAvail").checked = item ? !!item.is_available : true;
  $("itemError").textContent = "";
  $("itemModal").classList.add("open");
}

async function saveItem() {
  const payload = {
    name: $("fName").value.trim(),
    category: $("fCategory").value,
    price: Number($("fPrice").value),
    rating: Number($("fRating").value),
    description: $("fDesc").value.trim(),
    image: $("fImage").value.trim() || "🍽️",
    is_veg: $("fVeg").checked ? 1 : 0,
    is_available: $("fAvail").checked ? 1 : 0,
  };
  $("itemError").textContent = "";
  try {
    if (editingId) {
      await api(`/api/admin/menu/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
      toast("Item updated ✅");
    } else {
      await api("/api/admin/menu", { method: "POST", body: JSON.stringify(payload) });
      toast("Item added ✅");
    }
    $("itemModal").classList.remove("open");
    loadMenuTable();
  } catch (e) { $("itemError").textContent = e.message; }
}

async function deleteItem(id) {
  if (!confirm("Delete this menu item permanently?")) return;
  try { await api(`/api/admin/menu/${id}`, { method: "DELETE" }); toast("Deleted 🗑️"); loadMenuTable(); }
  catch (e) { toast(e.message); }
}

async function toggleAvail(id, on) {
  try { await api(`/api/admin/menu/${id}`, { method: "PUT", body: JSON.stringify({ is_available: on ? 1 : 0 }) }); }
  catch (e) { toast(e.message); loadMenuTable(); }
}

/* ---------------- orders ---------------- */
async function loadOrders() {
  try {
    const { orders } = await api("/api/admin/orders");
    if (!orders.length) {
      $("ordersTable").innerHTML = `<tr><td>No orders yet.</td></tr>`;
      return;
    }
    $("ordersTable").innerHTML = `
      <tr><th>Order Code</th><th>Customer</th><th>Items</th><th>Total</th><th>Status</th><th>Placed</th></tr>` +
      orders.map((o) => `
      <tr>
        <td><b>${escapeHtml(o.order_code)}</b></td>
        <td>${escapeHtml(o.customer_name)}<br><small>${escapeHtml(o.phone)}</small></td>
        <td><small>${o.items.map((it) => `${escapeHtml(it.item_name)} × ${it.quantity}`).join("<br>")}</small></td>
        <td><b>${fmt(o.total)}</b></td>
        <td><select class="status-select" data-order="${o.id}">
          ${STATUSES.map((s) => `<option ${s === o.status ? "selected" : ""}>${s}</option>`).join("")}
        </select></td>
        <td><small>${escapeHtml(o.created_at || "")}</small></td>
      </tr>`).join("");
    $("ordersTable").querySelectorAll("[data-order]").forEach((sel) => {
      sel.onchange = async () => {
        try {
          await api(`/api/admin/orders/${sel.dataset.order}/status`, {
            method: "PUT", body: JSON.stringify({ status: sel.value }),
          });
          toast(`Order → ${sel.value} ✅`); loadStats();
        } catch (e) { toast(e.message); loadOrders(); }
      };
    });
  } catch (e) { toast(e.message); }
}

/* ---------------- stats ---------------- */
async function loadStats() {
  try {
    const s = await api("/api/admin/stats");
    $("statCards").innerHTML = `
      <div class="stat-card"><small>Total Orders</small><div class="big">${s.total_orders}</div></div>
      <div class="stat-card"><small>Revenue</small><div class="big">${fmt(s.revenue)}</div></div>
      <div class="stat-card"><small>Active Orders</small><div class="big">${s.pending_orders}</div></div>
      <div class="stat-card"><small>Avg Order Value</small><div class="big">${fmt(s.avg_order_value)}</div></div>`;
    $("topTable").innerHTML =
      `<tr><th>#</th><th>Item</th><th>Qty Sold</th></tr>` +
      (s.top_items.map((t, i) => `<tr><td>${i + 1}</td><td>${escapeHtml(t.name)}</td><td>${t.qty}</td></tr>`).join("") ||
        `<tr><td colspan="3">No sales yet.</td></tr>`);
  } catch (e) { toast(e.message); }
}

/* ---------------- boot ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  $("loginBtn").onclick = doLogin;
  $("adminPass").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
  $("logoutBtn").onclick = async () => {
    await api("/api/admin/logout", { method: "POST" }).catch(() => {});
    showLogin();
  };
  $("addItemBtn").onclick = () => openItemModal();
  $("itemCancel").onclick = () => $("itemModal").classList.remove("open");
  $("saveItemBtn").onclick = saveItem;
  $("refreshOrders").onclick = () => { loadOrders(); loadStats(); };
  // If a session is already active, skip the login screen.
  api("/api/admin/stats").then(() => {
    showDashboard(); loadMenuTable(); loadOrders(); loadStats();
  }).catch(() => showLogin());
});
