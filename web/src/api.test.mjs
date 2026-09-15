import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequestGate, requestJSON } from "./api.ts";

test("a newer comparison aborts and invalidates the previous request", () => {
  const gate = createRequestGate();
  const first = gate.begin();
  const second = gate.begin();
  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.signal.aborted, false);
  assert.equal(second.isCurrent(), true);
});

test("editing a query or closing an inspector invalidates pending work", () => {
  const gate = createRequestGate();
  const request = gate.begin();
  gate.cancel();
  assert.equal(request.signal.aborted, true);
  assert.equal(request.isCurrent(), false);
  const next = gate.begin();
  assert.equal(next.isCurrent(), true);
});

test("API errors retain the service's actionable message", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(
        JSON.stringify({
          detail: "Camera index is unavailable. Run the camera seed command.",
        }),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        },
      ),
  );
  await assert.rejects(
    requestJSON("/catalog"),
    /Camera index is unavailable\. Run the camera seed command\./,
  );
});

test("a non-JSON service error gives an actionable status instead of a parser error", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    async () => new Response("Bad gateway", { status: 502 }),
  );
  await assert.rejects(requestJSON("/catalog"), /502.*backend/i);
});

test("an explicit cancellation signal reaches the fetch boundary", async (context) => {
  const controller = new AbortController();
  let receivedSignal;
  context.mock.method(globalThis, "fetch", async (_path, init) => {
    receivedSignal = init.signal;
    return Response.json({ ready: true });
  });
  assert.deepEqual(
    await requestJSON("/catalog", { signal: controller.signal }),
    { ready: true },
  );
  controller.abort();
  assert.equal(receivedSignal.aborted, true);
});
