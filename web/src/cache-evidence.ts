import type { CacheTrace, ShopStatus } from "./shop-api.ts";

export function cosineSimilarity(distance: number | null | undefined): number | null {
  return distance != null && Number.isFinite(distance) && distance >= 0 && distance <= 2
    ? 1 - distance
    : null;
}

export function cacheReadiness(
  status: Pick<ShopStatus, "cache_enabled" | "cache_ready" | "cache_missing"> | null,
): string {
  if (!status) return "Checking cache readiness…";
  if (status.cache_enabled == null) return "Cache readiness is unavailable from this server.";
  if (!status.cache_enabled) return "Semantic caching is disabled on this server.";
  if (status.cache_ready) return "Ready. Jev checks whether a matching answer still applies.";
  return status.cache_missing?.length
    ? `Cache unavailable: configure ${status.cache_missing.join(", ")} and restart.`
    : "Cache unavailable. Check the backend cache connection.";
}

export type CacheRemovalTarget = {
  entryId: string;
  scope: string;
  shared: boolean;
  label: string;
};

export function cacheRemovalTargets(
  trace: Partial<CacheTrace> | undefined,
  ownerId: string,
): CacheRemovalTarget[] {
  if (!trace) return [];
  const targets: CacheRemovalTarget[] = [];
  for (const [entryId, scope, label] of [
    [trace.entry_id, trace.scope, "matched answer"],
    [trace.stored_entry_id, trace.stored_scope, "stored answer"],
  ] as const) {
    if (
      entryId && /^[a-f0-9]{32}$/.test(entryId) && scope &&
      (scope === ownerId || scope === "shared") &&
      !targets.some((target) => target.entryId === entryId && target.scope === scope)
    ) {
      targets.push({ entryId, scope, shared: scope === "shared", label });
    }
  }
  return targets;
}
