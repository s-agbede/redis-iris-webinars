import type { Comparison, Hit, Mode, ModeResult } from "./api";

export type VisibleCount = 3 | 5;
export type ProductRank =
  | { status: "ranked"; rank: number; outsideVisible: boolean }
  | { status: "outside" }
  | { status: "unavailable" };

export const modeOrder: Mode[] = ["basic", "text", "vector", "hybrid"];

export function rankForProduct(comparison: Comparison, mode: Mode, productId: string, visibleCount: VisibleCount): ProductRank {
  const result = comparison.results.find((item) => item.mode === mode);
  if (!result || result.error) return { status: "unavailable" };
  const index = result.hits.findIndex((hit) => hit.product_id === productId);
  return index < 0
    ? { status: "outside" }
    : { status: "ranked", rank: index + 1, outsideVisible: index >= visibleCount };
}

export function visibleProductUnion(comparison: Comparison, visibleCount: VisibleCount): Hit[] {
  const products = new Map<string, Hit>();
  for (const mode of modeOrder) {
    const result = comparison.results.find((item) => item.mode === mode);
    if (!result || result.error) continue;
    for (const hit of result.hits.slice(0, visibleCount)) {
      if (!products.has(hit.product_id)) products.set(hit.product_id, hit);
    }
  }
  return [...products.values()];
}

export function selectionAcrossModes(comparison: Comparison, productId: string, visibleCount: VisibleCount): { mode: Mode; result: ModeResult | null; hit: Hit | null; rank: ProductRank }[] {
  return modeOrder.filter((mode) => mode !== "basic" || comparison.results.some((result) => result.mode === "basic")).map((mode) => {
    const result = comparison.results.find((item) => item.mode === mode) ?? null;
    return {
      mode,
      result,
      hit: result && !result.error ? result.hits.find((hit) => hit.product_id === productId) ?? null : null,
      rank: rankForProduct(comparison, mode, productId, visibleCount),
    };
  });
}

export function highlightSegments(text: string, ranges: { start: number; end: number }[]): { text: string; matched: boolean }[] {
  // API offsets count Unicode code points, like Python strings, not UTF-16 units.
  const characters = Array.from(text);
  const valid = ranges
    .filter(({ start, end }) => Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= characters.length)
    .sort((left, right) => left.start - right.start);
  const merged: { start: number; end: number }[] = [];
  for (const range of valid) {
    const previous = merged.at(-1);
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end);
    else merged.push({ ...range });
  }
  const segments: { text: string; matched: boolean }[] = [];
  let cursor = 0;
  for (const range of merged) {
    if (range.start > cursor) segments.push({ text: characters.slice(cursor, range.start).join(""), matched: false });
    segments.push({ text: characters.slice(range.start, range.end).join(""), matched: true });
    cursor = range.end;
  }
  if (cursor < characters.length || segments.length === 0) segments.push({ text: characters.slice(cursor).join(""), matched: false });
  return segments;
}

export function highlightPreviewSegments(text: string, ranges: { start: number; end: number }[]): { text: string; matched: boolean }[] {
  const segments = highlightSegments(text, ranges);
  const firstMatch = segments.findIndex((segment) => segment.matched);
  const matchOffset = segments.slice(0, Math.max(0, firstMatch))
    .reduce((length, segment) => length + Array.from(segment.text).length, 0);
  const start = Math.max(0, matchOffset - 24);
  const end = Math.min(Array.from(text).length, start + 180);
  const preview: { text: string; matched: boolean }[] = [];
  if (start > 0) preview.push({ text: "…", matched: false });
  let offset = 0;
  for (const segment of segments) {
    const characters = Array.from(segment.text);
    const from = Math.max(0, start - offset);
    const to = Math.min(characters.length, end - offset);
    if (from < to) preview.push({ text: characters.slice(from, to).join(""), matched: segment.matched });
    offset += characters.length;
  }
  if (end < offset) preview.push({ text: "…", matched: false });
  return preview;
}
