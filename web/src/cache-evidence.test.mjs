import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";
import * as cacheEvidence from "./cache-evidence.ts";
import { cacheReadiness, cacheRemovalTargets, cosineSimilarity } from "./cache-evidence.ts";

const entryId = "a".repeat(32);
const storedId = "b".repeat(32);

test("cosine similarity is derived from Redis distance across its full range", () => {
  assert.equal(cosineSimilarity(0), 1);
  assert.equal(cosineSimilarity(1), 0);
  assert.equal(cosineSimilarity(2), -1);
  assert.equal(cosineSimilarity(0.25), 0.75);
  for (const value of [undefined, null, NaN, Infinity, -0.1, 2.1]) {
    assert.equal(cosineSimilarity(value), null);
  }
});

test("cache readiness distinguishes configuration, missing services, and ready", () => {
  assert.match(cacheReadiness(null), /Checking/);
  assert.match(cacheReadiness({}), /unavailable/);
  assert.match(cacheReadiness({ cache_enabled: false }), /disabled/);
  assert.match(cacheReadiness({ cache_enabled: true, cache_ready: false, cache_missing: ["JEV_API_KEY"] }), /JEV_API_KEY/);
  assert.match(cacheReadiness({ cache_enabled: true, cache_ready: true, cache_missing: [] }), /Ready/);
});

test("legacy turns and entries without a verified scope have no delete control", () => {
  assert.deepEqual(cacheRemovalTargets(undefined, "shopper:alex"), []);
  assert.deepEqual(cacheRemovalTargets({ entry_id: entryId, scope: "shopper:jordan" }, "shopper:alex"), []);
  assert.deepEqual(cacheRemovalTargets({ entry_id: entryId }, "shopper:alex"), []);
  assert.deepEqual(cacheRemovalTargets({ stored_entry_id: storedId }, "shopper:alex"), []);
  assert.deepEqual(cacheRemovalTargets({ entry_id: "invalid", scope: "shared" }, "shopper:alex"), []);
});

test("candidate and newly stored entries retain distinct verified deletion scopes", () => {
  assert.deepEqual(cacheRemovalTargets({
    entry_id: entryId, scope: "shared", stored_entry_id: storedId, stored_scope: "shopper:alex",
  }, "shopper:alex"), [
    { entryId, scope: "shared", shared: true, label: "matched answer" },
    { entryId: storedId, scope: "shopper:alex", shared: false, label: "stored answer" },
  ]);
});

test("the same cache record receives only one removal control", () => {
  assert.equal(cacheRemovalTargets({ entry_id: entryId, scope: "shared", stored_entry_id: entryId, stored_scope: "shared" }, "shopper:alex").length, 1);
});

function renderCache(trace) {
  const source = readFileSync(new URL("./CacheEvidence.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
  const component = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return React;
    if (name === "react/jsx-runtime") return jsxRuntime;
    assert.equal(name, "./cache-evidence");
    return cacheEvidence;
  }, component, component.exports);
  return renderToStaticMarkup(React.createElement(component.exports.CacheEvidence, {
    trace, ownerId: "shopper:alex", totalMs: 425, canRemove: true, onRemove: async () => true,
  }));
}

const trace = {
  status: "hit", reason: "Jev approved reuse.", entry_id: entryId, scope: "shared",
  matched_question: "What is aperture?", age_seconds: 90, distance: 1.25,
  similarity: 999, distance_threshold: 0.15, decision: "accept", confidence: 0.97,
  confidence_threshold: 0.95, probabilities: { accept: 0.97, reject: 0.03 },
  lookup_ms: 3.5, verifier_ms: 42.5, verifier_model: "jev-test",
  verifier_input_tokens: 127, verifier_cost_usd: 0.0002, store_status: "not_requested",
  store_reason: null, stored_entry_id: null, original_context: { message: "Historical aperture question" },
};

test("cache inspector labels stored turns without cache evidence accurately", () => {
  assert.match(renderCache(undefined), /No cache trace was captured for this saved reply/);
});

test("cache inspector keeps retrieval distance, verifier confidence, and observed time distinct", () => {
  const html = renderCache(trace);
  for (const text of ["hit", "not_requested", "What is aperture?", entryId, "shared", "90.0s", "1.2500", "0.1500", "-0.2500", "accept", "0.9700", "0.9500", "0.0300", "jev-test", "127", "$0.0002", "3.5ms", "42.5ms", "425.0ms"]) {
    assert.ok(html.includes(text), text);
  }
  assert.ok(!html.includes("999"), "Similarity is derived from distance, not a separate unchecked field");
  assert.ok(!html.includes("savings"));
});

test("cache hits identify historical context and no current answer-model request", () => {
  const html = renderCache(trace);
  assert.ok(html.includes("Historical cached source context"));
  assert.ok(html.includes("No answer-model request or retrieval tool calls ran for this cache hit."));
  assert.ok(html.includes("Historical aperture question"));
  assert.ok(html.includes("Remove matched answer (shared)"));
});

test("every cache outcome and storage outcome is rendered independently", () => {
  for (const status of ["disabled", "miss", "hit", "rejected", "bypass", "error"]) {
    for (const store_status of ["not_requested", "stored", "skipped", "error"]) {
      const html = renderCache({ ...trace, status, store_status, verifier_cost_usd: null });
      assert.ok(html.includes(`Lookup: ${status}`));
      assert.ok(html.includes(`Storage: ${store_status}`));
      assert.ok(!html.includes("Provider-reported Jev cost"));
    }
  }
});
