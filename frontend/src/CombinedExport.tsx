import { useCallback, useState } from "react";
import type { ExportPayload, Lang, ModuleId } from "./types";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import type { ModuleStatus } from "./App";
import { useExportPreview } from "./useExportPreview";

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

  const configReady = statuses.config.status === "ready" && statuses.config.resultId !== null;
  const streamReady = statuses.stream.status === "ready" && statuses.stream.resultId !== null;
  const nothingAvailable = !configReady && !streamReady;

  // C03: the selected results, language and format form a snapshot key;
  // the preview (and its download) is only valid while this key is
  // unchanged. Any related change invalidates it immediately.
  const selectedItems: { module: ModuleId; resultId: string }[] = [];
  if (includeConfig && configReady) {
    selectedItems.push({ module: "config", resultId: statuses.config.resultId! });
  }
  if (includeStream && streamReady) {
    selectedItems.push({ module: "stream", resultId: statuses.stream.resultId! });
  }
  const snapshotKey = JSON.stringify({
    items: selectedItems,
    lang,
    format,
  });

  const { preview, failed, getPreview, load, invalidate } = useExportPreview<
    ExportPayload & { items: ModuleId[] }
  >(selectedItems.length ? snapshotKey : null);

  const loadPreview = useCallback(async () => {
    const items = selectedItems;
    if (items.length === 0) return;
    await load(async () => {
      const payload = await adapter.exportCombined(items, lang, format);
      return { ...payload, items: items.map((i) => i.module) };
    });
  }, [snapshotKey, lang, format, load]);

  const downloadExport = useCallback(() => {
    const current = getPreview();
    if (!current) return;
    const blob = new Blob([current.content], {
      type: current.content_type,
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = current.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [getPreview]);

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
                invalidate();
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
                invalidate();
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
                invalidate();
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
          {failed && <p className="status-banner error">{t("networkError", lang)}</p>}
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
