import assert from "node:assert/strict";
import { test } from "node:test";
import * as learning from "./learning.ts";
import {
  highlightSegments,
  rankForProduct,
  selectionAcrossModes,
  visibleProductUnion,
} from "./learning.ts";

const hit = (id, passage = `${id}-passage`) => ({
  product_id: id,
  title: `Camera ${id}`,
  passage: { passage_id: passage },
});
const comparison = {
  results: [
    { mode: "text", error: null, hits: ["a", "b", "c", "d", "e"].map((id) => hit(id)) },
    { mode: "vector", error: null, hits: [hit("d", "different-passage"), hit("b"), hit("f")] },
    { mode: "hybrid", error: null, hits: [hit("b"), hit("d"), hit("a")] },
  ],
};

test("rank four is present in fetched results even when only three are visible", () => {
  assert.deepEqual(rankForProduct(comparison, "text", "d", 3), {
    status: "ranked", rank: 4, outsideVisible: true,
  });
  assert.deepEqual(rankForProduct(comparison, "text", "d", 5), {
    status: "ranked", rank: 4, outsideVisible: false,
  });
});

test("outside fetched results differs from an unavailable method", () => {
  assert.deepEqual(rankForProduct(comparison, "text", "f", 3), { status: "outside" });
  assert.deepEqual(rankForProduct({ results: [] }, "text", "a", 3), { status: "unavailable" });
  assert.deepEqual(rankForProduct({ results: [{ mode: "text", error: "offline", hits: [hit("a")] }] }, "text", "a", 3), { status: "unavailable" });
});

test("three/five toggle derives a stable product union without mutating fetched results", () => {
  assert.deepEqual(visibleProductUnion(comparison, 3).map((item) => item.product_id), ["a", "b", "c", "d", "f"]);
  assert.deepEqual(visibleProductUnion(comparison, 5).map((item) => item.product_id), ["a", "b", "c", "d", "e", "f"]);
  assert.equal(comparison.results[0].hits.length, 5);
});

test("one shared product selection retains each mode's distinct winning passage", () => {
  const selected = selectionAcrossModes(comparison, "d", 3);
  assert.deepEqual(selected.map((item) => item.mode), ["text", "vector", "hybrid"]);
  assert.deepEqual(selected.map((item) => item.hit.passage.passage_id), ["d-passage", "different-passage", "d-passage"]);
  assert.deepEqual(selected.map((item) => item.rank.rank), [4, 1, 2]);
  assert.equal(selectionAcrossModes(comparison, "f", 3)[0].hit, null);
});

test("highlight spans use supplied offsets, merge overlap, and preserve unmarked text", () => {
  assert.deepEqual(highlightSegments("Sony ZV E10 camera", [{ start: 0, end: 4 }, { start: 5, end: 10 }, { start: 8, end: 11 }]), [
    { text: "Sony", matched: true },
    { text: " ", matched: false },
    { text: "ZV E10", matched: true },
    { text: " camera", matched: false },
  ]);
  assert.deepEqual(highlightSegments("Sony camera", []), [{ text: "Sony camera", matched: false }]);
});

test("highlight offsets handle Unicode code points and ignore invalid spans", () => {
  assert.deepEqual(highlightSegments("📷 Sony", [{ start: -1, end: 3 }, { start: 2, end: 6 }, { start: 7, end: 9 }, { start: 4, end: 4 }]), [
    { text: "📷 ", matched: false }, { text: "Sony", matched: true },
  ]);
});

test("result excerpts bring a late match into view and preserve Unicode offsets", () => {
  const prefix = "📷 Accessories and technical specifications. ".repeat(12);
  const text = `${prefix}SONY lens for portraits. ${"More source details. ".repeat(12)}`;
  const start = Array.from(prefix).length;
  const segments = learning.highlightPreviewSegments?.(text, [{ start, end: start + 4 }]) ?? [];
  assert.deepEqual(segments.filter((segment) => segment.matched).map((segment) => segment.text), ["SONY"]);
  const excerpt = segments.map((segment) => segment.text).join("");
  assert.ok(excerpt.startsWith("…"));
  assert.ok(excerpt.endsWith("…"));
  assert.ok(excerpt.indexOf("SONY") <= 30);
  assert.ok(Array.from(excerpt).length <= 182);
});

test("result excerpts keep literal markup as text and ignore invalid match ranges", () => {
  const text = "<img src=x onerror=alert(1)> Sony lens";
  assert.deepEqual(learning.highlightPreviewSegments?.(text, [{ start: -1, end: 5 }]) ?? [], [
    { text, matched: false },
  ]);
});
