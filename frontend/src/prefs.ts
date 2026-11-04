import type { Lang } from "./types";

export type Theme = "system" | "light" | "dark";

const LANG_KEY = "aek.lang";
const THEME_KEY = "aek.theme";

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: preferences stay in memory only */
  }
}

/** First visit follows the browser languages: zh -> zh-CN, anything
 * else -> en. An explicit stored preference always wins. */
export function loadLang(): Lang {
  const stored = storageGet(LANG_KEY);
  if (stored === "zh-CN" || stored === "en") return stored;
  try {
    const langs = navigator.languages ?? [navigator.language];
    for (const tag of langs) {
      const lower = (tag ?? "").toLowerCase();
      if (lower.startsWith("zh")) return "zh-CN";
      if (lower.startsWith("en")) return "en";
    }
  } catch {
    /* keep default */
  }
  return "en";
}

export function saveLang(lang: Lang): void {
  storageSet(LANG_KEY, lang);
}

export function loadTheme(): Theme {
  const stored = storageGet(THEME_KEY);
  if (stored === "system" || stored === "light" || stored === "dark") return stored;
  return "system";
}

export function saveTheme(theme: Theme): void {
  storageSet(THEME_KEY, theme);
}

export function systemPrefersDark(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

/** Apply the resolved theme to <html data-theme>. Only `system` follows
 * the OS; switching themes never resets inputs or triggers requests. */
export function applyTheme(theme: Theme): void {
  const resolved =
    theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
  document.documentElement.setAttribute("data-theme", resolved);
}
