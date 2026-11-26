import { useMemo, useState } from "react";
import type { ExportPayload, Lang } from "./types";

export function ExportDocument({ preview, lang, testId }: {
  preview: ExportPayload;
  lang: Lang;
  testId: string;
}) {
  const [wrap, setWrap] = useState(true);
  const bytes = useMemo(() => new TextEncoder().encode(preview.content).byteLength, [preview.content]);
  return (
    <div className="export-document">
      <div className="export-document-bar">
        <div className="export-document-name">
          <strong>{preview.filename}</strong>
          <small>{bytes.toLocaleString(lang)} {lang === "en" ? "bytes" : "字节"}</small>
        </div>
        <button type="button" className="ghost small" aria-pressed={wrap} onClick={() => setWrap(!wrap)}>
          {lang === "en" ? "Wrap lines" : "自动换行"}
        </button>
      </div>
      <pre tabIndex={0} data-wrap={wrap} data-testid={testId}>{preview.content}</pre>
    </div>
  );
}
