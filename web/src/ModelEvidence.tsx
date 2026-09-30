import type { Context, ModelRequest } from "./shop-api";

function readablePayload(value: unknown): string {
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2) ?? "No output supplied.";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isToolError(output: unknown): boolean {
  try {
    const value: unknown =
      typeof output === "string" ? JSON.parse(output) : output;
    return isRecord(value) && value.isError === true;
  } catch {
    return false;
  }
}

function hasTextFields(
  value: unknown,
  fields: string[],
): value is Record<string, unknown> {
  return (
    isRecord(value) && fields.every((field) => typeof value[field] === "string")
  );
}

function optionalText(value: unknown): boolean {
  return value == null || typeof value === "string";
}

function recordsMatch(
  value: unknown,
  valid: (item: unknown) => boolean,
): boolean {
  return Array.isArray(value) && value.every(valid);
}

function isProduct(value: unknown): boolean {
  return hasTextFields(value, ["product_id", "title", "description"]);
}

function parseContext(input: unknown): Context | null {
  if (typeof input !== "string") return null;
  try {
    const value: unknown = JSON.parse(input);
    // Old captures can be valid JSON without the current rendering fields.
    // Validate everything the readable view uses; retain raw evidence otherwise.
    if (!hasTextFields(value, ["mode", "message"]) || !isRecord(value.session))
      return null;
    const valid =
      optionalText(value.session.summary) &&
      recordsMatch(value.session.events, (event) =>
        hasTextFields(event, ["event_id", "role", "text"]),
      ) &&
      recordsMatch(
        value.memories,
        (memory) =>
          hasTextFields(memory, ["id", "text", "memory_type"]) &&
          optionalText(memory.owner_id),
      ) &&
      recordsMatch(value.guidance, (guidance) =>
        hasTextFields(guidance, ["title", "text"]),
      ) &&
      recordsMatch(value.products, isProduct) &&
      recordsMatch(value.previous_products, isProduct) &&
      recordsMatch(
        value.purchases ?? [],
        (order) =>
          hasTextFields(order, ["order_id", "shopper_id", "purchased_at"]) &&
          isProduct(order.product),
      ) &&
      optionalText(value.search_query);
    return valid ? ({ ...value, purchases: value.purchases ?? [] } as Context) : null;
  } catch {
    return null;
  }
}

export function ModelEvidence({ request }: { request?: ModelRequest | null }) {
  // Only the captured provider input is used; current toggles and memory are irrelevant.
  const messages = request && Array.isArray(request.input) ? request.input : [];
  const calls = messages.filter((item) => item.type === "function_call");
  const input =
    typeof request?.input === "string"
      ? request.input
      : messages.find((item) => item.role === "user")?.content;
  const context = parseContext(input);
  const catalogueCalls = calls.filter(
    (call) => call.name === "search_catalogue",
  ).length;
  const retrievalSource = context?.shopper_id
    ? "Context Retriever (MCP)"
    : "Recorded retrieval tool";
  return (
    <details className="model-evidence">
      <summary>What the model saw</summary>
      {!request ? (
        <p className="shop-muted">
          This reply was created before request capture was available. Send a
          new message to inspect its actual request.
        </p>
      ) : (
        <div className="model-evidence-body">
          <div className="shop-section-heading">
            <strong>Answer request</strong>
            <span className="tiny-pill">
              {context?.mode === "none"
                ? "Memory off"
                : context?.mode === "session"
                  ? "Session only"
                  : context?.mode === "both"
                    ? "Session + long-term"
                    : "Captured request"}
            </span>
          </div>
          <p className="shop-small">
            {request.model} · Captured for this reply.
            {request.tools?.length
              ? " Includes the initial context and any tool exchanges used to answer."
              : ""}
          </p>
          {context && (
            <section>
              <h4>Context sources</h4>
              <p className="shop-small">
                Conversation memory (Redis Agent Memory):{" "}
                {`${context.session.events.length} prior events, `}
                {`${context.memories.length} recalled memories`}
                {context.session.summary ? ", plus a session summary." : "."}
              </p>
              <p className="shop-small">
                {`${retrievalSource}: ${calls.length - catalogueCalls} calls · Catalogue search: ${catalogueCalls} calls.`}
              </p>
              {context.mode === "none" && (
                <p className="shop-small">
                  Memory off omits conversation history and recalled memories; live
                  lookups remain available.
                </p>
              )}
            </section>
          )}
          <details className="request-instructions">
            <summary>Instructions</summary>
            <pre>{request.instructions}</pre>
          </details>
          {!!request.tools?.length && (
            <details>
              <summary>Available tools · {request.tools.length}</summary>
              <p className="shop-small">
                The names, descriptions and input schemas supplied for this reply.
                Current replies include discovered Context Retriever tools and
                search_catalogue for the full local catalogue. Available tools
                are definitions, not completed lookups.
              </p>
              {request.tools.map((tool, index) => (
                <details key={index}>
                  <summary>{String(tool.name ?? "Unnamed tool")}</summary>
                  <p>{String(tool.description ?? "")}</p>
                  <h4>Input schema</h4>
                  <pre>{readablePayload(tool.parameters)}</pre>
                </details>
              ))}
            </details>
          )}
          {!context && (
            <p className="request-absent">
              Readable context is unavailable for this capture. Inspect the raw
              request below.
            </p>
          )}
          {context && (
            <>
              <section>
                <h4>Earlier conversation</h4>
                {context.session.summary && (
                  <div className="request-fact">
                    <span className="eyebrow">Session summary</span>
                    <p>{context.session.summary}</p>
                  </div>
                )}
                {context.session.events.length ? (
                  context.session.events.map((event) => (
                    <div className="request-fact" key={event.event_id}>
                      <span className="eyebrow">{event.role}</span>
                      <p>{event.text}</p>
                    </div>
                  ))
                ) : (
                  <p className="request-absent">No previous turns supplied.</p>
                )}
              </section>
              <section>
                <h4>Retrieved memories</h4>
                {context.memories.length ? (
                  context.memories.map((memory) => (
                    <div className="request-fact" key={memory.id}>
                      <p>{memory.text}</p>
                      <span className="shop-small">
                        {memory.memory_type} · Owner:{" "}
                        {memory.owner_id ?? "unspecified"}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="request-absent">
                    No long-term memories supplied.
                  </p>
                )}
              </section>
              <section>
                <h4>Current message</h4>
                <p className="request-message">{context.message}</p>
              </section>
              <details>
                <summary>Other supplied context</summary>
                <p className="shop-small">
                  Memory off removes conversation and recalled memories. Adviser
                  guidance and requested catalogue or order data can still be
                  supplied.
                </p>
                <h4>Adviser guidance</h4>
                {context.guidance.length ? (
                  context.guidance.map((item, index) => (
                    <details key={index}>
                      <summary>
                        {item.title}
                        {item.version != null ? ` · v${item.version}` : ""}
                      </summary>
                      <pre>{item.text}</pre>
                    </details>
                  ))
                ) : (
                  <p className="request-absent">None supplied.</p>
                )}
                <h4>Initial catalogue context</h4>
                <p>
                  {context.search_query ??
                    (request.tools?.length
                      ? "Further retrieval is shown under Tool calls."
                      : "No search requested.")}
                </p>
                {[...context.products, ...context.previous_products].map(
                  (product, index) => (
                    <details key={index}>
                      <summary>{product.title}</summary>
                      <p>{product.description}</p>
                      <code>{product.product_id}</code>
                    </details>
                  ),
                )}
                <h4>Initial fictional purchase records</h4>
                {context.purchases.length ? (
                  context.purchases.map((order) => (
                    <div className="request-fact" key={order.order_id}>
                      <p>
                        {order.product.title} · {order.purchased_at}
                      </p>
                      <p className="shop-small">
                        Shopper: {order.shopper_id} · {order.order_id}
                      </p>
                      <p>{order.product.description}</p>
                    </div>
                  ))
                ) : (
                  <p className="request-absent">
                    None supplied. Later lookups appear under Tool calls.
                  </p>
                )}
              </details>
            </>
          )}
          {!!request.tools?.length && (
            <section>
              <h4>Tool calls</h4>
              {calls.length ? (
                calls.map((call, index) => {
                  const result = messages.find(
                    (item) =>
                      item.type === "function_call_output" &&
                      item.call_id === call.call_id,
                  );
                  return (
                    <details key={String(call.call_id ?? index)}>
                      <summary>
                        {index + 1}. {String(call.name)}
                      </summary>
                      <p className="shop-small">
                        {call.name === "search_catalogue"
                          ? "Catalogue search"
                          : retrievalSource}
                      </p>
                      {isToolError(result?.output) && (
                        <p className="shop-error">
                          Query failed — no records retrieved by this call.
                        </p>
                      )}
                      <h4>Arguments</h4>
                      <pre>{readablePayload(call.arguments)}</pre>
                      <h4>Result supplied to the model</h4>
                      <pre>{readablePayload(result?.output)}</pre>
                    </details>
                  );
                })
              ) : (
                <p className="request-absent">
                  No tools called for this reply.
                </p>
              )}
            </section>
          )}
          <details>
            <summary>Raw answer request (JSON)</summary>
            <pre>{JSON.stringify(request, null, 2)}</pre>
          </details>
          <p className="shop-small">
            These are the supplied instructions and input—not the model’s
            internal reasoning. Saved with this conversation; not written to
            console logs.
          </p>
        </div>
      )}
    </details>
  );
}
