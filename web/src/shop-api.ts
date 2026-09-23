import { requestJSON, type ProductPhoto } from "./api";
export type Shopper = "alex" | "jordan";
export type MemoryMode = "none" | "session" | "both";
export type Memory = { id: string; text: string; memory_type: string; owner_id?: string | null; created_at?: string | null; updated_at?: string | null };
export type Product = { product_id: string; title: string; brand: string | null; description: string; url: string; photo: ProductPhoto | null };
export type Guidance = { source: "built-in" | "playbook"; title: string; text: string; entry_id: string | null; version: number | null };
export type Context = {
  message: string; mode: MemoryMode;
  session: { events: { event_id: string; role: string; text: string }[]; summary: string | null };
  memories: Memory[]; previous_products: Product[]; products: Product[];
  purchases: { order_id: string; shopper_id: Shopper; purchased_at: string; fictional: boolean; product: Product }[];
  guidance: Guidance[]; search_query: string | null;
};
export type ModelRequest = { model: string; instructions: string; input: string | Record<string, unknown>[]; store: boolean; reasoning: Record<string, string>; max_output_tokens: number; text: Record<string, unknown>; tools?: Record<string, unknown>[]; tool_choice?: string; parallel_tool_calls?: boolean; include?: string[] };
export type ToolExecution = { call_id: string; name: "search_catalogue" | "get_purchase_history"; arguments: Record<string, unknown>; output: Record<string, unknown>; elapsed_ms: number };
export type Turn = { user: string; assistant: string; products: Product[]; inspector: { answer_request?: ModelRequest | null; tool_calls?: ToolExecution[]; context: Context; memory_ms: number; search_ms: number; model_ms: number; total_ms: number; event_ids: string[]; note: string } };
export type Session = { session_id: string; shopper_id: Shopper; owner_id: string; turns: Turn[] };
export type ShopStatus = { configured: boolean; missing: string[]; catalogue_ready: boolean; model: string; playbook_configured: boolean };
export type MemoryList = { memories: Memory[]; complete: boolean };
export function shopPost<T>(path: string, body: object): Promise<T> {
  return requestJSON<T>(`/shop/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
