import { useCallback, useEffect, useRef, useState } from "react";
import { adapter } from "./adapter";
import { useExportPreview } from "./useExportPreview";
import { t } from "./i18n";
import type { ExportPayload, Lang, ModuleId } from "./types";

/** Single-module share block: Markdown default, JSON optional; preview
 * then copy (primary) / download (secondary). The copied bytes are exactly
 * the preview; copy success feedback is bound to the same export snapshot
 * (any input/format/language change revokes it). */
export default function ShareBlock({
  lang,
  module,
  resultId,
  inputRevision,
}: {
  lang: Lang;
  module: ModuleId;
  resultId: string;
  inputRevision: number;
}) {
  const [format, setFormat] = useState<"md" | "json">("md");
  // The key binds the export to one committed input snapshot: editing the
  // input, changing format/language, or a newer result revokes the export
  // (format A->B->A also revokes via the snapshot generation).
  const key = resultId ? `${resultId}:${lang}:${format}:${inputRevision}` : null;
  const { preview, failed, load, invalidate, getPreview } =
    useExportPreview<ExportPayload>(key);
  const [copyState, setCopyState] = useState<"copied" | "failed" | null>(null);
  const copiedForRef = useRef<string | null>(null);
  // R04: every copy gets a request generation; the feedback applies
  // only if this exact copy is still the current preview snapshot.
  const copySeqRef = useRef(0);

  // Any snapshot change revokes copy feedback (bound to the same snapshot).
  useEffect(() => {
    if (copiedForRef.current !== key) setCopyState(null);
  }, [key, preview]);

  const doExport = useCallback(() => {
    void load(() => adapter.export(resultId, lang, format));
  }, [load, resultId, lang, format]);

  const onCopy = useCallback(async () => {
    if (!preview) return;
    const seq = ++copySeqRef.current;
    const snapshot = preview;
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        throw new Error("clipboard unavailable");
      }
      await navigator.clipboard.writeText(snapshot.content);
      // R04: discard feedback if the preview snapshot changed meanwhile
      // (format/language A-B-A, newer result, clear, unmount).
      if (copySeqRef.current !== seq || getPreview() !== snapshot) return;
      copiedForRef.current = key;
      setCopyState("copied");
    } catch {
      if (copySeqRef.current !== seq || getPreview() !== snapshot) return;
      copiedForRef.current = key;
      setCopyState("failed");
      // Explicit failure: the preview text stays selectable; no
      // execCommand fallback, no clipboard reading.
    }
  }, [preview, key, getPreview]);

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

  const moduleLabel = module === "config" ? t("moduleConfig", lang) : t("moduleStream", lang);
  return (
    <div className="share-block" aria-label={`${t("shareTitle", lang)} · ${moduleLabel}`}>
      <div className="share-row">
        <span className="share-title">{t("shareTitle", lang)}</span>
        <select
          value={format}
          onChange={(event) => {
            setFormat(event.target.value as "md" | "json");
          }}
          aria-label={t("exportPreview", lang)}
        >
          <option value="md">Markdown</option>
          <option value="json">JSON</option>
        </select>
        <button className="ghost" onClick={doExport}>
          {t("exportPreview", lang)}
        </button>
      </div>
      <p className="share-note">{t("shareNote", lang)}</p>
      {preview && (
        <div className="share-preview">
          <pre data-testid="export-preview">{preview.content}</pre>
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
      {failed && (
        <p className="share-error" role="alert">
          {t("networkError", lang)}
        </p>
      )}
    </div>
  );
}
