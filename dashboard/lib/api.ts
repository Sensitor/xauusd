/**
 * Typed fetch client for the GoldMind FastAPI backend.
 *
 * Resilience contract: every endpoint has a mock fallback. If a request fails
 * (network error, non-2xx, or timeout) the client returns the bundled mock
 * payload and marks the result `source: "mock"` so the UI can surface an
 * "offline (mock)" indicator instead of erroring out.
 */
import * as mock from "./mock";
import type {
  ConfigResponse,
  DecisionDetail,
  DecisionSummary,
  EvaluateRequest,
  EvaluationResult,
  HealthResponse,
  MarketRegime,
  NewsItem,
  PerformanceReport,
  AgentOutput,
  Trade,
  TradeStatus,
} from "./types";

export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const DEFAULT_TIMEOUT_MS = 6000;

export type DataSource = "api" | "mock";

/** Wrapper so callers always know whether data is live or mocked. */
export interface ApiResult<T> {
  data: T;
  source: DataSource;
  /** Present when a fallback occurred, for optional debugging/tooltips. */
  error?: string;
}

function ok<T>(data: T): ApiResult<T> {
  return { data, source: "api" };
}

function fallback<T>(data: T, error: unknown): ApiResult<T> {
  return {
    data,
    source: "mock",
    error: error instanceof Error ? error.message : String(error),
  };
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  timeoutMs?: number;
  /** Query params (undefined/empty values are dropped). */
  query?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const base = API_BASE.replace(/\/$/, "");
  const url = new URL(`${base}${path}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

/** Low-level JSON fetch with an AbortController timeout. Throws on failure. */
async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, timeoutMs = DEFAULT_TIMEOUT_MS, query } = opts;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(buildUrl(path, query), {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      // Always hit the network; freshness matters more than caching here.
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} for ${path}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** Run a request, falling back to the provided mock payload on any error. */
async function withFallback<T>(
  run: () => Promise<T>,
  mockData: T,
): Promise<ApiResult<T>> {
  try {
    return ok(await run());
  } catch (err) {
    return fallback(mockData, err);
  }
}

// ---------------------------------------------------------------------------
// Endpoint methods
// ---------------------------------------------------------------------------
export const api = {
  health(): Promise<ApiResult<HealthResponse>> {
    return withFallback(() => request<HealthResponse>("/health"), mock.mockHealth);
  },

  config(): Promise<ApiResult<ConfigResponse>> {
    return withFallback(() => request<ConfigResponse>("/config"), mock.mockConfig);
  },

  evaluate(req: EvaluateRequest = {}): Promise<ApiResult<EvaluationResult>> {
    return withFallback(
      () => request<EvaluationResult>("/evaluate", { method: "POST", body: req }),
      mock.mockEvaluation,
    );
  },

  decisions(limit = 50): Promise<ApiResult<DecisionSummary[]>> {
    return withFallback(
      () => request<DecisionSummary[]>("/decisions", { query: { limit } }),
      mock.mockDecisions,
    );
  },

  decision(id: string): Promise<ApiResult<DecisionDetail>> {
    return withFallback(
      () => request<DecisionDetail>(`/decisions/${encodeURIComponent(id)}`),
      mock.mockDecisionDetail,
    );
  },

  trades(status?: TradeStatus): Promise<ApiResult<Trade[]>> {
    return withFallback(
      () => request<Trade[]>("/trades", { query: { status } }),
      status ? mock.mockTrades.filter((t) => t.status === status) : mock.mockTrades,
    );
  },

  activeTrades(): Promise<ApiResult<Trade[]>> {
    return withFallback(
      () => request<Trade[]>("/trades/active"),
      mock.mockTrades.filter((t) => t.status === "open"),
    );
  },

  performance(): Promise<ApiResult<PerformanceReport>> {
    return withFallback(
      () => request<PerformanceReport>("/performance"),
      mock.mockPerformance,
    );
  },

  agents(): Promise<ApiResult<AgentOutput[]>> {
    return withFallback(() => request<AgentOutput[]>("/agents"), mock.mockAgents);
  },

  regime(): Promise<ApiResult<MarketRegime>> {
    return withFallback(() => request<MarketRegime>("/regime"), mock.mockRegime);
  },

  news(): Promise<ApiResult<NewsItem[]>> {
    return withFallback(() => request<NewsItem[]>("/news"), mock.mockNews);
  },
};

export type Api = typeof api;
