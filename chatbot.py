"""
chatbot.py -- FoodieAI Restaurant Assistant chatbot engine.

Two operating modes:
  1. AI mode   : if the OPENAI_API_KEY environment variable is set, the bot calls
                 an OpenAI-compatible chat-completions API (uses only stdlib urllib).
  2. Rule mode : a built-in intent engine that works fully offline (the default).

Both modes treat the LIVE menu (passed in from the database) as the single
source of truth. The bot must NEVER invent menu items, prices, availability
or order statuses. Anything it does not know, it says so.
"""

import json
import os
import re
import urllib.request

CATEGORIES = ["Pizza", "Burger", "Indian", "Chinese", "Beverages", "Desserts"]

TIMINGS_TEXT = (
    "Hum roz khule rehte hain! 🕐\n"
    "• Monday – Sunday: 11:00 AM to 11:00 PM\n"
    "• Kitchen last order: 10:30 PM"
)
DELIVERY_TEXT = (
    "Delivery ki jaankari 🚚\n"
    "• Free delivery on orders above ₹499 (within 5 km)\n"
    "• Delivery charge ₹40 for smaller orders\n"
    "• Average delivery time: 30–45 minutes"
)
CANCEL_TEXT = (
    "Cancellation policy ❌\n"
    "• Order cancel kar sakte hain jab tak status 'Preparing' na ho jaye.\n"
    "• 'Out for Delivery' ke baad cancellation possible nahi hai.\n"
    "• Cancel karne ke liye humein order code ke saath message karein."
)
PAYMENT_TEXT = (
    "Payment ke baare mein 💳\n"
    "• Ye college demo project hai, isliye payment MOCK hai — koi real paisa nahi katega.\n"
    "• Hum real card details kabhi store nahi karte."
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _norm(text):
    """Lowercase + strip everything except letters, digits and spaces."""
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


def _tokens(text):
    return [t for t in _norm(text).split() if t]


def find_items(menu, query, limit=5, only_available=True):
    """Fuzzy-find menu items by token overlap. Returns best matches first."""
    q_tokens = set(_tokens(query))
    if not q_tokens:
        return []
    scored = []
    for item in menu:
        if only_available and not item.get("is_available"):
            continue
        name_tokens = set(_tokens(item["name"]))
        overlap = len(q_tokens & name_tokens)
        # bonus if every query token appears in the name
        bonus = 2 if q_tokens <= name_tokens else 0
        if overlap:
            scored.append((overlap + bonus, item))
    scored.sort(key=lambda s: (-s[0], s[1]["name"]))
    return [item for _, item in scored[:limit]]


def format_item(item):
    veg = "🟢 Veg" if item.get("is_veg") else "🔴 Non-veg"
    avail = "" if item.get("is_available", 1) else " (currently unavailable)"
    return (
        f"{item.get('image', '🍽️')} *{item['name']}* — ₹{item['price']:.0f}{avail}\n"
        f"   {item.get('description', '')} | ⭐ {item.get('rating', 4.0)} | {veg}"
    )


def format_list(items, header):
    lines = [header]
    for it in items:
        lines.append("• " + format_item(it).replace("\n", "\n  "))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Rule-based engine (offline fallback -- always available)
# --------------------------------------------------------------------------

def rule_based_reply(message, menu, find_order=None):
    """Return dict(reply=str, actions=list, mode='rule')."""
    msg = (message or "").strip()
    low = msg.lower()
    actions = []

    def reply(text, acts=None):
        return {"reply": text, "actions": acts or [], "mode": "rule"}

    # ---- 1. Order status lookup: "track FA-20261013-0001" ------------------
    code_match = re.search(r"FA-\d{8}-\d{4}", msg.upper())
    if code_match or re.search(r"\b(track|status).*(order|mere)", low):
        if code_match and find_order:
            order = find_order(code_match.group(0))
            if order:
                items = ", ".join(
                    f"{it['item_name']} x{it['quantity']}" for it in order["items"]
                )
                return reply(
                    f"Order *{order['order_code']}* ka status: *{order['status']}* 📦\n"
                    f"Items: {items}\nTotal paid (mock): ₹{order['total']:.2f}\n"
                    "Status website ke 'Track Order' section mein bhi live dikhta hai."
                )
            return reply(
                f"Hmm, *{code_match.group(0)}* naam ka order nahi mila. "
                "Order code dobara check karein — ye checkout ke baad milta hai, "
                "jaise FA-20261013-0001."
            )
        return reply(
            "Apna order track karne ke liye order code bhejein, jaise: "
            "`track FA-20261013-0001` 🙂"
        )

    # ---- 2. Greetings -------------------------------------------------------
    if re.match(r"^(hi+|hello+|hey+|namaste|namaskar|yo|good (morning|evening|afternoon))\b", low):
        return reply(
            "Namaste! 🙏 Main FoodieAI hoon — aapka restaurant assistant.\n"
            "Main menu dikha sakta hoon, budget ke hisaab se recommend kar sakta hoon, "
            "aur order karne mein help kar sakta hoon.\n"
            "Try karein: 'under 200 mein kya hai?' ya 'veg pizza dikhao'"
        )

    # ---- 3. Thanks / bye ----------------------------------------------------
    if re.search(r"\b(thank|thanks|shukriya|dhanyava?d)\b", low):
        return reply("Koi baat nahi! 😊 Kuch aur chahiye to bas bataiye.")
    if re.search(r"\b(bye|alvida|see you)\b", low):
        return reply("Alvida! 👋 Phir zaroor aaiye — FoodieAI Restaurant!")

    # ---- 4. Add to cart (needs confirmation -- frontend asks the user) -------
    add_match = re.match(
        r"(?:please\s+|pls\s+)?add\s+(?:(\d{1,2})\s*[x×]?\s*)?(.+?)(?:\s+to\s+cart)?$", low
    )
    if add_match or re.search(r"\border\s+(?:(\d{1,2})\s+)?(.+)", low):
        m = add_match or re.search(r"\border\s+(?:(\d{1,2})\s+)?(.+)", low)
        qty = int(m.group(1)) if m.group(1) else 1
        qty = max(1, min(qty, 20))
        query = re.sub(r"\b(please|pls|to cart|cart me|mein)\b", "", m.group(2)).strip()
        matches = find_items(menu, query, limit=3)
        # Confident match: the top hit contains every query token
        # (e.g. "margherita pizza" -> "Margherita Pizza").
        confident = (matches and
                     set(_tokens(query)) <= set(_tokens(matches[0]["name"])))
        if confident or len(matches) == 1:
            item = matches[0]
            actions.append({
                "type": "add_to_cart",
                "item_id": item["id"],
                "item_name": item["name"],
                "qty": qty,
                "price": item["price"],
            })
            return reply(
                f"Bilkul! {qty} x *{item['name']}* (₹{item['price']:.0f} each) "
                f"= ₹{item['price'] * qty:.0f} 🛒\n"
                "Confirm karein — 'Yes' dabayein aur main cart mein add kar dunga.",
                actions,
            )
        if len(matches) > 1:
            names = "\n".join(f"• {it['name']} — ₹{it['price']:.0f}" for it in matches)
            return reply(
                f"'{query}' se milte-julte {len(matches)} items mile:\n{names}\n"
                "Kaunsa wala add karun? Exact naam likhkar bhejein 🙂"
            )
        return reply(
            f"Maaf kijiye, '{query}' naam ka koi item menu mein nahi hai. "
            "Main menu se bahar ki cheezein invent nahi karta 🙂\n"
            "'menu dikhao' likhein poori list dekhne ke liye."
        )

    # ---- 5. Budget recommendations: "under 200" -----------------------------
    budget_match = re.search(
        r"(?:under|below|less than|within|budget|max)[^\d]{0,12}(\d{2,5})", low
    ) or re.search(r"(\d{2,5})\s*(?:ke\s+)?(?:under|andar|se kam)", low)
    if budget_match:
        budget = int(budget_match.group(1))
        cheap = [it for it in menu if it["is_available"] and it["price"] <= budget]
        cheap.sort(key=lambda it: (-it.get("rating", 0), it["price"]))
        if not cheap:
            return reply(
                f"₹{budget} ke under koi item available nahi hai. "
                "Budget thoda badha kar try karein 🙂"
            )
        return reply(format_list(
            cheap[:6],
            f"₹{budget} ke under ye best options hain 🌟 (Veg/Non-veg batayein to filter kar dunga):"
        ))

    # ---- 6+7. Category listing, optionally filtered by veg preference ---------
    # Handles "veg pizza dikhao", "non-veg options", "chinese", "desserts", ...
    cat_found = None
    for cat in CATEGORIES:
        if cat.lower() in low or (cat == "Beverages" and "drink" in low):
            cat_found = cat
            break
    if re.search(r"\b(sweets?|meetha|desserts?)\b", low):
        cat_found = "Desserts"
    veg_pref = None
    if re.search(r"non[\s-]?veg|nonveg", low):
        veg_pref = False
    elif re.search(r"\bveg\b|vegetarian|shakahari", low):
        veg_pref = True

    if cat_found or veg_pref is not None:
        items = [it for it in menu
                 if it["is_available"]
                 and (cat_found is None or it["category"] == cat_found)
                 and (veg_pref is None or bool(it["is_veg"]) == veg_pref)]
        if items:
            label = cat_found or ("Veg" if veg_pref else "Non-veg")
            icon = "🟢" if veg_pref else ("🔴" if veg_pref is False else "🍽️")
            return reply(format_list(
                items[:10], f"{icon} *{label}* mein ye options hain:"))
        return reply("Is combination mein koi item available nahi hai 😕 — "
                     "kuch aur try karein.")

    # ---- 8. Price of a specific item -----------------------------------------
    price_match = re.search(r"(?:price|cost|rate|daam)[^\w]*of\s+(.+)", low)
    if price_match:
        matches = find_items(menu, price_match.group(1), limit=1)
        if matches:
            it = matches[0]
            return reply(f"*{it['name']}* ki price hai ₹{it['price']:.0f} "
                         f"({'available ✅' if it['is_available'] else 'abhi unavailable ❌'}).")
        return reply("Ye item menu mein nahi mila. 'menu dikhao' likhein 🙂")

    # ---- 9. Recommendations ---------------------------------------------------
    if re.search(r"\b(recommend|suggest|best|popular|famous|tasty|special|acha|badhiya|kya khaun)\b", low):
        top = sorted(
            [it for it in menu if it["is_available"]],
            key=lambda it: -it.get("rating", 0)
        )[:5]
        return reply(format_list(
            top,
            "Hamare sabse popular dishes 🌟 (rating ke hisaab se):\n"
            "Veg chahiye ya non-veg? Batayein to aur precise suggest karunga."
        ))

    # ---- 10. Full menu ---------------------------------------------------------
    if re.search(r"\b(menu|menue)\b|kya kya hai|what.*(have|offer|serve|available)", low):
        lines = ["*FoodieAI Restaurant — Full Menu* 📋"]
        for cat in CATEGORIES:
            items = [it for it in menu
                     if it["is_available"] and it["category"] == cat]
            if items:
                lines.append(f"\n*{cat}:*")
                for it in items:
                    veg = "🟢" if it["is_veg"] else "🔴"
                    lines.append(f"  {veg} {it['name']} — ₹{it['price']:.0f}")
        lines.append("\nKisi item ka detail chahiye to naam likhein, "
                     "jaise 'Margherita Pizza'.")
        return reply("\n".join(lines))

    # ---- 11. Item detail: "tell me about X" ------------------------------------
    detail_match = re.search(r"(?:about|detail).*?(.+)|^(.+?)\s+(kya hai|hai kya)$", low)
    if detail_match:
        query = (detail_match.group(1) or detail_match.group(2) or "").strip()
        matches = find_items(menu, query, limit=1)
        if matches and len(_tokens(query)) >= 1 and _norm(query) not in ("kya", "hai", ""):
            return reply(format_item(matches[0]))

    # ---- 12. Info: timings / delivery / cancel / payment / location ------------
    if re.search(r"\b(open|close|timings?|hours|kab|baje)\b|\btime\b", low):
        return reply(TIMINGS_TEXT)
    if re.search(r"\bdeliver", low):
        return reply(DELIVERY_TEXT)
    if re.search(r"\bcancel", low):
        return reply(CANCEL_TEXT)
    if re.search(r"\b(pay|payment|upi|cash|card|paisa)\b", low):
        return reply(PAYMENT_TEXT)
    if re.search(r"\b(where|location|address|kahan|pata)\b", low):
        return reply("📍 FoodieAI Restaurant, MG Road, Sector 12 — "
                     "dine-in, takeaway aur delivery teeno available hain!")

    # ---- 13. Help / fallback ----------------------------------------------------
    if re.search(r"\bhelp\b|madad", low):
        return reply(
            "Main ye sab kar sakta hoon 🤖:\n"
            "• 'menu dikhao' — poora menu\n"
            "• 'under 200 mein kya hai?' — budget recommendations\n"
            "• 'veg pizza' / 'non-veg options'\n"
            "• 'add 2 Margherita Pizza' — cart mein add (confirm karke)\n"
            "• 'track FA-20261013-0001' — order status\n"
            "• timings, delivery, cancellation ki jaankari"
        )

    return reply(
        "Samajh nahi aaya 🤔 — main menu, recommendations, cart aur order "
        "status mein help kar sakta hoon.\n"
        "'help' likhein saare options dekhne ke liye, ya 'menu dikhao' likhein."
    )


# --------------------------------------------------------------------------
# AI mode (OpenAI-compatible API) with rule-based fallback
# --------------------------------------------------------------------------

def _call_ai_api(messages):
    """POST to an OpenAI-compatible /chat/completions endpoint (stdlib only)."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    base_url = os.environ.get("OPENAI_BASE_URL",
                              "https://api.openai.com/v1").rstrip("/")
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 600,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def ai_reply(message, menu, history=None):
    menu_json = json.dumps([
        {"id": it["id"], "name": it["name"], "category": it["category"],
         "description": it.get("description", ""), "price": it["price"],
         "rating": it.get("rating", 4.0), "is_veg": bool(it.get("is_veg")),
         "is_available": bool(it.get("is_available", 1))}
        for it in menu
    ], ensure_ascii=False)
    system = (
        "You are 'FoodieAI', the friendly chatbot of FoodieAI Restaurant "
        "(open 11 AM - 11 PM daily; free delivery above Rs.499 within 5 km, "
        "else Rs.40; 30-45 min delivery). Reply in SIMPLE English with light "
        "Hinglish flavour (e.g. 'Bilkul!', 'Zaroor'). Keep replies short.\n"
        "STRICT RULES:\n"
        "1. Recommend ONLY dishes from MENU_JSON below. NEVER invent menu items, "
        "prices, availability or order statuses. If unsure, say you don't know.\n"
        "2. When the user wants to add a dish to the cart: name the EXACT item, "
        "quantity and total price, ask for confirmation, then append ONE action "
        "block on its own line exactly like:\n"
        "```action\n{\"action\":\"add_to_cart\",\"item_id\":<id from MENU_JSON>,"
        "\"qty\":<number>}\n```\n"
        "Only for items with is_available=true.\n"
        "3. For budget questions, filter MENU_JSON by price.\n"
        "4. You CANNOT check or change order status, payments or delivery -- "
        "for those, ask for the order code and point to the Track Order section.\n"
        f"MENU_JSON: {menu_json}"
    )
    messages = [{"role": "system", "content": system}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:500]})
    messages.append({"role": "user", "content": message})

    raw = _call_ai_api(messages)

    # Extract optional ```action {...}``` block and validate it against the menu.
    actions = []
    m = re.search(r"```action\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            act = json.loads(m.group(1))
            if act.get("action") == "add_to_cart":
                item = next((it for it in menu
                             if it["id"] == int(act.get("item_id", -1))), None)
                qty = max(1, min(int(act.get("qty", 1)), 20))
                if item and item.get("is_available"):
                    actions.append({"type": "add_to_cart",
                                    "item_id": item["id"],
                                    "item_name": item["name"],
                                    "qty": qty, "price": item["price"]})
                raw = raw[:m.start()].rstrip()
        except (ValueError, KeyError, TypeError):
            pass
    return {"reply": raw.strip(), "actions": actions, "mode": "ai"}


def get_chat_reply(message, menu, history=None, find_order=None):
    """Main entry point used by app.py. Falls back to rules on any AI failure."""
    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            return ai_reply(message, menu, history)
        except Exception as exc:  # noqa: BLE001 - any AI failure -> offline mode
            print(f"[chatbot] AI API failed ({exc}); using rule-based fallback.")
    return rule_based_reply(message, menu, find_order)
