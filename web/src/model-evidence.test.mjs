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
