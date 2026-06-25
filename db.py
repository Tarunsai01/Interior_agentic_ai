import sqlite3

DB_PATH = "interior_company_catalog.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def catalog_search(category=None, style_tag=None, max_price_inr=None,
                   room_type=None, include_out_of_stock=False):
    conn = get_db()
    cur = conn.cursor()
    query = "SELECT * FROM catalog WHERE 1=1"
    params = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if style_tag:
        query += " AND style_tags LIKE ?"
        params.append(f"%{style_tag}%")
    if max_price_inr:
        query += " AND price_inr <= ?"
        params.append(max_price_inr)
    if room_type:
        query += " AND room_types LIKE ?"
        params.append(f"%{room_type}%")
    if not include_out_of_stock:
        query += " AND in_stock = 1"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    results = []
    for row in rows:
        item = dict(row)
        if item["price_inr"] is None:
            item["WARNING"] = "PRICE_NULL — cannot include in budget total"
        if item["in_stock"] == 0:
            item["WARNING"] = f"OUT_OF_STOCK — {item['lead_time_days']}d lead time"
        results.append(item)
    return results

def budget_calculator(selected_item_ids, total_budget_inr):
    conn = get_db()
    cur = conn.cursor()
    ph = ",".join(["?" for _ in selected_item_ids])
    cur.execute(
        f"SELECT item_id, name, price_inr FROM catalog WHERE item_id IN ({ph})",
        selected_item_ids
    )
    rows = cur.fetchall()
    conn.close()
    total = 0
    priced, null_items = [], []
    for row in rows:
        if row["price_inr"] is None:
            null_items.append(row["item_id"])
        else:
            total += row["price_inr"]
            priced.append({"item_id": row["item_id"], "name": row["name"], "price_inr": row["price_inr"]})
    return {
        "total_spent_inr": total,
        "budget_inr": total_budget_inr,
        "remaining_inr": total_budget_inr - total,
        "over_budget": total > total_budget_inr,
        "priced_items": priced,
        "null_price_items": null_items,
        "warning": "Budget excludes NULL-price items" if null_items else None
    }

def layout_fit_check(room_length_cm, room_width_cm, selected_item_ids):
    conn = get_db()
    cur = conn.cursor()
    ph = ",".join(["?" for _ in selected_item_ids])
    cur.execute(
        f"SELECT item_id, name, width_cm, depth_cm FROM catalog WHERE item_id IN ({ph})",
        selected_item_ids
    )
    rows = cur.fetchall()
    conn.close()
    room_area = (room_length_cm * room_width_cm) / 10000
    footprint = 0
    issues, checked = [], []
    for row in rows:
        w, d = row["width_cm"], row["depth_cm"]
        if w and d:
            fp = (w * d) / 10000
            footprint += fp
            if w > room_length_cm or w > room_width_cm:
                issues.append(f"{row['item_id']} ({row['name']}) width {w}cm may exceed room dimension")
            checked.append({"item_id": row["item_id"], "name": row["name"], "footprint_sqm": round(fp, 2)})
        else:
            issues.append(f"{row['item_id']} has no dimension data")
    ratio = round(footprint / room_area, 2) if room_area else 1
    return {
        "fits": ratio <= 0.5 and not any("may exceed" in i for i in issues),
        "room_area_sqm": round(room_area, 2),
        "furniture_footprint_sqm": round(footprint, 2),
        "circulation_ratio": ratio,
        "verdict": "OK" if ratio <= 0.5 else "TIGHT — consider smaller or fewer pieces",
        "issues": issues,
        "items_checked": checked
    }