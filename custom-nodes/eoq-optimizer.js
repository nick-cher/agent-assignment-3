/**
 * Inventory Optimization Planner — Economic Order Quantity (EOQ).
 *
 * Pedagogical purpose
 * -------------------
 * EOQ (Wilson, 1934) is the canonical *classical* operations-research model:
 * a closed-form solution under strict assumptions —
 *   - constant demand
 *   - instantaneous replenishment
 *   - no stockouts allowed
 *   - fixed ordering cost, fixed holding cost
 *   - no quantity discounts
 *
 * Real e-commerce violates ALL of these for at least some SKUs. Viral
 * products (looking at you, SKU-007) blow past "constant demand." Discontinued
 * SKUs (SKU-013) make "no stockouts" expensive in the wrong direction.
 * Slow-movers make the formula numerically unstable.
 *
 * This node teaches the boundary problem: classical algorithms give crisp
 * answers exactly when their assumptions hold. Your two TODOs are
 *   (a) implement the formula
 *   (b) detect when its assumptions don't hold for a given SKU
 *
 * The downstream LLM exception node handles the SKUs you flag.
 *
 * Reading: docs/planning-primer.md §"STRIPS-style assumptions and where they break"
 */

// This node sits on a Switch branch, so $input carries the Master Planner's
// plan object rather than any data rows. We pull the two datasets directly from
// the CSV-parse nodes, mirroring the provided "Build Shipping Requests" node.
// The list is deliberately heterogeneous — inventory rows carry `on_hand`,
// sales rows carry `units_sold` — and partition() splits them apart below.
const all = [
  ...$('Read Inventory JSON').all().map(i => i.json),
  ...$('Read Sales JSON').all().map(i => i.json),
];

// Default ordering cost (S in the EOQ formula). In production this would
// vary by supplier and channel; we hard-code a single value so the focus
// stays on the formula and its assumptions.
const ORDERING_COST_USD = 50;

// ---- Helpers (provided) ---------------------------------------------------

function partition(rows) {
  const inventory = rows.filter(r => "on_hand" in r);
  const sales = rows.filter(r => "units_sold" in r);
  return { inventory, sales };
}

function annualDemand(salesForSku) {
  // Sum units_sold across the rows we have. With 12 months of data this is
  // the trailing-12-months annual demand.
  return salesForSku.reduce((acc, r) => acc + Number(r.units_sold), 0);
}

// ---- TODO #1 — the EOQ formula --------------------------------------------

/**
 * Wilson's Economic Order Quantity:
 *
 *   Q* = sqrt( (2 * D * S) / H )
 *
 * @param {number} D  Annual demand        (units per year)
 * @param {number} S  Fixed cost per order (dollars per order)
 * @param {number} H  Holding cost         (dollars per unit per year)
 * @returns {number}  Optimal order quantity, rounded to nearest integer.
 *
 * Hint: Math.sqrt is your friend. Guard against D=0 and H=0 — return 0 in
 *       either case. (You can't optimally order anything for zero demand,
 *       and dividing by zero holding cost is meaningless.)
 */
function eoq(D, S, H) {
  // No demand means there is no batch worth optimizing, and a zero holding cost
  // makes the ratio meaningless (the formula would divide by zero and imply an
  // infinite order). Both are outside the model's domain, so refuse rather than
  // return a number that looks authoritative.
  if (!D || D <= 0) return 0;
  if (!H || H <= 0) return 0;

  // Wilson (1934): the quantity where annual ordering cost and annual holding
  // cost are equal, which is where their sum is minimized.
  return Math.round(Math.sqrt((2 * D * S) / H));
}

// ---- TODO #2 — assumption-violation detection -----------------------------

/**
 * EOQ assumes:
 *   (a) demand is roughly constant
 *   (b) lead time is short enough to re-order before stocking out
 *   (c) the SKU isn't perishable (no holding-cost cliff)
 *   (d) demand volume is high enough that an "optimal batch" is meaningful
 *
 * Return an array of human-readable flag strings for any assumption that
 * FAILS for this SKU. An empty array means "EOQ is trustworthy here, ship
 * the formula's recommendation."
 *
 * Suggested checks (refine as you wish):
 *   - "viral_spike"   : mean(last 3 months) > 2.5 × mean(prior 9 months)
 *   - "declining"     : mean(last 3 months) < 0.5 × mean(first 3 months)
 *   - "low_velocity"  : annualDemand < 60   (less than ~5/month average)
 *   - "long_lead_time": inv.lead_time_days > 28 AND demand is volatile
 *
 * Note on perishability: none of our demo SKUs are perishable, so you do
 * NOT need a perishability check. Document the omission in your analysis
 * write-up — a real implementation would need it.
 *
 * @param {object} inv         Inventory row for the SKU
 * @param {Array}  salesSeries Chronologically sorted sales rows for the SKU
 * @returns {Array<string>}    Flag names, e.g. ["viral_spike", "low_velocity"]
 *
 * Hint: implement each check as its own small block. A flagged SKU may
 *       trigger multiple flags — that's expected and useful downstream.
 */
function detectViolations(inv, salesSeries) {
  const flags = [];
  if (!salesSeries || salesSeries.length === 0) return flags;

  const units = salesSeries.map(r => Number(r.units_sold));
  const mean = a => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);

  const recent3 = mean(units.slice(-3));   // the quarter we are ordering for
  const prior9  = mean(units.slice(0, -3)); // the rest of the year
  const first3  = mean(units.slice(0, 3));  // where the year started
  const D = annualDemand(salesSeries);

  // (a) "demand is roughly constant" — broken upward.
  //
  // Threshold 2.5 is chosen against the data, not plucked from the air. Every
  // winter SKU (jackets, beanies, boots, blankets) ramps into Q4 at ~2.4x its
  // own annual baseline, and that is ordinary seasonality that EOQ's annual
  // demand figure already absorbs. Wool Gloves runs at ~6.2x. Setting the bar at
  // 2.5 puts it above routine seasonality and below the genuine viral event, so
  // the flag fires for the real anomaly and stays quiet for the other four.
  if (prior9 > 0 && recent3 > 2.5 * prior9) {
    flags.push("viral_spike");
  }

  // (b) "demand is roughly constant" — broken downward.
  //
  // Compared against the START of the year, not the rest of it. That choice is
  // what separates a dying product from a seasonal one. A summer SKU in December
  // has collapsed relative to its recent months, but it ends the year roughly
  // where it began (~1.3x) because January is also its off-season — it is not
  // dying, it is winter. A structurally declining SKU ends far below its own
  // January (Wired Earbuds: 0.41x). Comparing to prior9 instead would flag every
  // seasonal product in the catalogue.
  if (first3 > 0 && recent3 < 0.5 * first3) {
    flags.push("declining");
  }

  // (c) "an optimal batch is meaningful" — broken by thin volume.
  //
  // Under ~5 units/month the sqrt is dominated by noise: one lumpy month moves
  // Q* enough to make the "optimum" arbitrary. Better to admit the model has
  // nothing useful to say than to ship a precise-looking number.
  if (D < 60) {
    flags.push("low_velocity");
  }

  // (d) "replenishment is instantaneous" — broken by a long, risky lead time.
  //
  // EOQ has no lead-time term at all: it assumes stock appears when ordered. A
  // long lead time only actually hurts when demand is also volatile, because a
  // steady seller can be covered by a reorder point. Volatility is measured with
  // the coefficient of variation so it is scale-free and comparable across SKUs
  // selling 5 or 500 units.
  const avg = mean(units);
  const sd = avg > 0
    ? Math.sqrt(mean(units.map(u => Math.pow(u - avg, 2))))
    : 0;
  const cv = avg > 0 ? sd / avg : 0;
  if (Number(inv.lead_time_days) > 28 && cv > 0.5) {
    flags.push("long_lead_time");
  }

  // (e) Dead stock: a glut that demand will never come back to clear.
  //
  // Note what this check is NOT. A naive "on_hand > 5x reorder_point" flag looks
  // reasonable and is badly wrong on this catalogue: it fires on Sunglasses,
  // Beach Towel and Swim Trunks, which are simply summer SKUs holding stock
  // through their off-season. By months-of-cover they are indistinguishable from
  // the genuinely dead SKU — Sunglasses carries 6.9 months, Wired Earbuds 6.8.
  //
  // The pile size is not the signal. What matters is whether demand is coming
  // back for it. A seasonal glut clears itself next season; a glut on a decaying
  // product never clears and only accrues holding cost. So overstock is only a
  // violation IN CONJUNCTION with decline, and that conjunction is the thing
  // worth routing to a human-style judgement.
  const onHand = Number(inv.on_hand);
  const rop = Number(inv.reorder_point);
  const overstocked = rop > 0 && onHand > 5 * rop;
  if (overstocked && flags.includes("declining")) {
    flags.push("dead_stock");
  }

  // Deliberately NOT implemented: perishability. EOQ's holding cost is linear in
  // time, which is wrong for anything with a shelf life (spoilage is a cliff, not
  // a slope). None of the 15 demo SKUs are perishable and the dataset carries no
  // expiry field, so a check here could never fire. Noted in analysis.md.

  return flags;
}

// ---- Main loop (provided) -------------------------------------------------

const { inventory, sales } = partition(all);
const salesBySku = sales.reduce((acc, r) => {
  (acc[r.sku] = acc[r.sku] || []).push(r);
  return acc;
}, {});
for (const sku of Object.keys(salesBySku)) {
  salesBySku[sku].sort((a, b) => a.month.localeCompare(b.month));
}

const results = [];
for (const inv of inventory) {
  const series = salesBySku[inv.sku] || [];
  const D = annualDemand(series);
  const H = Number(inv.holding_cost_per_unit_year);
  const Q = eoq(D, ORDERING_COST_USD, H);
  const flags = detectViolations(inv, series);

  results.push({
    sku: inv.sku,
    name: inv.name,
    on_hand: Number(inv.on_hand),
    reorder_point: Number(inv.reorder_point),
    annual_demand: D,
    eoq_units: Q,
    holding_cost_per_unit_year: H,
    ordering_cost_usd: ORDERING_COST_USD,
    assumption_flags: flags,
    needs_llm_review: flags.length > 0,
  });
}

return results.map(r => ({ json: r }));
