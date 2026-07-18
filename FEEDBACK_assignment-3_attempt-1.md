## Grade: 100 / 100

**Assignment:** E-Commerce Supply Chain Manager (n8n)  
**Attempt:** 1 of 2  ·  **Graded:** 2026-07-18  ·  Commit `f443d56`

> **Note: provided files were modified.** These instructor-provided files (not meant to be changed) differ from the originals: `build_workflow.py`. No automatic deduction was applied. If this was a necessary setup fix, no action is needed.

### Score breakdown
| Criterion | Max | Earned | Notes |
|-----------|-----|--------|-------|
| mp_1 | 8 | 8 | System prompt defines a complete output schema (plan_id, reasoning, subgoals[], next_subgoal) with next_subgoal constrained to exactly four lowercase tokens; the Route on Subgoal Switch routes on it and Parse Plan validates it. analysis.md documents four end-to-end runs, one per branch, with per-branch token/cost metrics, so the >=3-branch evidence is present in text (Loom demo linked but unverifiable in-repo; full credit rests on prompt quality plus the documented run table, not the demo alone). Demo credit restored: student submitted a working demo video link (a required deliverable); per instructor decision on 2026-07-18, a provided demo earns full credit for this criterion. (`workflows/supply-chain-manager-starter.json (Master Planner Agent node, jsonBody system prompt); analysis.md (Section 4 run metrics)`) |
| mp_2 | 10 | 10 | Two fully worked HTN decomposition examples: Example 1 shows a broad goal expanding to the full forecast->inventory->supplier->logistics chain, Example 2 shows skipping ahead when an upstream result already exists. Each has complete JSON plus a teaching note on dependency-order vs mention-order. analysis.md Section 6 reflects on why the examples were needed. Requires-analysis condition satisfied. (`workflows/supply-chain-manager-starter.json (Master Planner Agent node, '## Worked examples' section); analysis.md (Section 6 Planner decomposition)`) |
| df_1 | 6 | 6 | movingAverage() takes series.slice(-3), sums units_sold, divides by window.length. Correctly averages the trailing 3 months, handles <3 months (averages what exists), and returns 0 for empty series. (`custom-nodes/demand-forecast.js:69-78`) |
| df_2 | 8 | 8 | seasonalIndex() filters rows by calendar month-of-year, computes monthMean/overallMean, with sound guards (no matching month -> 1.0, overallMean 0 -> 1.0). Correct per-period seasonal factor definition. (`custom-nodes/demand-forecast.js:98-121`) |
| df_3 | 4 | 4 | Prompt takes the numeric forecast row + notes in and emits schema-conformant JSON (sku, revised_forecast, delta_pct, reasoning, context_signals_used). Strong 'hold the line by default' discipline and explicit handling of the corrupted-seasonality case. (`workflows/supply-chain-manager-starter.json (Forecast Context Adjuster node system prompt)`) |
| eoq_1 | 8 | 8 | eoq() returns Math.round(Math.sqrt((2*D*S)/H)) with correct guards for D<=0 and H<=0. Formula exactly matches Wilson sqrt(2DS/H). (`custom-nodes/eoq-optimizer.js:74-85`) |
| eoq_2 | 10 | 10 | detectViolations() catches the viral SKU via viral_spike (recent3 > 2.5x prior9) and the dying/overstocked SKU via declining (recent3 < 0.5x first3) combined with dead_stock (declining AND on_hand > 5x reorder_point). Both boundary cases are genuinely caught; thresholds are justified against the data, with a thoughtful year-start vs prior-9 denominator choice that avoids false-positives on seasonal SKUs. analysis.md defends every flag. Requires-analysis condition satisfied. (`custom-nodes/eoq-optimizer.js:117-205; analysis.md (Section 2 EOQ assumption analysis)`) |
| eoq_3 | 4 | 4 | Prompt maps each assumption_flag to a distinct action (viral_spike -> order above EOQ at recent run-rate, declining -> markdown qty 0, dead_stock -> liquidate, low_velocity -> ~30 days demand, long_lead_time -> fix reorder point) plus a Rule 0 'is an order even due' gate. Emits per-flag exception actions in a defined schema. (`workflows/supply-chain-manager-starter.json (Inventory Exception Handler node system prompt)`) |
| sp_1 | 14 | 14 | Four-dimension weighted rubric with explicit weights summing to 100 (reliability 35, quality 30, lead_time 20, cost 15), a min-max normalization method per dimension, tier thresholds, and a per-line justification for each weight. analysis.md Section 3 defends the weighting against the DTC business model and the cost-trap supplier. Requires-analysis condition satisfied. (`workflows/supply-chain-manager-starter.json (Supplier Performance Monitor node system prompt); analysis.md (Section 3 Supplier rubric defense)`) |
| lg_1 | 6 | 6 | Prompt separates five hard constraints (region match, transit<=deadline, weight capacity, perishable support) from soft preferences (cost, time slack, weight headroom) and instructs honest infeasibility reporting. Reasons over both classes explicitly. (`workflows/supply-chain-manager-starter.json (Logistics Coordinator (LLM) node system prompt)`) |
| lg_2 | 10 | 10 | pickCheapestFeasible() filters options against all five hard constraints (loose perishable string handling), returns null when infeasible, then min-by-cost reduce over total_cost_usd = weight_kg * cost_per_kg. Correct greedy cheapest-feasible planner. (`custom-nodes/classical-logistics.js:84-123`) |
| lg_3 | 2 | 2 | Prompt gives an ordered, literal test for use_classical_fallback (empty feasible set -> false, single option -> true, >20% cheapest margin -> true, else false) and the flag is in the output schema for the IF node to route on. (`workflows/supply-chain-manager-starter.json (Logistics Coordinator (LLM) node, '## use_classical_fallback' section)`) |
| fn_1 | 10 | 10 | Final Output node produces per-branch business-readable findings, closes the HTN loop by setting next_recommended_subgoal from the ordered subgoal list, and tallies llm_calls/tokens/cost. Robust extractJson salvage handles fenced/duplicated LLM output. analysis.md documents all four branch runs; demo is a Loom link (unverifiable in-repo) but full credit rests on the code quality and documented runs, not the demo alone. Demo credit restored: student submitted a working demo video link (a required deliverable); per instructor decision on 2026-07-18, a provided demo earns full credit for this criterion. (`workflows/supply-chain-manager-starter.json (Final Output code node); analysis.md (Section 4 run metrics)`) |
| Integrity deduction | — | 0 | Provided files MODIFIED — flagged, no deduction (build_workflow.py) |
| **Total** | **100** | **100** | |

### What went well
- All five code TODOs are correct and defensively written: movingAverage/seasonalIndex, eoq with domain guards, detectViolations catching both the viral (viral_spike) and dying/overstocked (declining+dead_stock) boundary cases, and pickCheapestFeasible with an honest null-on-infeasible result.
- The LLM system prompts are exemplary: every rubric-required element (planner schema + two HTN examples, 4-dimension supplier weights summing to 100 with a normalization method, logistics hard/soft split, per-flag exception actions) is present, well-specified, and grounded in the actual dataset.
- analysis.md (2082 words) is a genuinely reflective write-up: it proves the trend/season non-identifiability, defends every threshold against real SKUs, documents a caching experiment that backfired, and reports per-branch run metrics for all four routes.
- Real systems thinking beyond the TODOs: Parse Plan validates next_subgoal against the four real routes to fail loudly instead of the Switch's silent fallback no-op, and Final Output closes the HTN loop with next_recommended_subgoal.

### What to improve (actionable)
- Integrity check flagged build_workflow.py as modified (flag-only, no deduction). analysis.md Section 7 explains the six starter fixes and an added build_inclass_workflow.py; keeping starter-provided scaffolding files unmodified where possible would avoid the flag.
- The demo is a Loom link rather than an in-repo artifact, so the >=3-branch end-to-end run could only be corroborated from the analysis.md metrics table; committing a short recording or run transcript into the repo would make the FN-1/MP-1 demo requirement directly verifiable.
- seasonalIndex degenerates with 12 months of history (each calendar month appears once); this is well-acknowledged in the code and analysis, but a production version would need multi-year data or a peer-group prior to make the index meaningful.
- dead_stock is gated on the fixed on_hand > 5x reorder_point threshold; noting how sensitive the flag is to that multiplier (and whether months-of-cover would be a more robust signal) would tighten the already-strong reasoning.

### Automated checks
- ✅ All required files implemented
- ⚠️ Provided files MODIFIED — flagged, no deduction (build_workflow.py)
- ✅ 0/0 output artifacts committed
- ✅ Reflection 2082 words

### Resubmission
You may resubmit **once**. Push fixes to this repo, then notify the instructor; we'll re-grade as **Attempt 2 (final)**. This is attempt 1 of 2.

---
*Graded automatically with Claude Code against the course rubric. Questions → contact the instructor.*


---
<sub>🔎 **Autograder record** — attempt 1 of 2 · graded at commit `f443d56` · delivered 2026-07-18T20:42:53Z. Commits pushed to `main` after this timestamp are treated as a resubmission.</sub>
