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
  // E02 ordering: monotonically increasing sequence for revokes and runs.
  const compareSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  // E02: at most one server revoke is in flight; the next compare run awaits
  // it so revocation and creation stay ordered by the compare generation.
  const pendingRevokeRef = useRef<Promise<void> | null>(null);
  // E01: a ready comparison exists — the next edit fires exactly one server
  // revoke (never per keystroke) and immediately drops the old share.
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

  const fireServerRevoke = useCallback(() => {
    const revokeSeq = ++compareSeqRef.current;
    const pending = adapter
      .revokeCompare(revokeSeq)
      .catch(() => {
        // Transfer failed: say so precisely — the old share stays disabled
        // locally and the next compare run will surface any stale rejection.
        if (mountedRef.current) {
          setStatus((prev) => (prev === "loading" ? "empty" : prev));
          setMessage(
            lang === "zh-CN"
              ? "撤销请求未确认：旧分享保持禁用；重新比较将按当前代次执行。"
              : "Revoke was not confirmed: the previous share stays disabled; the next compare runs under the current generation.",
          );
        }
      });
    pendingRevokeRef.current = pending;
    return pending;
  }, [lang]);

  /** Any edit/new run revokes the previous comparison immediately: the UI
   * drops it and exits loading (the run button is usable again), and the
   * server revoke fires once per ready→edit transition. */
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
      // dropped by the generation check and the button is usable again.
      setStatus((prev) => (prev === "loading" ? "empty" : prev));
      setMessage(null);
      if (fireServer && wasReady && !isShowcase) {
        fireServerRevoke();
      }
    },
    [fireServerRevoke],
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
    // E02 ordering: an in-flight server revoke settles before this run's
    // analyses, so they capture the post-revoke compare generation.
    if (pendingRevokeRef.current) {
      const pending = pendingRevokeRef.current;
      pendingRevokeRef.current = null;
      try {
        await pending;
      } catch {
        /* handled by the revoke error path; the run proceeds fail-closed */
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
      const baselineOutcome = await adapter.analyzeBytes(
        "stream", baseBytes, null, lang, controller.signal, "baseline",
      );
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      const candidateOutcome = await adapter.analyzeBytes(
        "stream", candBytes, null, lang, controller.signal, "candidate",
      );
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      const runSeq = ++compareSeqRef.current;
      const outcome = await adapter.compareStream(
        baselineOutcome.result_id, candidateOutcome.result_id, lang, controller.signal, runSeq,
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
