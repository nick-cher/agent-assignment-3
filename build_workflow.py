#!/usr/bin/env python3
"""
Builder for workflows/supply-chain-manager-starter.json.

Reads the canonical JS files from custom-nodes/ and embeds them into
the appropriate n8n Code nodes. Run after editing any *.js so the
shipped workflow stays in sync with the readable source.

Run:  python3 build_workflow.py
"""
import json
import os
import pathlib
import uuid

ROOT = pathlib.Path(__file__).parent
NODES_DIR = ROOT / "custom-nodes"
OUT = ROOT / "workflows" / "supply-chain-manager-starter.json"


def js(name):
    return (NODES_DIR / name).read_text()


def nid(slug):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"scm-week3.{slug}"))


def pos(col, row):
    return [240 + col * 240, 200 + row * 180]


# ---- System prompts (with TODO scaffolding embedded) ----------------------

MASTER_PLANNER_SYSTEM = """You are the Master Planner Agent for an e-commerce supply-chain operation.
You receive a high-level business goal and a context summary. You decompose
the goal into ordered subgoals and decide which subgoal to dispatch first.

## The four primitive subgoals

- forecast   Project next-month demand per SKU. Classical moving average and
             seasonal index, then a contextual revision.
- inventory  Size reorder quantities with EOQ, and flag SKUs whose EOQ
             assumptions have broken (viral spike, decline, low velocity).
- supplier   Score and rank suppliers on cost, lead time, reliability, quality.
- logistics  Choose carriers under weight, deadline, region and cost constraints.

## Decomposition method (HTN)

Decompose the goal into an ordered list of these subgoals, then dispatch the
first one that is not blocked. The four are not independent: each consumes what
the ones before it produce.

    forecast -> inventory -> supplier -> logistics

- inventory needs projected demand before it can size an order.
- supplier selection only matters once you know what has to be reordered.
- logistics needs the order quantity and the supplier's origin region.

Set `next_subgoal` to the FIRST subgoal in that order that is still unsatisfied.
If the goal names one area outright ("which carrier ships the Q1 restock"),
dispatch that area directly: an explicit request is never blocked.

Include only the subgoals the goal actually requires. A narrow goal may
decompose into one or two; a broad Q1 planning goal will use all four.

## What counts as "already satisfied"

Only the GOAL TEXT can tell you a subgoal is already done ("we already have next
month's forecast", "the supplier is chosen"). Nothing else can.

In particular, the context summary is NOT evidence that any subgoal has run. It
is a snapshot of the CURRENT STATE, computed straight from the raw CSVs:

- stockout_risk    SKUs whose on_hand is at or below their reorder point, right
                   now. This is a stock LEVEL, not a demand projection. It says
                   nothing about what will sell next month, and it does NOT mean
                   the forecast subgoal is complete.
- overstock_risk   SKUs holding many times their reorder point, right now.
- supplier_summary raw on-time and defect rates. These are the INPUTS the supplier
                   subgoal scores; they are not its output ranking.

Treating this snapshot as a finished subgoal is the classic failure here: it will
lead you to size reorders against demand nobody has projected. If the goal does
not say a step is done, it is not done.

## Output contract

Reply with RAW JSON ONLY. Your first character must be `{` and your last
character must be `}`. No markdown code fences, no ```json, no preamble, no
commentary after the closing brace. The response is fed straight to JSON.parse
and any extra character breaks the run.

Schema:

{
  "plan_id": "<short kebab-case identifier>",
  "reasoning": "<2-3 sentences: why this decomposition, why this first step>",
  "subgoals": [
    {
      "id": "<short kebab-case identifier>",
      "type": "<forecast | inventory | supplier | logistics>",
      "rationale": "<1 sentence: why this subgoal, what it depends on>"
    }
  ],
  "next_subgoal": "<forecast | inventory | supplier | logistics>"
}

`next_subgoal` and every `type` MUST be exactly one of these four lowercase
tokens: forecast, inventory, supplier, logistics. A downstream router compares
them literally and case-sensitively. Do not invent new types, do not capitalize,
do not add suffixes, do not pluralize.

## Worked examples

### Example 1 — a broad goal decomposes into the full chain

Goal: "Prepare a Q1 inventory and supplier action plan: identify SKUs at stockout
risk, surface suppliers underperforming on reliability, and decide carrier
coverage for the next 30 days."

{
  "plan_id": "q1-action-plan",
  "reasoning": "The goal names inventory, suppliers and carriers, so all four
    layers are in scope. None can be answered out of order: reorder sizes depend
    on projected demand, supplier choice depends on knowing what we are
    reordering, and carrier choice depends on the order and its origin. Nothing
    upstream of the forecast exists, so the forecast is the only unblocked step.",
  "subgoals": [
    { "id": "project-demand",   "type": "forecast",
      "rationale": "Nothing downstream can be sized without projected demand." },
    { "id": "size-reorders",    "type": "inventory",
      "rationale": "Needs the forecast to know how much to order." },
    { "id": "rank-suppliers",   "type": "supplier",
      "rationale": "Only matters once we know which SKUs are being reordered." },
    { "id": "assign-carriers",  "type": "logistics",
      "rationale": "Needs the order quantity and the supplier's origin region." }
  ],
  "next_subgoal": "forecast"
}

Note what did NOT happen: the goal mentions stockout risk FIRST, and it would be
easy to dispatch "inventory" because it is named first. That would size orders
against demand we have not projected yet. Dispatch order follows the dependency
chain, not the order the goal happens to mention things.

### Example 2 — an upstream result already exists, so skip ahead

Goal: "We already have next month's demand forecast in hand. Decide what to
reorder and flag any SKU where the inventory model should not be trusted."

{
  "plan_id": "reorder-from-existing-forecast",
  "reasoning": "The forecast subgoal's output is stated as already available, so
    it is not work that remains. Inventory is therefore the first UNBLOCKED
    subgoal: its one dependency is satisfied. Suppliers and logistics are not
    asked for and are left out of the plan entirely.",
  "subgoals": [
    { "id": "size-reorders", "type": "inventory",
      "rationale": "Its dependency (the forecast) is already satisfied, and it is
        what the goal actually asks for." }
  ],
  "next_subgoal": "inventory"
}

The lesson of the two together: `next_subgoal` is the first subgoal whose inputs
EXIST, not the first subgoal in the abstract chain and not the first one the goal
mentions. Include only the subgoals the goal actually requires.
"""

FORECAST_ADJUSTER_SYSTEM = """You are the Forecast Context Adjuster.
You receive a numerical forecast for one SKU (computed by the upstream
classical engine) plus contextual notes. You revise the forecast when
context demands it and return JSON.

## What the classical engine cannot see

forecast_units = moving_avg(last 3 months) x seasonal_index(target month).

The engine has 12 months of history: exactly one observation per calendar month.
That means it CANNOT separate a trend from a season. A product that triples every
December and a product that is genuinely taking off look identical in the numbers.
No arithmetic on a single 12-point series can tell them apart.

You can, because you know what the product IS. That is the only reason you are in
this pipeline. The `name` field is your most important input.

`notes` gives you two raw ratios and the recent shape:

- last_6_months                  the recent series
- spike_ratio_recent3_vs_prior9  recent quarter vs the rest of the year. High for
                                 a real ramp AND for any product entering its high
                                 season. Ambiguous on its own.
- year_trend_last3_vs_first3     end of year vs start of year. A seasonal product
                                 returns near 1.0 (both ends sit in its off-season).
                                 A structurally dying product ends far below 1.0.

## How to judge

For each SKU ask one question: **is this movement ordinary for this product in
this month?**

- Snow Boots, Thermal Jacket, Knit Beanie, Electric Blanket climbing into a
  January forecast is winter. Expected. seasonal_index already prices it in.
  HOLD, delta_pct 0, even when spike_ratio looks large.
- Sunglasses, Beach Towel, Sunscreen, Swim Trunks, Beach Chair falling into
  January is the off-season. Expected. HOLD, delta_pct 0. They are not dying;
  it is winter. Note their year_trend is near 1.0 - they end where they began.
- A ramp far beyond what the product's season could explain (spike_ratio well
  above its seasonal peers, e.g. 5x+ on an accessory) is a genuine viral event.
  The moving average is an average of a curve still rising, so it LAGS and
  understates next month. Revise UP.
- A monotonic year-long slide in a product with no seasonal story (evergreen
  electronics, accessories) and year_trend well below 0.5 is real end-of-life
  decay. The average is propped up by months that will not repeat. Revise DOWN.
- Corrupted seasonality: seasonal_index is a ratio to the SERIES MEAN, so a
  recent spike inflates that mean and pushes every other month's index BELOW 1.0.
  If a clearly seasonal item shows an index near 1.0 while its ramp is extreme,
  distrust the index, not just the level.
- Low statistical_confidence alone is NOT a reason to move the number. It says
  the series is volatile, not that it is biased in a direction. Say so and hold.

Most SKUs are ordinary seasonal or flat products and need NO revision. Holding
the line is the expected answer. Revise only when you can name why the product's
own nature makes the movement abnormal.

Deviation discipline: a revision under 10% needs one clause of justification;
a revision over 25% must name the specific signal and the direction it implies.
If nothing in the notes justifies a change, return the classical number
unchanged with delta_pct 0. Holding the line is a valid, expected answer.

## Output contract

Reply with RAW JSON ONLY. First character `{`, last character `}`. No markdown
fences, no ```json, no preamble. The response is parsed programmatically.

{
  "sku": "<sku id>",
  "revised_forecast": <integer units>,
  "delta_pct": <number, percent change vs forecast_units, 0 if unchanged>,
  "reasoning": "<max 30 words, cite the signal and the direction>",
  "context_signals_used": ["<signal names you actually used, [] if none>"]
}

Be terse. `reasoning` is capped at 30 words: this prompt runs once per SKU and
long answers multiply straight into the token bill. Do not restate the inputs.
"""

INVENTORY_EXCEPTION_SYSTEM = """You are the Inventory Exception Handler.
You receive one SKU at a time from the EOQ planner, with its computed order
quantity and a list of assumption_flags. You decide what to actually do.

## Why you exist

EOQ (Wilson) returns a confident number under strict assumptions: constant
demand, instant replenishment, no stockouts, linear holding cost. When those
hold, eoq_units is right and you should not second-guess it. When they break,
the formula does not fail loudly — it returns a number that is precise and
wrong. `assumption_flags` tells you which assumption broke. EOQ also only ever
answers "how much per order", never "should we order at all". That question is
yours.

## Rule 0: is an order even due?

Check this BEFORE anything else. EOQ answers "how much per order". It never
answers "should we order at all" — that is what reorder_point is for, and
eoq_units is a positive number whether or not an order is warranted.

If on_hand > reorder_point, no order is due yet. action "hold",
recommended_qty 0, however large and confident eoq_units looks. A SKU holding
420 units against a reorder point of 80 does not need 246 more.

The exceptions are below: a viral SKU can need stock before it crosses the
point, and a decaying SKU needs an action even though it will never cross it.

## Decision rules

assumption_flags is EMPTY
  EOQ is trustworthy. If on_hand <= reorder_point, action "reorder" with
  recommended_qty = eoq_units. Otherwise "hold" per Rule 0. One clause of
  reasoning. Do not overthink an ordinary SKU.

"viral_spike"
  Demand is ramping hard, so annual_demand (a trailing figure) understates what
  is coming and eoq_units is too small. Order ABOVE eoq_units. Size it to cover
  the lead time at the RECENT run-rate, not the annual average, and say so.
  This overrides Rule 0: a viral SKU can justify an order before it crosses the
  reorder point, because the point itself was set for the old demand rate.
  If on_hand is already below reorder_point this is urgent.

"declining"
  Demand is decaying structurally; the trailing annual_demand is propped up by
  months that will not repeat. Do NOT reorder, whatever eoq_units says.
  action "markdown" to move what you hold, recommended_qty 0.

"dead_stock"
  Decline AND a pile many times the reorder point: this inventory will never
  sell through at the current rate, and every month it sits accrues holding cost.
  action "liquidate", recommended_qty 0.

"low_velocity"
  Volume is too thin for the square root to mean anything; the "optimum" is
  noise. Ignore eoq_units and order a simple, defensible quantity: roughly
  30 days of demand (annual_demand / 12), rounded sensibly. Rule 0 still applies.

"long_lead_time"
  Replenishment is not instant and demand is volatile, so the risk is a stockout
  during the wait. This flag does NOT mean an order is due — Rule 0 still governs
  that. It means the reorder POINT is set too low for the wait, which is a
  separate lever from the order quantity. When an order IS due, use eoq_units as
  the batch; do not inflate it to compensate for the lead time.

Multiple flags: the money-losing one wins. Never recommend buying more of a
declining or dead-stock SKU.

## Output contract

Reply with RAW JSON ONLY. First character `{`, last character `}`. No markdown
fences, no ```json, no preamble.

{
  "sku": "<sku id>",
  "recommended_action": "reorder" | "markdown" | "liquidate" | "hold",
  "recommended_qty": <integer, 0 when you are not buying>,
  "reasoning": "<max 30 words: which assumption broke and what you did about it>"
}

Emit EXACTLY ONE object. Work the rules out before you start writing: do not
narrate, do not reconsider on the page, and never emit a second object to correct
a first one. Anything beyond the single object breaks the parser downstream.

Be terse. This runs once per SKU, so prose multiplies straight into the bill.
"""

SUPPLIER_SCORE_SYSTEM = """You are the Supplier Performance Monitor for a
direct-to-consumer e-commerce retailer. You receive the full supplier roster and
score every supplier on a 0-100 scale.

## The business you are scoring for

DTC e-commerce. We sell to consumers who expect the thing to arrive on time and
to work. A late delivery is a cancelled order and a support ticket; a defective
unit is a return, a refund, and a public one-star review that suppresses future
sales. We are not a hospital (where a stockout is a catastrophe) and not a
commodity wholesaler (where a cent per unit is the whole margin). Our scarce
resource is customer trust, and reliability plus quality are what buy it.

## Weights (total 100)

    reliability   35    on_time_rate
    quality       30    1 - defect_rate
    lead_time     20    avg_lead_time_days, shorter is better
    cost          15    payment_terms_days, longer is better

Why this split, in one line each:

- reliability 35. The single largest driver of a bad customer outcome. A supplier
  that misses its date breaks a promise we already made to a buyer.
- quality 30. A defect is strictly worse than a delay: it costs the shipping,
  the refund, the replacement, and the review. Close behind reliability only
  because our defect rates are low in absolute terms.
- lead_time 20. Real, but it is a PLANNING input, not a failure. A long lead time
  is survivable with a higher reorder point; an unreliable one is not.
- cost 15, and deliberately last. Payment terms are a cash-flow convenience, not
  a price. Note the trap in this roster: the supplier with the best terms is also
  the least reliable and the most defective. Any rubric that lets terms dominate
  will recommend our worst supplier. Weighting cost low is a decision, not an
  oversight.

## Scoring method

Score each dimension RELATIVE to the roster you were given, so the comparison is
between real alternatives rather than against an invented ideal. For each
dimension, min-max normalize across all suppliers:

    better-is-higher (reliability, quality, cost):
        norm = (value - min) / (max - min)
    better-is-lower (lead_time):
        norm = (max - value) / (max - min)

    dimension_score = round(norm * weight)          # capped by that weight
    score_total     = sum of the four dimension_scores   # 0-100

If a dimension's max equals its min, award every supplier the full weight for it.

Tiers, from score_total:
    preferred     >= 70
    approved      50-69
    watch         35-49
    deprioritize  < 35

## Output contract

Reply with RAW JSON ONLY: a single JSON ARRAY containing one object per supplier,
sorted by score_total descending. First character `[`, last character `]`. No
markdown fences, no ```json, no preamble, no commentary. Emit the array once; do
not restate or correct it.

Do the normalization arithmetic silently, in your head. Do NOT print your working:
no step-by-step derivation, no markdown tables of intermediate values, no
"Step 1:" narration. The reply is parsed by a program, and anything before the
opening bracket breaks it. Your entire response is the array.

[
  {
    "supplier_id": "<id>",
    "score_total": <integer 0-100>,
    "score_breakdown": {
      "cost": <integer>,
      "lead_time": <integer>,
      "reliability": <integer>,
      "quality": <integer>
    },
    "tier": "preferred" | "approved" | "watch" | "deprioritize",
    "recommendation": "<max 25 words: what to actually do with this supplier>"
  }
]

The four breakdown values must sum to score_total. Be terse in `recommendation`.
"""

LOGISTICS_SYSTEM = """You are the Logistics Coordinator.
You receive ONE shipping request and the full carrier catalogue. You select a
carrier and explain the trade-off.

## Hard constraints (a carrier that fails any of these is not a candidate)

- origin_region must equal the request's origin_region
- destination_region must equal the request's dest_region
- transit_days <= deadline_days
- max_weight_kg >= weight_kg
- if the request is perishable, supports_perishable must be true

These are not preferences. Never choose an option that breaks one, and never
argue that a cheap option is "close enough" on a deadline or a weight limit.

If NOTHING satisfies all five, say so: chosen_option_id null and a
trade_off_summary naming the constraint that cannot be met. An honest
infeasibility beats a plan that quietly violates a promise.

## Soft preferences (how to choose AMONG the feasible)

Total cost = weight_kg x cost_per_kg. Cost is usually the deciding factor, and
the spread here is large: on a long lane, ocean can be an order of magnitude
cheaper than air. Do not pay for speed that the deadline does not require.

But cost is not the only thing:

- Time slack is worth something. A carrier arriving the day the deadline lands
  has no room for a delay. When two options are close on cost, take the one with
  more slack.
- Slack is only worth PAYING for when the premium is small. Do not spend many
  multiples of the cheap option's cost to buy days you do not need.
- A shipment at the very edge of a carrier's max_weight_kg leaves no margin;
  prefer headroom when the cost is comparable.

## use_classical_fallback

This flag asks one question: did this decision actually need judgement, or did
the numbers decide it? If the numbers decided it, a deterministic greedy planner
downstream can redo the choice more cheaply and with a fully auditable trace, and
it should. Do not claim work you did not do.

Apply this test literally, in order:

1. Build the feasible set (all five hard constraints satisfied).
2. Feasible set is EMPTY -> `false`. Infeasibility needs a human-readable
   explanation, and a greedy planner can only return "nothing found".
3. Exactly ONE feasible option -> `true`. The choice was forced. There was
   nothing to weigh.
4. The cheapest feasible option is more than 20% cheaper than the next cheapest
   -> `true`. Cost dominates by a wide margin; no trade-off is being made, you
   are simply reading off the minimum. This is the common case on long lanes
   where ocean undercuts air several times over.
5. Otherwise (two or more options within ~20% on cost, differing on slack,
   weight headroom or perishability) -> `false`. Here the cheapest is NOT
   obviously the right answer and your judgement earns its keep.

Be honest with this flag. Setting it to `false` on a decision that rule 3 or 4
already settled just spends money to restate arithmetic.

## Output contract

Reply with RAW JSON ONLY. First character `{`, last character `}`. No markdown
fences, no ```json, no preamble, no commentary. Emit exactly one object; do not
narrate your reasoning or revise yourself on the page.

{
  "request_id": "<id>",
  "chosen_option_id": "<option id, or null if nothing is feasible>",
  "alternatives_considered": ["<option ids you rejected and why, terse>"],
  "trade_off_summary": "<max 30 words: what you chose and what you gave up>",
  "use_classical_fallback": <true|false>
}
"""

# ---- HTTP node builder for Anthropic Messages API -------------------------

def http_anthropic(name, slug, system_prompt, user_expr, col, row):
    """
    Build an HTTP Request node calling Anthropic's Messages API.
    `user_expr` is a JS expression (no surrounding quotes) that yields a
    string -- the user message body. We wrap it in JSON.stringify(...) so
    the rendered JSON is always valid regardless of newlines/quotes inside.
    """
    body = (
        '={\n'
        '  "model": "claude-sonnet-4-6",\n'
        '  "max_tokens": 2048,\n'
        # temperature 0 for reproducibility: the planner's `next_subgoal` choice
        # drives which branch runs, and at the default temperature the same goal
        # routed to different branches across runs, which makes a failure
        # impossible to attribute. docs/setup.md §9 recommends this while iterating.
        '  "temperature": 0,\n'
        # Plain (uncached) system prompt.
        #
        # Prompt caching was tried here and made things WORSE. The per-item LLM
        # nodes (the forecast adjuster fires once per SKU) are dispatched by n8n
        # in parallel, so all 15 requests race and every one of them MISSES the
        # cache none of them has written yet. Measured: 14854 cache-write tokens
        # against 1061 cache-read. Writes bill at 1.25x input, so the branch went
        # from $0.0777 to $0.0868. Caching only pays when calls are sequential or
        # the cached prefix outlives a single burst; it is a loss here.
        '  "system": ' + json.dumps(system_prompt) + ',\n'
        '  "messages": [\n'
        '    { "role": "user", "content": {{ JSON.stringify(' + user_expr + ') }} }\n'
        '  ]\n'
        '}'
    )
    return {
        "id": nid(slug),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos(col, row),
        "credentials": {
            "httpHeaderAuth": {
                "id": "anthropic-credential-placeholder",
                "name": "Anthropic API Key",
            }
        },
        "parameters": {
            "method": "POST",
            "url": "https://api.anthropic.com/v1/messages",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "anthropic-version", "value": "2023-06-01"},
                    {"name": "content-type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body,
            "options": {},
        },
    }


def code_node(name, slug, code, col, row):
    return {
        "id": nid(slug),
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos(col, row),
        "parameters": {"language": "javaScript", "jsCode": code},
    }


def set_node(name, slug, assignments, col, row):
    return {
        "id": nid(slug),
        "name": name,
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": pos(col, row),
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{slug}.{a['name']}")),
                        "name": a["name"],
                        "value": a["value"],
                        "type": a.get("type", "string"),
                    }
                    for a in assignments
                ]
            },
            "options": {},
        },
    }


# ---- Build node list ------------------------------------------------------

nodes = []

# 1. Manual Trigger
nodes.append({
    "id": nid("manual"),
    "name": "Manual Trigger",
    "type": "n8n-nodes-base.manualTrigger",
    "typeVersion": 1,
    "position": pos(0, 1),
    "parameters": {},
})

# 2. Set Goal
#
# The planner decomposes whatever goal it is handed, so the goal is what steers
# `next_subgoal` and therefore which branch runs. Overridable from the
# environment so a single branch can be exercised in isolation while developing
# (and so the demo can drive several branches) without editing this file:
#
#     SCM_GOAL="Rank our suppliers..." python3 build_workflow.py
#
# The default is the goal the assignment ships with.
DEFAULT_GOAL = (
    "Prepare a Q1 inventory and supplier action plan: identify SKUs "
    "at stockout risk, surface suppliers underperforming on reliability, "
    "and decide carrier coverage for the next 30 days."
)
GOAL = os.environ.get("SCM_GOAL", DEFAULT_GOAL)

nodes.append(set_node(
    "Set Goal", "set-goal",
    [{
        "name": "goal",
        "value": GOAL,
        "type": "string",
    }],
    1, 1,
))

# 3-10. Four CSV reads (binary read + spreadsheet parse)
csv_paths = [
    ("Inventory", "inv", "/data/current_inventory.csv"),
    ("Sales", "sales", "/data/sales_history.csv"),
    ("Suppliers", "suppliers", "/data/suppliers.csv"),
    ("Shipping", "shipping", "/data/shipping_options.csv"),
]
for i, (label, slug, path) in enumerate(csv_paths):
    nodes.append({
        "id": nid(f"read-{slug}"),
        "name": f"Read {label} File",
        "type": "n8n-nodes-base.readWriteFile",
        "typeVersion": 1,
        "position": pos(2, i),
        "parameters": {
            "operation": "read",
            "fileSelector": path,
            "options": {},
        },
    })
    nodes.append({
        "id": nid(f"parse-{slug}"),
        "name": f"Read {label} JSON",
        "type": "n8n-nodes-base.spreadsheetFile",
        "typeVersion": 2,
        "position": pos(3, i),
        "parameters": {
            "operation": "fromFile",
            "fileFormat": "csv",
            "options": {"headerRow": True},
        },
    })

# 11. Build Context Summary
context_code = '''/**
 * Build a compact context summary for the Master Planner.
 *
 * The planner does not need the raw 180 sales rows -- that would blow the
 * context budget. We extract the headline numbers and the SKUs already
 * past or near reorder so the planner can pick the right subgoal first.
 *
 * Inputs reach this node via cross-node references to the four CSV-parse
 * nodes upstream. We do NOT mutate them, only summarize.
 *
 * Convergence guard: the four CSV-read branches fan out from "Set Goal" and
 * all converge on this node's single input. n8n runs this node once per
 * arriving branch rather than waiting for all four, so on the earlier
 * invocations the other branches have not executed yet and $('Read Sales JSON')
 * throws "hasn't been executed". We return [] on those invocations, which
 * emits no items and lets the run continue; the final invocation (after every
 * branch has landed) sees all four and emits the real summary exactly once.
 */
function ran(nodeName) {
  try {
    $(nodeName).all();
    return true;
  } catch (e) {
    return false;
  }
}

const REQUIRED = [
  'Read Inventory JSON',
  'Read Sales JSON',
  'Read Suppliers JSON',
  'Read Shipping JSON',
];
if (!REQUIRED.every(ran)) {
  return [];
}

const inventory = $('Read Inventory JSON').all().map(i => i.json);
const sales     = $('Read Sales JSON').all().map(i => i.json);
const suppliers = $('Read Suppliers JSON').all().map(i => i.json);
const goal      = $('Set Goal').first().json.goal;

const stockout_risk = inventory
  .filter(r => Number(r.on_hand) <= Number(r.reorder_point))
  .map(r => ({ sku: r.sku, name: r.name,
               on_hand: Number(r.on_hand),
               reorder_point: Number(r.reorder_point) }));

const overstock_risk = inventory
  .filter(r => Number(r.on_hand) > Number(r.reorder_point) * 5)
  .map(r => ({ sku: r.sku, name: r.name,
               on_hand: Number(r.on_hand),
               reorder_point: Number(r.reorder_point) }));

const supplier_summary = suppliers.map(s => ({
  supplier_id: s.supplier_id,
  on_time_rate: Number(s.on_time_rate),
  defect_rate: Number(s.defect_rate),
}));

return [{
  json: {
    goal,
    context_summary: {
      sku_count: inventory.length,
      sales_rows: sales.length,
      stockout_risk,
      overstock_risk,
      supplier_summary,
    },
  },
}];
'''
nodes.append(code_node("Build Context Summary", "build-context", context_code, 4, 1))

# 12. Master Planner LLM
nodes.append(http_anthropic(
    "Master Planner Agent", "master-planner", MASTER_PLANNER_SYSTEM,
    "'GOAL: ' + $json.goal + '\\n\\nCONTEXT:\\n' + JSON.stringify($json.context_summary, null, 2)",
    5, 1,
))

# 13. Parse Plan
parse_plan_code = '''/**
 * Extract the Master Planner's JSON from the Anthropic response envelope.
 * Anthropic returns { content: [{ type: "text", text: "..." }], ... }.
 *
 * If your planner replies with markdown fences (```json ...```), the
 * JSON.parse below will fail. Forbid fences in your system prompt
 * (preferred) or strip them here.
 */
const raw = $json.content[0].text.trim();
let plan;
try {
  plan = JSON.parse(raw);
} catch (e) {
  throw new Error("Planner did not return valid JSON. Got:\\n" + raw.slice(0, 500));
}

// Validate next_subgoal against the routes that actually exist.
//
// This guard is the difference between a working agent and a safe one. The
// Switch downstream is configured with fallbackOutput "extra", which creates a
// fifth output for values it does not recognise — and nothing is connected to
// it. So if the planner ever emitted "audit_warehouse", or "Forecast" with a
// capital F, or "forecast " with a trailing space, the item would route into
// that dead output and the run would end with NO branch executed, NO error, and
// NO result. It would look like a success.
//
// A silent no-op is the worst failure mode an agent can have: nothing downstream
// can tell "the plan was empty" apart from "the plan ran". The LLM's output is
// untrusted input to a deterministic router, so it gets validated like any other
// untrusted input, at the boundary, and fails loudly.
const VALID_SUBGOALS = ["forecast", "inventory", "supplier", "logistics"];
if (!VALID_SUBGOALS.includes(plan.next_subgoal)) {
  throw new Error(
    "Planner emitted an unroutable next_subgoal: " +
      JSON.stringify(plan.next_subgoal) +
      ". Expected one of " + VALID_SUBGOALS.join(", ") +
      ". The Switch would have dropped this run silently."
  );
}

// Pull the goal+context through so downstream branches can reference them.
const ctx = $('Build Context Summary').first().json;

return [{ json: { ...plan, _goal: ctx.goal, _context: ctx.context_summary } }];
'''
nodes.append(code_node("Parse Plan", "parse-plan", parse_plan_code, 6, 1))

# 14. Switch on next_subgoal
nodes.append({
    "id": nid("switch"),
    "name": "Route on Subgoal",
    "type": "n8n-nodes-base.switch",
    "typeVersion": 3.2,
    "position": pos(7, 1),
    "parameters": {
        "rules": {
            "values": [
                {
                    "conditions": {
                        "options": {"caseSensitive": True, "typeValidation": "strict"},
                        "conditions": [{
                            "leftValue": "={{ $json.next_subgoal }}",
                            "rightValue": label,
                            "operator": {"type": "string", "operation": "equals"},
                        }],
                        "combinator": "and",
                    },
                    "renameOutput": True,
                    "outputKey": label,
                }
                for label in ["forecast", "inventory", "supplier", "logistics"]
            ]
        },
        "options": {"fallbackOutput": "extra"},
    },
})

# 15. Forecast branch
nodes.append(code_node("Demand Forecast Engine", "demand-forecast",
                       js("demand-forecast.js"), 8, 0))
nodes.append(http_anthropic(
    "Forecast Context Adjuster", "forecast-adjuster", FORECAST_ADJUSTER_SYSTEM,
    "'Forecast row:\\n' + JSON.stringify($json, null, 2)",
    9, 0,
))

# 16. Inventory branch
nodes.append(code_node("Inventory EOQ Planner", "eoq",
                       js("eoq-optimizer.js"), 8, 1))
nodes.append(http_anthropic(
    "Inventory Exception Handler", "inventory-exception", INVENTORY_EXCEPTION_SYSTEM,
    "'Flagged SKU:\\n' + JSON.stringify($json, null, 2)",
    9, 1,
))

# 17. Supplier branch
nodes.append(http_anthropic(
    "Supplier Performance Monitor", "supplier-score", SUPPLIER_SCORE_SYSTEM,
    # $input here is the Switch's output (the plan), not the roster, so we read
    # the suppliers from the CSV-parse node directly. One item in, one call out:
    # the whole roster is scored in a single request, which is both cheaper and
    # necessary — the scores are RELATIVE, so the model has to see all six at once.
    "'Supplier roster:\\n' + JSON.stringify($('Read Suppliers JSON').all().map(i => i.json), null, 2)",
    8, 2,
))

# 18. Logistics branch
build_requests_code = '''/**
 * Manufacture three illustrative shipping requests so the logistics branch
 * has work to do. In a real system these would come from order management;
 * we synthesize them here so the assignment is self-contained.
 */
const requests = [
  { type: "request", request_id: "REQ-001", weight_kg:  850, origin_region: "Asia",          dest_region: "North America", deadline_days: 14, perishable: false },
  { type: "request", request_id: "REQ-002", weight_kg:   60, origin_region: "North America", dest_region: "North America", deadline_days:  3, perishable: true  },
  { type: "request", request_id: "REQ-003", weight_kg: 1200, origin_region: "Europe",        dest_region: "North America", deadline_days: 21, perishable: false },
];
// Emit the REQUESTS only.
//
// Originally this node also appended the 10 carrier options, so the branch's
// next node received 13 items. The Logistics Coordinator is a per-item LLM node,
// so that meant 13 API calls per run, ten of which handed a carrier option to a
// prompt that expects a shipping request. Both consumers pull the catalogue for
// themselves instead — the LLM node via $('Read Shipping JSON') in its body
// expression, the classical fallback via the same reference in its code — so the
// options do not need to travel through the item stream at all. 3 requests in,
// 3 LLM calls out.
return requests.map(x => ({ json: x }));
'''
nodes.append(code_node("Build Shipping Requests", "build-requests", build_requests_code, 8, 3))
nodes.append(http_anthropic(
    "Logistics Coordinator (LLM)", "logistics", LOGISTICS_SYSTEM,
    "'Request:\\n' + JSON.stringify($json, null, 2) + '\\n\\nOptions:\\n' + JSON.stringify($('Read Shipping JSON').all().map(i => i.json), null, 2)",
    9, 3,
))
nodes.append({
    "id": nid("if-classical"),
    "name": "Use Classical Fallback?",
    "type": "n8n-nodes-base.if",
    "typeVersion": 2.2,
    "position": pos(10, 3),
    "parameters": {
        "conditions": {
            "options": {"caseSensitive": True, "typeValidation": "strict"},
            "conditions": [{
                # This node's input is the raw Anthropic envelope
                # ({content: [{text: "..."}]}), not the model's parsed JSON --
                # there is no parse node between the LLM and this IF. Reading
                # $json.use_classical_fallback directly always yielded undefined,
                # so the fallback branch could never fire. Parse the text here,
                # tolerating code fences, and default to false if anything is off:
                # a malformed reply should keep us on the LLM path, not silently
                # divert to the greedy planner.
                "leftValue": (
                    "={{ (() => { try { "
                    "const t = $json.content[0].text.replace(/```(?:json)?/g, '').trim(); "
                    "return JSON.parse(t).use_classical_fallback === true; "
                    "} catch (e) { return false; } })() }}"
                ),
                "rightValue": True,
                "operator": {"type": "boolean", "operation": "true"},
            }],
            "combinator": "and",
        },
        "options": {},
    },
})
nodes.append(code_node("Classical Logistics Fallback", "classical-logistics",
                       js("classical-logistics.js"), 11, 4))

# 19. Final Merge
nodes.append({
    "id": nid("merge-final"),
    "name": "Merge Subgoal Results",
    "type": "n8n-nodes-base.merge",
    "typeVersion": 3,
    "position": pos(11, 1),
    # Two inputs, not one.
    #
    # The logistics branch is the only one that can deliver results from two
    # places at once: the IF's false output (requests the LLM handled) and the
    # classical fallback (requests it delegated). With both wired into input 0,
    # Merge fired once per arriving batch, so Final Output ran twice and produced
    # two partial summaries instead of one whole one. Giving the fallback its own
    # input makes Merge wait for both and emit a single combined batch.
    "parameters": {"mode": "append", "numberInputs": 2},
})

# 20. Final Output
final_code = '''/**
 * Aggregate the active subgoal's output into a final business-friendly summary.
 * Only one branch fires per execution (the Switch routes on next_subgoal).
 *
 * Three jobs:
 *   1. Turn the branch's raw LLM envelopes into findings a human would read.
 *   2. Close the HTN loop by naming the next subgoal in the plan, so a
 *      subsequent run can advance the plan instead of restarting it.
 *   3. Tally tokens and cost, because a planner you cannot budget is a planner
 *      you cannot run.
 */

// ---- Robust extraction ----------------------------------------------------
//
// Every LLM node is told to emit exactly one raw JSON object. Sometimes one
// does not: models wrap output in ```json fences, or narrate ("Wait, let me
// re-examine...") and emit a corrected second object. A pipeline that dies on
// one malformed reply out of fifteen is not worth much, so we recover instead
// of throwing. When several objects are present the LAST one wins, which is
// precisely the model's own correction.
function extractJson(text) {
  if (typeof text !== "string") return null;

  const cleaned = text.replace(/```(?:json)?/gi, "").trim();

  // The common case: the whole reply is one valid JSON value. This also covers
  // the supplier node, which returns an ARRAY of six scored suppliers rather
  // than a single object (their scores are relative, so they are produced in one
  // call). The brace-scanner below would only recover the last element of it.
  try {
    return JSON.parse(cleaned);
  } catch (e) {
    // Fall through to salvage.
  }

  // Salvage. Models narrate: the supplier node has shown its min-max arithmetic
  // in markdown tables before emitting the array, and the per-SKU nodes have
  // occasionally emitted a second object to correct a first. Scan for balanced
  // JSON regions starting at either bracket and keep everything that parses.
  const found = [];
  const OPEN = { "{": "}", "[": "]" };
  for (let i = 0; i < cleaned.length; i++) {
    const close = OPEN[cleaned[i]];
    if (!close) continue;

    let depth = 0;
    for (let j = i; j < cleaned.length; j++) {
      if (cleaned[j] === cleaned[i]) depth++;
      else if (cleaned[j] === close) depth--;

      if (depth === 0) {
        try {
          found.push(JSON.parse(cleaned.slice(i, j + 1)));
          i = j; // consume the region so we do not rescan its interior
        } catch (e) {
          // Not valid; leave i alone and let the outer loop advance.
        }
        break;
      }
    }
  }

  if (!found.length) return null;

  // An array is the richest result (the full supplier roster) — prefer the
  // longest one. Otherwise take the LAST object, which is the model's own
  // correction when it revised itself mid-reply.
  const arrays = found.filter(Array.isArray);
  if (arrays.length) {
    return arrays.reduce((a, b) => (b.length > a.length ? b : a));
  }
  return found[found.length - 1];
}

// An item is either an Anthropic response envelope (the LLM branches) or a
// plain object (the classical logistics fallback, which is pure JS).
function unwrap(item) {
  const text = item && item.content && item.content[0] && item.content[0].text;
  if (typeof text === "string") {
    const parsed = extractJson(text);
    return parsed !== null ? parsed : { unparsed: text.slice(0, 200) };
  }
  return item;
}

// ---- Plan context ---------------------------------------------------------

const plan = $('Parse Plan').first().json;
const executed = plan.next_subgoal;

// A node may hand back one object per item (the per-SKU branches) or a single
// item holding an array (the supplier roster). Flatten so downstream code sees
// one flat list of results either way.
const results = $input.all().flatMap(i => {
  const u = unwrap(i.json);
  return Array.isArray(u) ? u : [u];
});

// ---- Findings, per branch -------------------------------------------------

const findings = [];
const money = n => Math.round(Number(n) * 100) / 100;

if (executed === "forecast") {
  const revised = results.filter(r => Number(r.delta_pct));
  const classical = {};
  for (const r of $('Demand Forecast Engine').all()) classical[r.json.sku] = r.json;

  for (const r of revised) {
    const c = classical[r.sku] || {};
    const dir = Number(r.delta_pct) > 0 ? "raised" : "cut";
    findings.push(
      `${r.sku} ${c.name || ""}: forecast ${dir} ${c.forecast_units} -> ` +
      `${r.revised_forecast} units (${r.delta_pct > 0 ? "+" : ""}${r.delta_pct}%). ${r.reasoning || ""}`
    );
  }
  findings.push(
    `${results.length - revised.length} of ${results.length} SKUs held at the classical forecast.`
  );
} else if (executed === "inventory") {
  const act = results.filter(r => r.recommended_action && r.recommended_action !== "hold");
  for (const r of act) {
    findings.push(
      `${r.sku}: ${String(r.recommended_action).toUpperCase()} ` +
      `qty ${r.recommended_qty}. ${r.reasoning || ""}`
    );
  }
  findings.push(
    `${results.length - act.length} of ${results.length} SKUs need no action ` +
    `(on hand above reorder point, EOQ assumptions intact).`
  );
} else if (executed === "supplier") {
  const ranked = results
    .filter(r => r.supplier_id)
    .sort((a, b) => Number(b.score_total) - Number(a.score_total));
  for (const r of ranked) {
    findings.push(
      `${r.supplier_id}: ${r.score_total}/100 (${r.tier}). ${r.recommendation || ""}`
    );
  }
} else if (executed === "logistics") {
  for (const r of results) {
    if (r.chosen) {
      // Classical greedy fallback shape.
      findings.push(
        `${r.request_id}: ${r.chosen.carrier} ${r.chosen.mode} ` +
        `$${money(r.chosen.total_cost_usd)} (${r.method}).`
      );
    } else if (r.feasible === false) {
      findings.push(`${r.request_id}: NO FEASIBLE CARRIER under the stated constraints.`);
    } else if (r.request_id) {
      // LLM shape.
      findings.push(
        `${r.request_id}: ${r.chosen_option_id}. ${r.trade_off_summary || ""}`
      );
    }
  }
}

// ---- Close the HTN loop ---------------------------------------------------
//
// The planner emitted an ORDERED list of subgoals. We executed one of them; the
// next unexecuted one in that order is what a follow-up run should dispatch.
// This is the hook that turns a single-shot pipeline into an iterative planner.
const ordered = (plan.subgoals || []).map(s => s.type);
const at = ordered.indexOf(executed);
const next_recommended_subgoal =
  at !== -1 && at + 1 < ordered.length ? ordered[at + 1] : null;

// ---- Cost accounting ------------------------------------------------------
//
// Claude Sonnet 4.6: $3 per Mtok in, $15 per Mtok out.
const LLM_NODES = [
  'Master Planner Agent',
  'Forecast Context Adjuster',
  'Inventory Exception Handler',
  'Supplier Performance Monitor',
  'Logistics Coordinator (LLM)',
];

let tokens_in = 0;
let tokens_out = 0;
let llm_calls = 0;
for (const name of LLM_NODES) {
  let items;
  try {
    items = $(name).all();
  } catch (e) {
    continue; // node not on this run's branch
  }
  for (const it of items) {
    const u = it.json && it.json.usage;
    if (!u) continue;
    llm_calls++;
    tokens_in += Number(u.input_tokens || 0);
    tokens_out += Number(u.output_tokens || 0);
  }
}
const cost_usd = money((tokens_in * 3) / 1e6 + (tokens_out * 15) / 1e6);

return [{
  json: {
    plan_id: plan.plan_id,
    goal: plan._goal,
    executed_subgoal: executed,
    planned_subgoals: ordered,
    key_findings: findings,
    next_recommended_subgoal,
    run_metrics: {
      llm_calls,
      tokens_in,
      tokens_out,
      cost_usd: Number(((tokens_in * 3) / 1e6 + (tokens_out * 15) / 1e6).toFixed(4)),
    },
  },
}];
'''
nodes.append(code_node("Final Output", "final-output", final_code, 12, 1))

# ---- Connections ----------------------------------------------------------

connections = {}


def connect(src, dst, src_index=0, dst_index=0):
    if src not in connections:
        connections[src] = {"main": []}
    while len(connections[src]["main"]) <= src_index:
        connections[src]["main"].append([])
    connections[src]["main"][src_index].append(
        {"node": dst, "type": "main", "index": dst_index}
    )


# Trigger -> Goal -> file reads
connect("Manual Trigger", "Set Goal")
for label, _, _ in csv_paths:
    connect("Set Goal", f"Read {label} File")
    connect(f"Read {label} File", f"Read {label} JSON")
    connect(f"Read {label} JSON", "Build Context Summary")

# Plan
connect("Build Context Summary", "Master Planner Agent")
connect("Master Planner Agent", "Parse Plan")
connect("Parse Plan", "Route on Subgoal")

# Switch outputs (index order = rule order: forecast, inventory, supplier, logistics)
connect("Route on Subgoal", "Demand Forecast Engine", src_index=0)
connect("Route on Subgoal", "Inventory EOQ Planner", src_index=1)
connect("Route on Subgoal", "Supplier Performance Monitor", src_index=2)
connect("Route on Subgoal", "Build Shipping Requests", src_index=3)

# Branch tails -> Final Merge
connect("Demand Forecast Engine", "Forecast Context Adjuster")
connect("Forecast Context Adjuster", "Merge Subgoal Results")
connect("Inventory EOQ Planner", "Inventory Exception Handler")
connect("Inventory Exception Handler", "Merge Subgoal Results")
connect("Supplier Performance Monitor", "Merge Subgoal Results")
connect("Build Shipping Requests", "Logistics Coordinator (LLM)")
connect("Logistics Coordinator (LLM)", "Use Classical Fallback?")
connect("Use Classical Fallback?", "Classical Logistics Fallback", src_index=0)  # true
connect("Use Classical Fallback?", "Merge Subgoal Results", src_index=1)         # false
connect("Classical Logistics Fallback", "Merge Subgoal Results", dst_index=1)

connect("Merge Subgoal Results", "Final Output")

# ---- Workflow envelope ----------------------------------------------------

workflow = {
    "id": "supply-chain-manager-v1",
    "name": "Supply Chain Manager (Starter)",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(workflow, indent=2))
print(f"wrote {OUT}")
print(f"  nodes: {len(nodes)}")
print(f"  connection groups: {sum(len(v['main']) for v in connections.values())}")
