import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CatalogCase, ConfigCard } from "./types";
import type { Lang } from "./i18n";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import { RequestFailed, isSessionError } from "./api";
import type { AnalysisOutcome } from "./api";
import type { ModuleStatus } from "./App";
import EvidenceMark from "./EvidenceMark";
import ShareBlock from "./ShareBlock";
import FindingGuidance, { NextStepsInline } from "./FindingGuidance";

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
  visible: boolean;
  onStatus: (status: ModuleStatus) => void;
  combinedSlot?: ReactNode;
  scenario?: string | null;
  onScenarioConsumed?: () => void;
  /** R02: a global clear is pending/unconfirmed - gate this module too. */
  globallyGated?: boolean;
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KiB`;
}

function guessFormat(text: string): "json" | "toml" {
  // R05: heuristic only — the server parser stays authoritative. Handle
  // the representative shapes: BOM, leading comment, JSON object/array,
  // TOML table headers and arrays of tables.
  let t = text.trim();
  if (t.charCodeAt(0) === 0xfeff) t = t.slice(1).trimStart();
  if (t.startsWith("#")) return "toml";
  if (t.startsWith("{")) return "json";
  if (t.startsWith("[[")) return "toml";
  if (t.startsWith("[")) {
    const after = t.slice(1).trimStart();
    // JSON array if the first value token is an object, string, number,
    // boolean, null, or the array is closed immediately.
    if (/^(\{|"|'|[-\d]|true|false|null|\])/.test(after)) return "json";
    return "toml";
  }
  return "toml";
}

export default function ConfigModule({
  lang,
  visible,
  onStatus,
  combinedSlot,
  scenario,
  onScenarioConsumed,
  globallyGated = false,
}: Props) {
  const [cases, setCases] = useState<CatalogCase[]>([]);
  const [tab, setTab] = useState<"input" | "result">("input");
  const [inputTab, setInputTab] = useState<"examples" | "file" | "paste">("examples");
  const [pendingBytes, setPendingBytes] = useState<Uint8Array | null>(null);
  const [pendingFormat, setPendingFormat] = useState<"json" | "toml">("json");
  const [pendingInfo, setPendingInfo] = useState<string | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [pasteFormatChoice, setPasteFormatChoice] = useState<"auto" | "json" | "toml">("auto");
  const [result, setResult] = useState<ResultState>({
    status: "empty", resultId: null, card: null, message: null, sessionExpired: false,
  });
  const [severityFilter, setSeverityFilter] = useState<"all" | "warning" | "error">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [clearState, setClearState] = useState<"idle" | "clearing" | "unconfirmed">("idle");
  // R02: pending/unconfirmed clear gates analysis and share actions.
  const gated = clearState !== "idle" || globallyGated;
  const [clearNote, setClearNote] = useState<"success" | null>(null);
  const [inputRevision, setInputRevision] = useState(0);
  // inputRevisionRef mirrors the state for synchronous ticket checks.

  const revisionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // R03: every file selection gets a ticket; clear() invalidates the
  // current ticket so a deferred FileReader.onload can never land.
  const fileTicketRef = useRef(0);
  const readerRef = useRef<FileReader | null>(null);
  // R03/0420: the active input source is part of the input identity.
  const sourceRef = useRef<"examples" | "file" | "paste">("examples");
  /** R03-0345: switching the input source revokes any deferred file
   * read, so a pasted/paste-tab identity can never be poisoned by it. */
  // 0420: one shared revocation for the CURRENT input identity: supersede
  // deferred readers, abort the in-flight analysis, and exit loading/ready
  // into a truthful stale/empty state. Cached input text is kept; share
  // eligibility is not restored by switching back.
  const revokeIdentity = useCallback(() => {
    fileTicketRef.current += 1;
    if (readerRef.current) {
      try {
        readerRef.current.abort();
      } catch {
        /* ticket check still guards onload */
      }
      readerRef.current = null;
    }
    if (abortRef.current) abortRef.current.abort();
    inputRevisionRef.current += 1;
    setInputRevision(inputRevisionRef.current);
    setResult((prev) => {
      if (prev.status === "ready")
        return { ...prev, status: "stale", sessionExpired: false };
      if (prev.status === "loading")
        return prev.card
          ? { ...prev, status: "stale", sessionExpired: false }
          : {
              status: "empty",
              resultId: null,
              card: null,
              message: null,
              sessionExpired: false,
            };
      return prev;
    });
  }, []);

  /** Switching to a different source is an input-identity change: the old
   * analysis is superseded and stays stale until a real new analysis. */
  const setSource = useCallback(
    (next: "examples" | "file" | "paste") => {
      if (sourceRef.current === next) return;
      sourceRef.current = next;
      revokeIdentity();
    },
    [revokeIdentity],
  );
  const inputRevisionRef = useRef(0);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

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

  useEffect(() => {
    onStatus({ status: result.status, resultId: result.resultId });
  }, [result.status, result.resultId, onStatus]);

  // Language re-render bound to the exact result (C05): a late response
  // can never overwrite a newer analysis.
  useEffect(() => {
    if (result.status !== "ready" || !result.resultId) return;
    if (result.card && result.card.language === lang) return;
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
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    setResult((prev) => {
      // R03-0345: an invalidated in-flight analysis must exit loading.
      if (prev.status === "ready")
        return { ...prev, status: "stale", sessionExpired: false };
      if (prev.status === "loading")
        return prev.card
          ? { ...prev, status: "stale", sessionExpired: false }
          : {
              status: "empty",
              resultId: null,
              card: null,
              message: null,
              sessionExpired: false,
            };
      return prev;
    });
    setClearNote(null);
    inputRevisionRef.current += 1;
    setInputRevision(inputRevisionRef.current);
  }, []);

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
    setClearNote(null);
    inputRevisionRef.current += 1;
    setInputRevision(inputRevisionRef.current);
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
      // R03-0345: a new analysis supersedes any deferred file read.
      fileTicketRef.current += 1;
      if (readerRef.current) {
        try {
          readerRef.current.abort();
        } catch {
          /* ticket check still guards onload */
        }
        readerRef.current = null;
      }
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
    [applyOutcome, lang, clearState, globallyGated],
  );

  const runCase = useCallback(
    (caseId: string) => {
      if (clearState !== "idle" || globallyGated) return;
      // 0420: running a sample makes Examples the active input source and
      // supersedes any deferred file read.
      sourceRef.current = "examples";
      fileTicketRef.current += 1;
      if (readerRef.current) {
        try {
          readerRef.current.abort();
        } catch {
          /* ticket check still guards onload */
        }
        readerRef.current = null;
      }
      void runAnalysis((signal) => adapter.runDemo("config", caseId, lang).then((o) => {
        void signal;
        return o;
      }));
    },
    [lang, runAnalysis, clearState, globallyGated],
  );

  // Scenario entries (U02): App may ask this module to run a fixture.
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
  }, [inputTab, lang, pasteFormatChoice, pasteText, pendingBytes, pendingFormat, runAnalysis, clearState, globallyGated]);

  const onFiles = useCallback((files: FileList | null) => {
    // R03: capture the file BEFORE any value reset - FileList is live and
    // clearing the input would silently empty it.
    const file = files?.[0] ?? null;
    // R03: selection starts a new input identity - the previous share and
    // pending bytes are revoked immediately, even for an invalid file.
    fileTicketRef.current += 1;
    if (readerRef.current) {
      try {
        readerRef.current.abort();
      } catch {
        /* ticket check still guards onload */
      }
      readerRef.current = null;
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    setPendingBytes(null);
    setPendingInfo(null);
    sourceRef.current = "file";
    inputRevisionRef.current += 1;
    setInputRevision(inputRevisionRef.current);
    invalidate();
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
    const ticket = ++fileTicketRef.current;
    const ticketRevision = inputRevisionRef.current;
    const reader = new FileReader();
    readerRef.current = reader;
    reader.onload = () => {
      // R03: the read lands only if this is still the current selection,
      // the user is still on the file source, no newer input/analysis
      // happened, and the module is mounted.
      if (!mountedRef.current) return;
      if (ticket !== fileTicketRef.current) return;
      if (sourceRef.current !== "file") return;
      if (inputRevisionRef.current !== ticketRevision) return;
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      setPendingBytes(bytes);
      setPendingFormat(format);
      setPendingInfo(`${format.toUpperCase()} · ${formatBytes(bytes.length)}`);
      invalidate();
    };
    reader.onerror = () => {
      if (!mountedRef.current) return;
      if (ticket !== fileTicketRef.current) return;
      if (sourceRef.current !== "file") return;
      if (inputRevisionRef.current !== ticketRevision) return;
      setPendingInfo(`${t("formatLabel", lang)}: .json / .toml`);
    };
    reader.readAsArrayBuffer(file);
  }, [invalidate, lang]);

  /** S02 clear state machine: local revoke is immediate; the server clear
   * is confirmed separately; failure leaves a retry that never re-erases
   * the user's new input. */
  const doClear = useCallback(async () => {
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    // R03: revoke any in-flight/deferred file read and allow re-selecting
    // the same file later.
    fileTicketRef.current += 1;
    inputRevisionRef.current += 1;
    setInputRevision(inputRevisionRef.current);
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
    setPasteFormatChoice("auto");
    setResult({ status: "empty", resultId: null, card: null, message: null, sessionExpired: false });
    setTab("input");
    setClearState("clearing");
    setClearNote(null);
    try {
      await adapter.clear("config");
      setClearState("idle");
      setClearNote("success");
    } catch {
      setClearState("unconfirmed");
    }
  }, []);

  const retryClear = useCallback(async () => {
    setClearState("clearing");
    try {
      await adapter.clear("config");
      setClearState("idle");
      setClearNote("success");
    } catch {
      setClearState("unconfirmed");
    }
  }, []);

  const effectivePasteFormat =
    pasteFormatChoice === "auto" ? guessFormat(pasteText) : pasteFormatChoice;
  const hasPendingInput =
    inputTab === "paste" ? pasteText.trim().length > 0 : pendingBytes !== null;
  const card = result.card;
  const questionEntries: { caseId: string; q: string; desc: string }[] = [
    { caseId: "http-residue", q: t("qConfigMigration", lang), desc: t("qConfigDesc", lang) },
    { caseId: "plain-stdio", q: t("qNormalCompare", lang), desc: t("qNormalDesc", lang) },
  ];

  const inputPanel = (
    <section className="panel input-pane" aria-label={t("moduleConfig", lang)}>
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
            onClick={() => {
              setInputTab(key);
              // 0420: every input tab is a real source; switching revokes.
              setSource(key);
            }}
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
              // R03: editing paste input revokes any deferred file read.
              sourceRef.current = "paste";
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
                invalidate();
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

      <p className="input-warning">{t("noCommandExec", lang)}</p>
      <div className="input-actions">
        <button
          className="primary analyze-button"
          disabled={!hasPendingInput || inputDisabled || gated}
          onClick={analyzePending}
        >
          {t("analyzeConfig", lang)}
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

  const resultPanel = (
    <section className="panel result-pane" aria-label={t("resultTab", lang)}>
      {result.status === "empty" && (
        <div className="empty-state">
          <EvidenceMark accent="var(--primary)" size={24} />
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
          <EvidenceMark accent="var(--primary)" size={20} busy />
          <span>{t("loading", lang)}</span>
        </div>
      )}
      {result.status === "stale" && card && (
        <div className="status-banner stale" role="alert">
          {t("staleNotice", lang)}
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
      {/* R01: only a ready result is shareable; stale/loading/error
          keep no export affordance. */}
      {result.status === "ready" && result.resultId && (
        <ShareBlock
          lang={lang}
          module="config"
          resultId={result.resultId}
          inputRevision={inputRevision}
        />
      )}
      {combinedSlot}
    </section>
  );

  return (
    <div className="module-body" data-view={tab} data-visible={visible ? "true" : "false"}>
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
      <div className="module-columns">
        {inputPanel}
        {resultPanel}
      </div>
    </div>
  );
}

const inputDisabled = isShowcase;

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
        {card.error.next_steps && (
          <NextStepsInline steps={card.error.next_steps} lang={lang} />
        )}
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
        {card.outcome === "needs_review"
          ? t("findingsTitle", lang)
          : t("noFindingsTitle", lang)}
        <span className="summary-line">
          {t("servicesAnalyzed", lang)}: {card.summary.service_count} ·{" "}
          {t("warnings", lang)}: {card.summary.warning_count} · {t("errors", lang)}:{" "}
          {card.summary.error_count}
        </span>
      </div>
      {card.next_steps && <NextStepsView steps={card.next_steps} lang={lang} />}
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

export function NextStepsView({ steps, lang }: { steps: { observed: string; meaning: string; next_steps: string; does_not_prove: string }; lang: Lang }) {
  return (
    <dl className="next-steps" data-testid="next-steps">
      <div>
        <dt>{t("observedLabel", lang)}</dt>
        <dd>{steps.observed}</dd>
      </div>
      <div>
        <dt>{t("meaningLabel", lang)}</dt>
        <dd>{steps.meaning}</dd>
      </div>
      <div>
        <dt>{t("nextStepsLabel", lang)}</dt>
        <dd>{steps.next_steps}</dd>
      </div>
      <div>
        <dt>{t("cannotProveLabel", lang)}</dt>
        <dd>{steps.does_not_prove}</dd>
      </div>
    </dl>
  );
}

function ServiceGroup(props: {
  service: {
    id: string;
    transport: string;
    fields: Record<string, { present: boolean; type: string | null }>;
    findings: {
      code: string;
      severity: string;
      explanation: string;
      next_steps?: {
        observed: string;
        meaning: string;
        next_steps: string;
        does_not_prove: string;
      };
    }[];
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
      <button
        className="service-header"
        onClick={props.onToggle}
        aria-expanded={props.expanded}
      >
        <span className="service-id">{service.id}</span>
        <span className="service-transport">
          {t("transport", lang)}: {service.transport}
        </span>
        <span className="chevron" aria-hidden="true">
          {props.expanded ? "▾" : "▸"}
        </span>
      </button>
      {props.expanded && (
        <div className="service-body">
          <h4>{t("knownFields", lang)}</h4>
          <ul className="field-list">
            {Object.entries(service.fields).map(([name, meta]) => (
              <li key={name} className={meta.present ? "field present" : "field"}>
                <code>{name}</code>
                <span>{meta.present ? meta.type : t("absent", lang)}</span>
              </li>
            ))}
          </ul>
          <ul className="finding-list">
            {service.findings.map((finding, index) => {
              const isPrimary =
                finding.severity !== "info" &&
                index ===
                  service.findings.findIndex((f) => f.severity !== "info");
              return (
                <li key={finding.code} className={`finding ${finding.severity}`}>
                  <span className={`badge ${finding.severity}`}>{finding.code}</span>
                  <div className="finding-detail">
                    <span className="finding-text">{finding.explanation}</span>
                    {finding.next_steps && (
                      <FindingGuidance
                        steps={finding.next_steps}
                        lang={lang}
                        defaultOpen={isPrimary}
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
