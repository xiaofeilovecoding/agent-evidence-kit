export type Lang = "zh-CN" | "en";

const STRINGS = {
  productName: { "zh-CN": "Agent 证据集", en: "Agent Evidence Kit" },
  localNote: {
    "zh-CN": "本机处理 · 无需 API Key",
    en: "Runs locally · No API key",
  },
  moduleConfig: { "zh-CN": "配置检查", en: "Config check" },
  moduleStream: { "zh-CN": "流结束检查", en: "Stream end check" },
  inputTab: { "zh-CN": "输入", en: "Input" },
  resultTab: { "zh-CN": "结果", en: "Result" },
  examples: { "zh-CN": "示例", en: "Examples" },
  file: { "zh-CN": "文件", en: "File" },
  paste: { "zh-CN": "粘贴", en: "Paste" },
  chooseConfigFile: {
    "zh-CN": "拖放或选择 .json / .toml 文件（≤256KiB）",
    en: "Drop or choose a .json / .toml file (≤256KiB)",
  },
  chooseStreamFile: {
    "zh-CN": "拖放或选择 .sse / .txt 抓包文件（≤8MiB）",
    en: "Drop or choose an .sse / .txt capture (≤8MiB)",
  },
  pastePlaceholderConfig: {
    "zh-CN": "粘贴配置文本（JSON 或 TOML）",
    en: "Paste configuration text (JSON or TOML)",
  },
  pastePlaceholderStream: {
    "zh-CN": "粘贴SSE文本",
    en: "Paste SSE text",
  },
  pasteHintConfig: {
    "zh-CN": "粘贴文本可能被浏览器标准化换行；需要字节级复现时请导入原文件。",
    en: "Pasted text may have normalized line endings; import the original file for byte-exact input.",
  },
  pasteHintStream: {
    "zh-CN": "粘贴可能标准化换行；需要字节级复现时请导入原始抓包文件。",
    en: "Pasting may normalize line endings; import the original capture for byte-exact analysis.",
  },
  formatLabel: { "zh-CN": "格式", en: "Format" },
  formatAuto: { "zh-CN": "自动识别", en: "Auto-detect" },
  formatJson: { "zh-CN": "JSON", en: "JSON" },
  formatToml: { "zh-CN": "TOML", en: "TOML" },
  formatNote: {
    "zh-CN": "如识别不正确，请手动选择格式。",
    en: "If detection is wrong, choose the format manually.",
  },
  analyzeConfig: { "zh-CN": "分析配置", en: "Analyze config" },
  analyzeStream: { "zh-CN": "分析流", en: "Analyze stream" },
  clearThisModule: { "zh-CN": "清空当前模块", en: "Clear this module" },
  clearAll: { "zh-CN": "清空全部", en: "Clear all" },
  exportPreview: { "zh-CN": "导出预览", en: "Export preview" },
  download: { "zh-CN": "下载", en: "Download" },
  combinedExport: { "zh-CN": "组合导出", en: "Combined export" },
  combinedPick: {
    "zh-CN": "勾选要包含的模块结果（两个模块的输入可能来自不同运行，不会建立关联）：",
    en: "Select the module results to include (the two module inputs may come from different runs and are never correlated):",
  },
  combinedConfig: { "zh-CN": "包含配置检查结果", en: "Include config result" },
  combinedStream: { "zh-CN": "包含流结束检查结果", en: "Include stream result" },
  combinedUnavailable: {
    "zh-CN": "暂无可勾选的结果（需要至少一个模块已有未过期结果）。",
    en: "Nothing to combine yet (at least one module needs a fresh result).",
  },
  combinedStale: {
    "zh-CN": "该项结果已过期，不能纳入组合导出。",
    en: "That result is stale and cannot be included.",
  },
  combinedContains: { "zh-CN": "本次导出包含", en: "This export contains" },
  combinedLimitations: { "zh-CN": "固定局限", en: "Fixed limitations" },
  noFindingsTitle: {
    "zh-CN": "未发现结构问题",
    en: "No structural findings",
  },
  findingsTitle: { "zh-CN": "需要复核的发现", en: "Findings needing review" },
  errorTitle: { "zh-CN": "输入错误", en: "Input error" },
  servicesAnalyzed: {
    "zh-CN": "已分析服务数",
    en: "Services analyzed",
  },
  warnings: { "zh-CN": "警告", en: "warnings" },
  errors: { "zh-CN": "错误", en: "errors" },
  transport: { "zh-CN": "规范化传输", en: "Normalized transport" },
  knownFields: { "zh-CN": "已知字段（presence/type）", en: "Known fields (presence/type)" },
  absent: { "zh-CN": "未出现", en: "absent" },
  scopeNote: {
    "zh-CN": "仅结构检查：本工具不验证客户端版本、连接或运行行为，结果不含任何原始配置值。",
    en: "Structure check only: client versions, connectivity and runtime behavior are not validated; raw configuration values never appear.",
  },
  verdictNormal: { "zh-CN": "正常结束", en: "Normal termination" },
  verdictReview: { "zh-CN": "需要复核", en: "Needs review" },
  verdictInvalid: { "zh-CN": "输入无效", en: "Invalid input" },
  limitsNote: {
    "zh-CN": "固定局限：只观察结束证据，不推断真实时间/吞吐量，不验证供应商兼容性，不判断答案正确性。",
    en: "Fixed limits: terminal evidence only; no real timing/throughput, no provider compatibility, no answer-correctness judgment.",
  },
  finishEvidence: { "zh-CN": "finish 证据", en: "finish evidence" },
  doneEvidence: { "zh-CN": "[DONE] 证据", en: "[DONE] evidence" },
  present: { "zh-CN": "已观察到", en: "observed" },
  absentEvidence: { "zh-CN": "未观察到", en: "not observed" },
  events: { "zh-CN": "事件数", en: "events" },
  usageSeen: { "zh-CN": "usage出现", en: "usage seen" },
  compareTitle: { "zh-CN": "与正常样例对照", en: "Compare with normal sample" },
  compareCurrent: { "zh-CN": "当前结果", en: "Current" },
  compareNormal: { "zh-CN": "正常样例", en: "Normal sample" },
  normalReference: {
    "zh-CN": "正常样例加载中或不可用。",
    en: "Normal sample is loading or unavailable.",
  },
  sequenceTitle: {
    "zh-CN": "事件序列（顺序索引，非真实时间）",
    en: "Event sequence (order index, not real time)",
  },
  filterAll: { "zh-CN": "全部", en: "All" },
  filterTerminal: { "zh-CN": "结束相关", en: "End-related" },
  filterProblems: { "zh-CN": "发现问题", en: "Problems" },
  severityWarning: { "zh-CN": "警告", en: "warning" },
  severityError: { "zh-CN": "错误", en: "error" },
  noServices: {
    "zh-CN": "没有可展示的服务（空映射或结构错误）。",
    en: "No services to show (empty mapping or structure error).",
  },
  noEvents: {
    "zh-CN": "当前筛选下没有事件。",
    en: "No events match the current filter.",
  },
  page: { "zh-CN": "页", en: "Page" },
  prev: { "zh-CN": "上一页", en: "Prev" },
  next: { "zh-CN": "下一页", en: "Next" },
  selectedEvent: { "zh-CN": "选中事件证据", en: "Selected event evidence" },
  kind: { "zh-CN": "类型", en: "kind" },
  finishKind: { "zh-CN": "finish", en: "finish" },
  hasContent: { "zh-CN": "有content", en: "has_content" },
  hasToolCalls: { "zh-CN": "有tool_calls", en: "has_tool_calls" },
  diagnosticCodes: { "zh-CN": "诊断码", en: "diagnostic codes" },
  emptyTitle: { "zh-CN": "从合成样例开始", en: "Start with a sample" },
  emptyBody: {
    "zh-CN": "无需 API Key：点击任一示例立即体验真实诊断链。",
    en: "No API key needed: click any sample to run the real diagnostic chain.",
  },
  loading: { "zh-CN": "正在分析…", en: "Analyzing…" },
  stale: {
    "zh-CN": "输入已变更，以下结果已过期。",
    en: "Input changed; the result below is stale.",
  },
  networkError: {
    "zh-CN": "请求失败，请确认本地服务正在运行后重试。",
    en: "Request failed. Make sure the local service is running, then retry.",
  },
  tooLargeConfig: {
    "zh-CN": "输入超过256KiB上限。",
    en: "The input exceeds the 256KiB limit.",
  },
  tooLargeStream: {
    "zh-CN": "输入超过8MiB上限。",
    en: "The input exceeds the 8MiB limit.",
  },
  sessionExpired: {
    "zh-CN": "本地会话已过期，请重新开始。",
    en: "The local session has expired. Please restart.",
  },
  restart: { "zh-CN": "重新开始", en: "Restart" },
  exportNote: {
    "zh-CN": "导出内容与预览完全一致，仅含允许字段，不含原始值。",
    en: "The exported file matches this preview and contains only allowed fields, never raw values.",
  },
  referenceNote: {
    "zh-CN": "当前展示的是样例对照结果。",
    en: "Showing the sample reference result.",
  },
  showcaseBanner: {
    "zh-CN": "样例展示：以下为预生成的公开合成样例，不接受个人文件或粘贴。安装本地版可分析自己的配置或流。",
    en: "Sample showcase: pre-generated public synthetic samples only; personal files and paste are not accepted. Install the local version to analyze your own configs or streams.",
  },
  chars: { "zh-CN": "字符", en: "chars" },
  filter: { "zh-CN": "筛选", en: "Filter" },
} as const;

export type StringKey = keyof typeof STRINGS;

export function t(key: StringKey, lang: Lang): string {
  return STRINGS[key][lang];
}

export const CASE_ORDER = [
  "normal",
  "finish-only",
  "done-only",
  "truncated",
  "limit-stop",
  "after-done",
  "bad-json",
  "unterminated",
] as const;
