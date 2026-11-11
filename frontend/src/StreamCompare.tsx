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
  const clearTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      window.clearTimeout(clearTimerRef.current);
    };
  }, []);

  /** Any edit/new run revokes the previous comparison immediately: the UI
   * drops it, and the server-side clear wipes both sides' stored results so
   * a held old result_id can never be exported afterwards. */
  const revoke = useCallback(
    (resetMessage: boolean) => {
      compareRevRef.current += 1;
      if (abortRef.current) abortRef.current.abort();
      setCard(null);
      setCompareId(null);
      setInputRevision((r) => r + 1);
      if (resetMessage) setMessage(null);
      window.clearTimeout(clearTimerRef.current);
      adapter
        .clear("stream")
        .then(() => {
          if (mountedRef.current) setMessage(null);
        })
        .catch(() => {
          // Clear transfer failed: say so precisely, and the share stays
          // disabled because the comparison was already dropped locally.
          if (mountedRef.current) {
            setStatus((prev) => prev);
            setMessage(
              lang === "zh-CN"
                ? "清除请求未确认：旧分享保持禁用。"
                : "Clear was not confirmed: the previous share stays disabled.",
            );
          }
        });
    },
    [lang],
  );

  const onEdit = useCallback(
    (side: "baseline" | "candidate", value: string) => {
      revoke(true);
      if (side === "baseline") setBaselineText(value);
      else setCandidateText(value);
    },
    [revoke],
  );

  const loadSample = useCallback(
    (side: "baseline" | "candidate") => {
      revoke(true);
      if (side === "baseline") setBaselineText(SAMPLE_BASELINE);
      else setCandidateText(SAMPLE_CANDIDATE);
    },
    [revoke],
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
    compareRevRef.current += 1;
    const rev = compareRevRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
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
      const outcome = await adapter.compareStream(
        baselineOutcome.result_id, candidateOutcome.result_id, lang, controller.signal,
      );
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      setCard(outcome.result as unknown as StreamCompareCard);
      setCompareId(outcome.result_id);
      setInputRevision((r) => r + 1);
      setStatus("ready");
    } catch (error) {
      if (rev !== compareRevRef.current || !mountedRef.current) return;
      if ((error as Error).name === "AbortError") return;
      if (isSessionError(error)) {
        setMessage(t("sessionExpired", lang));
      } else if (error instanceof RequestFailed && error.code === "NO_RESULT") {
        setMessage(
          lang === "zh-CN"
            ? "一侧结果已被清除，请重新比较。"
            : "One side was cleared; run the comparison again.",
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
        <div className="compare-side">
          <label>{t("compareBaselineLabel", lang)}</label>
          <textarea
            aria-label={t("compareBaselineLabel", lang)}
            value={baselineText}
            onChange={(e) => onEdit("baseline", e.target.value)}
            rows={8}
            spellCheck={false}
            data-testid="compare-baseline-input"
          />
          <button
            className="ghost small"
            type="button"
            disabled={gated}
            onClick={() => loadSample("baseline")}
            data-testid="compare-sample-baseline"
          >
            {t("compareLoadNormalSample", lang)}
          </button>
        </div>
        <div className="compare-side">
          <label>{t("compareCandidateLabel", lang)}</label>
          <textarea
            aria-label={t("compareCandidateLabel", lang)}
            value={candidateText}
            onChange={(e) => onEdit("candidate", e.target.value)}
            rows={8}
            spellCheck={false}
            data-testid="compare-candidate-input"
          />
          <button
            className="ghost small"
            type="button"
            disabled={gated}
            onClick={() => loadSample("candidate")}
            data-testid="compare-sample-candidate"
          >
            {t("compareLoadErrorSample", lang)}
          </button>
        </div>
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
