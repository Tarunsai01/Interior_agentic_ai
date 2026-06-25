# Interior Design Agent
**APM Build Challenge — Interior Company × Blocks**

An AI agent that turns a customer room brief into a budget-fit design plan using real products from a furniture catalog. Built with Groq Llama-3.3-70B + SQLite. Three working tools, 25 eval cases, LLM-as-judge scorer.

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
Runs 25 test cases, prints pass/fail, outputs ship gate decision, saves `eval_results.json`.

---

## Project structure

```
interior_agent/
├── agent.py                     # Core agent — run_agent() and design_room()
├── db.py                        # Three tools: catalog_search, budget_calculator, layout_fit_check
├── eval.py                      # Eval harness — 25 cases, deterministic + LLM-as-judge scorers
├── eval_results.json            # Populated after running eval.py
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
| Structural / civil / plumbing questions | Hard declined at Python layer before any LLM call |
| Designer brands not in catalog (Eames, Togo, Noguchi) | LLM declines, offers closest catalog alternatives |
| Delivery date / price guarantees | LLM declines to promise |
| Impossible budgets | LLM flags honestly with real totals vs limit |
| SQL injection | Python blacklist rejects any non-SELECT statement |

---

## Eval harness

25 test cases across 6 categories:

| Category | Cases | What it checks |
|----------|-------|----------------|
| Happy path room briefs | T01, T23 | All 3 tools fire, real catalog items in output, budget not exceeded |
| Impossible budget | T02 | Agent flags impossibility, doesn't fake a plan |
| Structural / civil guardrails | T03–T07, T24, T25 | Python-layer decline fires correctly |
| Delivery / price guardrails | T08–T10 | Promise decline fires correctly |
| Designer brand guardrails | T11–T13 | Brand decline + catalog alternatives offered |
| Catalog searches | T14–T18 | Real results returned with ₹ prices |
| Data quality edge cases | T19–T20 | NULL-price and out-of-stock items handled |
| Impossible fit | T21 | Tiny room with oversized furniture flagged |
| LLM-as-judge | T22 | Style coherence scored 1–5 with written rubric, pass ≥ 4 |

### Ship gate
| Criterion | Threshold |
|-----------|-----------|
| Overall pass rate | ≥ 80% |
| Guardrail firing on structural questions | 100% |
| Items in catalog only | 100% |
| Budget never silently exceeded | 100% |

### LLM-as-judge rubric
A second Llama call scores style coherence 1–5:
- **5** — All items match the requested style tag
- **4** — Most items match, one minor mismatch
- **3** — Majority match, one notable mismatch
- **2** — Mixed styles, misalignment noticeable
- **1** — Style tags don't match the brief

Pass threshold: score ≥ 4.

---

## Known limitations (documented in decision_log.md)

- Layout fit check is floor-area heuristic only — won't catch L-shaped rooms
- CATEGORY_MAP is manually maintained — new catalog categories need a new entry
- No session memory — agent can't refine a previous design
- 5 catalog items have NULL prices — budget totals are uncertain when selected
- Style coverage is thin — only 1 Japandi item in the entire catalog

---

## Tools used
- **Groq API** — Llama-3.3-70B for SQL generation, response generation, and LLM-as-judge
- **SQLite** — furniture catalog and room briefs (provided)
- **Python** — re, sqlite3, json (stdlib)
- **Claude (Anthropic)** — architecture planning, debugging, prompt engineering
