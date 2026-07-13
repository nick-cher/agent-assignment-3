/**
 * Demand Forecasting Engine — classical statistical forecast.
 *
 * Pedagogical purpose
 * -------------------
 * This Code node implements the *classical* half of a hybrid planning
 * pipeline. It produces a deterministic, reproducible numeric forecast
 * for each SKU using:
 *   1. A 3-month moving average over recent demand
 *   2. A 12-month seasonal index that adjusts for cyclical patterns
 *
 * The downstream LLM node ("Forecast Context Adjuster") will take these
 * numbers and revise them using context the math cannot see — promotions,
 * news events, weather, viral product mentions. That handoff is the whole
 * point of the lesson: classical statistics for what is computable,
 * LLM reasoning for what is contextual.
 *
 * If your forecast looks suspicious (e.g. SKU-007 Wool Gloves projects
 * its low summer baseline forward), you have correctly built a *naive*
 * forecaster. The next node is supposed to catch what you missed.
 *
 * Reading: docs/planning-primer.md §"Classical vs LLM-based planning"
 */

// ---- Input contract -------------------------------------------------------
// This node sits on a Switch branch, so $input is the Master Planner's plan
// object, not the sales rows. We reach back to the CSV-parse node for the data,
// the same way the provided "Build Shipping Requests" node pulls its catalogue
// with $('Read Shipping JSON').
// Rows look like {month, sku, name, units_sold} (the parsed sales_history.csv).
const sales = $('Read Sales JSON').all().map(i => i.json);

// ---- Helpers (provided — do not change) -----------------------------------

function groupBySku(rows) {
  const out = {};
  for (const r of rows) {
    (out[r.sku] = out[r.sku] || []).push(r);
  }
  // Sort each SKU's series chronologically so "last 3" really means "most recent."
  for (const sku of Object.keys(out)) {
    out[sku].sort((a, b) => a.month.localeCompare(b.month));
  }
  return out;
}

function nextMonth(monthStr) {
  // "2025-12" -> "2026-01"
  const [y, m] = monthStr.split("-").map(Number);
  const d = new Date(Date.UTC(y, m, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

// ---- The two algorithms YOU implement -------------------------------------

/**
 * Compute a simple 3-month moving average over the most recent units_sold values.
 *
 * @param {Array<{units_sold: number}>} series  Full sorted series for one SKU.
 * @returns {number}  Mean of the last 3 months. If fewer than 3 months of
 *                    data exist, take the mean of what's available.
 *                    Empty series -> 0.
 *
 * Why this matters: the moving average is the simplest possible "trend"
 * estimator. It's a STRIPS-style assumption: we assume the recent past
 * predicts the near future. This breaks for viral products and discontinued
 * items — which is exactly why the seasonal index and the LLM step exist.
 */
function movingAverage(series) {
  if (!series || series.length === 0) return 0;

  // Take the most recent 3 months. slice(-3) yields the whole series when
  // fewer than 3 months exist, so short histories average what they have.
  const window = series.slice(-3);
  const total = window.reduce((acc, r) => acc + Number(r.units_sold), 0);

  return total / window.length;
}

/**
 * Seasonal index for a target forecast month.
 *
 * Definition for month M:
 *   index(M) = mean(units_sold across rows where month-of-year == M)
 *              / mean(units_sold across the entire series)
 *
 * Interpretation: 1.0 = "average month", 1.5 = "this month historically runs
 * 50% above average", 0.4 = "this month historically runs 60% below average."
 *
 * With only 12 months of history, the per-month mean degenerates to the
 * single observation we have for that month. That's a known weakness — we
 * accept it for this exercise. Production seasonality models use 2+ years.
 *
 * @param {Array<{month: string, units_sold: number}>} series
 * @param {string} targetMonth  e.g. "2026-01" — only the "01" portion matters.
 * @returns {number}            Multiplier. Default to 1.0 if you can't compute one.
 */
function seasonalIndex(series, targetMonth) {
  if (!series || series.length === 0) return 1.0;

  // "2026-01" -> "01". Only the month-of-year matters; the year is discarded
  // so that every January in the history contributes to January's index.
  const monthOfYear = targetMonth.split("-")[1];

  const sameMonth = series.filter(r => String(r.month).split("-")[1] === monthOfYear);

  // No observation for that calendar month: we have no seasonal evidence, so
  // stay neutral rather than inventing a multiplier.
  if (sameMonth.length === 0) return 1.0;

  const mean = rows =>
    rows.reduce((acc, r) => acc + Number(r.units_sold), 0) / rows.length;

  const monthMean = mean(sameMonth);
  const overallMean = mean(series);

  // A dead SKU (zero sales all year) has no meaningful ratio.
  if (overallMean === 0) return 1.0;

  return monthMean / overallMean;
}

// ---- Main loop (provided) -------------------------------------------------

const bySku = groupBySku(sales);
const results = [];

for (const sku of Object.keys(bySku)) {
  const series = bySku[sku];
  const last = series[series.length - 1].month;
  const target = nextMonth(last);

  // Classical forecast = trend (moving average) × seasonality
  const ma = movingAverage(series);
  const si = seasonalIndex(series, target);
  const forecast = ma * si;

  // Crude statistical confidence — coefficient of variation, inverted.
  // The downstream LLM is supposed to revise this when context demands it.
  // Watch how often statistical confidence and contextual confidence diverge.
  const variance = series.length > 1
    ? series.reduce((acc, r) => acc + Math.pow(r.units_sold - ma, 2), 0) / series.length
    : 0;
  const cv = ma > 0 ? Math.sqrt(variance) / ma : 1;
  const confidence = Math.max(0, Math.min(1, 1 - cv));

  // Contextual notes for the downstream LLM adjuster.
  //
  // The aggregates above are lossy on purpose: a moving average collapses the
  // SHAPE of the series into a single level. A SKU ramping 5x over three months
  // and a flat SKU can share a moving average, and the adjuster sees only the
  // aggregate — so on its own it cannot tell a viral product from a stable one.
  // We hand it a compact trend summary instead of all 12 rows, which would
  // multiply the token bill across every SKU on this branch.
  const units = series.map(r => Number(r.units_sold));
  const mean = a => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);

  const notes = [`last_6_months=[${units.slice(-6).join(", ")}]`];

  // Two orthogonal views of the trend. We deliberately hand the LLM raw ratios
  // rather than a "cleaned" signal, for a reason worth stating:
  //
  // We cannot deseasonalize our way out of this. With 12 months of history each
  // calendar month appears exactly once, so seasonalIndex(m) degenerates to
  // units(m) / seriesMean — and dividing each month by that index returns the
  // series mean for every month. The ratio flattens to 1.0 for every SKU and
  // the signal is gone. Trend and seasonality are simply not identifiable from
  // one SKU's 12 points; separating them needs multiple years, or a peer group,
  // or knowledge of what the product IS.
  //
  // That last one is exactly what the LLM has and the arithmetic does not. It
  // knows a snow boot climbing into January is a season, and wool gloves at 6x
  // is not. So the honest division of labour: the code reports what moved, the
  // model judges whether that movement is ordinary for this product this month.
  const recent3 = mean(units.slice(-3));
  const prior9 = mean(units.slice(0, -3));
  const first3 = mean(units.slice(0, 3));

  // Spike: recent quarter against the rest of the year. High for a genuine ramp,
  // but ALSO high for any product entering its high season.
  if (prior9 > 0) {
    notes.push(`spike_ratio_recent3_vs_prior9=${Math.round((recent3 / prior9) * 100) / 100}`);
  }

  // Year trend: end of the year against the start. A cyclical product returns to
  // where it began (~1.0) because both ends sit in its off-season. A product in
  // true structural decline ends far below where it started. This is the ratio
  // that separates "December" from "dying".
  if (first3 > 0) {
    notes.push(`year_trend_last3_vs_first3=${Math.round((recent3 / first3) * 100) / 100}`);
  }

  results.push({
    sku,
    name: series[0].name,
    target_month: target,
    forecast_units: Math.round(forecast),
    moving_avg: Math.round(ma * 10) / 10,
    seasonal_index: Math.round(si * 100) / 100,
    statistical_confidence: Math.round(confidence * 100) / 100,
    method: "moving_avg_3 × seasonal_index",
    notes,
  });
}

// n8n Code-node return contract: array of {json: ...}
return results.map(r => ({ json: r }));
