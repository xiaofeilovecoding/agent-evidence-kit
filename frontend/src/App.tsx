import { useCallback, useEffect, useState } from "react";
import type { Lang, ModuleId } from "./types";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import ConfigModule from "./ConfigModule";
import StreamModule from "./StreamModule";
import CombinedExport from "./CombinedExport";

export interface ModuleStatus {
  status: "empty" | "loading" | "ready" | "stale" | "error";
  resultId: string | null;
}

const LANG_KEY = "aek.lang";

function loadLang(): Lang {
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (stored === "zh-CN" || stored === "en") return stored;
  } catch {
    /* private mode */
  }
  return "zh-CN";
}

export default function App() {
  const [lang, setLang] = useState<Lang>(loadLang);
  const [narrow, setNarrow] = useState(window.innerWidth <= 720);
  const [activeModule, setActiveModule] = useState<ModuleId>("config");
  const [statuses, setStatuses] = useState<Record<ModuleId, ModuleStatus>>({
    config: { status: "empty", resultId: null },
    stream: { status: "empty", resultId: null },
  });
  const [clearAllBusy, setClearAllBusy] = useState(false);
  const [clearAllKey, setClearAllKey] = useState(0);

  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth <= 720);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      /* private mode */
    }
  }, [lang]);

  // Stable per-module reporters (C04): identical status must not create a
  // new state object, or the inline callbacks would re-render forever.
  const reportConfigStatus = useCallback((status: ModuleStatus) => {
    setStatuses((prev) =>
      prev.config.status === status.status && prev.config.resultId === status.resultId
        ? prev
        : { ...prev, config: status },
    );
  }, []);
  const reportStreamStatus = useCallback((status: ModuleStatus) => {
    setStatuses((prev) =>
      prev.stream.status === status.status && prev.stream.resultId === status.resultId
        ? prev
        : { ...prev, stream: status },
    );
  }, []);

  const doClearAll = useCallback(async () => {
    setClearAllBusy(true);
    try {
      await adapter.clear("all");
    } catch {
      /* local-only best effort */
    }
    setClearAllKey((k) => k + 1); // modules listen and reset their state
    setStatuses({
      config: { status: "empty", resultId: null },
      stream: { status: "empty", resultId: null },
    });
    setClearAllBusy(false);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-title">
          <span className="product-name">{t("productName", lang)}</span>
          <span className="local-note">{t("localNote", lang)}</span>
        </div>
        <div className="lang-switch" role="group" aria-label="language">
          <button
            className={lang === "zh-CN" ? "lang active" : "lang"}
            onClick={() => setLang("zh-CN")}
            aria-pressed={lang === "zh-CN"}
          >
            中文
          </button>
          <button
            className={lang === "en" ? "lang active" : "lang"}
            onClick={() => setLang("en")}
            aria-pressed={lang === "en"}
          >
            English
          </button>
        </div>
      </header>
      <div className="module-switch">
        <div className="segmented" role="tablist" aria-label={t("inputTab", lang)}>
          <button
            role="tab"
            aria-selected={activeModule === "config"}
            className={
              activeModule === "config" ? "segment active" : "segment"
            }
            onClick={() => setActiveModule("config")}
          >
            {t("moduleConfig", lang)}
          </button>
          <button
            role="tab"
            aria-selected={activeModule === "stream"}
            className={
              activeModule === "stream"
                ? "segment active module-stream"
                : "segment module-stream"
            }
            onClick={() => setActiveModule("stream")}
          >
            {t("moduleStream", lang)}
          </button>
        </div>
      </div>
      <main className={narrow ? "main narrow" : "main wide"}>
        <div className={activeModule === "config" ? "config-module" : "config-module module-hidden"}>
          <ConfigModule
            key={`config-${clearAllKey}`}
            lang={lang}
            narrow={narrow}
            visible={activeModule === "config"}
            onStatus={reportConfigStatus}
          />
        </div>
        <div className={activeModule === "stream" ? "stream-module" : "stream-module module-hidden"}>
          <StreamModule
            key={`stream-${clearAllKey}`}
            lang={lang}
            narrow={narrow}
            visible={activeModule === "stream"}
            onStatus={reportStreamStatus}
          />
        </div>
      </main>
      {!isShowcase && (
        <div className="combined-export">
          <CombinedExport
            lang={lang}
            statuses={statuses}
          />
          <div className="input-actions" style={{ justifyContent: "center" }}>
            <button
              className="ghost"
              onClick={() => void doClearAll()}
              disabled={clearAllBusy}
            >
              {t("clearAll", lang)}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
