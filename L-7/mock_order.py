"""
NOVA Mock Commerce Layer
Handles merchant search, menu, basket, checkout
Uses SQLite as backend — no real APIs needed for demo
Stripe test mode ready for payment
"""

import sqlite3
import uuid
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "nova_commerce.db")

# ── Seed Data ──────────────────────────────────────────────────────────────────
MERCHANTS = [
    {
        "id":       "m001",
        "name":     "Starbucks",
        "area":     "Union Square",
        "category": "coffee",
        "distance": "0.4 miles",
        "eta_drive": "2 min",
        "eta_order": "8 min",
        "rating":   4.6,
        "address":  "123 Union Square, San Francisco, CA",
        "lat":      37.7879,
        "lng":      -122.4075
    },
    {
        "id":       "m002",
        "name":     "Subway",
        "area":     "Market Street",
        "category": "food",
        "distance": "0.8 miles",
        "eta_drive": "4 min",
        "eta_order": "10 min",
        "rating":   4.2,
        "address":  "456 Market Street, San Francisco, CA",
        "lat":      37.7897,
        "lng":      -122.4002
    },
    {
        "id":       "m003",
        "name":     "Blue Bottle Coffee",
        "area":     "SoMa",
        "category": "coffee",
        "distance": "1.2 miles",
        "eta_drive": "6 min",
        "eta_order": "12 min",
        "rating":   4.8,
        "address":  "789 Howard Street, San Francisco, CA",
        "lat":      37.7820,
        "lng":      -122.4001
    },
    {
        "id":       "m004",
        "name":     "Shell",
        "area":     "Highway 101",
        "category": "fuel",
        "distance": "0.3 miles",
        "eta_drive": "1 min",
        "eta_order": "0 min",
        "rating":   4.0,
        "address":  "101 Highway Ave, San Francisco, CA",
        "lat":      37.7750,
        "lng":      -122.4180
    },
    {
        "id":       "m005",
        "name":     "McDonald's",
        "area":     "Financial District",
        "category": "food",
        "distance": "0.6 miles",
        "eta_drive": "3 min",
        "eta_order": "5 min",
        "rating":   4.1,
        "address":  "200 Montgomery St, San Francisco, CA",
        "lat":      37.7915,
        "lng":      -122.4018
    },
    {
        "id":       "m006",
        "name":     "Pizza Hut",
        "area":     "Mission District",
        "category": "food",
        "distance": "1.5 miles",
        "eta_drive": "8 min",
        "eta_order": "20 min",
        "rating":   3.9,
        "address":  "800 Mission St, San Francisco, CA",
        "lat":      37.7816,
        "lng":      -122.4055
    }
]

MENU_ITEMS = [
    # Starbucks
    {"id": "i001", "merchant_id": "m001", "name": "Caramel Frappuccino", "price": 6.50, "category": "cold"},
    {"id": "i002", "merchant_id": "m001", "name": "Caramel Latte",       "price": 5.50, "category": "hot"},
    {"id": "i003", "merchant_id": "m001", "name": "Espresso",            "price": 3.75, "category": "hot"},
    {"id": "i004", "merchant_id": "m001", "name": "Cold Brew",           "price": 5.00, "category": "cold"},

    # Subway
    {"id": "i005", "merchant_id": "m002", "name": "Veggie Delight",      "price": 4.50, "category": "sub"},
    {"id": "i006", "merchant_id": "m002", "name": "Chicken Teriyaki",    "price": 5.50, "category": "sub"},
    {"id": "i007", "merchant_id": "m002", "name": "Footlong BMT",        "price": 7.00, "category": "sub"},

    # Blue Bottle
    {"id": "i008", "merchant_id": "m003", "name": "Single Origin Pour Over", "price": 5.00, "category": "hot"},
    {"id": "i009", "merchant_id": "m003", "name": "Iced Latte",              "price": 4.75, "category": "cold"},

    # Shell
    {"id": "i010", "merchant_id": "m004", "name": "Regular Fuel",   "price": 0.00, "category": "fuel"},
    {"id": "i011", "merchant_id": "m004", "name": "Premium Fuel",   "price": 0.00, "category": "fuel"},
    
    # McDonald's
    {"id": "i012", "merchant_id": "m005", "name": "Big Mac",        "price": 6.99, "category": "burger"},
    {"id": "i013", "merchant_id": "m005", "name": "McChicken",      "price": 5.49, "category": "burger"},
    {"id": "i014", "merchant_id": "m005", "name": "French Fries",   "price": 3.29, "category": "side"},
    
    # Pizza Hut
    {"id": "i015", "merchant_id": "m006", "name": "Pepperoni Pizza", "price": 14.99, "category": "pizza"},
    {"id": "i016", "merchant_id": "m006", "name": "Cheese Pizza",    "price": 12.99, "category": "pizza"},
]


# ── Database Setup ─────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            id TEXT PRIMARY KEY,
            name TEXT,
            area TEXT,
            category TEXT,
            distance TEXT,
            eta_drive TEXT,
            eta_order TEXT,
            rating REAL,
            address TEXT,
            lat REAL,
            lng REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id TEXT PRIMARY KEY,
            merchant_id TEXT,
            name TEXT,
            price REAL,
            category TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS baskets (
            id TEXT PRIMARY KEY,
            merchant_id TEXT,
            created_at REAL,
            status TEXT DEFAULT 'active'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS basket_items (
            id TEXT PRIMARY KEY,
            basket_id TEXT,
            item_id TEXT,
            item_name TEXT,
            price REAL,
            quantity INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            basket_id TEXT,
            merchant_id TEXT,
            merchant_name TEXT,
            total REAL,
            nova_fee REAL,
            status TEXT,
            transaction_id TEXT,
            created_at REAL
        )
    """)

    # Seed merchants
    for m in MERCHANTS:
        c.execute("""
            INSERT OR IGNORE INTO merchants VALUES
            (?,?,?,?,?,?,?,?,?,?,?)
        """, (m["id"], m["name"], m["area"], m["category"],
              m["distance"], m["eta_drive"], m["eta_order"],
              m["rating"], m["address"], m["lat"], m["lng"]))

    # Seed menu items
    for item in MENU_ITEMS:
        c.execute("""
            INSERT OR IGNORE INTO menu_items VALUES (?,?,?,?,?)
        """, (item["id"], item["merchant_id"],
              item["name"], item["price"], item["category"]))

    conn.commit()
    conn.close()
    print("[Commerce] Database initialized with seed data")


# ── Tool Functions (what Layer 7 calls) ───────────────────────────────────────

def search_merchants(query: str) -> dict:
    """
    Find nearby merchants matching query.
    Called when driver says 'find coffee' or 'order from starbucks'
    """
    conn    = sqlite3.connect(DB_PATH)
    c       = conn.cursor()
    query_l = query.lower()

    # Match by name or category
    c.execute("""
        SELECT * FROM merchants
        WHERE LOWER(name) LIKE ? OR LOWER(category) LIKE ?
        ORDER BY rating DESC
        LIMIT 3
    """, (f"%{query_l}%", f"%{query_l}%"))

    rows = c.fetchall()
    conn.close()

    if not rows:
        return {"found": False, "message": f"No merchants found for '{query}'"}

    merchants = []
    for r in rows:
        merchants.append({
            "id":        r[0], "name":      r[1],
            "area":      r[2], "category":  r[3],
            "distance":  r[4], "eta_drive": r[5],
            "eta_order": r[6], "rating":    r[7],
            "address":   r[8], "lat":       r[9],
            "lng":       r[10]
        })

    # Build Nova's spoken response
    if len(merchants) == 1:
        m   = merchants[0]
        msg = (f"Found {m['name']} in {m['area']}, "
               f"{m['distance']} away, rated {m['rating']}. "
               f"Shall I show the menu?")
    else:
        names = ", ".join(
            f"{m['name']} ({m['distance']})" for m in merchants
        )
        msg = f"Found {len(merchants)} options nearby: {names}. Which one?"

    return {"found": True, "merchants": merchants, "nova_says": msg}


def get_menu(merchant_id: str) -> dict:
    """
    Get menu for a specific merchant.
    Called after driver picks a merchant.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,))
    merchant = c.fetchone()

    c.execute("SELECT * FROM menu_items WHERE merchant_id = ?", (merchant_id,))
    items = c.fetchall()
    conn.close()

    if not merchant or not items:
        return {"found": False, "message": "Menu not available"}

    menu = [{"id": i[0], "name": i[2], "price": i[3], "category": i[4]}
            for i in items]

    # Build spoken menu
    spoken = ", ".join(
        f"{item['name']} ${item['price']:.2f}" for item in menu[:4]
    )
    msg = f"{merchant[1]} menu: {spoken}. What would you like?"

    return {"found": True, "merchant_name": merchant[1],
            "menu": menu, "nova_says": msg}


def create_basket(merchant_id: str) -> dict:
    """Create a new basket for an order."""
    conn      = sqlite3.connect(DB_PATH)
    c         = conn.cursor()
    basket_id = f"BKT-{uuid.uuid4().hex[:8].upper()}"

    c.execute("""
        INSERT INTO baskets VALUES (?,?,?,?)
    """, (basket_id, merchant_id, time.time(), "active"))

    conn.commit()
    conn.close()
    return {"basket_id": basket_id}


def add_to_basket(basket_id: str, item_id: str, quantity: int = 1) -> dict:
    """
    Add item to basket.
    Called when driver selects an item from menu.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,))
    item = c.fetchone()

    if not item:
        conn.close()
        return {"success": False, "message": "Item not found"}

    basket_item_id = f"BI-{uuid.uuid4().hex[:6].upper()}"
    c.execute("""
        INSERT INTO basket_items VALUES (?,?,?,?,?,?)
    """, (basket_item_id, basket_id, item_id, item[2], item[3], quantity))

    conn.commit()
    conn.close()

    total_price = item[3] * quantity
    qty_str = f"{quantity}x " if quantity > 1 else ""

    return {
        "success":   True,
        "item_name": item[2],
        "price":     total_price,
        "nova_says": (f"Added {qty_str}{item[2]} — ${total_price:.2f}. "
                      f"Anything else or shall I checkout?")
    }


def remove_from_basket(basket_id: str, item_id: str) -> dict:
    """Remove item from basket."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        DELETE FROM basket_items
        WHERE basket_id = ? AND item_id = ?
    """, (basket_id, item_id))
    conn.commit()
    conn.close()
    return {"success": True, "nova_says": "Removed from your order."}


def checkout(basket_id: str) -> dict:
    """
    Process checkout — calculate total, apply Nova fee.
    Returns order summary for OTP confirmation.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # Get basket
    c.execute("SELECT * FROM baskets WHERE id = ?", (basket_id,))
    basket = c.fetchone()

    if not basket:
        conn.close()
        return {"success": False, "message": "Basket not found"}

    # Get items
    c.execute("""
        SELECT item_name, price, quantity
        FROM basket_items WHERE basket_id = ?
    """, (basket_id,))
    items = c.fetchall()

    # Get merchant
    c.execute("SELECT name, eta_order, address FROM merchants WHERE id = ?",
              (basket[1],))
    merchant = c.fetchone()

    conn.close()

    if not items:
        return {"success": False, "message": "Basket is empty"}

    subtotal  = sum(i[1] * i[2] for i in items)
    nova_fee  = round(subtotal * 0.03, 2)
    total     = round(subtotal + nova_fee, 2)

    item_list = ", ".join(f"{i[0]} x{i[2]}" for i in items)

    return {
        "success":       True,
        "basket_id":     basket_id,
        "merchant_name": merchant[0] if merchant else "merchant",
        "merchant_address": merchant[2] if merchant else "",
        "eta_order":     merchant[1] if merchant else "10 min",
        "items":         item_list,
        "subtotal":      subtotal,
        "nova_fee":      nova_fee,
        "total":         total,
        "nova_says": (
            f"Order summary: {item_list} from {merchant[0]}. "
            f"Total ${total:.2f} including ${nova_fee:.2f} Nova fee. "
            f"Say YES to confirm."
        )
    }


def process_payment(basket_id: str, checkout_data: dict) -> dict:
    """
    Process payment after OTP verified.
    Simulates Stripe test mode — no real money.
    """
    conn           = sqlite3.connect(DB_PATH)
    c              = conn.cursor()
    order_id       = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    transaction_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"

    c.execute("""
        INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        order_id,
        basket_id,
        checkout_data.get("merchant_id", ""),
        checkout_data.get("merchant_name", ""),
        checkout_data.get("total", 0),
        checkout_data.get("nova_fee", 0),
        "CONFIRMED",
        transaction_id,
        time.time()
    ))

    # Mark basket as completed
    c.execute("UPDATE baskets SET status = 'completed' WHERE id = ?",
              (basket_id,))

    conn.commit()
    conn.close()

    return {
        "success":          True,
        "order_id":         order_id,
        "transaction_id":   transaction_id,
        "merchant_name":    checkout_data.get("merchant_name", ""),
        "merchant_address": checkout_data.get("merchant_address", ""),
        "items":            checkout_data.get("items", ""),
        "total":            checkout_data.get("total", 0),
        "nova_fee":         checkout_data.get("nova_fee", 0),
        "eta_order":        checkout_data.get("eta_order", "10 min"),
        "payment_method":   "Nova Pay •••• 4242",
        "nova_says": (
            f"Order confirmed! "
            f"{checkout_data.get('items', 'Your order')} from "
            f"{checkout_data.get('merchant_name', 'the merchant')}. "
            f"${checkout_data.get('total', 0):.2f} charged via Nova Pay. "
            f"Ready in {checkout_data.get('eta_order', '10 min')}. "
            f"Added as next stop on your route."
        )
    }


# ── Initialize on import ───────────────────────────────────────────────────────
init_db()


# ── Quick Test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  NOVA Mock Commerce — Test")
    print("="*50)

    # Search
    print("\n1. Search for coffee:")
    result = search_merchants("coffee")
    print(f"   Nova: {result['nova_says']}")

    # Get menu
    print("\n2. Get Starbucks menu:")
    menu = get_menu("m001")
    print(f"   Nova: {menu['nova_says']}")

    # Create basket and add item
    print("\n3. Create basket and add Frappuccino:")
    basket = create_basket("m001")
    added  = add_to_basket(basket["basket_id"], "i001")
    print(f"   Nova: {added['nova_says']}")

    # Checkout
    print("\n4. Checkout:")
    order = checkout(basket["basket_id"])
    print(f"   Nova: {order['nova_says']}")

    # Payment
    print("\n5. Payment after OTP verified:")
    order["merchant_id"] = "m001"
    payment = process_payment(basket["basket_id"], order)
    print(f"   Nova: {payment['nova_says']}")
    print(f"   TXN:  {payment['transaction_id']}")
    print(f"   Fee:  ${payment['nova_fee']}")