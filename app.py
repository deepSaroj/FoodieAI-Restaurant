#!/usr/bin/env python3
"""
FoodieAI Restaurant -- AI-Powered Restaurant Assistant
B.Tech Computer Science mini project (Flask + SQLite + rule/AI chatbot).

Run locally:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000   (admin panel: /admin)
"""

import os
import re
import sqlite3
from datetime import date
from functools import wraps

from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from chatbot import get_chat_reply

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

TAX_RATE = 0.05  # 5% GST
CATEGORIES = ["Pizza", "Burger", "Indian", "Chinese", "Beverages", "Desserts"]
STATUSES = ["Pending", "Confirmed", "Preparing", "Out for Delivery",
            "Delivered", "Cancelled"]

app = Flask(__name__)
# In production set a strong SECRET_KEY env var; the default is for demo only.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-key-change-me")

# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS menu_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    category     TEXT NOT NULL,
    description  TEXT DEFAULT '',
    price        REAL NOT NULL CHECK (price >= 0),
    rating       REAL DEFAULT 4.0 CHECK (rating BETWEEN 0 AND 5),
    is_veg       INTEGER NOT NULL DEFAULT 1 CHECK (is_veg IN (0, 1)),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    image        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS admins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code    TEXT NOT NULL UNIQUE,          -- e.g. FA-20261013-0001
    customer_name TEXT NOT NULL,
    phone         TEXT NOT NULL,
    address       TEXT NOT NULL,
    subtotal      REAL NOT NULL,
    tax           REAL NOT NULL,
    total         REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'Pending',
    payment_mode  TEXT NOT NULL DEFAULT 'Mock (Demo)',
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
    item_name    TEXT NOT NULL,   -- snapshot of the name at order time
    unit_price   REAL NOT NULL,   -- snapshot of the price at order time
    quantity     INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20)
);
"""

# (name, category, description, price, rating, is_veg, is_available, image)
SEED_ITEMS = [
    ("Margherita Pizza", "Pizza", "Classic cheese pizza with fresh basil and tomato sauce", 199, 4.5, 1, 1, "🍕"),
    ("Farmhouse Veggie Pizza", "Pizza", "Loaded garden veggies, mozzarella and herbs", 249, 4.6, 1, 1, "🍕"),
    ("Paneer Tikka Pizza", "Pizza", "Smoky paneer tikka cubes on a cheesy base", 279, 4.7, 1, 1, "🍕"),
    ("Chicken Pepperoni Pizza", "Pizza", "Spicy chicken pepperoni with extra cheese", 349, 4.8, 0, 1, "🍕"),
    ("Classic Veg Burger", "Burger", "Crispy veg patty, lettuce, tomato and mayo", 99, 4.2, 1, 1, "🍔"),
    ("Cheese Burst Burger", "Burger", "Double cheese slice with crunchy patty", 149, 4.4, 1, 1, "🍔"),
    ("Paneer Crunch Burger", "Burger", "Crunchy paneer patty with mint mayo", 179, 4.5, 1, 1, "🍔"),
    ("Chicken Zinger Burger", "Burger", "Crispy fried chicken fillet with spicy mayo", 199, 4.6, 0, 1, "🍔"),
    ("Paneer Butter Masala", "Indian", "Creamy tomato gravy with soft paneer cubes", 229, 4.7, 1, 1, "🍛"),
    ("Dal Makhani", "Indian", "Slow-cooked black lentils with butter and cream", 189, 4.6, 1, 1, "🍛"),
    ("Veg Biryani", "Indian", "Fragrant basmati rice with mixed veggies and raita", 199, 4.4, 1, 1, "🍚"),
    ("Chicken Biryani", "Indian", "Hyderabadi dum biryani with mirchi ka salan", 249, 4.8, 0, 1, "🍚"),
    ("Masala Dosa", "Indian", "Crisp dosa with spiced potato filling, sambar and chutney", 129, 4.5, 1, 1, "🥞"),
    ("Veg Hakka Noodles", "Chinese", "Wok-tossed noodles with crunchy vegetables", 149, 4.3, 1, 1, "🍜"),
    ("Veg Fried Rice", "Chinese", "Smoky street-style fried rice with spring onion", 139, 4.2, 1, 1, "🍜"),
    ("Chilli Paneer", "Chinese", "Indo-Chinese tossed paneer with peppers", 219, 4.5, 1, 1, "🍲"),
    ("Chicken Hakka Noodles", "Chinese", "Noodles tossed with juicy chicken strips", 189, 4.4, 0, 1, "🍜"),
    ("Cold Coffee", "Beverages", "Thick blended cold coffee with ice cream", 99, 4.5, 1, 1, "🥤"),
    ("Mango Lassi", "Beverages", "Fresh mango pulp churned with creamy curd", 89, 4.6, 1, 1, "🥭"),
    ("Fresh Lime Soda", "Beverages", "Sweet-salted fizzy lime cooler", 69, 4.1, 1, 1, "🍋"),
    ("Gulab Jamun (4 pc)", "Desserts", "Soft khoya dumplings soaked in rose syrup", 79, 4.7, 1, 1, "🍨"),
    ("Chocolate Brownie", "Desserts", "Warm fudgy brownie with chocolate sauce", 129, 4.6, 1, 1, "🍫"),
    ("Ice Cream Sundae", "Desserts", "Triple scoop sundae with nuts and wafer", 119, 4.4, 1, 1, "🍨"),
]


def get_db():
    """One SQLite connection per request (stored on Flask's `g`)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row  # rows behave like dicts
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables, seed the menu and the default admin (first run only)."""
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO menu_items (name, category, description, price, rating,"
            " is_veg, is_available, image) VALUES (?,?,?,?,?,?,?,?)",
            SEED_ITEMS,
        )
        print(f"[init] seeded {len(SEED_ITEMS)} menu items")
    if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        db.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        print(f"[init] default admin -> username='{username}' password='{password}'")
        print("[init] IMPORTANT: change the admin password after first login!")
    db.commit()
    db.close()


def menu_list(only_available=False):
    db = get_db()
    q = "SELECT * FROM menu_items"
    if only_available:
        q += " WHERE is_available = 1"
    q += " ORDER BY category, name"
    return [dict(r) for r in db.execute(q).fetchall()]


def find_order_by_code(code):
    db = get_db()
    row = db.execute("SELECT * FROM orders WHERE order_code = ?",
                     (code,)).fetchone()
    if not row:
        return None
    order = dict(row)
    order["items"] = [dict(r) for r in db.execute(
        "SELECT item_name, unit_price, quantity FROM order_items WHERE order_id = ?",
        (order["id"],)).fetchall()]
    return order


# --------------------------------------------------------------------------
# Input validation helpers
# --------------------------------------------------------------------------
def clean_phone(raw):
    """Return a 10-digit Indian mobile number, or None if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify({"error": "Admin login required"}), 401
        return view(*args, **kwargs)
    return wrapper


# --------------------------------------------------------------------------
# Customer pages
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


# --------------------------------------------------------------------------
# Public API -- menu & chatbot
# --------------------------------------------------------------------------
@app.route("/api/menu")
def api_menu():
    """GET /api/menu?category=Pizza&search=pan&veg=1 -- customer menu."""
    category = (request.args.get("category") or "").strip()
    search = (request.args.get("search") or "").strip().lower()
    veg = request.args.get("veg")

    items = menu_list(only_available=True)
    if category and category in CATEGORIES:
        items = [i for i in items if i["category"] == category]
    if search:
        items = [i for i in items
                 if search in i["name"].lower()
                 or search in (i["description"] or "").lower()]
    if veg == "1":
        items = [i for i in items if i["is_veg"]]
    elif veg == "0":
        items = [i for i in items if not i["is_veg"]]
    return jsonify({"items": items})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """POST /api/chat  {message, history?} -> {reply, actions, mode}."""
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message is required"}), 400
    if len(message) > 500:
        return jsonify({"error": "Message too long (max 500 characters)"}), 400
    history = data.get("history") or []
    if not isinstance(history, list):
        history = []

    result = get_chat_reply(
        message,
        menu_list(only_available=False),  # bot knows sold-out items too
        history=history[-6:],
        find_order=find_order_by_code,
    )
    return jsonify(result)


# --------------------------------------------------------------------------
# Public API -- ordering
# --------------------------------------------------------------------------
def make_order_code(db):
    """Unique daily code like FA-20261013-0001 (server-generated)."""
    today = date.today().strftime("%Y%m%d")
    for _ in range(10):
        n = db.execute(
            "SELECT COUNT(*) FROM orders WHERE order_code LIKE ?",
            (f"FA-{today}-%",)).fetchone()[0] + 1
        code = f"FA-{today}-{n:04d}"
        exists = db.execute(
            "SELECT 1 FROM orders WHERE order_code = ?", (code,)).fetchone()
        if not exists:
            return code
    # Extremely unlikely fallback:
    import random
    return f"FA-{today}-{random.randint(1000, 9999):04d}"


@app.route("/api/orders", methods=["POST"])
def api_create_order():
    """Place an order. Totals are ALWAYS computed on the server."""
    data = request.get_json(force=True, silent=True) or {}

    name = (data.get("customer_name") or "").strip()
    phone = clean_phone(data.get("phone"))
    address = (data.get("address") or "").strip()
    items = data.get("items")

    if not (2 <= len(name) <= 60):
        return jsonify({"error": "Please enter your name (2-60 characters)"}), 400
    if not phone:
        return jsonify({"error": "Please enter a valid 10-digit mobile number"}), 400
    if not (5 <= len(address) <= 300):
        return jsonify({"error": "Please enter a delivery address"}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Your cart is empty"}), 400
    if len(items) > 30:
        return jsonify({"error": "Too many distinct items (max 30)"}), 400

    # Validate every item against the DB; ignore any client-side prices.
    db = get_db()
    lines = []
    for entry in items:
        try:
            item_id = int(entry.get("id"))
            qty = int(entry.get("qty"))
        except (TypeError, ValueError, AttributeError):
            return jsonify({"error": "Invalid cart item format"}), 400
        if not 1 <= qty <= 20:
            return jsonify({"error": "Quantity must be between 1 and 20"}), 400
        row = db.execute(
            "SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return jsonify({"error": f"Menu item #{item_id} does not exist"}), 400
        if not row["is_available"]:
            return jsonify(
                {"error": f"'{row['name']}' is currently unavailable"}), 400
        lines.append((dict(row), qty))

    subtotal = round(sum(it["price"] * qty for it, qty in lines), 2)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)

    code = make_order_code(db)
    cur = db.execute(
        "INSERT INTO orders (order_code, customer_name, phone, address,"
        " subtotal, tax, total, status, payment_mode)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (code, name, phone, address, subtotal, tax, total,
         "Pending", "Mock (Demo)"),
    )
    order_id = cur.lastrowid
    db.executemany(
        "INSERT INTO order_items (order_id, menu_item_id, item_name, unit_price,"
        " quantity) VALUES (?,?,?,?,?)",
        [(order_id, it["id"], it["name"], it["price"], qty)
         for it, qty in lines],
    )
    db.commit()

    return jsonify({
        "order_code": code,
        "status": "Pending",
        "customer_name": name,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "items": [{"name": it["name"], "qty": qty, "price": it["price"]}
                  for it, qty in lines],
    }), 201


@app.route("/api/orders/<code>")
def api_track_order(code):
    """Public order-status lookup by order code."""
    code = (code or "").strip().upper()
    if not re.fullmatch(r"FA-\d{8}-\d{4}", code):
        return jsonify({"error": "Invalid order code format"}), 404
    order = find_order_by_code(code)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    order.pop("id", None)
    return jsonify(order)


# --------------------------------------------------------------------------
# Admin API (session-protected)
# --------------------------------------------------------------------------
@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    row = get_db().execute(
        "SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        session["admin"] = username
        return jsonify({"ok": True, "username": username})
    return jsonify({"error": "Invalid username or password"}), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.pop("admin", None)
    return jsonify({"ok": True})


@app.route("/api/admin/menu")
@login_required
def api_admin_menu():
    return jsonify({"items": menu_list(only_available=False)})


def _validate_menu_payload(data, partial=False):
    """Return (clean_dict, error). Used by add & edit endpoints."""
    clean = {}
    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not (2 <= len(name) <= 80):
            return None, "Name must be 2-80 characters"
        clean["name"] = name
    if not partial or "category" in data:
        cat = (data.get("category") or "").strip()
        if cat not in CATEGORIES:
            return None, f"Category must be one of: {', '.join(CATEGORIES)}"
        clean["category"] = cat
    if not partial or "price" in data:
        try:
            price = float(data.get("price"))
        except (TypeError, ValueError):
            return None, "Price must be a number"
        if not 0 <= price <= 10000:
            return None, "Price must be between 0 and 10000"
        clean["price"] = round(price, 2)
    if "description" in data:
        clean["description"] = (data.get("description") or "").strip()[:300]
    if "rating" in data:
        try:
            rating = float(data.get("rating"))
        except (TypeError, ValueError):
            return None, "Rating must be a number"
        if not 0 <= rating <= 5:
            return None, "Rating must be between 0 and 5"
        clean["rating"] = rating
    if "is_veg" in data:
        clean["is_veg"] = 1 if data.get("is_veg") in (1, True, "1") else 0
    if "is_available" in data:
        clean["is_available"] = 1 if data.get("is_available") in (1, True, "1") else 0
    if "image" in data:
        clean["image"] = (data.get("image") or "").strip()[:10]
    if partial and not clean:
        return None, "Nothing to update"
    return clean, None


@app.route("/api/admin/menu", methods=["POST"])
@login_required
def api_admin_add_item():
    data = request.get_json(force=True, silent=True) or {}
    clean, err = _validate_menu_payload(data)
    if err:
        return jsonify({"error": err}), 400
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO menu_items (name, category, description, price, rating,"
            " is_veg, is_available, image) VALUES (?,?,?,?,?,?,?,?)",
            (clean["name"], clean["category"], clean.get("description", ""),
             clean["price"], clean.get("rating", 4.0),
             clean.get("is_veg", 1), clean.get("is_available", 1),
             clean.get("image", "🍽️")),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "An item with this name already exists"}), 400
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


@app.route("/api/admin/menu/<int:item_id>", methods=["PUT"])
@login_required
def api_admin_edit_item(item_id):
    data = request.get_json(force=True, silent=True) or {}
    clean, err = _validate_menu_payload(data, partial=True)
    if err:
        return jsonify({"error": err}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM menu_items WHERE id = ?",
                      (item_id,)).fetchone():
        return jsonify({"error": "Item not found"}), 404
    try:
        cols = ", ".join(f"{k} = ?" for k in clean)
        db.execute(f"UPDATE menu_items SET {cols} WHERE id = ?",
                   (*clean.values(), item_id))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "An item with this name already exists"}), 400
    return jsonify({"ok": True})


@app.route("/api/admin/menu/<int:item_id>", methods=["DELETE"])
@login_required
def api_admin_delete_item(item_id):
    db = get_db()
    cur = db.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Item not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/admin/orders")
@login_required
def api_admin_orders():
    db = get_db()
    orders = [dict(r) for r in db.execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT 200").fetchall()]
    for o in orders:
        o["items"] = [dict(r) for r in db.execute(
            "SELECT item_name, unit_price, quantity FROM order_items"
            " WHERE order_id = ?", (o["id"],)).fetchall()]
    return jsonify({"orders": orders})


@app.route("/api/admin/orders/<int:order_id>/status", methods=["PUT"])
@login_required
def api_admin_order_status(order_id):
    data = request.get_json(force=True, silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in STATUSES:
        return jsonify(
            {"error": f"Status must be one of: {', '.join(STATUSES)}"}), 400
    db = get_db()
    cur = db.execute("UPDATE orders SET status = ? WHERE id = ?",
                     (status, order_id))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Order not found"}), 404
    return jsonify({"ok": True, "status": status})


@app.route("/api/admin/stats")
@login_required
def api_admin_stats():
    db = get_db()
    total_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    revenue = db.execute(
        "SELECT COALESCE(SUM(total), 0) FROM orders WHERE status != 'Cancelled'"
    ).fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM orders WHERE status IN"
        " ('Pending','Confirmed','Preparing','Out for Delivery')").fetchone()[0]
    avg_value = db.execute(
        "SELECT COALESCE(AVG(total), 0) FROM orders WHERE status != 'Cancelled'"
    ).fetchone()[0]
    top = [dict(r) for r in db.execute(
        "SELECT item_name AS name, SUM(quantity) AS qty FROM order_items"
        " GROUP BY item_name ORDER BY qty DESC LIMIT 5").fetchall()]
    return jsonify({
        "total_orders": total_orders,
        "revenue": round(revenue, 2),
        "pending_orders": pending,
        "avg_order_value": round(avg_value, 2),
        "top_items": top,
    })


# --------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("\n  🍽️  FoodieAI Restaurant running at http://127.0.0.1:5000")
    print("     Admin panel: http://127.0.0.1:5000/admin\n")
    app.run(debug=True, port=5000)
