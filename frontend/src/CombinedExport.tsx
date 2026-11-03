import { useCallback, useState } from "react";
import type { Lang, ModuleId } from "./types";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import type { ModuleStatus } from "./App";

interface Props {
  lang: Lang;
  statuses: Record<ModuleId, ModuleStatus>;
}

/**
 * Combined export: the user explicitly opts existing, non-stale results in.
 * Stale or missing results can never be silently included; the preview
 * states exactly which modules are inside and the fixed limitations before
 * the download button appears.
 */
export default function CombinedExport({ lang, statuses }: Props) {
  const [includeConfig, setIncludeConfig] = useState(false);
  const [includeStream, setIncludeStream] = useState(false);
  const [format, setFormat] = useState<"json" | "md">("md");
  const [preview, setPreview] = useState<{ content: string; filename: string; items: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const configReady = statuses.config.status === "ready" && statuses.config.resultId !== null;
  const streamReady = statuses.stream.status === "ready" && statuses.stream.resultId !== null;
  const nothingAvailable = !configReady && !streamReady;

  const loadPreview = useCallback(async () => {
    setError(null);
    setPreview(null);
    const items: { module: ModuleId; resultId: string }[] = [];
    if (includeConfig && configReady) {
      items.push({ module: "config", resultId: statuses.config.resultId! });
    }
    if (includeStream && streamReady) {
      items.push({ module: "stream", resultId: statuses.stream.resultId! });
    }
    if (items.length === 0) return;
    try {
      const payload = await adapter.exportCombined(items, lang, format);
      setPreview({
        content: payload.content,
        filename: payload.filename,
        items: items.map((i) => i.module),
      });
    } catch {
      setError(t("networkError", lang));
    }
  }, [includeConfig, includeStream, configReady, streamReady, statuses, lang, format]);

  const downloadExport = useCallback(() => {
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

  if (isShowcase) return null;

  const moduleLabel = (m: ModuleId) => (m === "config" ? t("moduleConfig", lang) : t("moduleStream", lang));

  return (
    <section className="combined-box" aria-label={t("combinedExport", lang)}>
      <h3>{t("combinedExport", lang)}</h3>
      {nothingAvailable ? (
        <p className="hint">{t("combinedUnavailable", lang)}</p>
      ) : (
        <>
          <p className="combined-note">{t("combinedPick", lang)}</p>
          <label className="combined-option">
            <input
              type="checkbox"
              checked={includeConfig}
              disabled={!configReady}
              onChange={(e) => {
                setIncludeConfig(e.target.checked);
                setPreview(null);
              }}
            />
            <span>
              {t("combinedConfig", lang)}
              {!configReady && (
                <span className="hint"> · {t("combinedStale", lang)}</span>
              )}
            </span>
          </label>
          <label className="combined-option">
            <input
              type="checkbox"
              checked={includeStream}
              disabled={!streamReady}
              onChange={(e) => {
                setIncludeStream(e.target.checked);
                setPreview(null);
              }}
            />
            <span>
              {t("combinedStream", lang)}
              {!streamReady && (
                <span className="hint"> · {t("combinedStale", lang)}</span>
              )}
            </span>
          </label>
          <div className="export-controls" style={{ marginTop: "8px" }}>
            <select
              value={format}
              onChange={(e) => {
                setFormat(e.target.value as "json" | "md");
                setPreview(null);
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
          {error && <p className="status-banner error">{error}</p>}
          {preview && (
            <div className="export-preview">
              <div className="combined-meta">
                <strong>{t("combinedContains", lang)}:</strong>{" "}
                {preview.items.map((m) => moduleLabel(m as ModuleId)).join(" + ")}
                <ul>
                  <li>{t("scopeNote", lang)}</li>
                  <li>{t("limitsNote", lang)}</li>
                </ul>
              </div>
              <pre data-testid="combined-export-preview">{preview.content}</pre>
              <p className="hint">{t("exportNote", lang)}</p>
              <button className="primary" onClick={downloadExport}>
                {t("download", lang)}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
