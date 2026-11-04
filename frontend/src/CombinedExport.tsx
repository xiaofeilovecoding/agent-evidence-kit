import { useCallback, useEffect, useRef, useState } from "react";
import type { ExportPayload, Lang, ModuleId } from "./types";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import type { ModuleStatus } from "./App";
import { useExportPreview } from "./useExportPreview";

interface Props {
  lang: Lang;
  statuses: Record<ModuleId, ModuleStatus>;
}

/** Combined export (advanced area): the user explicitly opts existing,
 * non-stale results in. Preview and copy/download are bound to the
 * selected results + language + format snapshot; any related change
 * invalidates them, and a late response is discarded. Omitted modules are
 * never silently included. */
export default function CombinedExport({ lang, statuses }: Props) {
  const [includeConfig, setIncludeConfig] = useState(false);
  const [includeStream, setIncludeStream] = useState(false);
  const [format, setFormat] = useState<"md" | "json">("md");
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"copied" | "failed" | null>(null);
  const copiedForRef = useRef<string | null>(null);
  // R04: copy feedback carries a request generation.
  const copySeqRef = useRef(0);
  const requestSeqRef = useRef(0);

  const configReady = statuses.config.status === "ready" && statuses.config.resultId !== null;
  const streamReady = statuses.stream.status === "ready" && statuses.stream.resultId !== null;
  const nothingAvailable = !configReady && !streamReady;

  const selectedItems: { module: ModuleId; resultId: string }[] = [];
  if (includeConfig && configReady) {
    selectedItems.push({ module: "config", resultId: statuses.config.resultId! });
  }
  if (includeStream && streamReady) {
    selectedItems.push({ module: "stream", resultId: statuses.stream.resultId! });
  }
  const snapshotKey = JSON.stringify({ items: selectedItems, lang, format });
  const { preview, failed, load, invalidate, getPreview } =
    useExportPreview<ExportPayload>(snapshotKey);

  useEffect(() => {
    if (copiedForRef.current !== snapshotKey) setCopyState(null);
  }, [snapshotKey, preview]);

  const loadPreview = useCallback(async () => {
    setError(null);
    const items = selectedItems;
    if (items.length === 0) return;
    const seq = ++requestSeqRef.current;
    try {
      await load(() => adapter.exportCombined(items, lang, format));
      void seq;
    } catch {
      if (requestSeqRef.current === seq) setError(t("networkError", lang));
    }
  }, [includeConfig, includeStream, configReady, streamReady, statuses, lang, format, load]);

  const onCopy = useCallback(async () => {
    if (!preview) return;
    const seq = ++copySeqRef.current;
    const snapshot = preview;
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        throw new Error("clipboard unavailable");
      }
      await navigator.clipboard.writeText(snapshot.content);
      // R04: discard feedback when the snapshot changed meanwhile.
      if (copySeqRef.current !== seq || getPreview() !== snapshot) return;
      copiedForRef.current = snapshotKey;
      setCopyState("copied");
    } catch {
      if (copySeqRef.current !== seq || getPreview() !== snapshot) return;
      copiedForRef.current = snapshotKey;
      setCopyState("failed");
    }
  }, [preview, snapshotKey, getPreview]);

  const onDownload = useCallback(() => {
    if (!preview) return;
    const blob = new Blob([preview.content], {
      type: format === "json" ? "application/json" : "text/markdown",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = preview.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [preview, format]);

  useEffect(() => () => invalidate(), [invalidate]);

  if (isShowcase) return null;

  const moduleLabel = (m: ModuleId) =>
    m === "config" ? t("moduleConfig", lang) : t("moduleStream", lang);

  return (
    <section className="combined-box" aria-label={t("combinedExport", lang)}>
      <p className="combined-note">{t("combinedPick", lang)}</p>
      {nothingAvailable ? (
        <p className="hint">{t("combinedUnavailable", lang)}</p>
      ) : (
        <>
          <label className="combined-option">
            <input
              type="checkbox"
              checked={includeConfig}
              disabled={!configReady}
              onChange={(e) => {
                setIncludeConfig(e.target.checked);
              }}
            />
            <span>
              {t("combinedConfig", lang)}
              {!configReady && <span className="hint"> · {t("combinedStale", lang)}</span>}
            </span>
          </label>
          <label className="combined-option">
            <input
              type="checkbox"
              checked={includeStream}
              disabled={!streamReady}
              onChange={(e) => {
                setIncludeStream(e.target.checked);
              }}
            />
            <span>
              {t("combinedStream", lang)}
              {!streamReady && <span className="hint"> · {t("combinedStale", lang)}</span>}
            </span>
          </label>
          <div className="export-controls" style={{ marginTop: "8px" }}>
            <select
              value={format}
              onChange={(e) => {
                setFormat(e.target.value as "md" | "json");
              }}
              aria-label={t("exportPreview", lang)}
            >
              <option value="md">Markdown</option>
              <option value="json">JSON</option>
            </select>
            <button
              className="ghost"
              disabled={(!includeConfig || !configReady) && (!includeStream || !streamReady)}
              onClick={() => void loadPreview()}
            >
              {t("exportPreview", lang)}
            </button>
          </div>
          {error && <p className="share-error" role="alert">{error}</p>}
          {failed && <p className="share-error" role="alert">{t("networkError", lang)}</p>}
          {preview && (
            <div className="share-preview">
              <div className="combined-meta">
                <strong>{t("combinedContains", lang)}:</strong>{" "}
                {preview.filename.includes("combined")
                  ? selectedItems.map((i) => moduleLabel(i.module)).join(" + ")
                  : selectedItems.map((i) => moduleLabel(i.module)).join(" + ")}
                <ul>
                  <li>{t("scopeNote", lang)}</li>
                  <li>{t("limitsNote", lang)}</li>
                </ul>
              </div>
              <pre data-testid="combined-export-preview">{preview.content}</pre>
              <div className="share-actions">
                <button
                  className={copyState === "copied" ? "primary copied" : "primary"}
                  onClick={() => void onCopy()}
                  aria-live="polite"
                >
                  {copyState === "copied" ? t("copied", lang) : t("copy", lang)}
                </button>
                <button className="ghost" onClick={onDownload}>
                  {t("download", lang)}
                </button>
                {copyState === "failed" && (
                  <span className="share-error" role="alert">
                    {t("copyFailed", lang)}
                  </span>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
