#!/usr/bin/env python3
"""
Builder for workflows/smart-order-router-inclass.json.

This is the Week 3 in-class exercise — a fully-built reference workflow
that students import, trigger via webhook, and modify to learn n8n's
core planning patterns: webhook input, LLM classification, Switch
routing, IF-based fallback, and audit logging.

Unlike the homework (supply-chain-manager-starter), this workflow has
NO TODOs. Every prompt is reference-quality and every Code node is
complete. The lesson is reading and modifying, not building from
scratch.

Run:  python3 build_inclass_workflow.py
"""
import json
import pathlib
import uuid

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "workflows" / "smart-order-router-inclass.json"


def nid(slug):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"scm-week3-inclass.{slug}"))


def pos(col, row):
    return [240 + col * 240, 200 + row * 180]


# ---------------------------------------------------------------------------
# System prompt for the AI classification node — reference quality.
# ---------------------------------------------------------------------------

CLASSIFICATION_SYSTEM = """You are an order routing assistant for an e-commerce platform.
Your job: classify each incoming order's priority so the workflow can route it
to the appropriate warehouse.

Classification rules (apply in this order — first match wins):
  1. URGENT  -- customer_tier == "vip"
              OR shipping_method matches /express|overnight|next-day/i
              OR order_value > 500
  2. BULK    -- customer_tier == "wholesale"
              OR total quantity across items > 50
  3. STANDARD -- everything else

Respond with RAW JSON only (no markdown fences, no preamble). The downstream
Code node parses this with JSON.parse so any extra text breaks the workflow.

Required output shape:
{
  "priority": "urgent" | "standard" | "bulk",
  "reasoning": "<one-sentence explanation citing the specific rule that fired>",
  "confidence": <number between 0 and 1>
}
"""


# ---------------------------------------------------------------------------
# Helpers (same shape as build_workflow.py — kept local for self-containment)
# ---------------------------------------------------------------------------

def http_anthropic(name, slug, system_prompt, user_expr, col, row):
    body = (
        '={\n'
        '  "model": "claude-sonnet-4-6",\n'
        '  "max_tokens": 1024,\n'
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


# ---------------------------------------------------------------------------
# Build node list
# ---------------------------------------------------------------------------

nodes = []

# 1. Webhook trigger
nodes.append({
    "id": nid("webhook"),
    "name": "Order Webhook",
    "type": "n8n-nodes-base.webhook",
    "typeVersion": 2,
    "position": pos(0, 1),
    # n8n registers a PRODUCTION webhook only for a node that carries a
    # webhookId. Without it, the workflow can be flipped to active (the flag is
    # set in the DB) and POSTs to /webhook/smart-order-router still come back
    # 404 "not registered". The editor mints this id when you save in the UI,
    # which is why the toggle works there but a CLI activation does not.
    "webhookId": nid("order-webhook"),
    "parameters": {
        "httpMethod": "POST",
        "path": "smart-order-router",
        "responseMode": "lastNode",
        "options": {},
    },
})

# 2. Normalize order + attach mock inventory
normalize_code = '''/**
 * Normalize incoming order data and attach a mock warehouse inventory snapshot.
 *
 * In production the inventory snapshot would come from your WMS, your inventory
 * service, or a Postgres lookup. We hard-code it here so the in-class exercise
 * is fully self-contained — no DB to provision, no API to mock.
 *
 * Mutate the inventory object below to drive different scenarios:
 *   - Set a SKU to 0 in WAREHOUSE_A to force fallback routing.
 *   - Set a SKU to 0 in all three warehouses to force the manual-review path.
 */
const order = $json.body || $json;

// Normalize / default missing fields so downstream nodes can rely on the shape.
const normalized = {
  order_id:        order.order_id        || `ORD-${Date.now()}`,
  customer_id:     order.customer_id     || "CUST-UNKNOWN",
  customer_tier:   order.customer_tier   || "regular",
  items:           order.items           || [],
  shipping_method: order.shipping_method || "standard",
  payment_method:  order.payment_method  || "credit_card",
  order_value:     Number(order.order_value || 0),
  total_quantity:  (order.items || []).reduce((acc, i) => acc + Number(i.quantity || 0), 0),
};

// Mock inventory: per-warehouse stock for each SKU.
const inventory = {
  WAREHOUSE_A: { "SKU-001": 50,  "SKU-002": 0,   "SKU-003": 200 },  // Express hub
  WAREHOUSE_B: { "SKU-001": 800, "SKU-002": 600, "SKU-003": 400 },  // Standard hub
  WAREHOUSE_C: { "SKU-001": 200, "SKU-002": 1500,"SKU-003": 0   },  // Bulk hub
};

return [{ json: { order: normalized, inventory } }];
'''
nodes.append(code_node("Normalize Order", "normalize", normalize_code, 1, 1))

# 3. AI Classification
nodes.append(http_anthropic(
    "AI Order Classification", "classify", CLASSIFICATION_SYSTEM,
    "'Order:\\n' + JSON.stringify($json.order, null, 2)",
    2, 1,
))

# 4. Parse classification + carry order context forward
parse_code = '''/**
 * Pull the classification JSON out of the Anthropic response envelope and
 * combine it with the original order/inventory so downstream nodes have
 * everything they need in $json.
 *
 * The Anthropic API returns: { content: [{ type: "text", text: "..." }], ... }
 * Our system prompt forbids markdown fences, so JSON.parse should succeed
 * directly. If it doesn't, the system prompt is what to debug.
 */
const raw = $json.content[0].text.trim();
let classification;
try {
  classification = JSON.parse(raw);
} catch (e) {
  throw new Error("Classifier did not return valid JSON. Got:\\n" + raw.slice(0, 500));
}

// Cross-node references pull the order + inventory back into scope.
const upstream = $('Normalize Order').first().json;

return [{
  json: {
    order: upstream.order,
    inventory: upstream.inventory,
    priority:                classification.priority,
    classification_reasoning: classification.reasoning,
    classification_confidence: classification.confidence,
  },
}];
'''
nodes.append(code_node("Parse Classification", "parse", parse_code, 3, 1))

# 5. Switch on priority -> 3 branches
nodes.append({
    "id": nid("switch"),
    "name": "Route by Priority",
    "type": "n8n-nodes-base.switch",
    "typeVersion": 3.2,
    "position": pos(4, 1),
    "parameters": {
        "rules": {
            "values": [
                {
                    "conditions": {
                        "options": {"caseSensitive": True, "typeValidation": "strict"},
                        "conditions": [{
                            "leftValue": "={{ $json.priority }}",
                            "rightValue": label,
                            "operator": {"type": "string", "operation": "equals"},
                        }],
                        "combinator": "and",
                    },
                    "renameOutput": True,
                    "outputKey": label,
                }
                for label in ["urgent", "standard", "bulk"]
            ]
        },
        "options": {"fallbackOutput": "extra"},
    },
})

# 6. Three "Pick Warehouse" Code nodes — one per priority lane.
def pick_warehouse_code(warehouse, lane_name, rationale):
    return f'''/**
 * Lane: {lane_name}
 * Assigned warehouse: {warehouse}
 * Why: {rationale}
 *
 * Each lane assigns its preferred warehouse and checks whether stock is
 * available for every SKU in the order. The downstream IF node routes
 * to the fulfillment path or the fallback-sourcing path based on the
 * `in_stock` boolean we set here.
 */
const j = $json;
const warehouse = "{warehouse}";

// Check every line item against the assigned warehouse's stock.
const stock_per_item = j.order.items.map(item => {{
  const available = (j.inventory[warehouse] || {{}})[item.sku] || 0;
  return {{ sku: item.sku, requested: item.quantity, available, ok: available >= item.quantity }};
}});
const in_stock = stock_per_item.every(s => s.ok);

return [{{
  json: {{
    ...j,
    assigned_warehouse: warehouse,
    lane: "{lane_name}",
    stock_per_item,
    in_stock,
  }},
}}];
'''


nodes.append(code_node(
    "Pick Warehouse A (Express)", "pick-a",
    pick_warehouse_code("WAREHOUSE_A", "express", "fastest carrier coverage, regional hub"),
    5, 0,
))
nodes.append(code_node(
    "Pick Warehouse B (Standard)", "pick-b",
    pick_warehouse_code("WAREHOUSE_B", "standard", "balanced cost vs transit time"),
    5, 1,
))
nodes.append(code_node(
    "Pick Warehouse C (Bulk)", "pick-c",
    pick_warehouse_code("WAREHOUSE_C", "bulk", "lowest per-unit cost, highest volume capacity"),
    5, 2,
))

# 7. IF node: in_stock?
nodes.append({
    "id": nid("if-stock"),
    "name": "Stock Available?",
    "type": "n8n-nodes-base.if",
    "typeVersion": 2.2,
    "position": pos(6, 1),
    "parameters": {
        "conditions": {
            "options": {"caseSensitive": True, "typeValidation": "strict"},
            "conditions": [{
                "leftValue": "={{ $json.in_stock }}",
                "rightValue": True,
                "operator": {"type": "boolean", "operation": "true"},
            }],
            "combinator": "and",
        },
        "options": {},
    },
})

# 8. Alternative sourcing (out-of-stock branch)
fallback_code = '''/**
 * Out-of-stock fallback: scan the other warehouses for stock and route
 * the order there. If no warehouse has stock, escalate to manual review.
 *
 * In production this would also consider transfer cost, transit time,
 * and customer-facing SLA implications. We keep it simple here: first
 * warehouse with stock wins.
 */
const j = $json;
const candidates = ["WAREHOUSE_A", "WAREHOUSE_B", "WAREHOUSE_C"]
  .filter(w => w !== j.assigned_warehouse);

let fallback = null;
for (const w of candidates) {
  const ok = j.order.items.every(item => (j.inventory[w] || {})[item.sku] >= item.quantity);
  if (ok) { fallback = w; break; }
}

return [{
  json: {
    ...j,
    fallback_warehouse: fallback,
    action: fallback ? "fallback_routed" : "manual_review",
    fallback_reason: fallback
      ? `Original warehouse ${j.assigned_warehouse} lacked stock; routed to ${fallback}.`
      : `No warehouse has stock for all line items. Escalating to manual review.`,
  },
}];
'''
nodes.append(code_node("Alternative Sourcing", "fallback", fallback_code, 7, 2))

# 9. In-stock branch: just sets action
in_stock_set = set_node(
    "Mark Routed", "mark-routed",
    [{
        "name": "action",
        "value": "routed_primary",
        "type": "string",
    }],
    7, 0,
)
# A Set node on typeVersion 3.x emits ONLY the fields it assigns unless told
# otherwise, so this node was passing {action: "routed_primary"} downstream and
# dropping `order`, `priority`, `inventory` and the rest of the item. "Log
# Decision" then read j.order.order_id and threw "Cannot read properties of
# undefined". That broke the entire in-stock path: only orders that fell through
# to Alternative Sourcing (which spreads ...j) could reach the audit log.
in_stock_set["parameters"]["includeOtherFields"] = True
nodes.append(in_stock_set)

# 10. Logging Code node — combines both branches
log_code = '''/**
 * Audit log entry — records the routing decision and reasoning trace.
 *
 * In production this would write to a database or log shipper. Here we
 * just structure the log entry and pass it forward; the workflow's
 * webhook response is the audit record for now.
 */
const j = $json;

const log_entry = {
  timestamp: new Date().toISOString(),
  order_id: j.order.order_id,
  customer_id: j.order.customer_id,
  customer_tier: j.order.customer_tier,
  priority: j.priority,
  classification_reasoning: j.classification_reasoning,
  classification_confidence: j.classification_confidence,
  assigned_warehouse: j.assigned_warehouse,
  fallback_warehouse: j.fallback_warehouse || null,
  final_warehouse: j.fallback_warehouse || j.assigned_warehouse,
  action: j.action,
  in_stock_primary: j.in_stock,
  stock_check: j.stock_per_item,
};

return [{ json: log_entry }];
'''
nodes.append(code_node("Log Decision", "log", log_code, 8, 1))

# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

connections = {}


def connect(src, dst, src_index=0):
    if src not in connections:
        connections[src] = {"main": []}
    while len(connections[src]["main"]) <= src_index:
        connections[src]["main"].append([])
    connections[src]["main"][src_index].append({"node": dst, "type": "main", "index": 0})


connect("Order Webhook", "Normalize Order")
connect("Normalize Order", "AI Order Classification")
connect("AI Order Classification", "Parse Classification")
connect("Parse Classification", "Route by Priority")

# Switch outputs: 0=urgent, 1=standard, 2=bulk
connect("Route by Priority", "Pick Warehouse A (Express)", src_index=0)
connect("Route by Priority", "Pick Warehouse B (Standard)", src_index=1)
connect("Route by Priority", "Pick Warehouse C (Bulk)", src_index=2)

# All three "Pick" nodes feed the same IF
connect("Pick Warehouse A (Express)", "Stock Available?")
connect("Pick Warehouse B (Standard)", "Stock Available?")
connect("Pick Warehouse C (Bulk)", "Stock Available?")

# IF: true (in stock) -> Mark Routed; false (out of stock) -> Alternative Sourcing
connect("Stock Available?", "Mark Routed", src_index=0)
connect("Stock Available?", "Alternative Sourcing", src_index=1)

# Both branches converge at Log Decision
connect("Mark Routed", "Log Decision")
connect("Alternative Sourcing", "Log Decision")

# ---------------------------------------------------------------------------
# Workflow envelope
# ---------------------------------------------------------------------------

workflow = {
    "id": "smart-order-router-v1",
    "name": "Smart Order Router (In-Class)",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}
# NOTE: n8n's CLI import does not honor an "active": true field on the
# workflow. After importing, students must toggle activation via the
# editor's top-right switch before the production webhook URL works.
# This is documented in docs/in-class.md.

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(workflow, indent=2))
print(f"wrote {OUT}")
print(f"  nodes: {len(nodes)}")
print(f"  connection groups: {sum(len(v['main']) for v in connections.values())}")
