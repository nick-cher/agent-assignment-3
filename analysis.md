# Assignment 3 Analysis

**Name:** Nick Cherepanov
**Course:** UCLA Extension, Agentic AI, Week 3 (Planning and Reasoning)

## Demo video

https://www.loom.com/share/b0003ee3b9ba471eba70532f63704323

---

## 1. Algorithm comparison

I am comparing SKU-007 (Wool Gloves, the viral case) against SKU-011 (Stainless Bottle, a well behaved evergreen SKU), forecasting January 2026.

**SKU-011, the easy case.** The classical engine computes a 3 month moving average of 76.0 and a seasonal index of 0.98, giving a forecast of 75 units. The LLM adjuster returned the same 75 units, delta 0, and said the series is flat and there is no directional signal worth acting on. This is the outcome I wanted. Holding the line has to be the default, otherwise the LLM just adds noise to a number the math already got right. 13 of the 15 SKUs came back untouched.

**SKU-007, the case the math gets wrong.** The classical engine computes a moving average of 376.7 and a seasonal index of 0.94, giving 354 units. The LLM revised this to 520, a 47 percent increase.

Both classical numbers are wrong, and they are wrong in interesting ways.

The moving average is wrong because it averages a curve that is still climbing. The last six months are [20, 41, 88, 173, 339, 518]. The mean of the final three is 376.7, but the most recent single month is 518 and rising. A trailing average of a rising curve always lags it.

The seasonal index is wrong for a subtler reason. `seasonalIndex` divides a month's demand by the mean of the whole series. The viral spike in the back half of the year dragged that series mean way up, which pushed January's index down to 0.94, implying gloves are an average month product. The other winter SKUs all land near 1.78. So the spike corrupted the very index that was supposed to correct for seasonality, and then that deflated index was multiplied back against an already lagging average. Two errors compounding in the same direction.

**Which I would trust.** The LLM's 520, and not because it is a better statistician. It is not. It got there because it knows what a wool glove is. I will expand on this in section 5, but the short version is that with 12 months of history there is exactly one observation per calendar month, so trend and season are mathematically inseparable for a single SKU. No arithmetic can distinguish "gloves are going viral" from "it is December." The model can, because it has seen the world. That is the entire reason there is an LLM at this seam.

---

## 2. EOQ assumption analysis

`detectViolations()` implements five flags.

| flag | threshold | fires on | handler action | agree? |
|---|---|---|---|---|
| `viral_spike` | mean(last 3) > 2.5 x mean(prior 9) | SKU-007 (6.24x) | reorder 558, above EOQ's 431 | yes |
| `declining` | mean(last 3) < 0.5 x mean(first 3) | SKU-013 (0.41x) | markdown, qty 0 | yes |
| `low_velocity` | annual demand < 60 | nothing in this dataset | n/a | yes, kept anyway |
| `long_lead_time` | lead time > 28 days AND CV > 0.5 | SKU-005, 006, 007, 009 | note the reorder point, do not inflate the order | yes |
| `dead_stock` | `declining` AND on_hand > 5x reorder point | SKU-013 | liquidate, qty 0 | yes |

Two threshold choices carry the weight here.

**Why 2.5 for `viral_spike`.** Every winter SKU (jacket, beanie, boots, blanket) ramps into Q4 at about 2.4x its own annual baseline. That is ordinary seasonality and EOQ's annual demand figure already absorbs it. Wool Gloves runs at 6.24x. A threshold of 2.5 sits above routine seasonality and well below the real anomaly, so the flag fires once and stays quiet four times. Set it at 2.0 and you flag every winter product in the catalogue.

**Why `declining` compares against the START of the year, not the rest of it.** This is the check I got wrong first. Comparing recent demand to the prior 9 months flags every summer SKU in December, because a beach towel in Q4 has obviously collapsed relative to its summer. But it is not dying, it is winter. Compared against its own January, a seasonal product ends the year roughly where it began (Beach Chair: 1.31x), while a structurally dying product ends far below it (Wired Earbuds: 0.41x). Same data, different denominator, and the false positives disappear.

**`dead_stock` and the overstock trap.** My first version flagged any SKU holding more than 5x its reorder point. It fired on Sunglasses, Beach Towel and Swim Trunks, and the handler recommended marking all of them down. That is wrong. By months of cover, Sunglasses (6.9 months) and Wired Earbuds (6.8 months) are indistinguishable. The pile size is not the signal. What matters is whether demand is ever coming back for it: a seasonal glut clears next season, a glut on a decaying product never clears. So overstock only counts as a violation in conjunction with decline.

**Perishability: deliberately not implemented.** EOQ's holding cost is linear in time, which is wrong for anything with a shelf life, where spoilage is a cliff rather than a slope. None of the 15 demo SKUs are perishable and the dataset has no expiry column, so the check could never fire. A real implementation would need it, and would probably need to replace EOQ entirely for those SKUs rather than just flagging them.

**One thing EOQ never told me.** The formula answers "how much per order" and never "should we order at all." Nothing in it looks at the reorder point. Early on, the handler cheerfully recommended ordering 246 more Sunglasses while we were holding 420 against a reorder point of 80. I had to add that gate explicitly in the exception prompt. EOQ is not wrong about this so much as silent, which is worse, because silence reads as consent.

---

## 3. Supplier rubric defense

**Assumed business model: direct to consumer e-commerce.** We sell to consumers who expect the thing to arrive on time and to work. A late delivery is a cancelled order and a support ticket. A defect is a return, a refund, and a public one star review that suppresses future sales. Our scarce resource is customer trust.

**Weights, out of 100:** reliability 35, quality 30, lead time 20, cost 15.

Reliability is the largest single driver of a bad customer outcome, because a missed date breaks a promise we already made to a buyer. Quality is close behind: a defect is strictly worse than a delay, since it costs the shipping, the refund, the replacement, and the review. It sits at 30 rather than 35 only because our defect rates are low in absolute terms. Lead time is real but it is a planning input, not a failure. A long lead time is survivable with a higher reorder point; an unreliable one is not. Cost is last, deliberately.

**Cost is last because this roster is a trap.** SUP-002 (Pacific Rim) has the best payment terms on the board, 60 days, and scored a perfect 15 out of 15 on cost. It also has the worst on time rate (0.84) and the worst defect rate (0.022). Any rubric that lets cost dominate confidently recommends our worst supplier. Weighting it at 15 is a decision, not an oversight.

**Result from a real run.** Top: SUP-006 Bavaria Paper Mills, 88/100, preferred (best on time at 0.98, best defect rate at 0.005). Bottom: SUP-002 Pacific Rim, 28/100, deprioritize, with the model noting that its "best payment terms mask poor reliability." That matches my intuition exactly. The ranking is the one I would defend to a buyer.

A hospital supply chain would weight this very differently. There, a stockout can be a fatality, so lead time and reliability would crowd out almost everything else, and I would expect cost to fall to near zero weight.

---

## 4. Run metrics

Four end to end runs on the final code, one per branch, driven by varying the goal text.

| goal | branch | LLM calls | tokens in | tokens out | cost | wall clock |
|---|---|---|---|---|---|---|
| default Q1 plan | forecast | 16 | 20,904 | 1,854 | $0.0905 | 17.5s |
| forecast given | inventory | 16 | 20,350 | 1,117 | $0.0778 | 12.8s |
| suppliers only | supplier | 2 | 3,918 | 803 | $0.0238 | 17.6s |
| carriers only | logistics | 4 | 8,378 | 939 | $0.0392 | 14.7s |

All four land under the $0.10 target, but the spread is nearly 4x and that is the interesting part.

**What surprised me.** Cost is driven almost entirely by how many times a node fires, not by how much it thinks. The forecast and inventory branches are per item LLM nodes, so they make 15 calls each and re-send the entire system prompt every single time. The supplier branch scores all six suppliers in one call and costs a quarter as much. Input tokens, not output tokens, are the bill: 20,904 in against 1,854 out on the forecast branch.

My first draft of the forecast adjuster cost $0.11 on its own, over budget on a single node, because the model was writing 400 word explanations per SKU. Capping the reasoning field at 30 words cut output tokens from 6,406 to 1,378 with no loss of decision quality.

**Prompt caching backfired.** I tried marking the system prompt as an ephemeral cache block, expecting the 15 per SKU calls to share it. Measured result: 14,854 cache write tokens against 1,061 cache read. n8n dispatches the per item HTTP requests in parallel, so all 15 race and every one of them misses a cache none of them has written yet. Cache writes bill at 1.25x normal input, so the branch got more expensive, not less ($0.0777 to $0.0868). I reverted it. Caching only pays when calls are sequential or the cached prefix outlives a single burst.

---

## 5. The four primer questions

**1. Where does the classical layer get it wrong, and where does the LLM?**

Classical wrong, LLM catches: SKU-007. The moving average lags a rising curve and the seasonal index is corrupted by the very spike it should be correcting for, so the math says 354 when the truth is closer to 520. The LLM catches it because it knows a wool glove is a winter product and that a 6x ramp exceeds what winter explains.

LLM wrong, classical catches: the logistics branch, and I saw this happen. Given three shipping requests, the LLM is perfectly capable of picking a carrier that misses a deadline or exceeds a weight cap if the prose is persuasive enough, because hard constraints are just words to it. `pickCheapestFeasible()` filters on all five constraints mechanically and cannot be talked out of them. On the two purely numeric requests the greedy planner reproduced the LLM's answers exactly (DHL at $10,030, Hapag-Lloyd at $1,980), which is the point: it is a deterministic, auditable baseline the LLM's plan can be checked against.

**2. What if the planner emitted `next_subgoal: "audit_warehouse"`?**

Today, before my fix: nothing. The Switch is configured with `fallbackOutput: "extra"`, which creates a fifth output, and nothing is connected to it. The item routes into that dead output, no branch runs, no error is raised, and the execution ends looking like a success. A silent no-op is the worst failure an agent can have, because nothing downstream can tell "the plan was empty" apart from "the plan ran."

My fix is in `Parse Plan`: validate `next_subgoal` against the four routes that actually exist and throw if it is not one of them. The LLM's output is untrusted input to a deterministic router, so it gets validated at the boundary like any other untrusted input, and it fails loudly. This also catches the near misses that are easy to overlook, like `"Forecast"` with a capital F or a trailing space, since the Switch compares case sensitively with strict type validation.

**3. Why is EOQ confidently wrong for SKU-013, and which flag saves you?**

EOQ takes annual demand as a given and assumes it is constant. SKU-013's trailing annual demand is 948 units, but that total is propped up by early months that will never repeat: the series slides monotonically all year and ends at 0.41x its January level. Feed a stale 948 into the formula and it returns a perfectly precise 397 units, for a product that already has 540 sitting on the shelf against a reorder point of 80. The formula is not broken, its input assumption is, and it has no way to notice.

`declining` is the flag that saves you, and `dead_stock` (decline plus a pile more than 5x the reorder point) is what escalates it from "stop buying" to "actively liquidate." The handler recommends liquidate at qty 0.

**4. Why is supplier scoring an LLM job and EOQ a classical job? What if you swapped them?**

EOQ is a closed form solution. There is one right answer, `sqrt(2DS/H)`, it is cheap, exact, reproducible, and auditable. Asking an LLM to compute a square root is paying dollars for arithmetic while introducing a chance of getting it wrong.

Supplier scoring has no correct answer at all. It is a value judgement about what the business cares about, and the weights ARE the answer. The reason it is an LLM job is not that the arithmetic is hard (min-max normalization is trivial), it is that the job includes reading a roster and noticing that the cheapest supplier is also the worst one, and that this matters for a DTC brand in a way it would not for a wholesaler.

Swapped, both get worse in opposite ways. A classical supplier scorer is just a weighted sum with hardcoded weights: it will happily rank suppliers, but the moment the business changes (we move into perishables, or into a hospital supply market) someone has to go re-derive the weights by hand, and the model can never explain itself. An LLM-driven EOQ is worse: you would be paying per call for a formula, accepting nondeterminism in a number that gets multiplied by real money, and losing the ability to reproduce a purchase order.

The general rule I take from this: use the classical layer where the answer is computable and the assumptions are checkable, use the LLM where the question is "is this normal?" or "what do we care about?", and spend most of your engineering effort on the seam between them. Almost every bug I hit this week was at that seam, not inside either layer.

---

## 6. Deviations from the starter, and why

The starter workflow does not run as shipped. Documenting the fixes, since they change files I was not strictly asked to touch.

1. **`Build Context Summary` fired before its inputs existed.** Four CSV read branches fan out from `Set Goal` and converge on this node, which reaches across all of them with `$('Read Sales JSON')`. n8n runs it as soon as the first branch lands, so three of the four had not executed and it threw `Node 'Read Sales JSON' hasn't been executed`. Reproduced on both n8n 2.29.10 and 2.19.5 (the version the docs pin), so it is not version drift. Added a guard that returns `[]` until all four reads have landed, so it emits once, on the final invocation.

2. **File access sandbox.** n8n 2.2x onward restricts the Read/Write File node to `/home/node/.n8n-files`, so every CSV read failed with "Access to the file is not allowed." Allow-listed `/data` via `N8N_RESTRICT_FILE_ACCESS_TO` in `docker-compose.yml`. I also pinned the image to `2.19.5` to match `docs/setup.md`, since `:latest` is a moving target.

3. **Branch code nodes read the wrong input.** `demand-forecast.js` and `eoq-optimizer.js` shipped with `$input.all()` and comments claiming the sales and inventory rows arrive that way. They do not: these nodes sit on a Switch branch, so their input is the planner's plan object. `eoq-optimizer.js` failed silently as a result (it partitioned the plan, found zero inventory rows, and its loop never ran, so the TODO never even threw). Both now use cross node references, matching the pattern the provided `Build Shipping Requests` node already used.

4. **The logistics IF node could never fire.** It routes on `$json.use_classical_fallback`, but its input is the raw Anthropic envelope, and there is no parse node between them, so the field was always undefined. Its condition now parses the model's JSON (tolerating fences) and defaults to false, so a malformed reply keeps us on the LLM path rather than silently diverting.

5. **`Build Shipping Requests` emitted 13 items** (3 requests plus 10 carrier options) into a per item LLM node, which would have made 13 API calls per run, ten of them handing a carrier option to a prompt expecting a shipping request. It now emits the 3 requests, and both consumers pull the catalogue directly.

6. **`Merge Subgoal Results` ran twice on the logistics branch**, once per arriving batch, so `Final Output` produced two partial summaries. Gave the classical fallback its own merge input so Merge waits and emits once.

I also set `temperature: 0` on all LLM calls. At the default, the same goal routed to different branches across runs, which makes any failure impossible to attribute. `docs/setup.md` section 9 suggests this while iterating.

The topology is unchanged: same 25 nodes, same five components, no rewiring beyond the merge input index.
