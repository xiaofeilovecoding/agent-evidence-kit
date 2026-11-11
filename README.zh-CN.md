# Agent Evidence Kit（Agent 证据集）

[English](README.md) · [简体中文](README.zh-CN.md)

**分享证据，保留原文。**

把 MCP 配置和已捕获的 chat-completions SSE 流转成可附在 Issue 中的结构证据卡。在本机检查，预览后再分享，无需上传原始输入。

## 为什么用它？

- **分享有用事实，保留私密原值。** 证据包含字段是否存在、字段类型和流事件顺序；不包含命令、URL、凭据、生成文本或工具参数的原值。
- **不调用模型，也不需要 API Key。** 对你提供的内容做确定性检查，提供固定中英双语建议，并明确每条发现能说明什么、不能证明什么。
- **先检查，再分享。** Markdown / JSON 导出先预览，再复制或下载；清空操作会明确说明本机服务是否已确认移除会话结果。
- **兼顾使用者与维护者。** 本地网页和 CLI 使用相同证据核心，中英双语材料可直接附在 Issue 中；无遥测、不上传第三方。

![配置证据卡](docs/screenshots/zh-config-light.png)

## 它做什么

一个本地工具内含两个有界检查器：

- **配置检查** — 粘贴或拖入 agent 的 MCP 服务器配置（`.json` / `.toml`，≤256KiB）。得到仅结构层面的证据卡：每个服务的传输事实（presence/type，绝不含值）、传输冲突、迁移残留、字段类型问题；每条发现附*已观察 / 含义 / 下一步 / 不能证明*四段说明。
- **流结束检查** — 粘贴或拖入抓包的 chat-completions SSE 流（`.sse` / `.txt`，≤8MiB）。得到结束证据：是否观察到 `finish_reason`、是否收到 `[DONE]`、流被截断、`length`/`content_filter` 停止、上游错误、`[DONE]` 后残留数据——与正常结束样例左右对照，事件序列按 50 条/页分页。

![流证据与正常样例对照](docs/screenshots/zh-stream-dark.png)

全部在同一个工作区内完成（浅色/深色/跟随系统主题，中文或 English）：点击任一示例即可体验真实诊断链——无需 API Key、不访问外部网络。

## 快速上手（从源码检出运行）

```bash
git clone https://github.com/xiaofeilovecoding/agent-evidence-kit
cd agent-evidence-kit

# Windows (PowerShell)
py -3 -m venv .venv                       # 需要 Python 3.11+
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[web]"
python -m agent_evidence_kit web

# macOS / Linux
python3 -m venv .venv                     # 需要 Python 3.11+
. .venv/bin/activate
python -m pip install -e ".[web]"
python -m agent_evidence_kit web
```

Web UI 在 `http://127.0.0.1:7411` 打开，**无需 Node.js**——界面已预构建并随包分发。包正式发布到 PyPI 后，`pip install "agent-evidence-kit[web]"` 将是最快入口；在此之前以上源码方式为受支持安装。

CLI 与 Web 使用相同核心和退出码：

```bash
python -m agent_evidence_kit config --input config.toml --format md --lang en
python -m agent_evidence_kit stream --input capture.sse --format json
python -m agent_evidence_kit stream demo --case finish-only
```

## 把正常流和异常流放在一起比较

两份捕获流，一条命令——比较先展示终态差异，再展开其余诊断：

```bash
python -m agent_evidence_kit stream compare --baseline normal.sse --candidate failed.sse --format md
```

两份合成捕获流的真实输出（正常结束 vs 上游错误；因观察到差异退出码为 1）：

```markdown
# 流结束比较：正常 vs 异常

- 基线（正常）: NORMAL_TERMINATION · finish_reason（受控枚举）: stop · 是否见 [DONE]: 有
- 候选（待比较）: UPSTREAM_ERROR · finish_reason（受控枚举）: none（未观察到 finish） · 是否见 [DONE]: 无

## 终态差异

- **终态**: NORMAL_TERMINATION → UPSTREAM_ERROR
  - NORMAL_TERMINATION: 观察到正常finish且收到[DONE]：本profile下结束证据完整。这不代表答案正确或完整。
  - UPSTREAM_ERROR: 流中包含上游错误事件（错误正文不回显）。
- **判定**: NORMAL_TERMINATION → NEEDS_REVIEW

## 诊断差异（逐步展开）

- **finish_reason（受控枚举）**: stop → none（未观察到 finish）
- **是否见 [DONE]**: 有 → 无
- **终态事件位置**: @event2 → 未观察到
- **诊断代码**: NORMAL_TERMINATION → UPSTREAM_ERROR
  - [候选] UPSTREAM_ERROR: 流中包含上游错误事件（错误正文不回显）。
- **事件数**: 4 → 2

> 以上为两侧捕获流之间的观察差异；本比较不证明上游根因。
```

比较只读取两侧的结构投影：事件数据、生成文本、工具参数、未知原因原文、地址、会话标识和文件名都不会进入输出；未知 `finish_reason` 归入 `other` 类别而不回显原文。Web 端在「流结束检查」页有同样的比较（展开「正常 vs 异常比较」，粘贴两侧或载入两份合成样例后比较并分享）；静态展示页继续展示单份样例卡，并明确标注比较需在本地 CLI / Web 中使用。

## 它回答三个问题

1. **“配置改完服务就不工作了”** — 检查配置中的传输冲突与迁移残留；每条发现说明已观察什么、含义、下一步怎么做、不能证明什么。
2. **“流突然结束，原因不明”** — 检查抓包里有没有 `finish`、有没有 `[DONE]`、还是两者皆无；证据卡把两个独立信号分开呈现，不靠猜。
3. **“一条正常的流长什么样”** — 每个结果都有正常结束样例可对照（配置模块也提供普通结构样例）。

所有样例都是合成 fixture，走与你自己的输入完全相同的真实核心——不伪造任何结果。

## 证据包含什么——从不包含什么

证据卡与导出**只包含**：字段 presence/type、事件顺序与类型（chunk/finish/done）、稳定的发现码与固定双语解释及下一步建议、固定的范围声明。

**从不包含**：服务名、命令、URL、env 名或值、模型输出文本、tool 参数、id、哈希、原始错误或堆栈。即便它显示的结构事实（服务数、传输类型、事件数）也值得在分享前看一眼——预览即复制/下载的字节内容。

## 隐私：本机处理，可核查

- 原文只存在于你正在使用的输入控件中（这是预期显示），以及本机临时解析内存。本地服务只保留有界的结构投影在内存中；临时内存不是安全擦除。
- 无第三方上传、无遥测、无远程字体。唯一持久化数据是你的语言/主题偏好。
- 应用内 **“本机处理”** 按钮可打开四步数据路径面板，核实这句话而不是相信徽章。
- 复制/下载是你主动离开会话的动作——下载文件与剪贴板不受“清空”影响。
- 安装依赖与打开文档链接会联网，均需你主动操作。

## 不适用的场景

- 对运行中的 agent 做实时调试：本工具不发起任何对外连接、不发送请求，也不读取你提供的文件之外的日志。
- 判断答案是否正确，或供应商兼容性。
- 自动修复：发现附带人工下一步说明；你的配置绝不会被修改。

## 反馈

问题与讨论请到仓库
[issue tracker](https://github.com/xiaofeilovecoding/agent-evidence-kit/issues)。安全相关报告见 [SECURITY.md](SECURITY.md)——请勿以公开 issue 提交。

## 开发

```bash
python -m unittest tests.test_config_core tests.test_stream_core tests.test_next_steps -v
pip install -e ".[web]" httpx
python -m unittest tests.test_web tests.test_clear_race tests.test_export_races -v
python scripts/build_frontend.py          # 锁定 npm ci + 双构建 + 资产同步
python -m unittest tests.test_browser tests.test_review_fixes tests.test_public_ready -v
python scripts/capture_screenshots.py     # 从生产构建重新生成 README 截图
```

浏览器测试需要 Playwright Chromium（`pip install playwright && python -m playwright install chromium`，或设置 `PLAYWRIGHT_BROWSERS_PATH` 指向已有缓存）。见 [CONTRIBUTING.md](CONTRIBUTING.md)。English: [README.md](README.md)。

## 状态与许可

版本 0.2.0，实验性候选。MIT — 见 [LICENSE](LICENSE)。
