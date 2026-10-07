import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";
import * as api from "./api.ts";
import * as shopEvidence from "./shop-evidence.ts";
import * as cacheEvidence from "./cache-evidence.ts";

// Render with React itself; only HTTP is excluded from this server-side view test.
function loadComponent(filename, dependencies) {
  const source = readFileSync(new URL(filename, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const component = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    assert.ok(name in dependencies, `Unexpected import: ${name}`);
    return dependencies[name];
  }, component, component.exports);
  return component.exports;
}

const dependencies = { react: React, "react/jsx-runtime": jsxRuntime };
const cacheComponent = loadComponent("./CacheEvidence.tsx", {
  ...dependencies, "./cache-evidence": cacheEvidence,
});
const { ShopInspector } = loadComponent("./ShopInspector.tsx", {
  ...dependencies,
  "./api": api,
  "./shop-api": { shopPost: () => { throw new Error("No request should run during rendering"); } },
  "./shop-evidence": shopEvidence,
  "./CacheEvidence": cacheComponent,
});

const context = {
  mode: "both", message: "What is aperture?", session: { events: [], summary: null },
  memories: [], guidance: [], products: [], previous_products: [], purchases: [], search_query: null,
};
const turn = {
  user: "What is aperture?", assistant: "Aperture controls light.", products: [],
  inspector: { context, total_ms: 425, memory_ms: 1, search_ms: 0, model_ms: 0, event_ids: [], note: "Recorded evidence." },
};
const render = turns => renderToStaticMarkup(React.createElement(ShopInspector, {
  shopper: "alex", session: { session_id: "example", owner_id: "shopper:alex", turns },
  revision: 0, cacheReady: true, busy: false, onClose: () => {},
}));

test("inspector distinguishes current cache-hit context from historical source evidence", () => {
  const html = render([{ ...turn, inspector: { ...turn.inspector, cache: {
    status: "hit", store_status: "not_requested", reason: "Approved reuse.",
    lookup_ms: 2, verifier_ms: 20, probabilities: {},
    original_context: { ...context, message: "Historical question" },
  } } }]);
  for (const text of [
    "validated cached product cards", "Historical cached source context", "Historical question",
    "Current memory and validated cached product cards for this reply.",
    "No tool calls recorded for this reply.",
  ]) assert.ok(html.includes(text), text);
  assert.ok(!html.includes("Includes products collected during tool calls."));
});

test("inspector initially selects the latest reply and preserves its recorded calls", () => {
  const html = render([turn, { ...turn, user: "Find a lens", inspector: {
    ...turn.inspector, context: { ...context, message: "Find a lens" },
    tool_calls: [{ call_id: "search", name: "search_catalogue", elapsed_ms: 12.4, arguments: { query: "lens" }, output: { products: [] } }],
  } }]);
  assert.ok(html.includes('value="-1" selected=""'));
  assert.ok(html.includes("2. Find a lens"));
  assert.ok(html.includes("search_catalogue · 12ms"));
  assert.ok(html.includes("Includes products collected during tool calls."));
  assert.ok(!html.includes("validated cached product cards"));
});

test("an empty conversation invites a message before showing reply evidence", () => {
  const html = render([]);
  assert.ok(html.includes("Send a message to inspect its context."));
  assert.ok(!html.includes("Current-turn context JSON"));
});
