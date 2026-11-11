import { useCallback, useEffect, useRef, useState } from "react";
import type { Lang } from "./i18n";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import { RequestFailed, isSessionError } from "./api";
import type { StreamCompareCard } from "./types";
import ShareBlock from "./ShareBlock";

/** Synthetic compare samples (never real user material). The two sides have
 * the same profile; one terminates normally, one carries an upstream error. */
const SAMPLE_BASELINE = [
  'data: {"choices": [{"index": 0, "delta": {"content": "hello"}}]}',
  "",
  'data: {"choices": [{"index": 0, "delta": {"content": " world"}}]}',
  "",
  'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}',
  "",
  "data: [DONE]",
  "",
  "",
].join("\n");

const SAMPLE_CANDIDATE = [
  'data: {"choices": [{"index": 0, "delta": {"content": "partial"}}]}',
  "",
  'data: {"error": {"message": "synthetic upstream failure", "type": "server_error"}}',
  "",
  "",
].join("\n");

const MAX_STREAM_BYTES = 8 * 1024 * 1024;

type Status = "empty" | "loading" | "ready" | "error";

interface Props {
  lang: Lang;
  /** R02: a pending/unconfirmed clear gates the compare flow too. */
  gated: boolean;
}

const FIELD_LABEL_KEYS: Record<string, string> = {
  terminal: "compareTerminal",
  verdict: "compareVerdict",
  finish_reason: "compareFinishReason",
  done_seen: "compareDoneSeen",
  terminal_event_index: "compareTerminalIndex",
  diagnostic_codes: "compareDiagCodes",
  event_count: "compareEventCount",
};

function formatValue(field: string, value: unknown, lang: Lang): string {
  if (field === "done_seen") {
    return lang === "zh-CN" ? (value ? "有" : "无") : value ? "yes" : "none";
  }
  if (field === "terminal_event_index") {
    if (value === null || value === undefined) {
      return lang === "zh-CN" ? "未观察到" : "not observed";
    }
    return `@event${value}`;
  }
  if (field === "diagnostic_codes") {
    const side = value as { code: string }[] | null | undefined;
    const codes = (side ?? []).map((d) => d.code);
    return codes.length ? codes.join(", ") : lang === "zh-CN" ? "—" : "none";
  }
  if (value === null || value === undefined) {
    return lang === "zh-CN" ? "—" : "none";
  }
  return String(value);
}

type Side = "baseline" | "candidate";

export default function StreamCompare({ lang, gated }: Props) {
  const [baselineText, setBaselineText] = useState("");
  const [candidateText, setCandidateText] = useState("");
  const [status, setStatus] = useState<Status>("empty");
  const [message, setMessage] = useState<string | null>(null);
  const [card, setCard] = useState<StreamCompareCard | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [inputRevision, setInputRevision] = useState(0);
  const compareRevRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  // E03: compare identity is server-issued per run. The CURRENT run id lives
  // here; starting a new run (prepare) immediately revokes everything the
  // previous run landed, and edits cancel the current run server-side.
  const runIdRef = useRef<string | null>(null);
  // at most one server cancel is in flight; the next prepare awaits it
  const pendingCancelRef = useRef<Promise<void> | null>(null);
  // a ready comparison exists — the next edit cancels its run exactly once
  const readyRef = useRef(false);
  // E02: per-side file reads carry side + generation tickets.
  const fileTicketRef = useRef<Record<Side, number>>({ baseline: 0, candidate: 0 });
  const fileInputRef = useRef<Record<Side, HTMLInputElement | null>>({
    baseline: null,
    candidate: null,
  });

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  /** Server-side cancel of the CURRENT run: drops what it landed and marks
   * it dead so in-flight results can never land, even if this response is
   * lost. Cancelling an older run never touches a newer comparison. */
  const fireServerCancel = useCallback(() => {
    const runId = runIdRef.current;
    if (!runId) return;
    const pending = adapter
      .cancelCompare(runId)
      .catch(() => {
        // Transfer failed: say so precisely — the old share stays disabled
        // locally and the next prepare revokes everything compare-mode has.
        if (mountedRef.current) {
          setStatus((prev) => (prev === "loading" ? "empty" : prev));
          setMessage(
            lang === "zh-CN"
              ? "取消请求未确认：旧分享保持禁用；重新比较将立即撤销旧比较。"
              : "Cancel was not confirmed: the previous share stays disabled; the next compare revokes the old one immediately.",
          );
        }
      });
    pendingCancelRef.current = pending;
  }, [lang]);

  /** Any edit/new run revokes the previous comparison immediately: the UI
   * drops it and exits loading (the run button is usable again), and the
   * server cancel fires once per ready/edit→next-transition. */
  const revoke = useCallback(
    (fireServer: boolean) => {
      compareRevRef.current += 1;
      if (abortRef.current) abortRef.current.abort();
      const wasReady = readyRef.current;
      readyRef.current = false;
      setCard(null);
      setCompareId(null);
      setInputRevision((r) => r + 1);
      // E01: an in-flight compare must leave loading — the stale response is
      // dropped by the run-identity check and the button is usable again.
      setStatus((prev) => (prev === "loading" ? "empty" : prev));
      setMessage(null);
      if (fireServer && !isShowcase && (wasReady || runIdRef.current)) {
        // E03: cancel the current run server-side — it revokes landed and
        // in-flight results of that run; the next prepare revokes the rest.
        fireServerCancel();
        runIdRef.current = null;
      }
    },
    [fireServerCancel],
  );

  const onEdit = useCallback(
    (side: Side, value: string) => {
      revoke(readyRef.current);
      if (side === "baseline") setBaselineText(value);
      else setCandidateText(value);
    },
    [revoke],
  );

  const loadSample = useCallback(
    (side: Side) => {
      revoke(readyRef.current);
      if (side === "baseline") setBaselineText(SAMPLE_BASELINE);
      else setCandidateText(SAMPLE_CANDIDATE);
    },
    [revoke],
  );

  const clearSide = useCallback(
    (side: Side) => {
      revoke(readyRef.current);
      fileTicketRef.current[side] += 1;
      if (fileInputRef.current[side]) fileInputRef.current[side]!.value = "";
      if (side === "baseline") setBaselineText("");
      else setCandidateText("");
    },
    [revoke],
  );

  const clearBoth = useCallback(() => {
    revoke(readyRef.current);
    fileTicketRef.current.baseline += 1;
    fileTicketRef.current.candidate += 1;
    if (fileInputRef.current.baseline) fileInputRef.current.baseline.value = "";
    if (fileInputRef.current.candidate) fileInputRef.current.candidate.value = "";
    setBaselineText("");
    setCandidateText("");
  }, [revoke]);

  const onFiles = useCallback(
    (side: Side, files: FileList | null) => {
      const file = files?.[0] ?? null;
      // a new selection starts a new input identity for THIS side
      fileTicketRef.current[side] += 1;
      revoke(readyRef.current);
      if (!file) return;
      const lower = file.name.toLowerCase();
      if (!lower.endsWith(".sse") && !lower.endsWith(".txt")) {
        setMessage(t("formatLabel", lang) + ": .sse / .txt");
        return;
      }
      if (file.size > MAX_STREAM_BYTES) {
        setMessage(t("tooLargeStream", lang));
        return;
      }
      const ticket = ++fileTicketRef.current[side];
      const rev = compareRevRef.current;
      const reader = new FileReader();
      reader.onload = () => {
        if (!mountedRef.current) return;
        if (ticket !== fileTicketRef.current[side]) return;
        if (rev !== compareRevRef.current) return;
        const bytes = new Uint8Array(reader.result as ArrayBuffer);
        const text = new TextDecoder().decode(bytes);
        if (side === "baseline") setBaselineText(text);
        else setCandidateText(text);
      };
      reader.onerror = () => {
        if (!mountedRef.current) return;
        if (ticket !== fileTicketRef.current[side]) return;
        if (rev !== compareRevRef.current) return;
        setMessage(t("formatLabel", lang) + ": .sse / .txt");
      };
      reader.readAsArrayBuffer(file);
    },
    [lang, revoke],
  );

  // Late language responses obey the current comparison and language.
  useEffect(() => {
    if (!compareId) return;
    if (card && card.language === lang) return;
    const rid = compareId;
    const rev = compareRevRef.current;
    let cancelled = false;
    adapter
      .rerender(rid, lang)
      .then((result) => {
        if (cancelled || !mountedRef.current) return;
        if (rev !== compareRevRef.current) return;
        setCard(result as unknown as StreamCompareCard);
      })
      .catch(() => {
        if (cancelled || !mountedRef.current) return;
        if (rev !== compareRevRef.current) return;
        setCard(null);
        setCompareId(null);
        readyRef.current = false;
        setMessage(
          lang === "zh-CN" ? "结果已失效，请重新比较。" : "The result expired; run the comparison again.",
        );
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, compareId]);

  const runCompare = useCallback(async () => {
    if (gated || isShowcase) return;
    if (!baselineText.trim() || !candidateText.trim()) {
      setMessage(t("compareNeedsBoth", lang));
      return;
    }
    const baseBytes = new TextEncoder().encode(baselineText);
    const candBytes = new TextEncoder().encode(candidateText);
    if (baseBytes.length > MAX_STREAM_BYTES || candBytes.length > MAX_STREAM_BYTES) {
      setMessage(t("tooLargeStream", lang));
      return;
    }
    // E03 ordering: an in-flight server cancel settles before the prepare so
    // revocation and creation stay ordered; the prepare itself revokes
    // everything the previous run landed, immediately.
    if (pendingCancelRef.current) {
      const pending = pendingCancelRef.current;
      pendingCancelRef.current = null;
      try {
        await pending;
      } catch {
        /* handled by the cancel error path; the run proceeds fail-closed */
      }
    }
    compareRevRef.current += 1;
    const rev = compareRevRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    readyRef.current = false;
    setStatus("loading");
    setMessage(null);
    setCard(null);
    setCompareId(null);
    try {
      // E03: the server issues this run's identity; the prepare already
      // revoked everything the previous run landed.
      const prepared = await adapter.prepareCompare();
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      const runId = prepared.run_id;
      runIdRef.current = runId;
      const baselineOutcome = await adapter.analyzeBytes(
        "stream", baseBytes, null, lang, controller.signal, "baseline", runId,
      );
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      const candidateOutcome = await adapter.analyzeBytes(
        "stream", candBytes, null, lang, controller.signal, "candidate", runId,
      );
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      const outcome = await adapter.compareStream(
        baselineOutcome.result_id, candidateOutcome.result_id, lang, runId, controller.signal,
      );
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      setCard(outcome.result as unknown as StreamCompareCard);
      setCompareId(outcome.result_id);
      setInputRevision((r) => r + 1);
      readyRef.current = true;
      setStatus("ready");
    } catch (error) {
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      // E01: a superseded/aborted run must leave loading — the button stays
      // usable and a fresh comparison can start immediately.
      if ((error as Error).name === "AbortError") {
        setStatus((prev) => (prev === "loading" ? "empty" : prev));
        return;
      }
      readyRef.current = false;
      runIdRef.current = null;
      if (isSessionError(error)) {
        setMessage(t("sessionExpired", lang));
      } else if (error instanceof RequestFailed && (error.code === "NO_RESULT" || error.code === "STALE_ANALYSIS")) {
        setMessage(
          lang === "zh-CN"
            ? "一侧结果已被撤销，请重新比较。"
            : "One side was revoked; run the comparison again.",
        );
      } else {
        setMessage(t("networkError", lang));
      }
      setStatus("error");
    }
  }, [baselineText, candidateText, gated, lang]);

  const cardDiffs = card?.differences ?? [];
  const sameFields = (card?.same_fields ?? []).filter(
    (f) => FIELD_LABEL_KEYS[f] !== undefined,
  );

  const sideEditor = (side: Side) => {
    const value = side === "baseline" ? baselineText : candidateText;
    const label = side === "baseline" ? t("compareBaselineLabel", lang) : t("compareCandidateLabel", lang);
    const sampleLabel =
      side === "baseline" ? t("compareLoadNormalSample", lang) : t("compareLoadErrorSample", lang);
    const testSuffix = side === "baseline" ? "baseline" : "candidate";
    return (
      <div className="compare-side">
        <label>{label}</label>
        <textarea
          aria-label={label}
          value={value}
          onChange={(e) => onEdit(side, e.target.value)}
          rows={8}
          spellCheck={false}
          data-testid={`compare-${testSuffix}-input`}
        />
        <div className="compare-side-actions">
          <button
            className="ghost small"
            type="button"
            disabled={gated}
            onClick={() => fileInputRef.current[side]?.click()}
            data-testid={`compare-file-${testSuffix}`}
          >
            {t("file", lang)}
          </button>
          <input
            ref={(el) => {
              fileInputRef.current[side] = el;
            }}
            type="file"
            accept=".sse,.txt"
            hidden
            onChange={(e) => onFiles(side, e.target.files)}
          />
          <button
            className="ghost small"
            type="button"
            disabled={gated}
            onClick={() => loadSample(side)}
            data-testid={`compare-sample-${testSuffix}`}
          >
            {sampleLabel}
          </button>
          <button
            className="ghost small"
            type="button"
            disabled={gated || !value}
            onClick={() => clearSide(side)}
            data-testid={`compare-clear-${testSuffix}`}
          >
            {t("clearSide", lang)}
          </button>
        </div>
      </div>
    );
  };

  return (
    <details className="compare-details" data-testid="stream-compare">
      <summary>{t("compareSectionTitle", lang)}</summary>
      <p className="hint">{t("compareSectionHint", lang)}</p>
      {isShowcase && (
        <p className="hint" role="note" data-testid="compare-showcase-note">
          {t("compareShowcaseNote", lang)}
        </p>
      )}
      <div className="compare-grid">
        {sideEditor("baseline")}
        {sideEditor("candidate")}
      </div>
      <div className="input-actions">
        <button
          className="primary"
          type="button"
          disabled={gated || isShowcase || status === "loading"}
          onClick={() => void runCompare()}
          data-testid="compare-run"
        >
          {status === "loading" ? t("compareRunning", lang) : t("compareRun", lang)}
        </button>
        <button
          className="ghost"
          type="button"
          disabled={gated || (!baselineText && !candidateText && status === "empty")}
          onClick={clearBoth}
          data-testid="compare-clear-both"
        >
          {t("compareClearBoth", lang)}
        </button>
      </div>
      {status !== "ready" && message && (
        <div className="status-banner error" role="alert">{message}</div>
      )}
      {status === "ready" && message && (
        <div className="status-banner stale" role="status">{message}</div>
      )}
      {card && status === "ready" && (
        <div className="compare-result" data-testid="compare-result">
          <h4>{t("compareDiffTitle", lang)}</h4>
          {cardDiffs.length === 0 ? (
            <p className="hint">
              {lang === "zh-CN" ? "两侧结构投影一致。" : "Both structure projections are equal."}
            </p>
          ) : (
            <ul className="compare-diff-list">
              {cardDiffs.map((d) => (
                <li key={d.field} className="compare-diff-row" data-field={d.field}>
                  <span className="compare-field">
                    {FIELD_LABEL_KEYS[d.field] ? t(FIELD_LABEL_KEYS[d.field] as never, lang) : d.field}
                  </span>
                  <span className="compare-value">
                    {formatValue(d.field, d.baseline, lang)}
                    {" → "}
                    {formatValue(d.field, d.candidate, lang)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {sameFields.length > 0 && (
            <>
              <h4>{t("compareSameTitle", lang)}</h4>
              <p className="hint">
                {sameFields
                  .map((f) => (FIELD_LABEL_KEYS[f] ? t(FIELD_LABEL_KEYS[f] as never, lang) : f))
                  .join(lang === "zh-CN" ? "、" : ", ")}
              </p>
            </>
          )}
          <p className="hint">{t("compareNote", lang)}</p>
          {compareId && (
            <ShareBlock
              lang={lang}
              module="stream"
              resultId={compareId}
              inputRevision={inputRevision}
            />
          )}
        </div>
      )}
    </details>
  );
}
