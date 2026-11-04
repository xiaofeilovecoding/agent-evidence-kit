import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { t } from "./i18n";
import type { Lang } from "./types";

interface Props {
  title: string;
  lang: Lang;
  onClose: () => void;
  children: ReactNode;
}

/** Accessible dialog: titled, focus moves to the panel on open, Tab stays
 * inside, Esc/backdrop/close returns focus to the opener. */
export default function Dialog({ title, lang, onClose, children }: Props) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<Element | null>(null);

  useEffect(() => {
    openerRef.current = document.activeElement;
    const panel = panelRef.current;
    if (panel) {
      const focusable = panel.querySelector<HTMLElement>(
        "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
      );
      (focusable ?? panel).focus();
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
        ),
      ).filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      if (openerRef.current instanceof HTMLElement) openerRef.current.focus();
    };
  }, [onClose]);

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="dialog-panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={panelRef}
        tabIndex={-1}
      >
        <div className="dialog-header">
          <h2>{title}</h2>
          <button
            className="ghost small"
            onClick={onClose}
            aria-label={t("close", lang)}
          >
            {t("close", lang)}
          </button>
        </div>
        <div className="dialog-body">{children}</div>
      </div>
    </div>
  );
}
