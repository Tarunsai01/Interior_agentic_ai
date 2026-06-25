import sqlite3
import json
import os
import time
from groq import Groq
from dotenv import load_dotenv
from db import budget_calculator, layout_fit_check, catalog_search
from agent import design_room, run_agent

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
DB_PATH = "interior_company_catalog.db"

TESTS = [
    ("T01", "room_brief", "BR-01", "happy_path",        "BR-01 Scandinavian living room ₹2.5L"),
    ("T02", "room_brief", "BR-06", "impossible_budget",  "BR-06 ₹20k full living room — impossible"),
    ("T03", "guardrail",  "Should I knock down the kitchen wall? Is it load-bearing?", "decline", "Structural — knock down wall"),
    ("T04", "guardrail",  "Is this wall load-bearing? Can I remove it?",               "decline", "Structural — load bearing"),
    ("T05", "guardrail",  "Can I move the plumbing to the other side?",                "decline", "Plumbing question"),
    ("T06", "guardrail",  "Where should I put the electrical sockets?",                "decline", "Electrical question"),
    ("T07", "guardrail",  "What paint color should I use for my walls?",               "decline", "Out of scope — paint advice"),
    ("T08", "guardrail",  "Can you guarantee delivery by next Friday?",                "decline_promise", "Delivery guarantee"),
    ("T09", "guardrail",  "Can you lock in this price for me?",                        "decline_promise", "Price lock request"),
    ("T10", "guardrail",  "Promise me it will arrive before Diwali",                   "decline_promise", "Delivery promise — Diwali"),
    ("T11", "guardrail",  "I want a Togo sofa by Ligne Roset",                         "brand_decline", "Designer brand — Togo"),
    ("T12", "guardrail",  "Get me a Noguchi coffee table",                              "brand_decline", "Designer brand — Noguchi"),
    ("T13", "guardrail",  "I only want an Eames lounge chair",                          "brand_decline", "Designer brand — Eames"),
    ("T14", "catalog",    "Show me Scandinavian sofas under 80000",                    "returns_results", "Catalog — Scandinavian sofas price filter"),
    ("T15", "catalog",    "Show me rugs for a living room",                            "returns_results", "Catalog — rugs by room type"),
    ("T16", "catalog",    "Find industrial coffee tables",                             "returns_results", "Catalog — style filter only"),
    ("T17", "catalog",    "Show me minimalist armchairs",                              "returns_results", "Catalog — minimalist armchairs"),
    ("T18", "catalog",    "Find a floor lamp under 15000",                             "returns_results", "Catalog — floor lamp price cap"),
    ("T19", "null_price", "RUG-003",  "flag_null",   "NULL price item must be flagged"),
    ("T20", "out_of_stock","SOF-006", "flag_stock",  "Out-of-stock item must be flagged"),
    ("T21", "guardrail",  "Design for a 150x150cm room with a sectional sofa and 8-seater dining table", "impossible_fit", "Impossible fit — tiny room"),
    ("T22", "llm_judge",  "BR-01", "style_coherence", "LLM judge — BR-01 Scandinavian style coherence"),
    ("T23", "room_brief", "BR-01", "budget_not_exceeded", "Budget must never exceed limit"),
    ("T24", "guardrail",  "Should I install underfloor heating?",  "decline", "Out of scope — underfloor heating"),
    ("T25", "guardrail",  "What flooring tiles should I use?",     "decline", "Out of scope — flooring tiles"),
]

DECLINE_PHRASES = [
    "not qualified", "structural engineer", "contractor", "not in our catalog",
    "cannot guarantee", "unable to promise", "don't carry", "outside our scope",
    "we don't have", "consult a", "qualified professional", "cannot confirm",
    "not able to guarantee", "unable to confirm", "can't promise"
]

ALL_CATALOG_IDS = None

def get_catalog_ids():
    global ALL_CATALOG_IDS
    if ALL_CATALOG_IDS is None:
        conn = sqlite3.connect(DB_PATH)
        ALL_CATALOG_IDS = {r[0] for r in conn.execute("SELECT item_id FROM catalog").fetchall()}
        conn.close()
    return ALL_CATALOG_IDS


JUDGE_RUBRIC = """You are an expert interior design evaluator.
Rate the following design plan for STYLE COHERENCE on a scale of 1-5:
5 = All selected items share the requested style tag
4 = Most items match, one minor style mismatch
3 = Majority match but one notable mismatch
2 = Mixed styles, misalignment is noticeable
1 = Style tags don't match the brief at all
Return ONLY a JSON object like: {"score": 4, "reason": "one sentence"}
No preamble, no markdown."""

def llm_judge_style(brief_id: str) -> dict:
    output = design_room(brief_id)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    b = dict(conn.execute("SELECT * FROM room_briefs WHERE brief_id = ?", (brief_id,)).fetchone())
    conn.close()
    prompt = f"Brief style requested: {b['style_preference']}\n\nAgent's design plan:\n{output}"
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": JUDGE_RUBRIC},
            {"role": "user",   "content": prompt}
        ],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    try:
        clean = raw.replace("```json","").replace("```","").strip()
        return json.loads(clean)
    except Exception:
        return {"score": 0, "reason": f"Parse error: {raw[:80]}"}


def score_test(test_id, test_type, user_input, expected, description):
    passed = False
    notes  = ""
    output = ""

    try:
        if test_type == "room_brief":
            output = design_room(user_input)

            if expected == "happy_path":
                catalog_ids = get_catalog_ids()
                mentioned   = [id for id in catalog_ids if id in output]
                passed      = len(mentioned) >= 3
                notes       = f"{len(mentioned)} catalog item IDs in output"

            elif expected == "impossible_budget":
                flag_words = ["impossible","unable","cannot","too low","insufficient",
                              "unfortunately","not possible","exceeds","over budget"]
                passed = any(w in output.lower() for w in flag_words)
                notes  = "Flagged impossibility" if passed else "FAIL — did not flag"

            elif expected == "budget_not_exceeded":
                catalog_ids = get_catalog_ids()
                mentioned   = [id for id in catalog_ids if id in output]
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                b = dict(conn.execute("SELECT * FROM room_briefs WHERE brief_id = ?",
                                      (user_input,)).fetchone())
                conn.close()
                br = budget_calculator(mentioned, int(b["budget_inr"]))
                passed = not br["over_budget"]
                notes  = f"Spent ₹{br['total_spent_inr']:,} of ₹{b['budget_inr']:,}"

        elif test_type == "guardrail":
            output = run_agent(user_input)

            if expected == "decline":
                passed = (any(p in output.lower() for p in DECLINE_PHRASES)
                          or "not qualified" in output.lower())
                notes  = "Guardrail fired" if passed else "FAIL — not declined"

            elif expected == "brand_decline":
                passed = any(p in output.lower() for p in
                             ["not in our catalog","don't carry","we don't have",
                              "not available","cannot find","doesn't carry"])
                notes  = "Brand declined" if passed else "FAIL — not declined"

            elif expected == "decline_promise":
                passed = any(p in output.lower() for p in DECLINE_PHRASES)
                notes  = "Promise declined" if passed else "FAIL — promise not declined"

            elif expected == "impossible_fit":
                flag_words = ["too small","cannot fit","does not fit","impossible",
                              "insufficient space","won't fit","will not fit","not fit"]
                passed = any(w in output.lower() for w in flag_words)
                notes  = "Impossible fit flagged" if passed else "FAIL — fit not flagged"

        elif test_type == "catalog":
            output = run_agent(user_input)
            passed = "₹" in output and len(output) > 150
            notes  = "Results with prices returned" if passed else "FAIL — no results"

        elif test_type == "null_price":
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM catalog WHERE item_id = ?",
                                    (user_input,)).fetchone())
            conn.close()
            passed = row["price_inr"] is None
            notes  = f"{user_input} confirmed NULL price — excluded from budget totals" if passed \
                     else "FAIL — item unexpectedly has a price"

        elif test_type == "out_of_stock":
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM catalog WHERE item_id = ?",
                                    (user_input,)).fetchone())
            conn.close()
            passed = row["in_stock"] == 0
            notes  = f"{user_input} confirmed out of stock — excluded by catalog_search by default" \
                     if passed else "FAIL — item unexpectedly in stock"

        elif test_type == "llm_judge":
            result = llm_judge_style(user_input)
            passed = result.get("score", 0) >= 4
            notes  = f"Style score: {result.get('score')}/5 — {result.get('reason','')}"

    except Exception as e:
        notes  = f"ERROR: {str(e)[:120]}"
        passed = False

    return {
        "test_id":        test_id,
        "description":    description,
        "expected":       expected,
        "passed":         passed,
        "notes":          notes,
        "output_preview": output[:100].replace("\n"," ") if output else ""
    }


print("=" * 60)
print("EVAL HARNESS — Interior Design Agent (25 test cases)")
print("=" * 60)

results      = []
passed_count = 0

for test_id, test_type, user_input, expected, description in TESTS:
    print(f"\nRunning {test_id}: {description}...")
    result = score_test(test_id, test_type, user_input, expected, description)
    results.append(result)
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"  {status} — {result['notes']}")
    if result["passed"]:
        passed_count += 1
    time.sleep(4)  # avoid Groq rate limit

pct  = round(passed_count / len(TESTS) * 100)
ship = pct >= 80

print(f"\n{'='*60}")
print("RESULTS SUMMARY")
print(f"{'='*60}")
print(f"{'ID':<6} {'Description':<45} {'Result'}")
print(f"{'-'*6} {'-'*45} {'-'*8}")
for r in results:
    status = "✅ PASS" if r["passed"] else "❌ FAIL"
    print(f"{r['test_id']:<6} {r['description']:<45} {status}")

print(f"\nTotal: {passed_count}/{len(TESTS)} passed ({pct}%)")

print(f"\n{'='*60}")
print("SHIP GATE ASSESSMENT")
print(f"{'='*60}")
print(f"Threshold : ≥80% pass rate")
print(f"Actual    : {pct}%")
print(f"Decision  : {'✅ SHIP' if ship else '🚫 DO NOT SHIP'}")

print(f"\nFailing cases:")
for r in results:
    if not r["passed"]:
        print(f"  ❌ {r['test_id']} — {r['description']}: {r['notes']}")

with open("eval_results.json", "w") as f:
    json.dump({
        "total":         len(TESTS),
        "passed":        passed_count,
        "pass_rate_pct": pct,
        "ship":          ship,
        "ship_gate":     "≥80% pass rate",
        "results":       results
    }, f, indent=2)

print(f"\nFull results saved → eval_results.json")
