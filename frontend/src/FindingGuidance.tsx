import { useState } from "react";
import type { Lang } from "./types";
import { t } from "./i18n";
import type { NextSteps } from "./types";

/** R06: progressive detail. The primary finding's guidance is expanded by
 * default; every other finding keeps its guidance reachable behind an
 * explicit toggle so no evidence is hidden, only folded. */
export default function FindingGuidance({
  steps,
  lang,
  defaultOpen = false,
}: {
  steps: NextSteps;
  lang: Lang;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="finding-guidance">
      <button
        className="ghost small guidance-toggle"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        {t("guidanceLabel", lang)}
      </button>
      {open && <NextStepsInline steps={steps} lang={lang} />}
    </div>
  );
}

export function NextStepsInline({
  steps,
  lang,
}: {
  steps: NextSteps;
  lang: Lang;
}) {
  return (
    <dl className="next-steps" data-testid="next-steps">
      <div>
        <dt>{t("observedLabel", lang)}</dt>
        <dd>{steps.observed}</dd>
      </div>
      <div>
        <dt>{t("meaningLabel", lang)}</dt>
        <dd>{steps.meaning}</dd>
      </div>
      <div>
        <dt>{t("nextStepsLabel", lang)}</dt>
        <dd>{steps.next_steps}</dd>
      </div>
      <div>
        <dt>{t("cannotProveLabel", lang)}</dt>
        <dd>{steps.does_not_prove}</dd>
      </div>
    </dl>
  );
}
