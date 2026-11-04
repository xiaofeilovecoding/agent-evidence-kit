import pathlib

# ---- App: R02 global clear gating + honest progress/success banner ----
p = pathlib.Path("src/App.tsx")
s = p.read_text(encoding="utf-8")

s = s.replace(
    '''  const [clearAllState, setClearAllState] = useState<"idle" | "clearing" | "unconfirmed">("idle");''',
    '''  const [clearAllState, setClearAllState] = useState<
    "idle" | "clearing" | "unconfirmed" | "done"
  >("idle");''',
)

s = s.replace(
    """  const doClearAll = useCallback(async () => {
    // Revoke local state and share eligibility immediately.
    setClearAllKey((k) => k + 1);
    setStatuses({
      config: { status: "empty", resultId: null },
      stream: { status: "empty", resultId: null },
    });
    setClearAllState("clearing");
    try {
      await adapter.clear("all");
      setClearAllState("idle");
    } catch {
      // Page is already cleared; the server-side clear is unconfirmed.
      setClearAllState("unconfirmed");
    }
  }, []);""",
    """  const doClearAll = useCallback(async () => {
    // Revoke local state and share eligibility immediately.
    setClearAllKey((k) => k + 1);
    setStatuses({
      config: { status: "empty", resultId: null },
      stream: { status: "empty", resultId: null },
    });
    setClearAllState("clearing");
    try {
      await adapter.clear("all");
      // R02: success wording only after the server acknowledged.
      setClearAllState("done");
    } catch {
      // Page is already cleared; the server-side clear is unconfirmed.
      setClearAllState("unconfirmed");
    }
  }, []);""",
)

s = s.replace(
    """        {clearAllState !== "idle" && (
          <div
            className={clearAllState === "unconfirmed" ? "clear-banner error" : "clear-banner"}
            role={clearAllState === "unconfirmed" ? "alert" : "status"}
          >
            {clearAllState === "unconfirmed" ? (
              <>
                <span>{t("clearUnconfirmed", lang)}</span>
                <button className="ghost small" onClick={() => void retryClearAll()}>
                  {t("retryClear", lang)}
                </button>
              </>
            ) : (
              <span>{t("clearSuccess", lang)}</span>
            )}
          </div>
        )}""",
    """        {(clearAllState === "clearing" || clearAllState === "unconfirmed" || clearAllState === "done") && (
          <div
            className={
              clearAllState === "unconfirmed"
                ? "clear-banner error"
                : "clear-banner"
            }
            role={clearAllState === "unconfirmed" ? "alert" : "status"}
          >
            {clearAllState === "unconfirmed" ? (
              <>
                <span>{t("clearUnconfirmed", lang)}</span>
                <button className="ghost small" onClick={() => void retryClearAll()}>
                  {t("retryClear", lang)}
                </button>
              </>
            ) : clearAllState === "clearing" ? (
              <span>{t("clearInProgress", lang)}</span>
            ) : (
              <span>{t("clearSuccess", lang)}</span>
            )}
          </div>
        )}""",
)

s = s.replace(
    """            <ConfigModule
              key={`config-${clearAllKey}`}
              lang={lang}
              visible={activeModule === "config"}
              onStatus={reportConfigStatus}""",
    """            <ConfigModule
              key={`config-${clearAllKey}`}
              lang={lang}
              visible={activeModule === "config"}
              onStatus={reportConfigStatus}
              globallyGated={clearAllState === "clearing" || clearAllState === "unconfirmed"}""",
)
s = s.replace(
    """            <StreamModule
              key={`stream-${clearAllKey}`}
              lang={lang}
              visible={activeModule === "stream"}
              onStatus={reportStreamStatus}""",
    """            <StreamModule
              key={`stream-${clearAllKey}`}
              lang={lang}
              visible={activeModule === "stream"}
              onStatus={reportStreamStatus}
              globallyGated={clearAllState === "clearing" || clearAllState === "unconfirmed"}""",
)

s = s.replace(
    """            <button
              className="ghost"
              onClick={() => void doClearAll()}
              disabled={clearAllState === "clearing"}
            >""",
    """            <button
              className="ghost"
              onClick={() => void doClearAll()}
              disabled={clearAllState === "clearing"}
            >
""",
)
p.write_text(s, encoding="utf-8")
print("App patched")

# ---- i18n: clearInProgress ----
p = pathlib.Path("src/i18n.ts")
s = p.read_text(encoding="utf-8")
if "clearInProgress" not in s:
    marker = '  clearSuccess: { "zh-CN": "本机会话结果已清空。", en: "Local session results cleared." },'
    assert marker in s
    s = s.replace(
        marker,
        '  clearInProgress: {\n'
        '    "zh-CN": "正在清空本机会话结果…",\n'
        '    en: "Clearing local session results…",\n'
        "  },\n" + marker,
    )
p.write_text(s, encoding="utf-8")
print("i18n patched")
