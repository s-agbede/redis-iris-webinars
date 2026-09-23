import assert from "node:assert/strict";
import test from "node:test";
import { compareMemories, shouldForgetSession } from "./shop-evidence.ts";
import { APIError } from "./api.ts";

test("only confirmed missing or mismatched sessions discard the saved ID", () => {
  assert.equal(shouldForgetSession(new APIError(400, "Conversation not found. Start a new conversation.")), true);
  assert.equal(shouldForgetSession(new APIError(400, "This conversation does not belong to this shopper.")), true);
  assert.equal(shouldForgetSession(new APIError(503, "Redis is unavailable.")), false);
  assert.equal(shouldForgetSession(new Error("Network timeout")), false);
});

test("snapshot comparison distinguishes updates from additions and removals", () => {
  const record = (id, text) => ({ id, text, memory_type: "semantic", owner_id: "alex" });
  const changes = compareMemories([record("camera", "Sony"), record("old", "old")], [record("camera", "Canon"), record("new", "new")]);
  assert.equal(changes.updated[0].before.text, "Sony");
  assert.equal(changes.updated[0].after.text, "Canon");
  assert.deepEqual(changes.added.map(r => r.id), ["new"]);
  assert.deepEqual(changes.removed.map(r => r.id), ["old"]);
});

test("unchanged records and timestamp changes do not imply reconciliation", () => {
  const record = { id: "camera", text: "Sony", memory_type: "semantic" };
  assert.deepEqual(compareMemories([record], [{ ...record, updated_at: "later" }]), { added: [], removed: [], updated: [] });
});
