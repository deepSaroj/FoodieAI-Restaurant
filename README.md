# 🍽️ FoodieAI Restaurant — AI-Powered Restaurant Assistant

A B.Tech Computer Science mini project: a full-stack restaurant web app with an
AI chatbot, cart & ordering, order tracking, and an admin dashboard.
**Stack:** HTML5 + CSS3 + JavaScript (frontend), Python **Flask** (backend),
**SQLite** (database), optional OpenAI-compatible API for the chatbot with a
built-in **rule-based fallback** that works fully offline.

> 💳 Payments are **mocked for the college demo** — no real money moves and no
> card details are ever asked for or stored.

---

## 1. Project Structure

```
foodieai-restaurant/
├── app.py                 # Flask backend: routes, validation, DB, admin auth
├── chatbot.py             # Chatbot engine (AI mode + offline rule-based mode)
├── requirements.txt       # Python dependencies
├── .env.example           # Copy to .env and fill in secrets
├── README.md              # This file
├── database.db            # Created automatically on first run
└── templates/
│   ├── index.html         # Customer site: menu, cart, chat, tracking
│   └── admin.html         # Admin login + dashboard
└── static/
    ├── css/style.css      # Restaurant theme (light + dark mode, responsive)
    └── js/
        ├── script.js      # Menu, cart, checkout, tracking, chatbot UI
        └── admin.js       # Admin dashboard logic
```

## 2. Setup & Run (step by step)

```bash
# 1. Go to the project folder
cd foodieai-restaurant

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) configure secrets / AI key
cp .env.example .env            # then edit .env in any text editor

# 5. Run the app (creates database.db and seeds menu + admin on first run)
python app.py
```

Open **http://127.0.0.1:5000** in your browser.
Admin panel: **http://127.0.0.1:5000/admin** — default login `admin / admin123`
(change it after first login; better: set `ADMIN_USERNAME`/`ADMIN_PASSWORD` in `.env`
*before* the first run).

### Enable AI mode (optional)
1. Get an API key from an OpenAI-compatible provider.
2. In `.env` set `OPENAI_API_KEY=sk-...` (and optionally `OPENAI_MODEL`, `OPENAI_BASE_URL`).
3. Restart `python app.py`. The chat header shows "AI mode ✨".
4. Without a key, the chatbot runs 100% offline in rule-based mode.

## 3. Sample Menu Data
Seeded automatically into SQLite on first run — 23 items across
Pizza, Burger, Indian, Chinese, Beverages, Desserts, each with description,
price (₹), rating, veg/non-veg flag, availability and an icon. Edit freely from
the admin panel.

## 4. API Endpoints

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/` | – | Customer homepage |
| GET | `/admin` | – | Admin panel page |
| GET | `/api/menu?category=&search=&veg=` | – | Menu list (available items, filterable) |
| POST | `/api/chat` | – | Chatbot: `{message, history?}` → `{reply, actions, mode}` |
| POST | `/api/orders` | – | Place order (server computes totals) → `{order_code, …}` |
| GET | `/api/orders/<code>` | – | Track order status by code |
| POST | `/api/admin/login` | – | Admin login (sets session) |
| POST | `/api/admin/logout` | admin | Admin logout |
| GET | `/api/admin/menu` | admin | All menu items (incl. unavailable) |
| POST | `/api/admin/menu` | admin | Add menu item |
| PUT | `/api/admin/menu/<id>` | admin | Edit item (price, availability…) |
| DELETE | `/api/admin/menu/<id>` | admin | Delete item |
| GET | `/api/admin/orders` | admin | All orders with line items |
| PUT | `/api/admin/orders/<id>/status` | admin | Update status |
| GET | `/api/admin/stats` | admin | Revenue, order counts, top items |

Try them with curl, e.g.:
```bash
curl http://127.0.0.1:5000/api/menu?category=Pizza
curl -X POST http://127.0.0.1:5000/api/chat -H "Content-Type: application/json" \
     -d '{"message":"under 200 mein kya hai?"}'
```

## 5. Testing Instructions & Sample Test Cases

### A. Automated smoke test (run while the server is up)
```bash
# 1. Menu loads
curl -s http://127.0.0.1:5000/api/menu | head -c 200
# 2. Chatbot answers
curl -s -X POST http://127.0.0.1:5000/api/chat -H "Content-Type: application/json" \
  -d '{"message":"veg pizza dikhao"}'
# 3. Place an order (replace IDs from /api/menu)
curl -s -X POST http://127.0.0.1:5000/api/orders -H "Content-Type: application/json" \
  -d '{"customer_name":"Test User","phone":"9876543210","address":"MG Road","items":[{"id":1,"qty":2}]}'
# 4. Track it (use the returned order_code)
curl -s http://127.0.0.1:5000/api/orders/FA-<date>-0001
```

### B. Manual test-case table (for your report)

| # | Test case | Steps | Expected result |
|---|---|---|---|
| 1 | Menu loads | Open `/` | 23 items render with images, prices, ratings |
| 2 | Search | Type "biryani" | Only biryani items shown |
| 3 | Category filter | Click "Chinese" chip | Only Chinese items shown |
| 4 | Veg toggle | Enable "Veg only" | No non-veg items shown |
| 5 | Add to cart | Click Add + on 2 items | Cart badge = 2, drawer lists items |
| 6 | Quantity +/- | Increase, decrease to 0 | Quantity updates; item removed at 0 |
| 7 | Checkout validation | Submit empty name / bad phone | Inline error, order NOT placed |
| 8 | Place order | Valid details → Place Order | Success modal with real `FA-…` code |
| 9 | Order in DB | Check admin → Orders | New order appears with correct totals |
| 10 | Track order | Enter code in Track section | Timeline shows current status |
| 11 | Chatbot budget | "under 200 mein kya hai?" | Lists items ≤ ₹200, none invented |
| 12 | Chatbot add flow | "add 2 margherita pizza" | Asks for confirmation first; adds only on Yes |
| 13 | Chatbot unknown item | "add 1 sushi" | Politely says it's not on the menu |
| 14 | Chatbot order status | "track FA-…-0001" | Returns the REAL status from DB |
| 15 | Admin auth | Wrong password | 401, stays on login |
| 16 | Admin menu CRUD | Add/edit/toggle/delete item | Customer menu reflects change |
| 17 | Admin status update | Change order → "Preparing" | Track page shows Preparing |
| 18 | Fake price tampering | POST order with edited price | Server recomputes; total stays correct |
| 19 | SQL injection attempt | Name = `' OR '1'='1` | Stored as plain text, DB safe |
| 20 | Offline chatbot | No `OPENAI_API_KEY` | All chat features still work (rule mode) |

## 6. Security Notes
- Admin passwords hashed with Werkzeug (scrypt); admin routes need a session.
- All SQL uses **parameterized queries** — no string formatting into SQL.
- API keys live in environment variables / `.env`, never in frontend JS.
- Order totals are computed on the **server**; client totals are ignored.
- Inputs validated on the server (name/phone/address lengths, qty 1–20, price ≥ 0, rating 0–5, status whitelist).
- No payment-card data is collected or stored (mock payment only).

## 7. Future Enhancements
- Real payment gateway (Razorpay/Stripe) in test mode
- Table reservation module & live order tracking with WebSockets
- Image uploads for menu items; customer reviews & ratings
- Multilingual chatbot (Hindi) and voice input
- JWT-based admin auth + role-based staff accounts
- Docker container + deployment guide
