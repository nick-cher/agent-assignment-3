# Assignment 3 Analysis

**Name:** Nick Cherepanov
**Course:** UCLA Extension, Agentic AI, Week 3 (Planning and Reasoning)

## Demo video

https://www.loom.com/share/b0003ee3b9ba471eba70532f63704323

---

## 1. Algorithm comparison

Comparing SKU-007 (Wool Gloves, the viral case) against SKU-011 (Stainless Bottle, a well behaved evergreen SKU), forecasting January 2026.

**SKU-011, the easy case.** Moving average 76.0, seasonal index 0.98, classical forecast 75 units. The LLM returned the same 75, delta 0, noting the series is flat with no directional signal. This is the outcome I wanted: holding the line has to be the default, or the LLM just adds noise to a number the math already got right. 13 of 15 SKUs came back untouched.

**SKU-007, the case the math gets wrong.** Moving average 376.7, seasonal index 0.94, classical forecast 354. The LLM revised to 520, up 47 percent.

Both classical numbers are wrong, and they are wrong in compounding ways.

The moving average is wrong because it averages a curve that is still climbing. The last six months are [20, 41, 88, 173, 339, 518]. The mean of the final three is 376.7, but the most recent month alone is 518 and rising. A trailing average of a rising curve always lags it.

The seasonal index is wrong for a subtler reason. `seasonalIndex` divides a month's demand by the mean of the whole series. The viral spike in the back half of the year dragged that mean up, pushing January's index down to 0.94, implying gloves are an average-month product. The other winter SKUs all sit near 1.78. So the spike corrupted the very index meant to correct for seasonality, and that deflated index was then multiplied against an already lagging average.

**Which I would trust: the LLM's 520.** Not because it is a better statistician. It is not. With 12 months of history each calendar month appears exactly once, so trend and season are mathematically inseparable for a single SKU. I proved this to myself by trying to deseasonalize the series: dividing each month by its own index returns the series mean for every month, and the ratio flattens to exactly 1.0 for all 15 SKUs. The signal is destroyed. No arithmetic can distinguish "gloves are going viral" from "it is December," because Snow Boots ramp every December too. The model can, because it knows what a wool glove is. That is the entire reason an LLM sits at this seam.

---

## 2. EOQ assumption analysis

| flag | threshold | fires on | action | agree? |
|---|---|---|---|---|
| `viral_spike` | mean(last 3) > 2.5 x mean(prior 9) | SKU-007 (6.24x) | reorder 558, above EOQ's 431 | yes |
| `declining` | mean(last 3) < 0.5 x mean(first 3) | SKU-013 (0.41x) | markdown, qty 0 | yes |
| `low_velocity` | annual demand < 60 | nothing in this data | n/a | yes, kept |
| `long_lead_time` | lead time > 28d AND CV > 0.5 | SKU-005/006/007/009 | fix the reorder point, do not inflate the order | yes |
| `dead_stock` | `declining` AND on_hand > 5x reorder point | SKU-013 | liquidate, qty 0 | yes |

**Why 2.5 for `viral_spike`.** Every winter SKU ramps into Q4 at about 2.4x its annual baseline, ordinary seasonality that EOQ's annual demand already absorbs. Wool Gloves runs at 6.24x. A bar at 2.5 sits above routine seasonality and below the real anomaly, so it fires once and stays quiet four times. At 2.0 it would flag every winter product in the catalogue.

**Why `declining` compares against the START of the year.** I got this wrong first. Comparing recent demand to the prior 9 months flags every summer SKU in December: a beach towel in Q4 has collapsed relative to its summer, but it is not dying, it is winter. Against its own January, a seasonal product ends where it began (Beach Chair 1.31x) while a dying one ends far below (Wired Earbuds 0.41x). Same data, different denominator, and the false positives vanish.

**`dead_stock` and the overstock trap.** My first version flagged anything holding more than 5x its reorder point. It fired on Sunglasses, Beach Towel and Swim Trunks and marked all three down. That is wrong. By months of cover, Sunglasses (6.9) and Wired Earbuds (6.8) are indistinguishable. Pile size is not the signal; whether demand is coming back is. A seasonal glut clears next season, a glut on a decaying product never clears. So overstock only counts as a violation in conjunction with decline.

**Perishability: deliberately omitted.** EOQ's holding cost is linear in time, wrong where spoilage is a cliff. No demo SKU is perishable and there is no expiry column, so the check could never fire. A real system would need it, and would likely replace EOQ entirely for those SKUs.

**What EOQ never says.** It answers "how much per order," never "should we order at all," and never looks at the reorder point. It first had me ordering 246 more Sunglasses while holding 420 against a reorder point of 80. EOQ is not wrong here so much as silent, which is worse, because silence reads as consent.

---

## 3. Supplier rubric defense

**Assumed business model: direct to consumer e-commerce.** A late delivery is a cancelled order and a support ticket. A defect is a return, a refund, and a public one-star review that suppresses future sales. Our scarce resource is customer trust.

**Weights out of 100:** reliability 35, quality 30, lead time 20, cost 15.

Reliability is the largest driver of a bad customer outcome, because a missed date breaks a promise we already made to a buyer. Quality is close behind, since a defect costs the shipping, the refund, the replacement and the review; it sits at 30 only because our defect rates are low in absolute terms. Lead time is real but it is a planning input, not a failure: a long lead time is survivable with a higher reorder point, an unreliable one is not.

**Cost is last because this roster is a trap.** SUP-002 (Pacific Rim) has the best payment terms on the board, 60 days, and scored a perfect 15 of 15 on cost. It also has the worst on-time rate (0.84) and worst defect rate (0.022). Any rubric that lets cost dominate confidently recommends our worst supplier. Weighting it at 15 is a decision, not an oversight.

**From a real run.** Top: SUP-006 Bavaria, 88/100, preferred (best on-time 0.98, best defect 0.005). Bottom: SUP-002, 28/100, deprioritize, with the model noting its "best payment terms mask poor reliability." That matches my intuition. A hospital supply chain would weight this very differently: a stockout can be a fatality, so reliability and lead time would crowd out cost almost entirely.

---

## 4. Run metrics

Four end-to-end runs on the final code, one per branch, driven by varying the goal text.

| goal | branch | LLM calls | tokens in | tokens out | cost | wall clock |
|---|---|---|---|---|---|---|
| default Q1 plan | forecast | 16 | 20,904 | 1,854 | $0.0905 | 17.5s |
| forecast given | inventory | 16 | 20,350 | 1,117 | $0.0778 | 12.8s |
| suppliers only | supplier | 2 | 3,918 | 803 | $0.0238 | 17.6s |
| carriers only | logistics | 4 | 8,378 | 939 | $0.0392 | 14.7s |

All four land under the $0.10 target, but the 4x spread is the interesting part.

**What surprised me.** Cost is driven by how many times a node fires, not how much it thinks. The forecast and inventory branches are per-item LLM nodes: 15 calls each, re-sending the whole system prompt every time. The supplier branch scores all six suppliers in one call and costs a quarter as much. Input tokens are the bill (20,904 in against 1,854 out). My first adjuster cost $0.11 alone because the model wrote 400-word explanations per SKU; capping `reasoning` at 30 words cut output from 6,406 to 1,378 tokens with no loss of decision quality.

**Prompt caching backfired.** Marking the system prompt as an ephemeral cache block produced 14,854 cache-write tokens against 1,061 cache-read. n8n dispatches the per-item calls in parallel, so all 15 race and every one misses a cache none has written yet. Writes bill at 1.25x input, so the branch got dearer ($0.0777 to $0.0868). Reverted. Caching only pays when calls are sequential.

---

## 5. The four primer questions

**1. Where does each layer get it wrong?** Classical wrong, LLM catches: SKU-007, above. LLM wrong, classical catches: logistics, where hard constraints are only words to a model. `pickCheapestFeasible()` enforces all five mechanically and cannot be argued out of them. On the two purely numeric requests it reproduced the LLM's picks exactly (DHL $10,030, Hapag-Lloyd $1,980).

**2. If the planner emitted `next_subgoal: "audit_warehouse"`?** Before my fix, nothing at all. The Switch's `fallbackOutput: "extra"` creates a fifth output nothing is connected to, so the run ends with no branch, no error, and the appearance of success. A silent no-op is the worst failure an agent can have: nothing downstream can tell "the plan was empty" from "the plan ran." `Parse Plan` now validates `next_subgoal` against the four real routes and throws otherwise, because LLM output is untrusted input to a deterministic router.

**3. Why is EOQ confidently wrong for SKU-013?** It assumes constant demand. The trailing annual figure of 948 is propped up by months that will never repeat, since the series ends at 0.41x its January level. Feed 948 in and it returns a precise 397 units for a product already holding 540 against a reorder point of 80. The formula is not broken, its input assumption is, and it cannot notice. `declining` catches it; `dead_stock` escalates to liquidate.

**4. Why supplier scoring for the LLM and EOQ for the classical layer?** EOQ is a closed form with one right answer: cheap, exact, reproducible. Paying a model to compute a square root buys nondeterminism in a number multiplied by real money. Supplier scoring has no correct answer; it is a judgement about what the business values, and the weights ARE the answer. Swapped, the scorer becomes a hardcoded sum that cannot explain itself, and EOQ becomes irreproducible.

---

## 6. Planner decomposition (MP-2)

The two worked examples in the planner prompt teach one thing: `next_subgoal` is the first subgoal whose inputs EXIST, not the first the goal happens to mention. The default goal names stockout risk first, and without the examples the planner dispatched `inventory`, sizing reorders against demand nobody had projected. It also read the context summary's stockout flags as evidence the forecast was already done, so the prompt now states that only the goal text can declare a step complete. With both in place it decomposes into all four subgoals in dependency order and dispatches `forecast`, then `Final Output` names `inventory` as the next step, which closes the loop.

---

## 7. Deviations from the starter

The starter does not run as shipped. Six fixes, all outside the TODOs. Topology unchanged: same 25 nodes, same five components.

1. **`Build Context Summary` fired before its inputs existed.** Four read branches converge on it and n8n runs it as soon as the first lands, so `$('Read Sales JSON')` threw "hasn't been executed." Reproduced on 2.29.10 and 2.19.5 alike, so not version drift. Guarded to return `[]` until all four have run.
2. **File sandbox.** n8n 2.2x restricts reads to `/home/node/.n8n-files`, failing every CSV read. Allow-listed `/data`; pinned the image to 2.19.5 per `docs/setup.md`.
3. **Branch code nodes read the wrong input.** On a Switch branch, `$input` is the plan object, not the data. `eoq-optimizer.js` failed *silently*: it partitioned the plan, found zero rows, and its loop never ran, so its TODO never even threw. Both now use cross-node references, as the provided `Build Shipping Requests` node already did.
4. **The logistics IF could never fire.** It routes on `$json.use_classical_fallback`, but its input is the raw Anthropic envelope with no parse node, so the field was always undefined.
5. **`Build Shipping Requests` emitted 13 items** (3 requests plus 10 carrier options) into a per-item LLM node: 13 calls per run, ten of them handing a carrier option to a prompt expecting a request. Now emits 3.
6. **Merge ran twice on the logistics branch**, yielding two partial summaries. Gave the fallback its own merge input.

I also set `temperature: 0` (per `docs/setup.md` §9): at the default, one goal routed to different branches across runs, making failures impossible to attribute.
