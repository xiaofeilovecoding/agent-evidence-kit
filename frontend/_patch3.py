import pathlib

# ---- ShareBlock: R04 copy request generation (applies to both copies) ----
p = pathlib.Path("src/ShareBlock.tsx")
s = p.read_text(encoding="utf-8")

if "copySeqRef" not in s:
    s = s.replace(
        "  const copiedForRef = useRef<string | null>(null);",
        "  const copiedForRef = useRef<string | null>(null);\n"
        "  // R04: every copy gets a request generation; the feedback applies\n"
        "  // only if this exact copy is still the current preview snapshot.\n"
        "  const copySeqRef = useRef(0);",
    )

s = s.replace(
    """  const onCopy = useCallback(async () => {
    if (!preview) return;
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        throw new Error("clipboard unavailable");
      }
      await navigator.clipboard.writeText(preview.content);
      copiedForRef.current = key;
      setCopyState("copied");
    } catch {
      copiedForRef.current = key;
      setCopyState("failed");
      // Explicit failure: the preview text stays selectable; no
      // execCommand fallback, no clipboard reading.
    }
  }, [preview, key]);""",
    """  const onCopy = useCallback(async () => {
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
  }, [preview, key, getPreview]);""",
)

s = s.replace(
    "  const { preview, failed, load, invalidate } = useExportPreview<ExportPayload>(key);",
    "  const { preview, failed, load, invalidate, getPreview } =\n"
    "    useExportPreview<ExportPayload>(key);",
)
p.write_text(s, encoding="utf-8")
print("ShareBlock patched")

# ---- CombinedExport: same R04 treatment ----
p = pathlib.Path("src/CombinedExport.tsx")
s = p.read_text(encoding="utf-8")

if "copySeqRef" not in s:
    s = s.replace(
        "  const copiedForRef = useRef<string | null>(null);",
        "  const copiedForRef = useRef<string | null>(null);\n"
        "  // R04: copy feedback carries a request generation.\n"
        "  const copySeqRef = useRef(0);",
    )

s = s.replace(
    "  const { preview, failed, load, invalidate } = useExportPreview<ExportPayload>(snapshotKey);",
    "  const { preview, failed, load, invalidate, getPreview } =\n"
    "    useExportPreview<ExportPayload>(snapshotKey);",
)

s = s.replace(
    """  const onCopy = useCallback(async () => {
    if (!preview) return;
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        throw new Error("clipboard unavailable");
      }
      await navigator.clipboard.writeText(preview.content);
      copiedForRef.current = snapshotKey;
      setCopyState("copied");
    } catch {
      copiedForRef.current = snapshotKey;
      setCopyState("failed");
    }
  }, [preview, snapshotKey]);""",
    """  const onCopy = useCallback(async () => {
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
  }, [preview, snapshotKey, getPreview]);""",
)
p.write_text(s, encoding="utf-8")
print("CombinedExport patched")
