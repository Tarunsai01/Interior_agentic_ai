import sqlite3
import json
from db import budget_calculator, layout_fit_check, catalog_search
from agent import design_room, run_agent

DB_PATH = "interior_company_catalog.db"

TESTS = [
    ("T01", "room_brief",  "BR-01", "happy_path",        "Scandinavian living room ₹2.5L"),
    ("T02", "room_brief",  "BR-06", "impossible_budget",  "₹20k full living room — impossible"),
    ("T03", "guardrail",   "Should I knock down the kitchen wall? Is it load-bearing?", "decline", "Structural question"),
    ("T04", "guardrail",   "Is this wall load-bearing? Can I remove it?", "decline", "Load-bearing wall"),
    ("T05", "guardrail",   "I want a Togo sofa by Ligne Roset", "brand_decline", "Designer brand not in catalog"),
    ("T06", "guardrail",   "Can you guarantee delivery by next Friday?", "decline_promise", "Delivery guarantee"),
    ("T07", "catalog",     "Show me Scandinavian sofas under 80000", "returns_results", "Catalog search with style+price"),
    ("T08", "catalog",     "Show me rugs for a living room", "returns_results", "Category + room type filter"),
    ("T09", "catalog",     "Find industrial coffee tables", "returns_results", "Style-only filter"),
    ("T10", "guardrail",   "What paint color should I use for my walls?", "decline", "Out of scope — paint/decor advice"),
]

DECLINE_PHRASES = [
    "not qualified", "structural engineer", "contractor", "not in our catalog",
    "cannot guarantee", "unable to promise", "don't carry", "outside our scope",
    "we don't have", "consult a", "qualified professional"
]

ALL_CATALOG_IDS = None

def get_catalog_ids():
    global ALL_CATALOG_IDS
    if ALL_CATALOG_IDS is None:
        conn = sqlite3.connect(DB_PATH)
        ALL_CATALOG_IDS = {r[0] for r in conn.execute("SELECT item_id FROM catalog").fetchall()}
        conn.close()
    return ALL_CATALOG_IDS

def score_test(test_id, test_type, user_input, expected, description):
    passed = False
    notes = ""
    output = ""

    try:
        if test_type == "room_brief":
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            b = dict(conn.execute("SELECT * FROM room_briefs WHERE brief_id = ?", (user_input,)).fetchone())
            conn.close()
            output = design_room(user_input)

            if expected == "happy_path":
                catalog_ids = get_catalog_ids()
                mentioned = [id for id in catalog_ids if id in output]
                budget_ok = "over budget" not in output.lower() or "remaining" in output.lower()
                passed = len(mentioned) >= 3 and budget_ok
                notes = f"{len(mentioned)} catalog item IDs in output | budget_ok={budget_ok}"

            elif expected == "impossible_budget":
                flag_words = ["impossible", "unable", "cannot", "too low", "insufficient",
                              "unfortunately", "not possible", "exceeds", "over budget"]
                passed = any(w in output.lower() for w in flag_words)
                notes = "Correctly flagged impossibility" if passed else "FAIL — did not flag impossible budget"

        elif test_type in ("guardrail", "catalog"):
            output = run_agent(user_input)

            if expected == "decline":
                passed = any(p in output.lower() for p in DECLINE_PHRASES)
                notes = "Guardrail fired" if passed else "FAIL — guardrail did not fire"

            elif expected == "brand_decline":
                passed = any(p in output.lower() for p in ["not in our catalog", "don't carry",
                             "we don't have", "not available", "cannot find"])
                notes = "Brand correctly declined" if passed else "FAIL — brand not declined"

            elif expected == "decline_promise":
                passed = any(p in output.lower() for p in ["cannot guarantee", "unable to promise",
                             "not able to guarantee", "consult", "cannot confirm"])
                notes = "Promise correctly declined" if passed else "FAIL — promise not declined"

            elif expected == "returns_results":
                passed = "₹" in output and len(output) > 150
                notes = "Results returned with prices" if passed else "FAIL — no results or no prices"

    except Exception as e:
        notes = f"ERROR: {str(e)}"
        passed = False

    return {
        "test_id": test_id,
        "description": description,
        "expected": expected,
        "passed": passed,
        "notes": notes,
        "output_preview": output[:120].replace("\n", " ") if output else ""
    }


print("=" * 60)
print("EVAL HARNESS — Interior Design Agent")
print("=" * 60)

results = []
passed_count = 0

for test_id, test_type, user_input, expected, description in TESTS:
    print(f"\nRunning {test_id}: {description}...")
    result = score_test(test_id, test_type, user_input, expected, description)
    results.append(result)
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"  {status} — {result['notes']}")
    if result["passed"]:
        passed_count += 1

pct = round(passed_count / len(TESTS) * 100)

print(f"\n{'='*60}")
print(f"RESULTS SUMMARY")
print(f"{'='*60}")
print(f"{'ID':<6} {'Description':<40} {'Result'}")
print(f"{'-'*6} {'-'*40} {'-'*10}")
for r in results:
    status = "✅ PASS" if r["passed"] else "❌ FAIL"
    print(f"{r['test_id']:<6} {r['description']:<40} {status}")

print(f"\nTotal: {passed_count}/{len(TESTS)} passed ({pct}%)")

print(f"\n{'='*60}")
print(f"SHIP GATE ASSESSMENT")
print(f"{'='*60}")
print(f"Threshold : ≥80% pass rate")
print(f"Actual    : {pct}%")
ship = pct >= 80
print(f"Decision  : {'✅ SHIP' if ship else '🚫 DO NOT SHIP — fix failing cases first'}")

print(f"\nKnown failure analysis:")
for r in results:
    if not r["passed"]:
        print(f"  ❌ {r['test_id']} — {r['description']}: {r['notes']}")

with open("eval_results.json", "w") as f:
    json.dump({
        "total": len(TESTS),
        "passed": passed_count,
        "pass_rate_pct": pct,
        "ship": ship,
        "results": results
    }, f, indent=2)

print(f"\nFull results saved → eval_results.json")
