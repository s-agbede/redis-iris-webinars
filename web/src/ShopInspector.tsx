import { useEffect, useState } from "react";
import { errorMessage, requestJSON } from "./api";
import type { Memory, MemoryList, Session, Shopper, Turn } from "./shop-api";
import { compareMemories } from "./shop-evidence";

export function ShopInspector({ shopper, session, revision, onClose }: { shopper: Shopper; session: Session | null; revision: number; onClose: () => void }) {
  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [baseline, setBaseline] = useState<{ records: Memory[]; at: number } | null>(null);
  const [refreshed, setRefreshed] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [auto, setAuto] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [turnIndex, setTurnIndex] = useState(-1);
  useEffect(() => {
    const controller = new AbortController();
    setError(""); setLoading(true);
    requestJSON<MemoryList>(`/shop/memories?shopper_id=${shopper}`, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return;
        if (!data.complete) throw new Error("Inventory is incomplete; no comparison can be made.");
        setMemories(data.memories); setRefreshed(Date.now());
      }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(errorMessage(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [shopper, revision, attempt]);
  useEffect(() => {
    if (!auto || loading) return;
    const timer = window.setTimeout(() => setAttempt(value => value + 1), 10000);
    return () => window.clearTimeout(timer);
  }, [auto, loading]);
  useEffect(() => setTurnIndex(-1), [session?.session_id, session?.turns.length]);
  const turns = session?.turns ?? [];
  const turn: Turn | undefined = turnIndex < 0 ? turns.at(-1) : turns[turnIndex];
  const changes = baseline && memories ? compareMemories(baseline.records, memories) : null;
  return <aside className="memory-inspector" aria-label="Memory inspector" onKeyDown={event => { if (event.key === "Escape") onClose(); }}>
    <div className="shop-section-heading"><span className="eyebrow">Live memory evidence</span><button autoFocus className="close-button" onClick={onClose} aria-label="Close memory inspector">×</button></div>
    <h2>What does it remember?</h2>
    <p className="shop-muted">A session is one conversation. Long-term memory belongs to the shopper and survives a new conversation.</p>
    <details open><summary>Long-term memory <span>{memories?.length ?? "…"}</span></summary>
      <div className="inspector-actions"><button disabled={loading} onClick={() => setAttempt(value => value + 1)}>{loading ? "Reading…" : "Refresh"}</button><button disabled={!memories || !refreshed || !!error || loading} onClick={() => setBaseline({ records: memories ?? [], at: refreshed ?? Date.now() })}>Capture before</button></div>
      <label className="shop-check"><input type="checkbox" checked={auto} onChange={event => setAuto(event.target.checked)} />Refresh every 10 seconds</label>
      {error && <p className="shop-error" role="alert">{error} Previously shown records may be stale.</p>}
      {refreshed && <p className="shop-small">Last read {new Date(refreshed).toLocaleTimeString()}{baseline && ` · ${Math.max(0, Math.round((refreshed - baseline.at) / 1000))}s since snapshot`}</p>}
      {memories?.length === 0 && <p className="shop-empty">No long-term records for {shopper} yet.</p>}
      {memories?.map(memory => <article className="memory-record" key={memory.id}><span className="eyebrow">{memory.memory_type}</span><p>{memory.text}</p><details><summary>Record identity</summary><code>{memory.id}</code><p className="shop-small">Owner: {memory.owner_id}</p></details></article>)}
      {changes && <div className="snapshot-diff"><h3>Observed changes</h3><p>{changes.added.length} added · {changes.updated.length} updated · {changes.removed.length} removed</p>
        {changes.updated.map(change => <p key={change.after.id}><del>{change.before.text}</del><br /><ins>{change.after.text}</ins></p>)}
        {changes.added.map(record => <p key={record.id}><ins>+ {record.text}</ins></p>)}
        {changes.removed.map(record => <p key={record.id}><del>− {record.text}</del></p>)}
        <p className="shop-small">A change is evidence to inspect, not an automatic correctness score. No change may mean extraction is still pending.</p>
      </div>}
    </details>
    <details open><summary>Context supplied to the model</summary>
      {turn ? <>
        <label className="shop-field">Inspect turn<select value={turnIndex} onChange={event => setTurnIndex(Number(event.target.value))}><option value={-1}>Latest reply</option>{turns.map((item, index) => <option key={index} value={index}>{index + 1}. {item.user.slice(0, 45)}</option>)}</select></label>
        <div className="evidence-counts"><span><b>{turn.inspector.context.session.events.length}</b>session events</span><span><b>{turn.inspector.context.memories.length}</b>recalled facts</span><span><b>{turn.inspector.context.products.length}</b>search results</span></div>
        <p className="shop-small">Mode: {turn.inspector.context.mode} · {(turn.inspector.total_ms / 1000).toFixed(1)}s total</p>
        {turn.inspector.context.guidance.map(item => <p className="guidance-source" key={item.entry_id ?? "built-in"}>{item.title}{item.version != null && ` · v${item.version}`}</p>)}
        <details><summary>Retrieval tool calls</summary>{turn.inspector.tool_calls?.length ? turn.inspector.tool_calls.map(call => <details key={call.call_id}><summary>{call.name} · {Math.round(call.elapsed_ms)}ms</summary><pre>{JSON.stringify({ arguments: call.arguments, result: call.output }, null, 2)}</pre></details>) : <p className="shop-small">No tool calls recorded for this reply.</p>}</details>
        <details><summary>Exact context JSON</summary><pre>{JSON.stringify(turn.inspector.context, null, 2)}</pre></details>
        <details><summary>Timing and saved events</summary><pre>{JSON.stringify({ memory_ms: turn.inspector.memory_ms, search_ms: turn.inspector.search_ms, model_ms: turn.inspector.model_ms, total_ms: turn.inspector.total_ms, event_ids: turn.inspector.event_ids }, null, 2)}</pre></details>
        <p className="shop-small">{turn.inspector.note}</p>
      </> : <p className="shop-empty">Send a message to inspect its context.</p>}
    </details>
    <details><summary>PII and reconciliation</summary><p>Use fictional details only. RAM’s configured exclusions apply to automatic extraction. Original session events and direct onboarding writes can still contain those details.</p><p>Capture before, send a correction, then refresh. Redis processes the events asynchronously. This app does not update long-term records to simulate reconciliation.</p><p className="shop-small">The two shopper identities are a local teaching control, not login or production authorization.</p></details>
    {session && <details><summary>Conversation identity</summary><code>{session.session_id}</code><p className="shop-small">Owner: {session.owner_id}</p></details>}
  </aside>;
}
