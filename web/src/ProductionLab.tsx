import { useEffect, useRef, useState } from "react";
import { errorMessage, requestJSON } from "./api";
import "./production.css";

type LabStatus = {
  paused: boolean;
  unread: number;
  pending: number;
  failed_count: number;
  failures: { event_id: string; original_event_id: string; product_id: string; error: string; attempts: number }[];
  last_error: string | null;
  products: { product_id: string; title: string; exists: boolean; passage_count: number }[];
  active_index: string;
};

type ProductionLabProps = {
  onChanged?: () => void;
  initiallyOpen?: boolean;
  onSearch: (query: string) => void;
};

const defaultProduct = {
  title: "Aurora ZV Demo Camera",
  brand: "Demo",
  color: "White",
  description: "A fictional compact camera for filming yourself. Created only to demonstrate search index freshness.",
  features: "Fictional demo features: flip-out screen, interchangeable lenses, and a lightweight white body. Not a real product.",
};

export function ProductionLab({ onChanged, onSearch, initiallyOpen = false }: ProductionLabProps) {
  const [expanded, setExpanded] = useState(initiallyOpen);
  const [status, setStatus] = useState<LabStatus | null>(null);
  const [product, setProduct] = useState(defaultProduct);
  const [busy, setBusy] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;
  const lastStatus = useRef<string | null>(null);
  const busyRef = useRef(false);
  const pollController = useRef<AbortController | null>(null);
  const mutationController = useRef<AbortController | null>(null);

  function acceptStatus(next: LabStatus, forceRefresh = false) {
    const signature = JSON.stringify({ ...next, products: [...next.products].sort((a, b) => a.product_id.localeCompare(b.product_id)) });
    const changed = lastStatus.current !== null && signature !== lastStatus.current;
    lastStatus.current = signature;
    setStatus(next);
    if (changed || forceRefresh) onChangedRef.current?.();
  }

  useEffect(() => () => mutationController.current?.abort(), []);

  useEffect(() => {
    if (!expanded) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!busyRef.current) {
        const controller = new AbortController();
        pollController.current = controller;
        try {
          const next = await requestJSON<LabStatus>("/lab", { signal: controller.signal });
          if (!stopped && !controller.signal.aborted) {
            acceptStatus(next);
            setConnectionError("");
          }
        } catch (cause: unknown) {
          if (!stopped && !controller.signal.aborted) setConnectionError(errorMessage(cause));
        }
      }
      if (!stopped) timer = setTimeout(() => void poll(), 1000);
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      pollController.current?.abort();
    };
  }, [expanded]);

  async function mutate(path: string, method: "POST" | "DELETE", body?: unknown) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setMutationError("");
    pollController.current?.abort();
    const controller = new AbortController();
    mutationController.current = controller;
    try {
      const next = await requestJSON<LabStatus>(path, {
        method,
        ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        acceptStatus(next, true);
        setConnectionError("");
      }
    } catch (cause: unknown) {
      if (!controller.signal.aborted) setMutationError(errorMessage(cause));
    } finally {
      busyRef.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <details className="production-lab" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
    <summary>Production lab</summary>
    <section className="production-content" aria-labelledby="freshness-heading" aria-busy={busy}>
      <header className="production-heading"><h2 id="freshness-heading">Freshness</h2><span>Source → stream → search index</span></header>
      <p className="production-help">Pause indexing, add a demo camera, then search for it. Resume to see its passages appear. Delete it while paused to explore stale records.</p>
      {(connectionError || mutationError || status?.last_error) && <div className="production-error" role="alert">{mutationError || connectionError || status?.last_error}</div>}
      {!status && <p className="production-help" role="status">{connectionError ? "Waiting for the lab service. Retrying automatically…" : "Loading freshness status…"}</p>}
      {status && <>
        <div className="production-status" role="status">
          <strong>{status.paused ? "Indexing paused" : "Indexer running"}</strong>
          <span>{status.unread} unread · {status.pending} pending · {status.failed_count} failed</span>
        </div>
        <div className="production-actions">
          <button type="button" disabled={busy} onClick={() => void mutate("/lab/pause", "POST", { paused: !status.paused })}>{status.paused ? "Resume indexing" : "Pause indexing"}</button>
          <button type="button" disabled={busy} onClick={() => void mutate("/lab/reset", "POST")}>Reset demo</button>
          {busy && <span role="status">Applying change…</span>}
        </div>
        <p className="production-help">Unread events await processing. Pending events have been received but are not yet acknowledged. Reset removes the demo products.</p>
        {status.failed_count > 0 && <section aria-label="Failed indexing changes">
          <h3>Failed changes ({status.failed_count})</h3>
          <p>These changes need attention after three failed attempts. Fix the cause, then retry the product’s current state. Showing the latest 50.</p>
          <ul className="production-products">
            {status.failures.map((failure) => <li key={failure.event_id}>
              <div><strong>{failure.product_id}</strong><p>{failure.error}</p><p>{failure.attempts} attempts · Event {failure.original_event_id}</p></div>
              <button type="button" disabled={busy} onClick={() => void mutate(`/lab/failures/${encodeURIComponent(failure.event_id)}/retry`, "POST")}>Retry</button>
            </li>)}
          </ul>
        </section>}
        <form className="production-form" onSubmit={(event) => { event.preventDefault(); void mutate("/lab/products", "POST", product); }}>
          <fieldset disabled={busy}>
            <legend>Add a fictional camera</legend>
            <label className="production-title-field">Title<input required maxLength={200} value={product.title} onChange={(event) => setProduct({ ...product, title: event.target.value })} /></label>
            <div className="production-fields">
              <label>Brand<input required maxLength={100} value={product.brand} onChange={(event) => setProduct({ ...product, brand: event.target.value })} /></label>
              <label>Colour<input required maxLength={100} value={product.color} onChange={(event) => setProduct({ ...product, color: event.target.value })} /></label>
            </div>
            <details className="production-description"><summary>Description and features</summary>
              <label>Description<textarea required rows={3} maxLength={4000} value={product.description} onChange={(event) => setProduct({ ...product, description: event.target.value })} /></label>
              <label>Features<textarea required rows={3} maxLength={4000} value={product.features} onChange={(event) => setProduct({ ...product, features: event.target.value })} /></label>
            </details>
            <button type="submit" disabled={!product.title.trim() || !product.brand.trim() || !product.color.trim() || !product.description.trim() || !product.features.trim()}>Add demo camera</button>
          </fieldset>
        </form>
        {status.products.length > 0 ? <ul className="production-products" aria-label="Demo products">
          {status.products.map((item) => <li key={item.product_id}>
            <div><strong>{item.title}</strong><p>Source: {item.exists ? "exists" : "deleted"} · Index: {item.passage_count} {item.passage_count === 1 ? "passage" : "passages"}</p></div>
            <div className="production-actions">
              <button type="button" disabled={busy} onClick={() => onSearch(item.title)} aria-label={`Search for ${item.title}`}>Search</button>
              <button type="button" disabled={busy || !item.exists} onClick={() => void mutate(`/lab/products/${encodeURIComponent(item.product_id)}`, "DELETE")} aria-label={`Delete ${item.title} from source`}>Delete</button>
            </div>
          </li>)}
        </ul> : <p className="production-help">No demo products yet. Add one above to begin.</p>}
        <p className="production-index">Active index <code>{status.active_index}</code></p>
      </>}
    </section>
  </details>;
}
