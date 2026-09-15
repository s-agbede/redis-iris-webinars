export type Mode = "text" | "vector" | "hybrid";
export type SourceLabel = "E" | "S" | "C" | "I";
export type Passage = {
  passage_id: string;
  field: string;
  text: string;
  start: number;
  end: number;
};
export type ProductPhoto = {
  url: string;
  alt: string;
  caption: string;
  source_url: string;
  author: string;
  license: string;
  license_url: string;
};
export type FusionEvidence = {
  constant: number;
  window: number;
  text_rank: number | null;
  vector_rank: number | null;
  text_contribution: number | null;
  vector_contribution: number | null;
  reconstructed_score: number | null;
  status: "verified" | "unavailable";
  note: string;
};
export type Hit = {
  product_id: string;
  title: string;
  brand: string | null;
  color: string | null;
  score: number;
  source_label: SourceLabel | null;
  passage: Passage;
  photo: ProductPhoto | null;
  indexed_text: string;
  /** Literal query-word overlap, not engine-reported matches. Offsets count Unicode code points. */
  lexical_matches: { start: number; end: number }[];
  passage_rank: number;
  fusion: FusionEvidence | null;
};
export type ModeResult = {
  mode: Mode;
  query_ms: number;
  score_kind: string;
  redis_query: string;
  error: string | null;
  hits: Hit[];
};
export type Comparison = {
  query: string;
  brands: string[];
  embedding_ms: number;
  explanation_ms: number;
  total_ms: number;
  embedding_model: string;
  source_revision: string;
  candidate_limit: number;
  results: ModeResult[];
};
export type Catalog = {
  name: string;
  product_count: number;
  passage_count: number;
  source_revision: string;
  embedding_model: string;
  embedding_revision: string;
  vector_dimensions: number;
  index_algorithm: string;
  brands: { value: string; count: number }[];
  examples: {
    query: string;
    title: string;
    kind: "exact" | "intent" | "constraint";
    origin: "esci" | "authored";
  }[];
};
export type ProductDetail = {
  product_id: string;
  product_title: string;
  product_description: string | null;
  product_bullet_point: string | null;
  product_brand: string | null;
  product_color: string | null;
  product_locale: "us";
  source_revision: string;
  passages: Passage[];
  photo: ProductPhoto | null;
};

export function createRequestGate() {
  let current: AbortController | null = null;
  return {
    begin() {
      current?.abort();
      const controller = new AbortController();
      current = controller;
      return {
        signal: controller.signal,
        isCurrent: () => current === controller && !controller.signal.aborted,
      };
    },
    cancel() {
      current?.abort();
      current = null;
    },
  };
}

export async function requestJSON<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(90_000);
  const response = await fetch(`/api${path}`, {
    ...init,
    signal: init.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
  });
  if (!response.ok) {
    const fallback = `Request failed (${response.status}). Check that the backend and Redis are running, then retry.`;
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : fallback);
  }
  return response.json() as Promise<T>;
}

export function errorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return "The request timed out. Check the backend while the local model or camera index starts, then retry.";
  }
  if (error instanceof TypeError) {
    return "Could not connect to the API. Start the backend and Redis, then retry.";
  }
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred. Please retry.";
}
