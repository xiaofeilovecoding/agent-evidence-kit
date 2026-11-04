import Dialog from "./Dialog";
import { t } from "./i18n";
import type { Lang } from "./types";

/** Verifiable data-path panel (S01): an information entry, not a security
 * score. Four fixed steps, no certification visuals. */
export default function PrivacyPanel({
  lang,
  onClose,
}: {
  lang: Lang;
  onClose: () => void;
}) {
  return (
    <Dialog title={t("privacyTitle", lang)} lang={lang} onClose={onClose}>
      <ol className="privacy-steps">
        <li>{t("privacyStep1", lang)}</li>
        <li>{t("privacyStep2", lang)}</li>
        <li>{t("privacyStep3", lang)}</li>
        <li>{t("privacyStep4", lang)}</li>
      </ol>
      <p className="privacy-note">{t("privacyNote", lang)}</p>
    </Dialog>
  );
}
