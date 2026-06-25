# Decision Log — Interior Design Agent
**Interior Company × Blocks | APM Build Challenge**

---

## What I scoped in / out and why

**Scoped in:**
- Living Room focus — 8 of 14 briefs are living room; richest catalog coverage; clearest customer need
- Free-text natural language queries (`run_agent`)
- Structured room brief design with full tool loop (`design_room`)
- Three working tools: catalog_search, budget_calculator, layout_fit_check
- Guardrails for structural questions, designer brand requests, delivery promises, impossible budgets

**Scoped out:**
- Bedroom, Dining, Study, Kids room planning — noted as next iteration, not cut for complexity
- UI / frontend — terminal output is sufficient to demonstrate agentic behavior
- Multi-user sessions, auth, deployment — not required per brief
- Image uploads, floor plan rendering, CAD-level layout

**Why Living Room only:** The brief explicitly says "one room done well beats a whole home done shallowly." BR-01 as a fully working happy path with all 3 tools firing is worth more than 5 half-working room types.

---

## How I directed AI tools and where I overrode them

**Model choice — Groq Llama-3.3-70B:**
Pivoted from Google Gemini (503/404/429 errors across three model versions) and Anthropic Claude (exhausted trial credits) within 2 minutes of each failure. Groq's free tier had zero quota issues and sub-second latency. Speed of pivot mattered more than model prestige.

**Schema injection into system prompt:**
Initial runs returned empty datasets. Root cause: the model was hallucinating SQL like `LOWER(category) = 'sofa'` against a DB that stores `'Sofa'`. Fixed by injecting the exact category vocabulary, style tags, and room types directly into the system prompt. The model cannot write correct SQL against a schema it has never seen.

**SQL operator precedence fix:**
Model generated OR conditions without parentheses — causing AND filters (in_stock, category) to be bypassed for OR branches. Added an explicit rule with an example to the system prompt. Overriding model behavior via explicit counter-examples in the prompt is more reliable than relying on the model to infer intent.

**Python-layer guardrail for structural questions:**
Prompt-only guardrails failed — the model consistently added "helpful" structural tips despite explicit instructions to decline. Moved the check to a Python keyword filter (`is_out_of_scope()`) that fires before any LLM call. Deterministic Python beats probabilistic prompting for hard safety requirements.

**Currency symbol fix at Python layer:**
Model output `$` instead of `₹` despite prompt instructions. Fixed with a `.replace("$", "₹")` on the final output string. This is a model behavior issue, not a reasoning issue — Python-layer post-processing is the right fix.

**Must-have normalization (`CATEGORY_MAP`):**
The `must_haves` column in `room_briefs` uses free text like `"3-seater sofa"`, `"lighting"`, `"TV unit"`. The `catalog_search` tool requires exact DB category names like `"Sofa"`, `"Floor Lamp"`, `"TV Unit"`. Built a CATEGORY_MAP dictionary to normalize before every tool call. Without this, every catalog_search returned zero results despite the data existing.

**VS Code auto-quote corruption:**
VS Code's smart quotes corrupted triple backticks and apostrophes during paste operations. Worked around by building markdown symbols dynamically in Python using ASCII codes (`chr(96)`), bypassing the IDE's string substitution entirely.

---

## What would break in production

| Issue | Impact | Fix |
|-------|--------|-----|
| 5 items with NULL prices | Budget totals are uncertain | Data pipeline to resolve pricing |
| 6 items out of stock | Agent flags but offers no substitute | Add fallback: re-search same category excluding flagged item |
| Layout heuristic is floor-area only (≤50%) | Won't catch awkward L-shapes or narrow rooms | Grid-based spatial planner |
| CATEGORY_MAP is manually maintained | New catalog categories will miss | LLM-based category classification |
| No session memory | Agent can't refine a previous design | Conversation history persistence |
| SQL generated dynamically | Prompt injection risk via user input | Parameterized queries for all catalog access |
| Style coverage is thin | Only 1 Japandi item in entire catalog | Catalog expansion |
| Free-text brief parsing depends on comma splitting | "sofa, armchair and rug" misses "and rug" | NLP-based must-have extractor |

---

## What I'd build next (priority order)

1. **Substitute suggestion** — when an item is out of stock, automatically re-run catalog_search and offer the next best match
2. **Multi-room support** — Bedroom and Dining briefs with room-specific must-have maps
3. **LLM-as-judge eval scorer** — second Claude/Llama call that scores style coherence 1–5 with a written rubric
4. **Streamlit UI** — already scaffolded; wire `run_agent` and `design_room` to the frontend
5. **Price NULL pipeline** — flag items to a data team with a structured report
6. **Spatial layout engine** — grid-based placement that accounts for doorways and circulation paths
7. **Session memory** — store previous brief context so customers can iterate ("make it cheaper", "swap the sofa")
