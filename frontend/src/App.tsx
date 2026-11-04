import { useCallback, useEffect, useState } from "react";
import type { Lang, ModuleId, Theme } from "./types";
import { t } from "./i18n";
import { adapter, isShowcase } from "./adapter";
import { applyTheme, loadLang, loadTheme, saveLang, saveTheme } from "./prefs";
import ConfigModule from "./ConfigModule";
import StreamModule from "./StreamModule";
import CombinedExport from "./CombinedExport";
import Dialog from "./Dialog";
import PrivacyPanel from "./PrivacyPanel";
import EvidenceMark from "./EvidenceMark";

export interface ModuleStatus {
  status: "empty" | "loading" | "ready" | "stale" | "error";
  resultId: string | null;
}

const ACCENTS: Record<ModuleId, string> = {
  config: "var(--primary)",
  stream: "var(--stream-accent)",
};

export default function App() {
  const [lang, setLang] = useState<Lang>(loadLang);
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [activeModule, setActiveModule] = useState<ModuleId>("config");
  const [statuses, setStatuses] = useState<Record<ModuleId, ModuleStatus>>({
    config: { status: "empty", resultId: null },
    stream: { status: "empty", resultId: null },
  });
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [clearAllState, setClearAllState] = useState<"idle" | "clearing" | "unconfirmed">("idle");
  const [clearAllKey, setClearAllKey] = useState(0);

  // Language: explicit preference saved; first visit followed the browser.
  useEffect(() => saveLang(lang), [lang]);

  // Theme: only `system` follows the OS; never resets inputs or requests.
  useEffect(() => {
    applyTheme(theme);
    saveTheme(theme);
    if (theme !== "system") return;
    try {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = () => applyTheme("system");
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    } catch {
      return undefined;
    }
  }, [theme]);

  // Stable per-module reporters (no idle re-render loops).
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
  }, []);

  const retryClearAll = useCallback(async () => {
    setClearAllState("clearing");
    try {
      await adapter.clear("all");
      setClearAllState("idle");
    } catch {
      setClearAllState("unconfirmed");
    }
  }, []);

  const moduleTabs = (
    <div className="module-tabs" role="tablist" aria-label={t("inputTab", lang)}>
      <button
        role="tab"
        aria-selected={activeModule === "config"}
        className={activeModule === "config" ? "module-tab active" : "module-tab"}
        onClick={() => setActiveModule("config")}
      >
        <span className="module-dot config" aria-hidden="true" />
        {t("moduleConfig", lang)}
      </button>
      <button
        role="tab"
        aria-selected={activeModule === "stream"}
        className={activeModule === "stream" ? "module-tab active" : "module-tab"}
        onClick={() => setActiveModule("stream")}
      >
        <span className="module-dot stream" aria-hidden="true" />
        {t("moduleStream", lang)}
      </button>
    </div>
  );

  return (
    <div className="workspace">
      <aside className="sidebar" aria-label={t("productName", lang)}>
        <div className="sidebar-brand">
          <EvidenceMark accent={ACCENTS[activeModule]} size={24} />
          <span className="product-name">{t("productName", lang)}</span>
        </div>
        <nav className="sidebar-nav" aria-label={t("inputTab", lang)}>
          <button
            className={activeModule === "config" ? "nav-item active" : "nav-item"}
            onClick={() => setActiveModule("config")}
            aria-current={activeModule === "config" ? "page" : undefined}
          >
            <span className="module-dot config" aria-hidden="true" />
            {t("moduleConfig", lang)}
          </button>
          <button
            className={activeModule === "stream" ? "nav-item active" : "nav-item"}
            onClick={() => setActiveModule("stream")}
            aria-current={activeModule === "stream" ? "page" : undefined}
          >
            <span className="module-dot stream" aria-hidden="true" />
            {t("moduleStream", lang)}
          </button>
        </nav>
        <div className="sidebar-footer">
          <button className="nav-item" onClick={() => setPrivacyOpen(true)}>
            <span aria-hidden="true">·</span>
            {t("privacy", lang)}
          </button>
          <button className="nav-item" onClick={() => setHelpOpen(true)}>
            <span aria-hidden="true">·</span>
            {t("help", lang)}
          </button>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <div className="topbar-title">
            <span className="topbar-task">
              {activeModule === "config" ? t("moduleConfig", lang) : t("moduleStream", lang)}
            </span>
            <button
              className="local-badge"
              onClick={() => setPrivacyOpen(true)}
              title={t("privacyTitle", lang)}
            >
              {t("processedLocally", lang)}
            </button>
          </div>
          <div className="topbar-actions">
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
            <div className="theme-switch" role="group" aria-label={t("themeLabel", lang)}>
              <button
                className={theme === "system" ? "lang active" : "lang"}
                onClick={() => setTheme("system")}
                aria-pressed={theme === "system"}
              >
                {t("themeSystem", lang)}
              </button>
              <button
                className={theme === "light" ? "lang active" : "lang"}
                onClick={() => setTheme("light")}
                aria-pressed={theme === "light"}
              >
                {t("themeLight", lang)}
              </button>
              <button
                className={theme === "dark" ? "lang active" : "lang"}
                onClick={() => setTheme("dark")}
                aria-pressed={theme === "dark"}
              >
                {t("themeDark", lang)}
              </button>
            </div>
          </div>
        </header>
        <div className="module-tabs-wide">{moduleTabs}</div>
        {clearAllState !== "idle" && (
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
        )}
        <main className="content">
          <div className={activeModule === "config" ? "config-module" : "config-module module-hidden"}>
            <ConfigModule
              key={`config-${clearAllKey}`}
              lang={lang}
              visible={activeModule === "config"}
              onStatus={reportConfigStatus}
              combinedSlot={
                !isShowcase ? (
                  <details className="advanced-combined">
                    <summary>{t("advanced", lang)}</summary>
                    <CombinedExport lang={lang} statuses={statuses} />
                  </details>
                ) : null
              }
            />
          </div>
          <div className={activeModule === "stream" ? "stream-module" : "stream-module module-hidden"}>
            <StreamModule
              key={`stream-${clearAllKey}`}
              lang={lang}
              visible={activeModule === "stream"}
              onStatus={reportStreamStatus}
              combinedSlot={
                !isShowcase ? (
                  <details className="advanced-combined">
                    <summary>{t("advanced", lang)}</summary>
                    <CombinedExport lang={lang} statuses={statuses} />
                  </details>
                ) : null
              }
            />
          </div>
        </main>
        {!isShowcase && (
          <div className="footer-clear">
            <button
              className="ghost"
              onClick={() => void doClearAll()}
              disabled={clearAllState === "clearing"}
            >
              {t("clearAll", lang)}
            </button>
          </div>
        )}
      </div>
      {privacyOpen && <PrivacyPanel lang={lang} onClose={() => setPrivacyOpen(false)} />}
      {helpOpen && (
        <Dialog title={t("helpTitle", lang)} lang={lang} onClose={() => setHelpOpen(false)}>
          <ol className="privacy-steps">
            <li>{t("helpStep1", lang)}</li>
            <li>{t("helpStep2", lang)}</li>
            <li>{t("helpStep3", lang)}</li>
          </ol>
        </Dialog>
      )}
    </div>
  );
}
