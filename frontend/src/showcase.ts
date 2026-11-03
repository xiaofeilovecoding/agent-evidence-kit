import type { DataAdapter } from "./api";
import type {
  AnalysisOutcome,
  Card,
  CatalogResponse,
  ExportPayload,
  Lang,
  ModuleId,
  StreamCard,
} from "./types";
import rawShowcase from "./showcase-data.json";

interface ShowcaseEntry {
  case_id: string;
  module: ModuleId;
  input_format?: "json" | "toml";
  description: Record<string, string>;
  results: Record<string, { card: Card; markdown: string }>;
}

interface ShowcaseFile {
  mode: string;
  generated_with: string;
  cases: ShowcaseEntry[];
}

// Static adapter for the sample showcase build. All data is pre-generated
// by the real cores (scripts/generate_showcase.py); no /api or network
// call happens here, and personal input is never accepted.
const showcase = rawShowcase as ShowcaseFile;

export function createShowcaseAdapter(): DataAdapter {
  const find = (caseId: string): ShowcaseEntry => {
    const entry = showcase.cases.find((c) => c.case_id === caseId);
    if (!entry) throw new Error(`unknown case ${caseId}`);
    return entry;
  };

  return {
    kind: "showcase",
    async catalog(module: ModuleId): Promise<CatalogResponse> {
      const cases = showcase.cases
        .filter((c) => c.module === module)
        .map((c) => ({
          case_id: c.case_id,
          input_format: c.input_format,
          description: c.description,
        }));
      if (module === "stream") {
        const normal = showcase.cases.find(
          (c) => c.module === "stream" && c.case_id === "normal",
        );
        return {
          cases,
          normal_reference: normal ? (normal.results["zh-CN"].card as StreamCard) : undefined,
        };
      }
      return { cases };
    },
    async runDemo(module: ModuleId, caseId: string, lang: Lang): Promise<AnalysisOutcome> {
      const entry = find(caseId);
      return {
        result_id: `sample-${entry.case_id}`,
        revision: 0,
        result: entry.results[lang].card,
        slot: "reference",
        module,
      };
    },
    async analyzeBytes(): Promise<AnalysisOutcome> {
      throw new Error("showcase accepts no personal input");
    },
    async rerender(resultId: string, lang: Lang): Promise<Card> {
      const entry = find(resultId.replace(/^sample-/, ""));
      return entry.results[lang].card;
    },
    async export(
      resultId: string,
      lang: Lang,
      format: "json" | "md",
    ): Promise<ExportPayload> {
      const entry = find(resultId.replace(/^sample-/, ""));
      if (format === "md") {
        return {
          filename: `evidence-sample-${entry.case_id}-${lang}.md`,
          content_type: "text/markdown; charset=utf-8",
          content: entry.results[lang].markdown,
        };
      }
      return {
        filename: `evidence-sample-${entry.case_id}-${lang}.json`,
        content_type: "application/json",
        content: JSON.stringify(entry.results[lang].card, null, 2),
      };
    },
    async exportCombined(
      items,
      lang,
    ): Promise<ExportPayload> {
      // Showcase combines pre-generated sample cards only.
      const parts: string[] = [];
      const included: string[] = [];
      for (const item of items) {
        const entry = find(item.resultId.replace(/^sample-/, ""));
        parts.push(entry.results[lang].markdown);
        included.push(entry.case_id);
      }
      return {
        filename: `evidence-sample-combined-${lang}.md`,
        content_type: "text/markdown; charset=utf-8",
        content: parts.join("\n\n") + `\n\nSamples: ${included.join(", ")}`,
      };
    },
    async clear(): Promise<void> {
      /* nothing to clear in showcase */
    },
  };
}
