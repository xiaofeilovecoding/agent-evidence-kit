// Shared result-card types for both diagnostic modules.

export type Severity = "warning" | "error" | "info";
export type Lang = "zh-CN" | "en";
export type ModuleId = "config" | "stream";

export interface NextSteps {
  observed: string;
  meaning: string;
  next_steps: string;
  does_not_prove: string;
}

export interface Finding {
  code: string;
  severity: Severity;
  explanation: string;
  next_steps?: NextSteps;
}

// ---- config module card (schema_version 1) ----

export interface FieldMeta {
  present: boolean;
  type: string | null;
}

export interface ServiceCard {
  id: string;
  transport: string;
  fields: Record<string, FieldMeta>;
  findings: Finding[];
}

export interface ConfigSummary {
  service_count: number;
  warning_count: number;
  error_count: number;
}

export interface ConfigErrorCard {
  schema_version: 1;
  scope: "structure_only";
  language: string;
  outcome: "error";
  summary: ConfigSummary;
  services: never[];
  error: { code: string; explanation: string; next_steps?: NextSteps };
  next_steps?: NextSteps;
}

export interface ConfigSuccessCard {
  schema_version: 1;
  scope: "structure_only";
  language: string;
  outcome: "needs_review" | "not_validated";
  summary: ConfigSummary;
  services: ServiceCard[];
  next_steps?: NextSteps;
  error?: undefined;
}

export type ConfigCard = ConfigErrorCard | ConfigSuccessCard;

// ---- stream module card (schema_version 2) ----

export interface TimelineEntry {
  index: number;
  kind: string;
  finish_kind: string | null;
  has_content: boolean;
  has_tool_calls: boolean;
  diagnostic_codes: string[];
}

export interface StreamSummary {
  event_count: number;
  saw_finish: boolean;
  saw_done: boolean;
  usage_seen: boolean;
}

export interface StreamFinding {
  code: string;
  severity: Severity;
  event_index: number | null;
  explanation: string;
  next_steps?: NextSteps;
}

export interface StreamCard {
  schema_version: 2;
  profile: string;
  language: string;
  verdict: "NORMAL_TERMINATION" | "NEEDS_REVIEW" | "INVALID_INPUT";
  summary: StreamSummary;
  findings: StreamFinding[];
  timeline: TimelineEntry[];
  next_steps?: NextSteps;
}

export type Card = ConfigCard | StreamCard;

export type Theme = "system" | "light" | "dark";

export interface CatalogCase {
  case_id: string;
  input_format?: "json" | "toml";
  description: Record<string, string>;
}

export interface CatalogResponse {
  cases: CatalogCase[];
  normal_reference?: StreamCard;
}

export type AnalysisOutcome = {
  result_id: string;
  revision: number;
  slot?: "current" | "reference";
  module?: ModuleId;
  result: Card;
};

export interface ExportPayload {
  filename: string;
  content_type: string;
  content: string;
}
