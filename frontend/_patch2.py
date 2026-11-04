import pathlib

# ---- StreamModule: same R02 gating + R03 tickets ----
p = pathlib.Path("src/StreamModule.tsx")
s = p.read_text(encoding="utf-8")

if "globallyGated" not in s:
    s = s.replace(
        """interface Props {
  lang: Lang;
  visible: boolean;
  onStatus: (status: ModuleStatus) => void;
  combinedSlot?: ReactNode;
  scenario?: string | null;
  onScenarioConsumed?: () => void;
}""",
        """interface Props {
  lang: Lang;
  visible: boolean;
  onStatus: (status: ModuleStatus) => void;
  combinedSlot?: ReactNode;
  scenario?: string | null;
  onScenarioConsumed?: () => void;
  /** R02: a global clear is pending/unconfirmed - gate this module too. */
  globallyGated?: boolean;
}""",
    )
    s = s.replace(
        """export default function StreamModule({
  lang,
  visible,
  onStatus,
  combinedSlot,
  scenario,
  onScenarioConsumed,
}: Props) {""",
        """export default function StreamModule({
  lang,
  visible,
  onStatus,
  combinedSlot,
  scenario,
  onScenarioConsumed,
  globallyGated = false,
}: Props) {""",
    )

if "fileTicketRef" not in s:
    s = s.replace(
        """  const revisionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);""",
        """  const revisionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // R03: every file selection gets a ticket; clear() invalidates the
  // current ticket so a deferred FileReader.onload can never land.
  const fileTicketRef = useRef(0);
  const readerRef = useRef<FileReader | null>(null);""",
    )

if "const gated = " not in s:
    s = s.replace(
        '  const [clearState, setClearState] = useState<"idle" | "clearing" | "unconfirmed">("idle");',
        '  const [clearState, setClearState] = useState<"idle" | "clearing" | "unconfirmed">("idle");\n'
        "  // R02: pending/unconfirmed clear gates analysis and share actions.\n"
        "  const gated = clearState !== \"idle\" || globallyGated;",
    )

if "R02: a pending/unconfirmed clear gates new analyses" not in s:
    s = s.replace(
        """  const runAnalysis = useCallback(
    async (promise: (signal: AbortSignal) => Promise<AnalysisOutcome>) => {
      const revision = ++revisionRef.current;""",
        """  const runAnalysis = useCallback(
    async (promise: (signal: AbortSignal) => Promise<AnalysisOutcome>) => {
      // R02: a pending/unconfirmed clear gates new analyses too.
      if (clearState !== "idle" || globallyGated) return;
      const revision = ++revisionRef.current;""",
    )
    s = s.replace(
        "    },\n    [applyOutcome, lang],\n  );",
        "    },\n    [applyOutcome, lang, clearState, globallyGated],\n  );",
    )

s = s.replace(
    """  const runCase = useCallback(
    (caseId: string) => {
      void runAnalysis((signal) => adapter.runDemo("stream", caseId, lang).then((o) => {
        void signal;
        return o;
      }));
    },
    [lang, runAnalysis],
  );""",
    """  const runCase = useCallback(
    (caseId: string) => {
      if (clearState !== "idle" || globallyGated) return;
      void runAnalysis((signal) => adapter.runDemo("stream", caseId, lang).then((o) => {
        void signal;
        return o;
      }));
    },
    [lang, runAnalysis, clearState, globallyGated],
  );""",
)

s = s.replace(
    """  const analyzePending = useCallback(() => {
    if (inputTab === "paste") {""",
    """  const analyzePending = useCallback(() => {
    if (clearState !== "idle" || globallyGated) return;
    if (inputTab === "paste") {""",
)
s = s.replace(
    "  }, [inputTab, lang, pendingBytes, pasteText, runAnalysis]);",
    "  }, [inputTab, lang, pendingBytes, pasteText, runAnalysis, clearState, globallyGated]);",
)

if "R03: revoke any in-flight" not in s:
    s = s.replace(
        """  const doClear = useCallback(async () => {
    revisionRef.current += 1;
    if (abortRef.current) abortRef.current.abort();""",
        """  const doClear = useCallback(async () => {
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
    if (fileInputRef.current) fileInputRef.current.value = "";""",
    )

if "R03: a clear or a newer selection" not in s:
    s = s.replace(
        """    const reader = new FileReader();
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      setPendingBytes(bytes);
      setPendingInfo(`${bytes.length} B`);
      invalidate();
    };
    reader.readAsArrayBuffer(file);
  }, [invalidate, lang]);""",
        """    const ticket = ++fileTicketRef.current;
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
  }, [invalidate, lang]);""",
    )

if "disabled={gated}" not in s:
    s = s.replace(
        """        <button className="ghost" onClick={() => void doClear()}>
          {t("clearThisModule", lang)}
        </button>""",
        """        <button
          className="ghost"
          onClick={() => void doClear()}
          disabled={gated}
        >
          {t("clearThisModule", lang)}
        </button>""",
    )
    s = s.replace(
        """            <button key={entry.case_id} className="example-card" onClick={() => runCase(entry.case_id)}>""",
        """            <button
              key={entry.case_id}
              className="example-card"
              disabled={gated}
              onClick={() => runCase(entry.case_id)}
            >""",
    )

p.write_text(s, encoding="utf-8")
print("StreamModule patched:", s.count("globallyGated"), "gated refs")
