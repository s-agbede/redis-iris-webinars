import { useState, type ReactNode } from "react";
import type { CacheTrace } from "./shop-api";
import {
  cacheRemovalTargets,
  cosineSimilarity,
  type CacheRemovalTarget,
} from "./cache-evidence";

type CacheEvidenceProps = {
  trace?: CacheTrace;
  ownerId: string;
  totalMs: number;
  canRemove: boolean;
  onRemove: (target: CacheRemovalTarget) => Promise<boolean>;
};

function Metric({ label, value }: { label: string; value: ReactNode }) {
  if (value == null) return null;
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function CacheEvidence({
  trace,
  ownerId,
  totalMs,
  canRemove,
  onRemove,
}: CacheEvidenceProps) {
  const [removing, setRemoving] = useState<string | null>(null);
  const [removed, setRemoved] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  if (!trace) {
    return (
      <p className="shop-small">
        No cache trace was captured for this saved reply.
      </p>
    );
  }
  const similarity = cosineSimilarity(trace.distance);
  const targets = cacheRemovalTargets(trace, ownerId);

  async function remove(target: CacheRemovalTarget) {
    if (removing || !canRemove) return;
    const key = `${target.scope}:${target.entryId}`;
    setRemoving(key);
    setError("");
    try {
      const deleted = await onRemove(target);
      setRemoved((previous) => ({
        ...previous,
        [key]: deleted
          ? "Removed from cache."
          : "This entry is already absent from the cache.",
      }));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not remove the cache entry.",
      );
    } finally {
      setRemoving(null);
    }
  }

  return (
    <section className="cache-evidence" aria-label="Semantic cache evidence">
      <h3>Semantic answer cache</h3>
      <p className="cache-outcomes">
        <strong>{`Lookup: ${trace.status}`}</strong>
        <span>{`Storage: ${trace.store_status}`}</span>
      </p>
      <p className="shop-small">{trace.reason}</p>
      {trace.store_reason && <p className="shop-small">{trace.store_reason}</p>}
      {trace.status === "hit" && (
        <p className="shop-small">
          No answer-model request or retrieval tool calls ran for this cache hit.
        </p>
      )}
      <dl className="cache-metrics">
        <Metric label="Matched scope" value={trace.scope} />
        <Metric
          label="Matched entry"
          value={trace.entry_id && <code>{trace.entry_id}</code>}
        />
        <Metric
          label="Age at lookup"
          value={
            trace.age_seconds != null
              ? `${trace.age_seconds.toFixed(1)}s`
              : null
          }
        />
        <Metric label="Redis cosine distance" value={trace.distance?.toFixed(4)} />
        <Metric
          label="Distance threshold"
          value={trace.distance_threshold?.toFixed(4)}
        />
        <Metric
          label="Cosine similarity"
          value={
            similarity != null
              ? `${similarity.toFixed(4)} (1 − distance; −1 to 1)`
              : null
          }
        />
        <Metric label="Jev decision" value={trace.decision} />
        <Metric label="Jev confidence" value={trace.confidence?.toFixed(4)} />
        <Metric
          label="Confidence threshold"
          value={trace.confidence_threshold?.toFixed(4)}
        />
        <Metric label="Verifier model" value={trace.verifier_model} />
        <Metric label="Verifier input tokens" value={trace.verifier_input_tokens} />
        <Metric
          label="Provider-reported Jev cost"
          value={
            trace.verifier_cost_usd != null
              ? `$${trace.verifier_cost_usd}`
              : null
          }
        />
        <Metric label="Cache lookup" value={`${trace.lookup_ms.toFixed(1)}ms`} />
        <Metric label="Jev verification" value={`${trace.verifier_ms.toFixed(1)}ms`} />
        <Metric label="Actual turn total" value={`${totalMs.toFixed(1)}ms`} />
        <Metric
          label="Stored entry"
          value={trace.stored_entry_id && <code>{trace.stored_entry_id}</code>}
        />
        <Metric label="Stored scope" value={trace.stored_scope} />
      </dl>
      {trace.matched_question != null && (
        <div className="memory-record">
          <strong>Matched prompt</strong>
          <p>{trace.matched_question}</p>
        </div>
      )}
      {!!Object.keys(trace.probabilities).length && (
        <details>
          <summary>Jev label probabilities</summary>
          <dl className="cache-metrics">
            {Object.entries(trace.probabilities).map(([label, probability]) => (
              <Metric key={label} label={label} value={probability.toFixed(4)} />
            ))}
          </dl>
        </details>
      )}
      {trace.original_context && (
        <details>
          <summary>Historical cached source context</summary>
          <p className="shop-small">
            Captured when the cached answer was created. This is historical
            evidence, not current retrieval for this reply.
          </p>
          <pre>{JSON.stringify(trace.original_context, null, 2)}</pre>
        </details>
      )}
      {!!targets.length && (
        <div className="cache-removal">
          <p className="shop-small">
            Presenter controls. Shared entries are available to both demo
            shoppers. Saved turn evidence remains after removal.
          </p>
          {targets.map((target) => {
            const key = `${target.scope}:${target.entryId}`;
            return (
              <div key={key}>
                <button
                  className="shop-secondary"
                  disabled={!canRemove || !!removing || !!removed[key]}
                  onClick={() => void remove(target)}
                >
                  {removing === key
                    ? "Removing…"
                    : `Remove ${target.label} (${target.shared ? "shared" : "this shopper"})`}
                </button>
                {removed[key] && (
                  <p className="shop-small" role="status">{removed[key]}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && (
        <p className="shop-error" role="alert">{error}</p>
      )}
    </section>
  );
}
