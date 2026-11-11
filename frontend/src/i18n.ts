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
  // stream compare (baseline vs candidate)
  compareSectionTitle: { "zh-CN": "正常 vs 异常比较", en: "Baseline vs candidate compare" },
  compareSectionHint: {
    "zh-CN": "展开后输入两侧捕获流：基线（正常）与候选（待比较）。比较只读取结构投影。",
    en: "Expand and provide both captured streams: baseline (normal) and candidate. The comparison reads structure projections only.",
  },
  compareBaselineLabel: { "zh-CN": "基线（正常）", en: "Baseline (normal)" },
  compareCandidateLabel: { "zh-CN": "候选（待比较）", en: "Candidate (to compare)" },
  compareLoadNormalSample: { "zh-CN": "载入正常样例 → 基线", en: "Load normal sample → baseline" },
  compareLoadErrorSample: { "zh-CN": "载入上游错误样例 → 候选", en: "Load upstream-error sample → candidate" },
  compareRun: { "zh-CN": "比较两侧", en: "Compare both sides" },
  compareRunning: { "zh-CN": "比较中…", en: "Comparing…" },
  compareNeedsBoth: {
    "zh-CN": "需要两侧输入（粘贴或载入样例）后才能比较。",
    en: "Provide both sides (paste or load a sample) before comparing.",
  },
  compareRevoked: {
    "zh-CN": "任一侧修改后旧比较与分享立即失效。",
    en: "Editing either side immediately revokes the previous comparison and share.",
  },
  compareDiffTitle: { "zh-CN": "观察差异（终态优先）", en: "Observed differences (terminal first)" },
  compareSameTitle: { "zh-CN": "两侧一致", en: "Equal on both sides" },
  compareTerminal: { "zh-CN": "终态", en: "Terminal state" },
  compareVerdict: { "zh-CN": "判定", en: "Verdict" },
  compareFinishReason: { "zh-CN": "finish_reason", en: "finish_reason" },
  compareDoneSeen: { "zh-CN": "是否见 [DONE]", en: "[DONE] seen" },
  compareTerminalIndex: { "zh-CN": "终态事件位置", en: "Terminal event index" },
  compareDiagCodes: { "zh-CN": "诊断代码", en: "Diagnostic codes" },
  compareEventCount: { "zh-CN": "事件数", en: "Event count" },
  compareNote: {
    "zh-CN": "以上为观察差异；本比较不证明上游根因。",
    en: "Observed differences only; this comparison does not prove upstream root causes.",
  },
  compareShowcaseNote: {
    "zh-CN": "静态展示页不支持比较；请在本地 CLI 或 Web 应用中使用。",
    en: "The static showcase cannot run comparisons; use the local CLI or web app.",
  },
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
  // ---- PUBLIC-READY-002 additions ----
  noCommandExec: {
    "zh-CN": "不会执行配置中的命令；只分析你提供的内容。",
    en: "Commands in the config are never executed; only the content you provide is analyzed.",
  },
  noUploadNote: {
    "zh-CN": "不读取账户、不扫描磁盘；只分析你粘贴或选择的内容。",
    en: "No accounts are read and no disks are scanned; only the content you paste or choose is analyzed.",
  },
  sampleTag: { "zh-CN": "合成样例", en: "Synthetic sample" },
  guidanceLabel: { "zh-CN": "含义与下一步", en: "Meaning & next step" },
  close: { "zh-CN": "关闭", en: "Close" },
  help: { "zh-CN": "帮助", en: "Help" },
  privacy: { "zh-CN": "隐私", en: "Privacy" },
  processedLocally: { "zh-CN": "本机处理", en: "Processed locally" },
  themeLabel: { "zh-CN": "主题", en: "Theme" },
  themeSystem: { "zh-CN": "跟随系统", en: "System" },
  themeLight: { "zh-CN": "浅色", en: "Light" },
  themeDark: { "zh-CN": "深色", en: "Dark" },
  privacyTitle: { "zh-CN": "本机处理：数据路径", en: "Processed locally: where your data goes" },
  privacyStep1: {
    "zh-CN": "1. 原文仅在你正在使用的输入框/文件控件中可见（这是预期显示）。",
    en: "1. Your raw text is visible only in the input control you are using (this display is expected).",
  },
  privacyStep2: {
    "zh-CN": "2. 点击分析后，内容通过本机HTTP发送给同一台机器上的本地Python服务解析；没有第三方上传、遥测或云同步。",
    en: "2. When you click Analyze, the content goes over local HTTP to the Python service on this same machine for parsing; there is no third-party upload, telemetry, or cloud sync.",
  },
  privacyStep3: {
    "zh-CN": "3. 服务端只保留有界的结构投影（presence/type/kind等事实），留在内存中；原值不写入结果、导出或日志。临时解析内存不是安全擦除。",
    en: "3. The server keeps only a bounded structural projection (presence/type/kind facts) in memory; raw values never enter results, exports, or logs. Temporary parse memory is not secure erasure.",
  },
  privacyStep4: {
    "zh-CN": "4. 只有你主动点击复制/下载，证据才会离开本会话内存；下载文件与剪贴板内容不受“清空”影响。浏览器扩展或同用户恶意进程不在防护承诺内。",
    en: "4. Evidence leaves this session's memory only when you click Copy or Download; downloads and clipboard are not affected by Clear. Browser extensions or other processes running as your user are out of scope.",
  },
  privacyNote: {
    "zh-CN": "安装依赖与点击外链（如文档链接）会联网，均需你主动操作。偏好（语言/主题）是唯一持久化数据。",
    en: "Installing dependencies and clicking external links (e.g. documentation) touch the network, and only on your explicit action. Preferences (language/theme) are the only persisted data.",
  },
  helpTitle: { "zh-CN": "快速上手", en: "Quick start" },
  helpStep1: {
    "zh-CN": "选择一个模块：配置检查分析MCP服务器配置（JSON/TOML），流结束检查分析chat-completions SSE抓包。",
    en: "Pick a module: Config check analyzes MCP server configs (JSON/TOML); Stream end check analyzes chat-completions SSE captures.",
  },
  helpStep2: {
    "zh-CN": "从示例开始或粘贴/拖入自己的内容，点击分析。",
    en: "Start from a sample or paste/drop your own content, then click Analyze.",
  },
  helpStep3: {
    "zh-CN": "查看结论与每条发现的“已观察/含义/下一步”，然后复制或下载证据。",
    en: "Read the verdict and each finding's observed/meaning/next-step, then copy or download the evidence.",
  },
  qConfigMigration: { "zh-CN": "配置迁移后服务异常？", en: "Config changed and a service broke?" },
  qStreamEnded: { "zh-CN": "流突然结束，原因不明？", en: "Stream ended without a clear reason?" },
  qNormalCompare: { "zh-CN": "想看一条正常流长什么样？", en: "What does a healthy stream look like?" },
  qConfigDesc: {
    "zh-CN": "用样例检查传输冲突与迁移残留的结构痕迹。",
    en: "Check a sample for transport conflicts and migration residue.",
  },
  qStreamDesc: {
    "zh-CN": "样例：两种结束证据都缺失的截断流。",
    en: "Sample: a truncated stream missing both terminal signals.",
  },
  qNormalDesc: {
    "zh-CN": "正常结束：finish stop + [DONE] 的对照基线。",
    en: "Normal termination: a finish stop + [DONE] baseline to compare with.",
  },
  copy: { "zh-CN": "复制", en: "Copy" },
  copied: { "zh-CN": "已复制", en: "Copied" },
  copyFailed: {
    "zh-CN": "复制被浏览器拒绝或不可用；预览文本仍可手动选择复制。",
    en: "The browser refused or has no clipboard access; the preview text stays selectable below.",
  },
  shareTitle: { "zh-CN": "分享证据", en: "Share evidence" },
  shareNote: {
    "zh-CN": "包含结构事实（字段存在性/类型、事件序列），不含原文/命令/URL/token；分享前请先检查预览。",
    en: "Contains structural facts (field presence/type, event order) — never raw values, commands, URLs, or tokens. Review the preview before sharing.",
  },
  clearInProgress: {
    "zh-CN": "正在清空本机会话结果…",
    en: "Clearing local session results…",
  },
  clearSuccess: {
    "zh-CN": "本机会话结果已清空。",
    en: "Local session results cleared.",
  },
  clearUnconfirmed: {
    "zh-CN": "页面已清空，服务端清空未确认。你可以继续输入新内容，稍后重试清空。",
    en: "Cleared on this page; server-side clear is unconfirmed. You can keep typing — retry the clear later.",
  },
  retryClear: { "zh-CN": "重试清空", en: "Retry clear" },
  nextStepsLabel: { "zh-CN": "下一步", en: "Next step" },
  cannotProveLabel: { "zh-CN": "不能证明", en: "Does not prove" },
  observedLabel: { "zh-CN": "已观察", en: "Observed" },
  meaningLabel: { "zh-CN": "含义", en: "Meaning" },
  advanced: { "zh-CN": "高级：添加另一模块的证据（组合导出）", en: "Advanced: add the other module's evidence (combined export)" },
  clearStateAll: { "zh-CN": "清空全部（两模块）", en: "Clear both modules" },
  staleNotice: {
    "zh-CN": "输入已变更，以下结果已过期。",
    en: "Input changed; the result below is stale.",
  },

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
