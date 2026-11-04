import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CatalogCase, StreamCard, TimelineEntry } from "./types";
import type { Lang } from "./i18n";
import { t, CASE_ORDER } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import { RequestFailed, isSessionError } from "./api";
import type { AnalysisOutcome } from "./api";
import type { ModuleStatus } from "./App";
import type { ExportPayload } from "./types";
import { useExportPreview } from "./useExportPreview";

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
  narrow: boolean;
  visible: boolean;
  onStatus: (status: ModuleStatus) => void;
}

const PAGE_SIZE = 50;

export default function StreamModule({ lang, narrow, visible, onStatus }: Props) {
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
  const [compareView, setCompareView] = useState<"current" | "normal">("current");
  const [timelineFilter, setTimelineFilter] = useState<"all" | "terminal" | "problems">("all");
  const [page, setPage] = useState(0);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [exportFormat, setExportFormat] = useState<"json" | "md">("json");

  const revisionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const exportKey = result.status === "ready" && result.resultId
    ? JSON.stringify([result.resultId, revisionRef.current, lang, exportFormat]) : null;
  const { preview: exportPayload, failed: exportFailed, load: loadExport,
    invalidate: invalidateExport, getPreview: getExportPreview } = useExportPreview<ExportPayload>(exportKey);
  const exportPreview = exportPayload?.content ?? null;
  const showExport = exportPayload !== null;

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

  useLayoutEffect(() => {
    onStatus({ status: result.status, resultId: result.resultId });
  }, [result.status, result.resultId, onStatus]);

  useEffect(() => {
    if (result.status !== "ready" || !result.resultId) return;
    if (result.card && result.card.language === lang) return;
    // C05: bind the re-render to this exact result; a late response must
    // never overwrite a newer analysis result.
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
    invalidateExport();
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    setResult((prev) => (prev.status === "ready" ? { ...prev, status: "stale", sessionExpired: false } : prev));
  }, [invalidateExport]);

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
    invalidateExport();
    if (narrow) setTab("result");
  }, [narrow, lang, invalidateExport]);

  const runAnalysis = useCallback(
    async (promise: (signal: AbortSignal) => Promise<AnalysisOutcome>) => {
      invalidateExport();
      const revision = ++revisionRef.current;
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setResult((prev) => ({ ...prev, status: "loading", message: null, sessionExpired: false }));
      try {
        const outcome = await promise(controller.signal);
        if (revision !== revisionRef.current) return; // late response
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
    [applyOutcome, lang, invalidateExport],
  );

  const runCase = useCallback(
    (caseId: string) => {
      void runAnalysis((signal) => adapter.runDemo("stream", caseId, lang).then((o) => {
        void signal;
        return o;
      }));
    },
    [lang, runAnalysis],
  );

  const analyzePending = useCallback(() => {
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
  }, [inputTab, lang, pendingBytes, pasteText, runAnalysis]);

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
    const reader = new FileReader();
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      setPendingBytes(bytes);
      setPendingInfo(`${bytes.length} B`);
      invalidate();
    };
    reader.readAsArrayBuffer(file);
  }, [invalidate, lang]);

  const doClear = useCallback(async () => {
    invalidateExport();
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    await adapter.clear("stream").catch(() => undefined);
    setPendingBytes(null);
    setPendingInfo(null);
    setPasteText("");
    setResult({ status: "empty", resultId: null, card: null, message: null, sessionExpired: false });
    setTab("input");
  }, [invalidateExport]);

  const loadExportPreview = useCallback(async () => {
    if (result.status !== "ready" || !result.resultId) return;
    await loadExport(() => adapter.export(result.resultId!, lang, exportFormat));
  }, [exportFormat, lang, result.resultId, result.status, loadExport]);

  const downloadExport = useCallback(() => {
    const current = getExportPreview();
    if (!current) return;
    const blob = new Blob([current.content], { type: current.content_type });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = current.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [getExportPreview]);

  const card = result.card;
  const timeline: TimelineEntry[] = card ? card.timeline : [];
  const filteredTimeline = timeline.filter((entry) => {
    if (timelineFilter === "all") return true;
    if (timelineFilter === "problems")
      return entry.diagnostic_codes.length > 0 || entry.kind === "error" || entry.kind === "unsupported";
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
        {t("events", lang)}: {c.summary.event_count} · {t("usageSeen", lang)}: {c.summary.usage_seen ? "✓" : "—"}
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

  const resultPanel = (
    <section className="panel result-panel" aria-label={t("resultTab", lang)}>
      {result.status === "empty" && (
        <div className="empty-state">
          <h2>{t("emptyTitle", lang)}</h2>
          <p>{t("emptyBody", lang)}</p>
          {cases.filter((c) => ["normal", "finish-only", "truncated"].includes(c.case_id)).map((entry) => (
            <button key={entry.case_id} className="example-card" onClick={() => runCase(entry.case_id)}>
              <span className="example-name">{entry.description[lang] ?? entry.case_id}</span>
            </button>
          ))}
        </div>
      )}
      {result.status === "loading" && (
        <div className="status-banner loading" role="status">{t("loading", lang)}</div>
      )}
      {result.status === "stale" && card && (
        <div className="status-banner stale" role="alert">{t("stale", lang)}</div>
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
                  <span className="finding-text">{f.explanation}</span>
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
                  onClick={() => setShowCompare(!showCompare)}
                >
                  {showCompare ? "▾" : "▸"}
                </button>
              </div>
              {showCompare && (
                narrow ? (
                  <div className="compare-narrow">
                    <div className="segmented">
                      <button className={compareView === "current" ? "segment active" : "segment"} onClick={() => setCompareView("current")}>{t("compareCurrent", lang)}</button>
                      <button className={compareView === "normal" ? "segment active" : "segment"} onClick={() => setCompareView("normal")}>{t("compareNormal", lang)}</button>
                    </div>
                    {compareView === "current" ? compactCard(card) : compactCard(normalCard)}
                  </div>
                ) : (
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
                )
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
                {value === "all" ? t("filterAll", lang) : value === "terminal" ? t("filterTerminal", lang) : t("filterProblems", lang)}
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
              <button className="ghost small" disabled={page === 0} onClick={() => setPage(page - 1)}>
                {t("prev", lang)}
              </button>
              <span>{t("page", lang)} {page + 1} / {pageCount}</span>
              <button className="ghost small" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}>
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

          <div className="export-block">
            <div className="export-controls">
              <span>{t("exportPreview", lang)}</span>
              <select
                value={exportFormat}
                onChange={(event) => {
                  setExportFormat(event.target.value as "json" | "md");
                  invalidateExport();
                }}
                aria-label={t("exportPreview", lang)}
              >
                <option value="json">JSON</option>
                <option value="md">Markdown</option>
              </select>
              <button className="ghost" onClick={() => void loadExportPreview()}>
                {t("exportPreview", lang)}
              </button>
            </div>
            {exportFailed && <p className="status-banner error">{t("networkError", lang)}</p>}
          {showExport && exportPreview !== null && (
              <div className="export-preview">
                <pre data-testid="export-preview">{exportPreview}</pre>
                <p className="hint">{t("exportNote", lang)}</p>
                <button className="primary" onClick={downloadExport}>{t("download", lang)}</button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );

  const inputPanel = (
    <section className="panel input-panel" aria-label={t("moduleStream", lang)}>
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
            <button key={entry.case_id} className="example-card" onClick={() => runCase(entry.case_id)}>
              <span className="example-name">{entry.description[lang] ?? entry.case_id}</span>
            </button>
          ))}
        </div>
      )}
      {inputTab === "file" && (
        <div className="dropzone" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); onFiles(e.dataTransfer.files); }}>
          <p>{t("chooseStreamFile", lang)}</p>
          <button className="primary" onClick={() => fileInputRef.current?.click()}>{t("file", lang)}</button>
          <input ref={fileInputRef} type="file" accept=".sse,.txt" hidden onChange={(e) => onFiles(e.target.files)} />
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
      <div className="input-actions">
        <button
          className="primary analyze-button"
          disabled={!(
            (inputTab === "paste" && pasteText.trim().length > 0) ||
            (inputTab === "file" && pendingBytes !== null)
          ) || isShowcase}
          onClick={analyzePending}
        >
          {t("analyzeStream", lang)}
        </button>
        <button className="ghost" onClick={() => void doClear()}>{t("clearThisModule", lang)}</button>
      </div>
    </section>
  );

  return (
    <>
      {narrow && visible && (
        <div className="segmented view-switch">
          <button className={tab === "input" ? "segment active" : "segment"} onClick={() => setTab("input")}>
            {t("inputTab", lang)}
          </button>
          <button className={tab === "result" ? "segment active" : "segment"} onClick={() => setTab("result")}>
            {t("resultTab", lang)}
          </button>
        </div>
      )}
      {!narrow ? (
        <div className="stream-columns" style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "24px" }}>
          {inputPanel}
          {resultPanel}
        </div>
      ) : (
        <>{tab === "input" ? inputPanel : resultPanel}</>
      )}
    </>
  );
}
