import type { Memory } from "./shop-api.ts";
import { APIError, errorMessage } from "./api.ts";

export function chatFailureMessage(error: unknown): string {
  const recovery = error instanceof APIError && error.retrySafe
    ? "No conversation events were saved. Your message is ready to retry."
    : "A failed request may have saved session events; inspect before resending.";
  return `${errorMessage(error)} ${recovery}`;
}

export function shouldForgetSession(error: unknown): boolean {
  return error instanceof APIError && error.status === 400 && (
    error.message === "Conversation not found. Start a new conversation." ||
    error.message === "This conversation does not belong to this shopper."
  );
}
export function compareMemories(before: Memory[], after: Memory[]) {
  const old = new Map(before.map(record => [record.id, record]));
  const current = new Map(after.map(record => [record.id, record]));
  return {
    added: after.filter(record => !old.has(record.id)),
    removed: before.filter(record => !current.has(record.id)),
    updated: after.flatMap(record => {
      const prior = old.get(record.id);
      return prior && (prior.text !== record.text || prior.memory_type !== record.memory_type) ? [{ before: prior, after: record }] : [];
    }),
  };
}
