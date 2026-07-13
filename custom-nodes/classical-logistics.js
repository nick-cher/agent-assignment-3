/**
 * Classical Logistics Planner — greedy fallback.
 *
 * Pedagogical purpose
 * -------------------
 * This is the "planning without an LLM" branch of the Logistics Coordinator.
 * The LLM logistics node handles soft-constraint cases (special instructions,
 * supplier relationships, urgency framing, multi-leg trade-offs). When the
 * upstream IF node decides a situation is purely numerical — fixed weight,
 * fixed deadline, available carriers — it routes here for a deterministic,
 * auditable choice.
 *
 * Greedy is the simplest classical search: at each decision point, take the
 * locally best option. It's not always globally optimal, but it's fast,
 * explainable, and a perfect baseline to compare LLM plans against.
 *
 * Reading: docs/planning-primer.md §"Classical search and the cost of optimality"
 */

// Inputs are merged upstream — shipping requests AND the catalogue of options.
//
// A request: { type: "request", request_id, weight_kg, origin_region,
//              dest_region, deadline_days, perishable }
// An option: { type: "option",  option_id, carrier, mode, origin_region,
//              destination_region, transit_days, cost_per_kg,
//              max_weight_kg, supports_perishable }

// $input here is whatever the IF node passed through — the Logistics LLM's raw
// response envelopes, not the requests themselves. The IF forwards exactly those
// requests the LLM flagged as purely numeric, so the envelopes tell us WHICH
// requests were handed to us; we then fetch the real data from the nodes that
// own it.
const routedIds = new Set(
  $input.all()
    .map(i => {
      try {
        const text = i.json.content[0].text.replace(/```(?:json)?/g, "").trim();
        return JSON.parse(text).request_id;
      } catch (e) {
        return null;
      }
    })
    .filter(Boolean)
);

const allRequests = $('Build Shipping Requests').all().map(i => i.json);

// Re-plan only what was routed here. Falling back to the full set keeps the node
// runnable standalone (Execute Node) when there is no upstream IF output to read.
const requests = routedIds.size
  ? allRequests.filter(r => routedIds.has(r.request_id))
  : allRequests;

const options = $('Read Shipping JSON').all().map(i => i.json);

// ---- TODO — greedy carrier assignment -------------------------------------

/**
 * Pick the cheapest shipping option satisfying ALL hard constraints
 * for one request:
 *   - origin_region matches request.origin_region
 *   - destination_region matches request.dest_region
 *   - transit_days <= request.deadline_days
 *   - max_weight_kg >= request.weight_kg
 *   - if request.perishable === true, supports_perishable must also be true
 *
 * Total cost = request.weight_kg × option.cost_per_kg  (we ignore time cost)
 *
 * @param {object} req
 * @param {Array}  options
 * @returns {object|null}  Chosen option augmented with `total_cost_usd`,
 *                         or null if nothing satisfies the constraints.
 *
 * Hint: this is two steps — filter, then min-by-cost.
 *   1. Array.prototype.filter against the 5 hard constraints.
 *   2. If the filtered list is empty, return null (infeasible).
 *   3. Map each survivor to {...option, total_cost_usd: req.weight_kg * option.cost_per_kg}.
 *   4. Reduce to the one with the minimum total_cost_usd.
 *
 * Why greedy and not exhaustive? With ~10 options per request the search
 * space is trivial. We use greedy to keep the comparison clean against
 * the LLM branch, not because we couldn't afford the optimal search.
 */
function pickCheapestFeasible(req, options) {
  // Step 1 — feasibility. These are HARD constraints: an option either satisfies
  // all of them or it is not a candidate at all. There is no trading a day of
  // lateness against a cheaper rate here; that kind of judgement is exactly what
  // the LLM branch is for. This branch is the deterministic, auditable one.
  const feasible = options.filter(opt => {
    if (opt.origin_region !== req.origin_region) return false;
    if (opt.destination_region !== req.dest_region) return false;
    if (Number(opt.transit_days) > Number(req.deadline_days)) return false;
    if (Number(opt.max_weight_kg) < Number(req.weight_kg)) return false;

    // Perishable cargo may only ride a carrier that supports it. The CSV parses
    // this column as the strings "true"/"false", so compare loosely rather than
    // trusting a boolean to have survived the trip.
    if (req.perishable === true) {
      const supports =
        opt.supports_perishable === true || opt.supports_perishable === "true";
      if (!supports) return false;
    }
    return true;
  });

  // Step 2 — infeasible is a real answer, not an error. REQ-002 (60kg, perishable,
  // 3-day deadline) has no carrier: the only perishable-capable North America
  // lane is UPS Ground at 5 days. Returning null lets the caller report "no
  // feasible carrier" instead of inventing one that breaks a hard constraint.
  if (feasible.length === 0) return null;

  // Step 3 — greedy: among the survivors, take the cheapest. Cost is linear in
  // weight, so the per-kg rate decides it. With ~10 options the exhaustive search
  // IS this search; greedy is not an approximation here, it is optimal. We use it
  // because it is a clean, explainable baseline to hold the LLM's plan against.
  return feasible
    .map(opt => ({
      ...opt,
      total_cost_usd:
        Math.round(Number(req.weight_kg) * Number(opt.cost_per_kg) * 100) / 100,
    }))
    .reduce((best, opt) => (opt.total_cost_usd < best.total_cost_usd ? opt : best));
}

// ---- Main loop (provided) -------------------------------------------------

const assignments = [];
for (const req of requests) {
  const choice = pickCheapestFeasible(req, options);
  assignments.push({
    request_id: req.request_id,
    weight_kg: req.weight_kg,
    deadline_days: req.deadline_days,
    chosen: choice,
    feasible: choice !== null,
    method: "classical_greedy",
  });
}

return assignments.map(a => ({ json: a }));
