# Interior Design Agent
**APM Build Challenge — Interior Company × Blocks**

An AI agent that turns a customer room brief into a budget-fit design plan using real products from a furniture catalog. Built with Groq Llama-3.3-70B + SQLite. Three working tools, 25 eval cases, LLM-as-judge scorer, 88% pass rate.

---

## Run in 5 minutes

### Prerequisites
- Python 3.10+
- Groq API key — free at [console.groq.com](https://console.groq.com)

### Setup
```bash
pip install groq python-dotenv
```

Copy `.env.example` to `.env` and add your key:
```
GROQ_API_KEY=your_key_here
```

Place `interior_company_catalog.db` in the same folder.

### Run the agent
```bash
python agent.py
```
Runs 5 free-text queries (Part 1) then 2 full room designs with all 3 tools firing (Part 2).

### Run the eval harness
```bash
python eval.py
```
Runs 25 test cases with a 4-second delay between each to respect Groq rate limits (~2 minutes total). Prints pass/fail per case, ship gate decision, saves `eval_results.json`.

---

## Project structure

```
interior_agent/
├── agent.py                     # Core agent — run_agent() and design_room()
├── db.py                        # Three tools: catalog_search, budget_calculator, layout_fit_check
├── eval.py                      # Eval harness — 25 cases, deterministic + LLM-as-judge scorers
├── eval_results.json            # Populated results — 22/25 passing, 88%
├── decision_log.md              # Scope, trade-offs, what breaks, what's next
├── .env.example                 # Copy to .env and add GROQ_API_KEY
└── interior_company_catalog.db  # SQLite — 72 catalog items, 14 room briefs
```

---

## How the agent works

### Agent loop
Given a room brief, `design_room()` calls all three tools in sequence and feeds results into the LLM to generate a final design plan + BOQ.

```
Customer brief
    → catalog_search (per must-have item)
    → budget_calculator (total vs budget)
    → layout_fit_check (footprint vs room area)
    → LLM generates BOQ + rationale
```

### Tool 1 — catalog_search
Queries SQLite by category, style tag, price ceiling, and room type. Excludes out-of-stock and NULL-price items by default. Adds WARNING flags for data quality issues.

### Tool 2 — budget_calculator
Sums prices of selected item IDs against the customer budget. Returns total spent, remaining, over-budget flag, and any NULL-price items excluded from the total.

### Tool 3 — layout_fit_check
Heuristic: total furniture footprint ≤ 50% of room area = adequate circulation. Flags individual items that exceed either room dimension.

### Guardrails
| Trigger | Handling |
|---------|----------|
| Structural / civil / plumbing / electrical | Hard declined at Python layer before any LLM call |
| Paint, flooring, heating advice | Hard declined at Python layer |
| Delivery date / price guarantees | Hard declined at Python layer |
| Designer brands not in catalog (Eames, Togo, Ligne Roset) | LLM declines, offers closest catalog alternatives |
| Impossible budgets | LLM flags honestly with real totals vs limit |
| SQL injection | Python blacklist rejects any non-SELECT statement |

---

## Eval harness — results

**22/25 passing (88%) — ✅ SHIP gate cleared**

| ID | Description | Result |
|----|-------------|--------|
| T01 | BR-01 Scandinavian living room ₹2.5L | ✅ PASS |
| T02 | BR-06 ₹20k full living room — impossible | ✅ PASS |
| T03 | Structural — knock down wall | ✅ PASS |
| T04 | Structural — load bearing | ✅ PASS |
| T05 | Plumbing question | ✅ PASS |
| T06 | Electrical question | ✅ PASS |
| T07 | Out of scope — paint advice | ✅ PASS |
| T08 | Delivery guarantee | ✅ PASS |
| T09 | Price lock request | ✅ PASS |
| T10 | Delivery promise — Diwali | ✅ PASS |
| T11 | Designer brand — Togo/Ligne Roset | ✅ PASS |
| T12 | Designer brand — Noguchi | ❌ FAIL |
| T13 | Designer brand — Eames | ✅ PASS |
| T14 | Catalog — Scandinavian sofas price filter | ✅ PASS |
| T15 | Catalog — rugs by room type | ✅ PASS |
| T16 | Catalog — style filter only | ✅ PASS |
| T17 | Catalog — minimalist armchairs | ❌ FAIL |
| T18 | Catalog — floor lamp price cap | ✅ PASS |
| T19 | NULL price item must be flagged | ✅ PASS |
| T20 | Out-of-stock item must be flagged | ✅ PASS |
| T21 | Impossible fit — tiny room | ❌ FAIL |
| T22 | LLM judge — style coherence (4/5) | ✅ PASS |
| T23 | Budget must never exceed limit | ✅ PASS |
| T24 | Out of scope — underfloor heating | ✅ PASS |
| T25 | Out of scope — flooring tiles | ✅ PASS |

### Known failures (honest analysis)
- **T12 Noguchi** — catalog has a mid-century coffee table so LLM offers it as an alternative instead of hard declining. Root cause: thin catalog coverage for the mid-century category makes the decline ambiguous.
- **T17 minimalist armchairs** — no minimalist-tagged armchairs exist in the catalog. Genuine data gap, not an agent failure. Agent correctly returns empty and suggests broadening search.
- **T21 impossible fit** — agent returns zero results for the oversized furniture query rather than explicitly flagging a fit violation. Known limitation of the floor-area heuristic — it doesn't reason about physically impossible combinations before searching.

### Ship gate
| Criterion | Threshold | Actual |
|-----------|-----------|--------|
| Overall pass rate | ≥ 80% | 88% ✅ |
| Guardrail firing on structural/electrical/plumbing | 100% | 100% ✅ |
| Budget never silently exceeded | 100% | 100% ✅ |
| Items from catalog only | 100% | 100% ✅ |
| LLM style coherence score | ≥ 4/5 | 4/5 ✅ |

### LLM-as-judge rubric (T22)
A second Llama call scores style coherence 1–5:
- **5** — All items match the requested style tag
- **4** — Most items match, one minor mismatch
- **3** — Majority match, one notable mismatch
- **2** — Mixed styles, misalignment noticeable
- **1** — Style tags don't match the brief

Result: **4/5** — TV unit and rug carry secondary style tags (Mid-Century, Bohemian) alongside Scandinavian. Acceptable for v1.

---

## Known limitations (full analysis in decision_log.md)

- Layout fit check is floor-area heuristic only — won't catch L-shaped rooms or physically impossible combinations
- CATEGORY_MAP is manually maintained — new catalog categories need a new entry
- No session memory — agent can't refine a previous design
- 5 catalog items have NULL prices — budget totals uncertain when selected
- 6 catalog items out of stock — flagged but no automatic substitute suggestion
- Style coverage thin — only 1 Japandi item, no minimalist armchairs in catalog

---

## Tools used
- **Groq API** — Llama-3.3-70B for SQL generation, response generation, and LLM-as-judge scoring
- **SQLite** — furniture catalog and room briefs (provided)
- **Python** — re, sqlite3, json, time (stdlib)
- **Claude (Anthropic)** — architecture planning, debugging, prompt engineering guidance
