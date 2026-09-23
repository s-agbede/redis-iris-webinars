import type { Context, ModelRequest } from "./shop-api";

function readablePayload(value: unknown): string {
  if (typeof value === "string") {
    try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; }
  }
  return JSON.stringify(value, null, 2) ?? "No output supplied.";
}

export function ModelEvidence({ request }: { request?: ModelRequest | null }) {
  // Only the captured provider input is used; current toggles and memory are irrelevant.
  let context: Context | null = null;
  const messages = request && Array.isArray(request.input) ? request.input : [];
  const calls = messages.filter(item => item.type === "function_call");
  if (request) {
    const input = typeof request.input === "string" ? request.input : messages.find(item => item.role === "user")?.content;
    if (typeof input === "string") {
      try { context = JSON.parse(input) as Context; } catch { /* Raw capture stays available. */ }
    }
  }
  return <details className="model-evidence">
    <summary>What the model saw</summary>
    {!request ? <p className="shop-muted">This reply was created before request capture was available. Send a new message to inspect its actual request.</p> : <div className="model-evidence-body">
      <div className="shop-section-heading"><strong>Answer request</strong><span className="tiny-pill">{context?.mode === "none" ? "Memory off" : context?.mode === "session" ? "Session only" : context?.mode === "both" ? "Session + long-term" : "Captured request"}</span></div>
      <p className="shop-small">{request.model} · Captured for this reply.{request.tools?.length ? " Includes the initial context and any tool exchanges used to answer." : ""}</p>
      <details className="request-instructions"><summary>Instructions</summary><pre>{request.instructions}</pre></details>
      {context && <>
        <section><h4>Earlier conversation</h4>
          {context.session.summary && <div className="request-fact"><span className="eyebrow">Session summary</span><p>{context.session.summary}</p></div>}
          {context.session.events.length ? context.session.events.map(event => <div className="request-fact" key={event.event_id}><span className="eyebrow">{event.role}</span><p>{event.text}</p></div>) : <p className="request-absent">No previous turns supplied.</p>}
        </section>
        <section><h4>Retrieved memories</h4>{context.memories.length ? context.memories.map(memory => <div className="request-fact" key={memory.id}><p>{memory.text}</p><span className="shop-small">{memory.memory_type} · Owner: {memory.owner_id ?? "unspecified"}</span></div>) : <p className="request-absent">No long-term memories supplied.</p>}</section>
        <section><h4>Current message</h4><p className="request-message">{context.message}</p></section>
        <details><summary>Other supplied context</summary>
          <p className="shop-small">Memory off removes conversation and recalled facts. Adviser guidance and requested catalogue or order data can still be supplied.</p>
          <h4>Adviser guidance</h4>{context.guidance.length ? context.guidance.map((item, index) => <details key={index}><summary>{item.title}{item.version != null ? ` · v${item.version}` : ""}</summary><pre>{item.text}</pre></details>) : <p className="request-absent">None supplied.</p>}
          <h4>Initial catalogue context</h4><p>{context.search_query ?? (request.tools?.length ? "Further retrieval is shown under Tool calls." : "No search requested.")}</p>
          {[...context.products, ...context.previous_products].map((product, index) => <details key={index}><summary>{product.title}</summary><p>{product.description}</p><code>{product.product_id}</code></details>)}
          <h4>Fictional purchase records</h4>{context.purchases.length ? context.purchases.map(order => <div className="request-fact" key={order.order_id}><p>{order.product.title} · {order.purchased_at}</p><p className="shop-small">Shopper: {order.shopper_id} · {order.order_id}</p><p>{order.product.description}</p></div>) : <p className="request-absent">None supplied.</p>}
        </details>
      </>}
      {!!request.tools?.length && <section><h4>Tool calls</h4>
        {calls.length ? calls.map((call, index) => {
          const result = messages.find(item => item.type === "function_call_output" && item.call_id === call.call_id);
          return <details key={String(call.call_id ?? index)}><summary>{index + 1}. {String(call.name)}</summary>
            <h4>Arguments</h4><pre>{readablePayload(call.arguments)}</pre>
            <h4>Result supplied to the model</h4><pre>{readablePayload(result?.output)}</pre>
          </details>;
        }) : <p className="request-absent">No tools called for this reply.</p>}
      </section>}
      <details><summary>Raw answer request (JSON)</summary><pre>{JSON.stringify(request, null, 2)}</pre></details>
      <p className="shop-small">These are the supplied instructions and input—not the model’s internal reasoning. Saved with this conversation; not written to console logs.</p>
    </div>}
  </details>;
}
