import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CatalogCase, StreamCard, TimelineEntry } from "./types";
import type { Lang } from "./i18n";
import { t, CASE_ORDER } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import { RequestFailed, isSessionError } from "./api";
import type { AnalysisOutcome } from "./api";
import type { ModuleStatus } from "./App";
import EvidenceMark from "./EvidenceMark";
import ShareBlock from "./ShareBlock";
import FindingGuidance from "./FindingGuidance";

type Status = "empty" | "loading" | "ready" | "stale" | "error";

interface ResultState {
  status: Status;
  resultId: string | null;
  card: StreamCard | null;
  message: string | null;
  sessionExpired: boolean;
}

interface Props {
  lang: Lang;
  visible: boolean;
  onStatus: (status: ModuleStatus) => void;
  combinedSlot?: ReactNode;
  scenario?: string | null;
  onScenarioConsumed?: () => void;
  /** R02: a global clear is pending/unconfirmed - gate this module too. */
  globallyGated?: boolean;
}

const PAGE_SIZE = 50;

export default function StreamModule({
  lang,
  visible,
  onStatus,
  combinedSlot,
  scenario,
  onScenarioConsumed,
  globallyGated = false,
}: Props) {
  const [cases, setCases] = useState<CatalogCase[]>([]);
  const [normalCard, setNormalCard] = useState<StreamCard | null>(null);
  const [tab, setTab] = useState<"input" | "result">("input");
  const [inputTab, setInputTab] = useState<"examples" | "file" | "paste">("examples");
  const [pendingBytes, setPendingBytes] = useState<Uint8Array | null>(null);
  const [pendingInfo, setPendingInfo] = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [result, setResult] = useState<ResultState>({
    status: "empty", resultId: null, card: null, message: null, sessionExpired: false,
  });
  const [showCompare, setShowCompare] = useState(false);
  const [timelineFilter, setTimelineFilter] = useState<"all" | "terminal" | "problems">("all");
  const [page, setPage] = useState(0);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [clearState, setClearState] = useState<"idle" | "clearing" | "unconfirmed">("idle");
  // R02: pending/unconfirmed clear gates analysis and share actions.
  const gated = clearState !== "idle" || globallyGated;
  const [clearNote, setClearNote] = useState<"success" | null>(null);
  const [inputRevision, setInputRevision] = useState(0);

  const revisionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // R03: every file selection gets a ticket; clear() invalidates the
  // current ticket so a deferred FileReader.onload can never land.
  const fileTicketRef = useRef(0);
  const readerRef = useRef<FileReader | null>(null);

  useEffect(() => {
    let cancelled = false;
    adapter.catalog("stream", lang).then((response) => {
      if (cancelled) return;
      const sorted = [...response.cases].sort(
        (a, b) =>
          CASE_ORDER.indexOf(a.case_id as typeof CASE_ORDER[number]) -
          CASE_ORDER.indexOf(b.case_id as typeof CASE_ORDER[number]),
      );
      setCases(sorted);
      setNormalCard(response.normal_reference ?? null);
    }).catch(() => {
      if (!cancelled) setCases([]);
    });
    return () => {
      cancelled = true;
    };
  }, [lang]);

  useEffect(() => {
    onStatus({ status: result.status, resultId: result.resultId });
  }, [result.status, result.resultId, onStatus]);

  useEffect(() => {
    if (result.status !== "ready" || !result.resultId) return;
    if (result.card && result.card.language === lang) return;
    const rid = result.resultId;
    let cancelled = false;
    adapter.rerender(rid, lang).then((card) => {
      if (cancelled) return;
      setResult((prev) =>
        prev.resultId === rid ? { ...prev, card: card as StreamCard } : prev,
      );
    }).catch(() => {
      if (cancelled) return;
      setResult((prev) =>
        prev.resultId === rid
          ? { ...prev, status: "error", message: t("sessionExpired", lang), sessionExpired: true }
          : prev,
      );
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, result.status, result.resultId]);

  const invalidate = useCallback(() => {
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    setResult((prev) =>
      prev.status === "ready" ? { ...prev, status: "stale", sessionExpired: false } : prev,
    );
    setClearNote(null);
    setInputRevision((r) => r + 1);
  }, []);

  const applyOutcome = useCallback((outcome: AnalysisOutcome) => {
    setResult({
      status: "ready",
      resultId: outcome.result_id,
      card: outcome.result as StreamCard,
      message: outcome.slot === "reference" ? t("referenceNote", lang) : null,
      sessionExpired: false,
    });
    setPage(0);
    setSelectedEvent(null);
    setTimelineFilter("all");
    setShowCompare(false);
    setClearNote(null);
    setInputRevision((r) => r + 1);
    // On narrow viewports switch to the result view (≤767 switch).
    try {
      if (window.innerWidth <= 767) setTab("result");
    } catch {
      /* jsdom-less safety */
    }
  }, [lang]);

  const runAnalysis = useCallback(
    async (promise: (signal: AbortSignal) => Promise<AnalysisOutcome>) => {
      // R02: a pending/unconfirmed clear gates new analyses too.
      if (clearState !== "idle" || globallyGated) return;
      const revision = ++revisionRef.current;
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setResult((prev) => ({ ...prev, status: "loading", message: null, sessionExpired: false }));
      try {
        const outcome = await promise(controller.signal);
        if (revision !== revisionRef.current) return;
        applyOutcome(outcome);
      } catch (error) {
        if (revision !== revisionRef.current) return;
        if ((error as Error).name === "AbortError") return;
        if (isSessionError(error)) {
          setResult((prev) => ({
            status: "error",
            resultId: prev.resultId,
            card: prev.card,
            message: t("sessionExpired", lang),
            sessionExpired: true,
          }));
          return;
        }
        const message =
          error instanceof RequestFailed && error.code === "BODY_TOO_LARGE"
            ? t("tooLargeStream", lang)
            : t("networkError", lang);
        setResult((prev) => ({
          status: "error",
          resultId: prev.resultId,
          card: prev.card,
          message,
          sessionExpired: false,
        }));
      }
    },
    [applyOutcome, lang, clearState, globallyGated],
  );

  const runCase = useCallback(
    (caseId: string) => {
      if (clearState !== "idle" || globallyGated) return;
      void runAnalysis((signal) => adapter.runDemo("stream", caseId, lang).then((o) => {
        void signal;
        return o;
      }));
    },
    [lang, runAnalysis, clearState, globallyGated],
  );

  useEffect(() => {
    if (!scenario) return;
    runCase(scenario);
    if (onScenarioConsumed) onScenarioConsumed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  const analyzePending = useCallback(() => {
    if (clearState !== "idle" || globallyGated) return;
    if (inputTab === "paste") {
      if (!pasteText.trim()) return;
      const bytes = new TextEncoder().encode(pasteText);
      if (bytes.length > 8 * 1024 * 1024) {
        setResult({
          status: "error", resultId: null, card: null,
          message: t("tooLargeStream", lang), sessionExpired: false,
        });
        return;
      }
      void runAnalysis((signal) => adapter.analyzeBytes("stream", bytes, null, lang, signal));
      return;
    }
    if (pendingBytes) {
      void runAnalysis((signal) => adapter.analyzeBytes("stream", pendingBytes, null, lang, signal));
    }
  }, [inputTab, lang, pendingBytes, pasteText, runAnalysis, clearState, globallyGated]);

  const onFiles = useCallback((files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".sse") && !lower.endsWith(".txt")) {
      setPendingInfo(`${t("formatLabel", lang)}: .sse / .txt`);
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setPendingInfo(t("tooLargeStream", lang));
      return;
    }
    const ticket = ++fileTicketRef.current;
    const reader = new FileReader();
    readerRef.current = reader;
    reader.onload = () => {
      // R03: a clear or a newer selection invalidates this read.
      if (ticket !== fileTicketRef.current) return;
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      setPendingBytes(bytes);
      setPendingInfo(`${bytes.length} B`);
      invalidate();
    };
    reader.onerror = () => {
      if (ticket !== fileTicketRef.current) return;
      setPendingInfo(`${t("formatLabel", lang)}: .sse / .txt`);
    };
    reader.readAsArrayBuffer(file);
  }, [invalidate, lang]);

  const doClear = useCallback(async () => {
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    // R03: revoke any in-flight/deferred file read and allow re-selecting
    // the same file later.
    fileTicketRef.current += 1;
    if (readerRef.current) {
      try {
        readerRef.current.abort();
      } catch {
        /* abort unsupported: the ticket check still guards onload */
      }
      readerRef.current = null;
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    setPendingBytes(null);
    setPendingInfo(null);
    setPasteText("");
    setResult({ status: "empty", resultId: null, card: null, message: null, sessionExpired: false });
    setTab("input");
    setClearState("clearing");
    setClearNote(null);
    try {
      await adapter.clear("stream");
      setClearState("idle");
      setClearNote("success");
    } catch {
      setClearState("unconfirmed");
    }
  }, []);

  const retryClear = useCallback(async () => {
    setClearState("clearing");
    try {
      await adapter.clear("stream");
      setClearState("idle");
      setClearNote("success");
    } catch {
      setClearState("unconfirmed");
    }
  }, []);

  const card = result.card;
  const timeline: TimelineEntry[] = card ? card.timeline : [];
  const filteredTimeline = timeline.filter((entry) => {
    if (timelineFilter === "all") return true;
    if (timelineFilter === "problems")
      return (
        entry.diagnostic_codes.length > 0 ||
        entry.kind === "error" ||
        entry.kind === "unsupported"
      );
    return (
      entry.kind === "finish" ||
      entry.kind === "done" ||
      entry.kind === "usage" ||
      entry.diagnostic_codes.length > 0
    );
  });
  const pageCount = Math.max(1, Math.ceil(filteredTimeline.length / PAGE_SIZE));
  const visibleTimeline = filteredTimeline.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const verdictLabel = (c: StreamCard) =>
    c.verdict === "NORMAL_TERMINATION"
      ? t("verdictNormal", lang)
      : c.verdict === "NEEDS_REVIEW"
        ? t("verdictReview", lang)
        : t("verdictInvalid", lang);

  const evidenceBlock = (c: StreamCard) => (
    <div className="evidence-row">
      <div className={c.summary.saw_finish ? "evidence on" : "evidence off"}>
        <span className="evidence-dot" aria-hidden="true" />
        {t("finishEvidence", lang)}: {c.summary.saw_finish ? t("present", lang) : t("absentEvidence", lang)}
      </div>
      <div className={c.summary.saw_done ? "evidence on" : "evidence off"}>
        <span className="evidence-dot" aria-hidden="true" />
        {t("doneEvidence", lang)}: {c.summary.saw_done ? t("present", lang) : t("absentEvidence", lang)}
      </div>
      <div className="evidence neutral">
        {t("events", lang)}: {c.summary.event_count} · {t("usageSeen", lang)}:{" "}
        {c.summary.usage_seen ? "✓" : "—"}
      </div>
    </div>
  );

  const compactCard = (c: StreamCard | null) =>
    c ? (
      <div className="compact-card">
        <span className={`verdict-chip ${c.verdict.toLowerCase()}`}>{verdictLabel(c)}</span>
        {evidenceBlock(c)}
      </div>
    ) : (
      <p className="hint">{t("normalReference", lang)}</p>
    );

  const questionEntries: { caseId: string; q: string; desc: string }[] = [
    { caseId: "truncated", q: t("qStreamEnded", lang), desc: t("qStreamDesc", lang) },
    { caseId: "normal", q: t("qNormalCompare", lang), desc: t("qNormalDesc", lang) },
  ];

  const resultPanel = (
    <section className="panel result-pane" aria-label={t("resultTab", lang)}>
      {result.status === "empty" && (
        <div className="empty-state">
          <EvidenceMark accent="var(--stream-accent)" size={24} />
          <h2>{t("emptyTitle", lang)}</h2>
          <p>{t("emptyBody", lang)}</p>
          <div className="question-entries">
            {questionEntries.map((entry) => (
              <button
                key={entry.caseId}
                className="question-card"
                onClick={() => runCase(entry.caseId)}
              >
                <span className="question-q">{entry.q}</span>
                <span className="question-desc">{entry.desc}</span>
                <span className="question-tag">{t("sampleTag", lang)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {result.status === "loading" && (
        <div className="status-banner loading" role="status">
          <EvidenceMark accent="var(--stream-accent)" size={20} busy />
          <span>{t("loading", lang)}</span>
        </div>
      )}
      {result.status === "stale" && card && (
        <div className="status-banner stale" role="alert">{t("staleNotice", lang)}</div>
      )}
      {result.status === "error" && (
        <div className="status-banner error" role="alert">
          {result.message ?? t("networkError", lang)}
          {result.sessionExpired && (
            <button
              className="ghost small restart-button"
              style={{ marginLeft: "12px" }}
              onClick={() => window.location.reload()}
            >
              {t("restart", lang)}
            </button>
          )}
        </div>
      )}
      {card && result.status !== "error" && (
        <div className="result-view" data-testid="result-view">
          <div className={`verdict-banner ${card.verdict.toLowerCase()}`}>
            {verdictLabel(card)}
          </div>
          <p className="scope-note">{t("limitsNote", lang)}</p>
          {evidenceBlock(card)}
          {card.findings.length > 0 && (
            <ul className="finding-list" aria-label="findings">
              {card.findings.map((f, i) => (
                <li key={`${f.code}-${f.event_index ?? "x"}-${i}`} className={`finding ${f.severity}`}>
                  <span className={`badge ${f.severity}`}>{f.code}</span>
                  <div className="finding-detail">
                    <span className="finding-text">{f.explanation}</span>
                    {f.next_steps && (
                      <FindingGuidance steps={f.next_steps} lang={lang} defaultOpen={i === 0} />
                    )}
                  </div>
                  {f.event_index !== null && (
                    <button
                      className="event-link"
                      onClick={() => {
                        setSelectedEvent(f.event_index);
                        setShowCompare(false);
                      }}
                    >
                      @{f.event_index}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {(normalCard || card) && (
            <div className="compare-block">
              <div className="compare-header">
                <span>{t("compareTitle", lang)}</span>
                <button
                  className="ghost small"
                  aria-label={t("compareTitle", lang)}
                  aria-expanded={showCompare}
                  onClick={() => setShowCompare(!showCompare)}
                >
                  {showCompare ? "▾" : "▸"}
                </button>
              </div>
              {showCompare && (
                <div className="compare-wide">
                  <div>
                    <h4>{t("compareCurrent", lang)}</h4>
                    {compactCard(card)}
                  </div>
                  <div>
                    <h4>{t("compareNormal", lang)}</h4>
                    {compactCard(normalCard)}
                  </div>
                </div>
              )}
            </div>
          )}

          <h3>{t("sequenceTitle", lang)}</h3>
          <div className="filter-row" role="group" aria-label={t("filter", lang)}>
            {(["all", "terminal", "problems"] as const).map((value) => (
              <button
                key={value}
                className={timelineFilter === value ? "segment active" : "segment"}
                onClick={() => {
                  setTimelineFilter(value);
                  setPage(0);
                }}
              >
                {value === "all"
                  ? t("filterAll", lang)
                  : value === "terminal"
                    ? t("filterTerminal", lang)
                    : t("filterProblems", lang)}
              </button>
            ))}
          </div>
          {visibleTimeline.length === 0 ? (
            <p className="hint">{t("noEvents", lang)}</p>
          ) : (
            <ul className="timeline-list">
              {visibleTimeline.map((entry) => (
                <li key={entry.index}>
                  <button
                    className={selectedEvent === entry.index ? "timeline-row selected" : "timeline-row"}
                    onClick={() => setSelectedEvent(entry.index)}
                  >
                    <span className="event-index">#{entry.index}</span>
                    <span className={`event-kind ${entry.kind}`}>{entry.kind}</span>
                    {entry.finish_kind && <span className="event-extra">{entry.finish_kind}</span>}
                    {entry.has_content && <span className="event-extra">content</span>}
                    {entry.has_tool_calls && <span className="event-extra">tool_calls</span>}
                    {entry.diagnostic_codes.map((code) => (
                      <span key={code} className="badge warning">{code}</span>
                    ))}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {pageCount > 1 && (
            <div className="pagination">
              <button
                className="ghost small"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                {t("prev", lang)}
              </button>
              <span>{t("page", lang)} {page + 1} / {pageCount}</span>
              <button
                className="ghost small"
                disabled={page >= pageCount - 1}
                onClick={() => setPage(page + 1)}
              >
                {t("next", lang)}
              </button>
            </div>
          )}
          {selectedEvent !== null && timeline[selectedEvent] && (
            <div className="event-detail" role="region" aria-label={t("selectedEvent", lang)}>
              <h4>{t("selectedEvent", lang)} #{selectedEvent}</h4>
              <ul className="event-props">
                <li><code>{t("kind", lang)}</code>: {timeline[selectedEvent].kind}</li>
                <li><code>{t("finishKind", lang)}</code>: {timeline[selectedEvent].finish_kind ?? "null"}</li>
                <li><code>{t("hasContent", lang)}</code>: {String(timeline[selectedEvent].has_content)}</li>
                <li><code>{t("hasToolCalls", lang)}</code>: {String(timeline[selectedEvent].has_tool_calls)}</li>
                <li><code>{t("diagnosticCodes", lang)}</code>: {timeline[selectedEvent].diagnostic_codes.join(", ") || "—"}</li>
              </ul>
            </div>
          )}
        </div>
      )}
      {/* R01: only a ready result is shareable; stale/loading/error
          keep no export affordance. */}
      {result.status === "ready" && result.resultId && (
        <ShareBlock
          lang={lang}
          module="stream"
          resultId={result.resultId}
          inputRevision={inputRevision}
        />
      )}
      {combinedSlot}
    </section>
  );

  const inputPanel = (
    <section className="panel input-pane" aria-label={t("moduleStream", lang)}>
      {isShowcase && <div className="showcase-banner" role="note">{t("showcaseBanner", lang)}</div>}
      <div className="segmented" role="tablist" aria-label={t("examples", lang)}>
        {(["examples", "file", "paste"] as const).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={inputTab === key}
            className={inputTab === key ? "segment active" : "segment"}
            disabled={key !== "examples" && isShowcase}
            onClick={() => setInputTab(key)}
          >
            {t(key, lang)}
          </button>
        ))}
      </div>
      {inputTab === "examples" && (
        <div className="example-list">
          {cases.map((entry) => (
            <button
              key={entry.case_id}
              className="example-card"
              disabled={gated}
              onClick={() => runCase(entry.case_id)}
            >
              <span className="example-name">{entry.description[lang] ?? entry.case_id}</span>
            </button>
          ))}
        </div>
      )}
      {inputTab === "file" && (
        <div
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            onFiles(e.dataTransfer.files);
          }}
        >
          <p>{t("chooseStreamFile", lang)}</p>
          <button className="primary" onClick={() => fileInputRef.current?.click()}>
            {t("file", lang)}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".sse,.txt"
            hidden
            onChange={(e) => onFiles(e.target.files)}
          />
          {pendingInfo && <p className="pending-info">{pendingInfo}</p>}
        </div>
      )}
      {inputTab === "paste" && (
        <div className="paste-area">
          <p className="hint">{t("pasteHintStream", lang)}</p>
          <textarea
            value={pasteText}
            placeholder={t("pastePlaceholderStream", lang)}
            onChange={(event) => {
              setPasteText(event.target.value);
              invalidate();
            }}
            rows={12}
            spellCheck={false}
          />
        </div>
      )}
      <p className="input-warning">{t("noUploadNote", lang)}</p>
      <div className="input-actions">
        <button
          className="primary analyze-button"
          disabled={
            !(
              (inputTab === "paste" && pasteText.trim().length > 0) ||
              (inputTab === "file" && pendingBytes !== null)
            ) || isShowcase
          }
          onClick={analyzePending}
        >
          {t("analyzeStream", lang)}
        </button>
        <button
          className="ghost"
          onClick={() => void doClear()}
          disabled={gated}
        >
          {t("clearThisModule", lang)}
        </button>
      </div>
      {clearState === "unconfirmed" && (
        <div className="clear-banner error" role="alert">
          <span>{t("clearUnconfirmed", lang)}</span>
          <button className="ghost small" onClick={() => void retryClear()}>
            {t("retryClear", lang)}
          </button>
        </div>
      )}
      {clearState === "idle" && clearNote === "success" && (
        <div className="clear-banner" role="status">
          <span>{t("clearSuccess", lang)}</span>
        </div>
      )}
    </section>
  );

  return (
    <div className="module-body" data-view={tab} data-visible={visible ? "true" : "false"}>
      <div className="segmented view-switch">
        <button className={tab === "input" ? "segment active" : "segment"} onClick={() => setTab("input")}>
          {t("inputTab", lang)}
        </button>
        <button className={tab === "result" ? "segment active" : "segment"} onClick={() => setTab("result")}>
          {t("resultTab", lang)}
        </button>
      </div>
      <div className="module-columns">
        {inputPanel}
        {resultPanel}
      </div>
    </div>
  );
}
