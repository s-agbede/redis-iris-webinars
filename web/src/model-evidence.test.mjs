import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";

// Compile the leaf component with existing tooling; no browser test dependency required.
const source = readFileSync(new URL("./ModelEvidence.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
const component = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  assert.equal(name, "react/jsx-runtime");
  return jsxRuntime;
}, component, component.exports);
const { ModelEvidence } = component.exports;
const context = { mode: "none", message: "What camera do I own?", session: { events: [], summary: null }, memories: [], guidance: [], products: [], previous_products: [], purchases: [], search_query: null };
const request = input => ({ model: "test-model", instructions: "Be a camera adviser.", input: JSON.stringify(input), store: false, reasoning: { effort: "low" }, max_output_tokens: 2000, text: {} });
const render = value => renderToStaticMarkup(createElement(ModelEvidence, { request: value }));

test("memory-off evidence makes omitted context visible and labels the answer call", () => {
  const html = render(request(context));
  for (const text of ["Answer request", "Memory off", "No previous turns supplied.", "No long-term memories supplied.", "Be a camera adviser.", "Raw answer request (JSON)"]) assert.ok(html.includes(text));
});

test("memory-on evidence shows captured turns, summary and scoped facts", () => {
  const html = render(request({ ...context, mode: "both", session: { events: [{ event_id: "1", role: "USER", text: "I film walking tours." }], summary: "Earlier we discussed travel." }, memories: [{ id: "kit", text: "Owns Sony ZV-E10", memory_type: "semantic", owner_id: "alex" }] }));
  for (const text of ["Session + long-term", "I film walking tours.", "Earlier we discussed travel.", "Owns Sony ZV-E10", "Owner: alex"]) assert.ok(html.includes(text));
  assert.ok(!html.includes("No previous turns supplied."));
});

test("legacy replies explicitly report missing capture", () => {
  const html = render(null);
  assert.ok(html.includes("before request capture"));
  assert.ok(!html.includes("Raw answer request"));
});

test("request text is rendered as text, never HTML", () => {
  const html = render({ ...request(context), instructions: '<img src=x onerror="alert(1)">' });
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
});

test("native tool requests show original memory context and the tool exchange", () => {
  const html = render({ ...request(context), tools: [{ name: "search_catalogue" }], input: [
    { role: "user", content: JSON.stringify({ ...context, mode: "both", message: "Find a microphone" }) },
    { type: "reasoning", encrypted_content: "opaque-provider-state" },
    { type: "function_call", name: "search_catalogue", call_id: "call-1", arguments: '{"query":"microphone Sony ZV-E10"}' },
    { type: "function_call_output", call_id: "call-1", output: '{"products":[{"title":"Example microphone","description":"<img src=x>"}]}' },
  ] });
  for (const text of ["Session + long-term", "Find a microphone", "Tool calls", "search_catalogue", "microphone Sony ZV-E10", "Example microphone"]) assert.ok(html.includes(text), text);
  assert.ok(!html.includes("separate search-planning call"));
  assert.ok(!html.includes("<img"));
});

test("native no-tool replies show context and explicitly report no calls", () => {
  const html = render({ ...request(context), tools: [{ name: "get_purchase_history" }], input: [
    { role: "user", content: JSON.stringify(context) },
  ] });
  assert.ok(html.includes("Memory off"));
  assert.ok(html.includes("No tools called for this reply."));
});

test("unsupported captured context keeps raw evidence available without crashing", () => {
  const unsupported = [
    {}, [], "legacy input", null,
    { ...context, session: {} },
    { ...context, session: { events: [null], summary: null } },
    { ...context, memories: [{ text: { invalid: true } }] },
    { ...context, purchases: [{ order_id: "old-order" }] },
  ];
  for (const value of unsupported) {
    const html = render(request(value));
    assert.ok(html.includes("Readable context is unavailable for this capture."));
    assert.ok(html.includes("Raw answer request (JSON)"));
  }
});

test("discovered MCP tools show their names, descriptions, schemas and selected calls", () => {
  const html = render({ ...request(context), tools: [{ name: "expand_results", description: "Follow a declared relationship.", parameters: { type: "object", properties: { relationship: { type: "string" } } } }], input: [
    { role: "user", content: JSON.stringify({ ...context, shopper_id: "alex" }) },
    { type: "function_call", name: "expand_results", call_id: "mcp-1", arguments: '{"relationship":"product"}' },
    { type: "function_call_output", call_id: "mcp-1", output: '{"results":[{"product_title":"Sony ZV-E10"}],"has_more":false}' },
  ] });
  for (const text of ["Available tools", "expand_results", "Follow a declared relationship.", "Input schema", "Sony ZV-E10"]) assert.ok(html.includes(text), text);
  assert.ok(!html.includes("get_purchase_history"));
});

test("generated-tool context does not need legacy purchase placeholders", () => {
  const { purchases, ...current } = context;
  const html = render(request({ ...current, shopper_id: "alex" }));
  assert.ok(html.includes("Memory off"));
  assert.ok(html.includes("None supplied. Later lookups appear under Tool calls."));
  assert.ok(!html.includes("Readable context is unavailable"));
});

test("teaching summary distinguishes executed sources from available tools", () => {
  const current = { ...context, shopper_id: "alex" };
  const base = { ...request(current), tools: [{ name: "filter_purchase" }, { name: "search_catalogue" }] };
  const noReads = render({ ...base, input: [{ role: "user", content: JSON.stringify(current) }] });
  assert.ok(noReads.includes("Context Retriever (MCP): 0 calls"));
  assert.ok(noReads.includes("Catalogue search: 0 calls"));
  assert.ok(noReads.includes("Available tools are definitions, not completed lookups."));
  const html = render({ ...base, input: [
    { role: "user", content: JSON.stringify(current) },
    { type: "function_call", name: "filter_purchase", call_id: "1", arguments: "{}" },
    { type: "function_call_output", call_id: "1", output: '{"isError":true,"error":"invalid_filter_field"}' },
    { type: "function_call", name: "search_catalogue", call_id: "2", arguments: '{"query":"microphone"}' },
    { type: "function_call_output", call_id: "2", output: '{"products":[]}' },
  ] });
  assert.ok(html.includes("Context Retriever (MCP): 1 call"));
  assert.ok(html.includes("Catalogue search: 1 call"));
  assert.ok(html.includes("Query failed — no records retrieved by this call."));
  assert.ok(html.includes("Memory off omits conversation history and recalled memories; live lookups remain available."));
});

test("legacy tool captures are not relabelled as autogenerated MCP calls", () => {
  const html = render({ ...request(context), tools: [{ name: "get_purchase_history" }], input: [
    { role: "user", content: JSON.stringify(context) },
    { type: "function_call", name: "get_purchase_history", call_id: "old", arguments: "{}" },
    { type: "function_call_output", call_id: "old", output: '{"purchases":[]}' },
  ] });
  assert.ok(!html.includes("Context Retriever (MCP): 1 call"));
  assert.ok(html.includes("Recorded retrieval tool"));
});
