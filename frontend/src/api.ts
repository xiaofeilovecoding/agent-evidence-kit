import type { AnalysisOutcome, CatalogResponse, Card, ExportPayload, Lang, ModuleId } from "./types";

export type { AnalysisOutcome };

export interface DataAdapter {
  readonly kind: "api" | "showcase";
  catalog(module: ModuleId, lang: Lang): Promise<CatalogResponse>;
  runDemo(module: ModuleId, caseId: string, lang: Lang): Promise<AnalysisOutcome>;
  analyzeBytes(
    module: ModuleId,
    data: Uint8Array,
    format: "json" | "toml" | null,
    lang: Lang,
    signal?: AbortSignal,
  ): Promise<AnalysisOutcome>;
  rerender(resultId: string, lang: Lang): Promise<Card>;
  export(resultId: string, lang: Lang, format: "json" | "md"): Promise<ExportPayload>;
  exportCombined(
    items: { module: ModuleId; resultId: string }[],
    lang: Lang,
    format: "json" | "md",
  ): Promise<ExportPayload>;
  clear(module: ModuleId | "all"): Promise<void>;
}

export class RequestFailed extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(`request failed: ${status}`);
  }
}

async function readError(response: Response): Promise<never> {
  let code = "INTERNAL_ERROR";
  try {
    const body = (await response.json()) as { error?: { code?: string } };
    if (body.error?.code) code = body.error.code;
  } catch {
    /* sanitized body only */
  }
  throw new RequestFailed(response.status, code);
}

export function isSessionError(error: unknown): boolean {
  return (
    error instanceof RequestFailed &&
    (error.code === "SESSION_EXPIRED" ||
      error.code === "NO_SESSION" ||
      error.code === "CSRF")
  );
}

export function createApiAdapter(): DataAdapter {
  let csrf: string | null = null;
  let bootPromise: Promise<void> | null = null;

  async function bootstrap(): Promise<void> {
    const response = await fetch("/api/session", { credentials: "same-origin" });
    if (!response.ok) await readError(response);
    const body = (await response.json()) as { csrf_token: string };
    csrf = body.csrf_token;
  }

  // Deduplicated bootstrap: React StrictMode double-invocation and parallel
  // initializations must not create concurrent sessions.
  function ensureSession(): Promise<void> {
    if (csrf) return Promise.resolve();
    if (!bootPromise) {
      bootPromise = bootstrap().catch((error) => {
        bootPromise = null;
        throw error;
      });
    }
    return bootPromise;
  }

  function resetSession(): void {
    csrf = null;
    bootPromise = null;
  }

  /**
   * Run a request; on a one-time session/CSRF failure, re-bootstrap once
   * (bounded recovery: the server reuses the existing cookie session) and
   * retry a single time. Never loops.
   */
  async function withRecovery<T>(attempt: (retry: boolean) => Promise<T>): Promise<T> {
    try {
      return await attempt(false);
    } catch (error) {
      if (!isSessionError(error)) throw error;
      resetSession();
      return attempt(true);
    }
  }

  async function postJson<T>(path: string, payload: unknown): Promise<T> {
    return withRecovery(async (_retry) => {
      await ensureSession();
      const response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf ?? "",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) await readError(response);
      return (await response.json()) as T;
    });
  }

  return {
    kind: "api",
    async catalog(module, lang) {
      const response = await fetch(`/api/catalog?module=${module}&lang=${lang}`);
      if (!response.ok) await readError(response);
      return (await response.json()) as CatalogResponse;
    },
    async runDemo(module, caseId, lang) {
      return postJson(`/api/${module}/demo`, { case_id: caseId, lang });
    },
    async analyzeBytes(module, data, format, lang, signal) {
      return withRecovery(async (_retry) => {
        await ensureSession();
        const headers: Record<string, string> = {
          "Content-Type": "application/octet-stream",
          "X-CSRF-Token": csrf ?? "",
        };
        if (module === "config") headers["X-Input-Format"] = format ?? "json";
        const response = await fetch(`/api/${module}/analyze?lang=${lang}`, {
          method: "POST",
          credentials: "same-origin",
          signal,
          headers,
          body: data as unknown as BodyInit,
        });
        if (!response.ok) await readError(response);
        return (await response.json()) as AnalysisOutcome;
      });
    },
    async rerender(resultId, lang) {
      const response = await fetch(
        `/api/results/${encodeURIComponent(resultId)}?lang=${lang}`,
        { credentials: "same-origin" },
      );
      if (!response.ok) await readError(response);
      const body = (await response.json()) as { result: Card };
      return body.result;
    },
    async export(resultId, lang, format) {
      return postJson("/api/export", {
        result_id: resultId,
        lang,
        format,
      });
    },
    async exportCombined(items, lang, format) {
      return postJson("/api/export/combined", {
        items: items.map((item) => ({
          module: item.module,
          result_id: item.resultId,
        })),
        lang,
        format,
      });
    },
    async clear(module) {
      await postJson("/api/clear", { module });
    },
  };
}
