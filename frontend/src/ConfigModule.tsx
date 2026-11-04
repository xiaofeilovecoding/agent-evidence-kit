import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CatalogCase, ConfigCard } from "./types";
import type { Lang } from "./i18n";
import { t } from "./i18n";
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
  card: ConfigCard | null;
  message: string | null;
  sessionExpired: boolean;
}

interface Props {
  lang: Lang;
  narrow: boolean;
  visible: boolean;
  onStatus: (status: ModuleStatus) => void;
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KiB`;
}

function guessFormat(text: string): "json" | "toml" {
  const trimmed = text.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) return "json";
  return "toml";
}

export default function ConfigModule({ lang, narrow, visible, onStatus }: Props) {
  const [cases, setCases] = useState<CatalogCase[]>([]);
  const [tab, setTab] = useState<"input" | "result">("input");
  const [inputTab, setInputTab] = useState<"examples" | "file" | "paste">("examples");
  const [pendingBytes, setPendingBytes] = useState<Uint8Array | null>(null);
  const [pendingFormat, setPendingFormat] = useState<"json" | "toml">("json");
  const [pendingInfo, setPendingInfo] = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");
  // R02: explicit, correctable format choice for pasted text. "auto" keeps
  // the guess as the default but the user can always override it.
  const [pasteFormatChoice, setPasteFormatChoice] = useState<"auto" | "json" | "toml">("auto");
  const [result, setResult] = useState<ResultState>({
    status: "empty", resultId: null, card: null, message: null, sessionExpired: false,
  });
  const [severityFilter, setSeverityFilter] = useState<"all" | "warning" | "error">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
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
    adapter.catalog("config", lang).then((response) => {
      if (!cancelled) setCases(response.cases);
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

  // Re-render the current result when the language changes, without
  // re-analysis. If the session is gone, offer a clear restart entry.
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
        prev.resultId === rid ? { ...prev, card: card as ConfigCard } : prev,
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
    setResult((prev) =>
      prev.status === "ready"
        ? { ...prev, status: "stale", sessionExpired: false }
        : prev,
    );
  }, [invalidateExport]);

  const applyOutcome = useCallback((outcome: AnalysisOutcome) => {
    setResult({
      status: "ready",
      resultId: outcome.result_id,
      card: outcome.result as ConfigCard,
      message: outcome.slot === "reference" ? t("referenceNote", lang) : null,
      sessionExpired: false,
    });
    setExpanded(null);
    setSeverityFilter("all");
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
          error instanceof RequestFailed && error.code === "INPUT_TOO_LARGE"
            ? t("tooLargeConfig", lang)
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
      void runAnalysis((signal) => adapter.runDemo("config", caseId, lang).then((o) => {
        void signal;
        return o;
      }));
    },
    [lang, runAnalysis],
  );

  const analyzePending = useCallback(() => {
    if (inputTab === "paste") {
      if (!pasteText.trim()) return;
      const format =
        pasteFormatChoice === "auto" ? guessFormat(pasteText) : pasteFormatChoice;
      const bytes = new TextEncoder().encode(pasteText);
      if (bytes.length > 256 * 1024) {
        setResult({
          status: "error", resultId: null, card: null,
          message: t("tooLargeConfig", lang), sessionExpired: false,
        });
        return;
      }
      void runAnalysis((signal) => adapter.analyzeBytes("config", bytes, format, lang, signal));
      return;
    }
    if (pendingBytes) {
      void runAnalysis((signal) =>
        adapter.analyzeBytes("config", pendingBytes, pendingFormat, lang, signal));
    }
  }, [inputTab, lang, pasteFormatChoice, pasteText, pendingBytes, pendingFormat, runAnalysis]);

  const onFiles = useCallback((files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".json") && !lower.endsWith(".toml")) {
      setPendingInfo(`${t("formatLabel", lang)}: .json / .toml`);
      return;
    }
    const format = lower.endsWith(".toml") ? "toml" : "json";
    if (file.size > 256 * 1024) {
      setPendingInfo(t("tooLargeConfig", lang));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      setPendingBytes(bytes);
      setPendingFormat(format);
      setPendingInfo(`${format.toUpperCase()} · ${formatBytes(bytes.length)}`);
      invalidate();
    };
    reader.readAsArrayBuffer(file);
  }, [invalidate, lang]);

  const doClear = useCallback(async () => {
    invalidateExport();
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    await adapter.clear("config").catch(() => undefined);
    setPendingBytes(null);
    setPendingInfo(null);
    setPasteText("");
    setPasteFormatChoice("auto");
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

  const inputDisabled = isShowcase;
  const hasPendingInput =
    inputTab === "paste" ? pasteText.trim().length > 0 : pendingBytes !== null;
  const effectivePasteFormat =
    pasteFormatChoice === "auto" ? guessFormat(pasteText) : pasteFormatChoice;

  const inputPanel = (
    <section className="panel input-panel" aria-label={t("moduleConfig", lang)}>
      {isShowcase && (
        <div className="showcase-banner" role="note">
          {t("showcaseBanner", lang)}
        </div>
      )}
      <div className="segmented" role="tablist" aria-label={t("inputTab", lang)}>
        {(["examples", "file", "paste"] as const).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={inputTab === key}
            className={inputTab === key ? "segment active" : "segment"}
            disabled={key !== "examples" && inputDisabled}
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
              onClick={() => runCase(entry.case_id)}
            >
              <span className="example-name">
                {entry.description[lang] ?? entry.case_id}
              </span>
              <span className="example-format">{entry.input_format?.toUpperCase()}</span>
            </button>
          ))}
        </div>
      )}

      {inputTab === "file" && (
        <div
          className="dropzone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            onFiles(event.dataTransfer.files);
          }}
        >
          <p>{t("chooseConfigFile", lang)}</p>
          <button className="primary" onClick={() => fileInputRef.current?.click()}>
            {t("file", lang)}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.toml"
            hidden
            onChange={(event) => onFiles(event.target.files)}
          />
          {pendingInfo && <p className="pending-info">{pendingInfo}</p>}
        </div>
      )}

      {inputTab === "paste" && (
        <div className="paste-area">
          <p className="hint">{t("pasteHintConfig", lang)}</p>
          <textarea
            value={pasteText}
            placeholder={t("pastePlaceholderConfig", lang)}
            onChange={(event) => {
              setPasteText(event.target.value);
              invalidate();
            }}
            rows={10}
            spellCheck={false}
          />
          <div className="format-row">
            <label htmlFor="config-format-select">{t("formatLabel", lang)}:</label>
            <select
              id="config-format-select"
              value={pasteFormatChoice}
              onChange={(event) => {
                setPasteFormatChoice(event.target.value as "auto" | "json" | "toml");
              }}
              aria-label={t("formatLabel", lang)}
            >
              <option value="auto">{t("formatAuto", lang)}</option>
              <option value="json">{t("formatJson", lang)}</option>
              <option value="toml">{t("formatToml", lang)}</option>
            </select>
            <span className="pending-info">
              {t("formatLabel", lang)}: {effectivePasteFormat.toUpperCase()} ·{" "}
              {pasteText.length} {t("chars", lang)}
            </span>
          </div>
          <p className="hint">{t("formatNote", lang)}</p>
        </div>
      )}

      <div className="input-actions">
        <button
          className="primary analyze-button"
          disabled={!hasPendingInput || inputDisabled}
          onClick={analyzePending}
        >
          {t("analyzeConfig", lang)}
        </button>
        <button className="ghost" onClick={() => void doClear()}>
          {t("clearThisModule", lang)}
        </button>
      </div>
    </section>
  );

  const card = result.card;
  const resultPanel = (
    <section className="panel result-panel" aria-label={t("resultTab", lang)}>
      {result.status === "empty" && (
        <div className="empty-state">
          <h2>{t("emptyTitle", lang)}</h2>
          <p>{t("emptyBody", lang)}</p>
          {cases.map((entry) => (
            <button key={entry.case_id} className="example-card" onClick={() => runCase(entry.case_id)}>
              <span className="example-name">{entry.description[lang] ?? entry.case_id}</span>
            </button>
          ))}
        </div>
      )}
      {result.status === "loading" && (
        <div className="status-banner loading" role="status">
          {t("loading", lang)}
        </div>
      )}
      {result.status === "stale" && card && (
        <div className="status-banner stale" role="alert">
          {t("stale", lang)}
        </div>
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
        <ResultCardView
          card={card}
          lang={lang}
          severityFilter={severityFilter}
          setSeverityFilter={setSeverityFilter}
          expanded={expanded}
          setExpanded={setExpanded}
        />
      )}
      {card && (
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
              <button className="primary" onClick={downloadExport}>
                {t("download", lang)}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );

  return (
    <>
      {narrow && visible && (
        <div className="segmented view-switch">
          <button
            className={tab === "input" ? "segment active" : "segment"}
            onClick={() => setTab("input")}
          >
            {t("inputTab", lang)}
          </button>
          <button
            className={tab === "result" ? "segment active" : "segment"}
            onClick={() => setTab("result")}
          >
            {t("resultTab", lang)}
          </button>
        </div>
      )}
      {!narrow ? (
        <div className="config-columns" style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "24px" }}>
          {inputPanel}
          {resultPanel}
        </div>
      ) : (
        <>{tab === "input" ? inputPanel : resultPanel}</>
      )}
    </>
  );
}

function ResultCardView(props: {
  card: ConfigCard;
  lang: Lang;
  severityFilter: "all" | "warning" | "error";
  setSeverityFilter: (value: "all" | "warning" | "error") => void;
  expanded: string | null;
  setExpanded: (value: string | null) => void;
}) {
  const { card, lang } = props;
  if (card.outcome === "error") {
    return (
      <div className="result-error" role="alert">
        <h2>{t("errorTitle", lang)}</h2>
        <p className="finding-code">{card.error.code}</p>
        <p>{card.error.explanation}</p>
      </div>
    );
  }
  const visible = card.services.filter((service) => {
    if (props.severityFilter === "all") return true;
    return service.findings.some((f) =>
      props.severityFilter === "error" ? f.severity === "error" : f.severity === "warning",
    );
  });
  return (
    <div className="result-view" data-testid="result-view">
      <div className={`outcome-banner ${card.outcome}`}>
        {card.outcome === "needs_review" ? t("findingsTitle", lang) : t("noFindingsTitle", lang)}
        <span className="summary-line">
          {t("servicesAnalyzed", lang)}: {card.summary.service_count} ·{" "}
          {t("warnings", lang)}: {card.summary.warning_count} · {t("errors", lang)}: {card.summary.error_count}
        </span>
      </div>
      <p className="scope-note">{t("scopeNote", lang)}</p>
      <div className="filter-row" role="group" aria-label={t("filter", lang)}>
        {(["all", "warning", "error"] as const).map((value) => (
          <button
            key={value}
            className={props.severityFilter === value ? "segment active" : "segment"}
            onClick={() => props.setSeverityFilter(value)}
          >
            {value === "all"
              ? t("filterAll", lang)
              : value === "warning"
                ? t("severityWarning", lang)
                : t("severityError", lang)}
          </button>
        ))}
      </div>
      {visible.length === 0 && <p className="hint">{t("noServices", lang)}</p>}
      {visible.map((service) => (
        <ServiceGroup
          key={service.id}
          service={service}
          lang={lang}
          expanded={props.expanded === service.id}
          onToggle={() =>
            props.setExpanded(props.expanded === service.id ? null : service.id)
          }
        />
      ))}
    </div>
  );
}

function ServiceGroup(props: {
  service: {
    id: string;
    transport: string;
    fields: Record<string, { present: boolean; type: string | null }>;
    findings: { code: string; severity: string; explanation: string }[];
  };
  lang: Lang;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { service, lang } = props;
  const hasProblems = service.findings.some(
    (f) => f.severity === "warning" || f.severity === "error",
  );
  return (
    <div className={hasProblems ? "service-group flagged" : "service-group"}>
      <button className="service-header" onClick={props.onToggle} aria-expanded={props.expanded}>
        <span className="service-id">{service.id}</span>
        <span className="service-transport">
          {t("transport", lang)}: {service.transport}
        </span>
        <span className="chevron" aria-hidden="true">{props.expanded ? "▾" : "▸"}</span>
      </button>
      {props.expanded && (
        <div className="service-body">
          <h4>{t("knownFields", lang)}</h4>
          <ul className="field-list">
            {Object.entries(service.fields).map(([name, meta]) => (
              <li key={name} className={meta.present ? "field present" : "field"}>
                <code>{name}</code>
                <span>
                  {meta.present ? meta.type : t("absent", lang)}
                </span>
              </li>
            ))}
          </ul>
          <ul className="finding-list">
            {service.findings.map((finding) => (
              <li key={finding.code} className={`finding ${finding.severity}`}>
                <span className={`badge ${finding.severity}`}>{finding.code}</span>
                <span className="finding-text">{finding.explanation}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
