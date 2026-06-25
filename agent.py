import os
import re
import sqlite3
import json
from groq import Groq
from dotenv import load_dotenv
from db import catalog_search, budget_calculator, layout_fit_check

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
DB_PATH = "interior_company_catalog.db"
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are an interior design agent for Interior Company India.
Your job is to help customers find furniture from our catalog using SQL queries.

DATABASE SCHEMA:
Table: catalog
Columns: item_id, category, name, style_tags, price_inr, width_cm, depth_cm, height_cm, color_finish, in_stock, lead_time_days, room_types

EXACT CATEGORY VALUES (use these exactly, case-sensitive):
Sofa, Coffee Table, TV Unit, Rug, Floor Lamp, Armchair, Ottoman, Side Table,
Bookshelf, Console, Curtains, Cushions, Wall Art, Planter, Mirror,
Pendant Light, Table Lamp, Bean Bag, Bed, Bedside Table, Desk,
Dining Chair, Dining Table, Mattress, Office Chair, Wardrobe

STYLE TAGS (use LIKE with wildcards):
Scandinavian, Minimalist, Mid-Century, Industrial, Bohemian, Coastal, Contemporary, Traditional, Japandi

ROOM TYPES (use LIKE with wildcards):
Living Room, Bedroom, Dining, Study, Kids

SQL RULES — follow all of these every time:
- Always filter: in_stock = 1
- Always filter: price_inr IS NOT NULL
- Use LOWER() on both sides for all text comparisons
- When combining AND with OR, always wrap OR conditions in parentheses:
  WHERE LOWER(category) = 'sofa' AND in_stock = 1 AND (LOWER(style_tags) LIKE '%contemporary%' OR LOWER(style_tags) LIKE '%minimalist%')
- Only generate SELECT statements — never INSERT, UPDATE, DELETE, DROP, ALTER

GUARDRAIL — HARD DECLINE for structural/civil/electrical/plumbing questions:
Respond with ONLY this one sentence, nothing more:
"I'm not qualified to advise on structural, civil, electrical, or plumbing matters. Please consult a qualified structural engineer or contractor."
Do NOT add tips, factors, checklists, or any additional information.

OTHER GUARDRAILS:
- Never recommend products not in the catalog
- If asked for designer brands (Togo, Noguchi, Eames, Ligne Roset): decline and offer closest catalog alternatives
- Never promise delivery dates or final negotiated prices
- If budget is impossible: say so honestly and offer the closest realistic option
- Always display prices in Indian Rupees using the ₹ symbol"""

OUT_OF_SCOPE_TRIGGERS = [
    # structural
    "load-bearing", "load bearing", "knock down", "demolish", "structural",
    "is it safe to remove", "can i remove",
    # electrical
    "electrical", "electrician", "wiring", "socket", "sockets", "switches",
    # plumbing
    "plumbing", "pipe", "drain", "move the plumbing",
    # flooring / heating
    "tile the floor", "install floor", "underfloor", "flooring tiles",
    "floor tiles", "heating", "ceiling beam", "roof",
    # paint
    "paint", "paint color", "wall color", "wallpaper",
    # delivery / price promises
    "guarantee delivery", "guarantee", "promise delivery", "lock the price",
    "lock in", "confirm delivery", "promise me",
]

SQL_BLACKLIST = ["insert ", "update ", "delete ", "drop ", "alter ", "create ", "truncate "]

CATEGORY_MAP = {
    "sofa": "Sofa", "3-seater sofa": "Sofa", "2-seater sofa": "Sofa",
    "sectional": "Sofa", "couch": "Sofa", "full living room: sofa": "Sofa",
    "coffee table": "Coffee Table", "center table": "Coffee Table",
    "tv unit": "TV Unit", "tv stand": "TV Unit", "media unit": "TV Unit",
    "rug": "Rug", "carpet": "Rug",
    "lighting": "Floor Lamp", "floor lamp": "Floor Lamp",
    "lamp": "Floor Lamp", "light": "Floor Lamp",
    "armchair": "Armchair", "chair": "Armchair",
    "side table": "Side Table", "end table": "Side Table",
    "bookshelf": "Bookshelf", "bookcase": "Bookshelf",
    "ottoman": "Ottoman", "footstool": "Ottoman",
    "curtains": "Curtains", "drapes": "Curtains",
    "dining table": "Dining Table", "dining chair": "Dining Chair",
    "bed": "Bed", "wardrobe": "Wardrobe", "desk": "Desk",
    "mirror": "Mirror", "planter": "Planter", "wall art": "Wall Art",
    "pendant light": "Pendant Light", "table lamp": "Table Lamp",
    "bean bag": "Bean Bag", "mattress": "Mattress", "office chair": "Office Chair",
    "bedside table": "Bedside Table", "console": "Console", "cushions": "Cushions",
}


def normalize_category(raw: str) -> str:
    return CATEGORY_MAP.get(raw.lower().strip(), raw.strip())


def is_out_of_scope(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(trigger in lowered for trigger in OUT_OF_SCOPE_TRIGGERS)


def extract_sql(text: str):
    match = re.search(r'```(?:sql)?\s*(SELECT.*?)```', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r'(SELECT\s+.+?)(?:;|$)', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def is_safe_sql(sql: str) -> bool:
    lowered = sql.lower()
    return not any(word in lowered for word in SQL_BLACKLIST)


def execute_sql(sql: str):
    if not is_safe_sql(sql):
        return None, "Blocked: unsafe SQL operation detected"
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql)
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows, None
    except Exception as e:
        return None, str(e)


def generate_sql(user_input: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Generate ONLY a SQL SELECT query for this request: {user_input}\n"
                    "Return only the raw SQL — no explanation, no markdown, no preamble."
                )
            }
        ],
        temperature=0
    )
    return response.choices[0].message.content.strip()


def generate_response(user_input: str, results: list) -> str:
    data_str = json.dumps(results, indent=2) if results else "No matching items found in the catalog."
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Customer asked: {user_input}\n\n"
                    f"Catalog results from database:\n{data_str}\n\n"
                    "Write a helpful, friendly response presenting these items. "
                    "Show item name, price in ₹, key dimensions, and a one-line reason to choose it. "
                    "If no results, be honest and suggest they broaden their search. "
                    "Do NOT show the SQL query in your response."
                )
            }
        ],
        temperature=0.7
    )
    return response.choices[0].message.content.strip()


def run_agent(user_input: str) -> str:
    print(f"\n🧠 Thinking... User asked: '{user_input}'")

    if is_out_of_scope(user_input):
        print("🚫 Out-of-scope — guardrail fired at Python layer")
        return (
            "I'm not qualified to advise on structural, civil, electrical, or plumbing matters. "
            "Please consult a qualified structural engineer or contractor."
        )

    raw_sql_response = generate_sql(user_input)
    sql = extract_sql(raw_sql_response) or raw_sql_response
    print(f"⚡ Generated SQL: {sql}")

    results, error = execute_sql(sql)
    if error:
        print(f"❌ SQL Error: {error}")
        return "I encountered an issue searching the catalog. Please try rephrasing your request."

    print(f"📦 Found {len(results)} item(s)")
    response_text = generate_response(user_input, results)
    response_text = response_text.replace("$", "₹")
    return response_text


def design_room(brief_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM room_briefs WHERE brief_id = ?", (brief_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return f"Brief {brief_id} not found in database."

    b = dict(row)
    print(f"\n{'='*60}")
    print(f"DESIGNING FOR {brief_id} | {b['room_type']} | ₹{b['budget_inr']:,} | {b['style_preference']}")
    print(f"Must-haves: {b['must_haves']}")
    print(f"{'='*60}")

    must_haves = [m.strip() for m in b['must_haves'].split(',')]
    selected_ids = []
    selected_items = []

    for item_type in must_haves:
        category = normalize_category(item_type)
        print(f"\n🔧 TOOL: catalog_search(category={category}, style={b['style_preference']})")
        results = catalog_search(
            category=category,
            style_tag=b['style_preference'],
            max_price_inr=int(b['budget_inr'] * 0.4),
            room_type=b['room_type']
        )
        if not results:
            results = catalog_search(category=category, room_type=b['room_type'])
        if results:
            best = results[0]
            selected_ids.append(best['item_id'])
            selected_items.append(best)
            print(f"   ↳ Selected: {best['item_id']} — {best['name']} — ₹{best['price_inr']:,}")
        else:
            print(f"   ↳ No match found for '{category}'")

    print(f"\n🔧 TOOL: budget_calculator({selected_ids}, budget=₹{b['budget_inr']:,})")
    budget_result = budget_calculator(selected_ids, int(b['budget_inr']))
    print(f"   ↳ Total: ₹{budget_result['total_spent_inr']:,} | Remaining: ₹{budget_result['remaining_inr']:,} | Over budget: {budget_result['over_budget']}")

    print(f"\n🔧 TOOL: layout_fit_check({b['length_cm']}x{b['width_cm']}cm, {len(selected_ids)} items)")
    layout_result = layout_fit_check(int(b['length_cm']), int(b['width_cm']), selected_ids)
    print(f"   ↳ Fits: {layout_result['fits']} | Coverage: {layout_result['circulation_ratio']} | {layout_result['verdict']}")

    context = f"""
Brief: {b['room_type']}, {b['length_cm']}x{b['width_cm']}cm, ₹{b['budget_inr']:,}, {b['style_preference']} style
Must-haves: {b['must_haves']}
Customer note: {b['customer_note']}

Tool results:
Selected items: {json.dumps(selected_items, indent=2)}
Budget check: {json.dumps(budget_result, indent=2)}
Layout check: {json.dumps(layout_result, indent=2)}

Generate a design plan with:
1. Two-sentence design rationale
2. BOQ table: Item | ID | Price (₹) | Dimensions | Notes
3. Total spent vs budget, and remaining budget
4. Trade-offs: what you prioritised and what you left out
Be honest if over budget or layout is tight. Always show prices with the ₹ symbol.
CRITICAL: Only reference items from the Selected items list above — never invent products or prices.
If over budget, state clearly that the budget is insufficient and show the real total vs the budget limit.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        temperature=0.7
    )
    result = response.choices[0].message.content.strip().replace("$", "₹")
    return result


if __name__ == "__main__":
    test_queries = [
        "Show me some modern sofas",
        "Should I knock down the kitchen wall? Is it load-bearing?",
        "Find me a Scandinavian coffee table under 20000",
        "Show me rugs for a living room",
        "I want a Togo sofa by Ligne Roset",
    ]

    print("=" * 60)
    print("PART 1 — FREE TEXT QUERIES")
    print("=" * 60)

    for query in test_queries:
        result = run_agent(query)
        print("\n" + result)
        print("-" * 60)

    print("\n\n" + "=" * 60)
    print("PART 2 — FULL ROOM DESIGN (all 3 tools fire)")
    print("=" * 60)

    print("\n>>> BR-01: Happy path — Scandinavian living room ₹2.5L")
    print(design_room("BR-01"))

    print("\n\n>>> BR-06: Impossible budget — ₹20,000 full living room")
    print(design_room("BR-06"))
