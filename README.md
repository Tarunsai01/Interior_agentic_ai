# Interior Design Agent
**APM Build Challenge — Interior Company × Blocks**

An AI agent that turns a customer room brief into a budget-fit design plan using real products from a furniture catalog. Built with Groq Llama-3.3-70B + SQLite.

---

## Run in 5 minutes

### Prerequisites
- Python 3.10+
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Setup
```bash
pip install groq python-dotenv
```

Create a `.env` file in the project folder:
```
GROQ_API_KEY=your_key_here
```

Place `interior_company_catalog.db` in the same folder as the scripts.

### Run the agent
```bash
python agent.py
```

Runs 5 free-text queries (Part 1) and 2 full room designs with all 3 tools firing (Part 2).

### Run the eval harness
```bash
python eval.py
```

Runs 10 test cases, prints pass/fail for each, outputs ship gate decision, saves `eval_results.json`.

---

## Project structure

```
interior_agent/
├── agent.py          # Core agent — run_agent() and design_room()
├── db.py             # Three tools: catalog_search, budget_calculator, layout_fit_check
├── eval.py           # Eval harness — 10 test cases, deterministic scorers, ship gate
├── eval_results.json # Generated after running eval.py
├── decision_log.md   # Scope, trade-offs, what breaks, what's next
├── .env              # GROQ_API_KEY (not committed)
└── interior_company_catalog.db  # SQLite catalog — 72 items, 14 briefs
```

---

## How the agent works

### Tool 1 — catalog_search
Queries the SQLite catalog by category, style tag, price ceiling, and room type. Excludes out-of-stock and NULL-price items by default. Returns WARNING flags when items have data quality issues.

### Tool 2 — budget_calculator
Sums prices of selected item IDs against the customer budget. Returns total spent, remaining budget, over-budget flag, and a list of any NULL-price items that couldn't be included in the total.

### Tool 3 — layout_fit_check
Checks whether selected furniture fits the room footprint. Heuristic: total furniture footprint ≤ 50% of room area leaves adequate circulation space. Flags individual items that exceed either room dimension.

### Guardrails
- **Structural/civil questions** — hard declined at Python layer before any LLM call
- **Designer brands not in catalog** — LLM declines and offers closest catalog alternatives
- **Delivery date promises** — LLM declines to guarantee dates or final prices
- **Impossible budgets** — LLM flags honestly with real totals vs budget limit
- **SQL injection** — Python-layer blacklist rejects any non-SELECT statement

---

## Eval harness — ship gate

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Pass rate | ≥ 80% | Overall quality floor |
| Guardrail firing | 100% on structural questions | Safety-critical, non-negotiable |
| Items in catalog | 100% | Core product requirement |
| Budget not silently exceeded | 100% | Trust-critical |

Run `python eval.py` to see current results and ship gate decision.

---

## Tools used
- **Groq API** — Llama-3.3-70B for SQL generation and natural language responses
- **SQLite** — furniture catalog and room briefs
- **Python stdlib** — re, sqlite3, json
- **VS Code** — development environment
- **Claude (Anthropic)** — architecture planning, debugging, prompt engineering guidance
