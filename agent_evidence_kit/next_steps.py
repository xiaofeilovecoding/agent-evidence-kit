"""Versioned, fixed bilingual next-step guidance for every finding code.

This is fixed knowledge about what each structural finding means and what
a human can do next. It is NOT a new judgment layer: suggestions never
claim root causes, verified compatibility/authentication, or one-click
fixes, and they never contain user text, URLs, commands, env names/values,
or paths. UI and Markdown exports share this single mapping.

Schema: NEXT_STEPS_SCHEMA_VERSION = 1. Unknown codes fall back to a safe
generic entry; the mapping is keyed by the finding codes the cores
already emit.
"""
from __future__ import annotations

NEXT_STEPS_SCHEMA_VERSION = 1

LANGUAGES = ("zh-CN", "en")

# Each entry: observed / meaning / next_steps / does_not_prove, zh-CN + en.
# Field names are schema-stable; values are fixed constants of this tool.
NEXT_STEPS: dict[str, dict[str, dict[str, str]]] = {
    # ---- config module codes ----
    "AMBIGUOUS_TRANSPORT": {
        "observed": {
            "zh-CN": "同一服务同时声明了command与url。",
            "en": "One service declares both command and url.",
        },
        "meaning": {
            "zh-CN": "两种传输入口并存，工具无法从结构判断哪一项实际生效。",
            "en": "Two transport entries coexist; structure alone cannot tell which one takes effect.",
        },
        "next_steps": {
            "zh-CN": "查阅你当前客户端的文档，确认它读取哪个字段，人工移除另一项前先备份配置。",
            "en": "Check your client's documentation for which field it reads; back up the config before removing the other field by hand.",
        },
        "does_not_prove": {
            "zh-CN": "不能认定command或url中哪一项实际生效，也不会自动修改配置。",
            "en": "This tool cannot tell which entry actually takes effect and never edits your config.",
        },
    },
    "POSSIBLE_TRANSPORT_RESIDUE": {
        "observed": {
            "zh-CN": "url字段与command/args/env/env_vars字段同时出现。",
            "en": "A url field appears together with command/args/env/env_vars fields.",
        },
        "meaning": {
            "zh-CN": "可能是从另一传输方式迁移后的残留字段，也可能是刻意共存。",
            "en": "These may be residue from a migrated transport, or an intentional coexistence.",
        },
        "next_steps": {
            "zh-CN": "备份配置后人工核对每个字段是否仍被使用，再决定是否清理；工具不会自动删除。",
            "en": "Back up the config, review whether each field is still used, then clean up by hand; the tool never deletes fields.",
        },
        "does_not_prove": {
            "zh-CN": "不能确认字段是否残留，不评估泄露风险，不自动清理。",
            "en": "This tool cannot confirm residue, does not assess exposure, and does not clean up automatically.",
        },
    },
    "INVALID_FIELD_TYPE": {
        "observed": {
            "zh-CN": "某个已知字段的类型或空值不符合结构要求。",
            "en": "A known field has a wrong type or an invalid empty value.",
        },
        "meaning": {
            "zh-CN": "command/url需非空字符串，args/env_vars需字符串列表，env/headers需字符串映射，type/transport需字符串。",
            "en": "command/url must be non-empty strings, args/env_vars string lists, env/headers string maps, type/transport strings.",
        },
        "next_steps": {
            "zh-CN": "按上述类型要求人工修正该字段的写法，保存前先备份。",
            "en": "Fix the field's shape to match the required type by hand; back up before saving.",
        },
        "does_not_prove": {
            "zh-CN": "修正后仍需实际运行验证；工具不验证字段值内容。",
            "en": "A corrected shape still needs a real run to verify; values are never validated.",
        },
    },
    "TRANSPORT_CONFLICT": {
        "observed": {
            "zh-CN": "显式type与transport字段指向不同传输方式。",
            "en": "The explicit type and transport fields point to different transports.",
        },
        "meaning": {
            "zh-CN": "两个显式声明互相矛盾，客户端行为取决于其读取顺序。",
            "en": "Two explicit declarations contradict each other; behavior depends on the client's read order.",
        },
        "next_steps": {
            "zh-CN": "对照客户端文档统一两个声明后人工保存。",
            "en": "Align the two declarations with your client's documentation and save by hand.",
        },
        "does_not_prove": {
            "zh-CN": "不能判断客户端实际采用哪个声明。",
            "en": "This tool cannot tell which declaration the client adopts.",
        },
    },
    "NOT_VALIDATED": {
        "observed": {
            "zh-CN": "仅完成结构检查。",
            "en": "Only the structure check ran.",
        },
        "meaning": {
            "zh-CN": "未知枚举/未知字段不回显，客户端版本与运行兼容性未检查。",
            "en": "Unknown enums/fields are not echoed; client versions and runtime compatibility are unchecked.",
        },
        "next_steps": {
            "zh-CN": "把结构核对结果当作清单，结合一次真实运行验证。",
            "en": "Treat the structure result as a checklist and verify with one real run.",
        },
        "does_not_prove": {
            "zh-CN": "不证明配置可正常运行或安全。",
            "en": "This does not prove the config runs correctly or is safe.",
        },
    },
    "INVALID_STRUCTURE": {
        "observed": {
            "zh-CN": "根结构不符合要求（缺少mcp_servers/mcpServers或类型不对）。",
            "en": "The root shape is invalid (missing mcp_servers/mcpServers or wrong types).",
        },
        "meaning": {
            "zh-CN": "文档被拒绝了，未产出任何服务投影。",
            "en": "The document was rejected; no service projection was produced.",
        },
        "next_steps": {
            "zh-CN": "核对根对象键名与嵌套结构后重试。",
            "en": "Check the root key names and nesting, then retry.",
        },
        "does_not_prove": {
            "zh-CN": "拒绝不表示其余部分有或没有问题。",
            "en": "Rejection says nothing about the rest of the file.",
        },
    },
    "DUPLICATE_KEY": {
        "observed": {
            "zh-CN": "存在重复键。",
            "en": "A duplicate key was found.",
        },
        "meaning": {
            "zh-CN": "重复键会因解析器而异，结果不可靠，已拒绝解析。",
            "en": "Duplicate keys parse differently across parsers, so the result would be unreliable; parsing was rejected.",
        },
        "next_steps": {
            "zh-CN": "删除或合并重复键后重试。",
            "en": "Remove or merge the duplicate keys, then retry.",
        },
        "does_not_prove": {
            "zh-CN": "不能指认重复键的位置（不回显原值）。",
            "en": "The tool does not echo the key itself.",
        },
    },
    "LIMIT_EXCEEDED": {
        "observed": {
            "zh-CN": "超出冻结的结构限制（256KiB/深度16/32服务或8MiB/128KiB行/256KiB事件/10000事件/JSON深度16）。",
            "en": "A frozen structural limit was exceeded (256KiB/depth16/32 services or 8MiB/128KiB line/256KiB event/10000 events/JSON depth 16).",
        },
        "meaning": {
            "zh-CN": "超出上限的输入被拒绝，不产出部分结果。",
            "en": "Over-limit input is rejected; no partial result is produced.",
        },
        "next_steps": {
            "zh-CN": "拆分输入为更小的文档/捕获后分别检查。",
            "en": "Split the input into smaller documents/captures and check them separately.",
        },
        "does_not_prove": {
            "zh-CN": "限制不是安全性判断，仅是解析边界。",
            "en": "Limits are parse boundaries, not security verdicts.",
        },
    },
    "INVALID_SYNTAX": {
        "observed": {
            "zh-CN": "文本无法按所选格式解析。",
            "en": "The text failed to parse in the selected format.",
        },
        "meaning": {
            "zh-CN": "多为JSON/TOML书写错误或格式选择不匹配。",
            "en": "Usually a JSON/TOML typo or a mismatched format choice.",
        },
        "next_steps": {
            "zh-CN": "确认格式选择（JSON/TOML）与内容一致后重试。",
            "en": "Confirm the format choice (JSON/TOML) matches the content, then retry.",
        },
        "does_not_prove": {
            "zh-CN": "不回显语法错误细节。",
            "en": "Syntax details are never echoed.",
        },
    },
    "INVALID_ENCODING": {
        "observed": {
            "zh-CN": "输入不是有效UTF-8文本。",
            "en": "The input is not valid UTF-8 text.",
        },
        "meaning": {
            "zh-CN": "编码不一致会导致解析结果不可靠。",
            "en": "Inconsistent encoding makes parsing unreliable.",
        },
        "next_steps": {
            "zh-CN": "以UTF-8重新导出/保存文件后重试。",
            "en": "Re-export/save the file as UTF-8, then retry.",
        },
        "does_not_prove": {
            "zh-CN": "不猜测原编码。",
            "en": "The original encoding is not guessed.",
        },
    },
    "UNSUPPORTED_FORMAT": {
        "observed": {
            "zh-CN": "文件扩展名不在支持范围（.json/.toml或.sse/.txt）。",
            "en": "The file extension is outside the supported set (.json/.toml or .sse/.txt).",
        },
        "meaning": {
            "zh-CN": "按扩展名拒绝，未读取内容。",
            "en": "Rejected by extension; the content was not read.",
        },
        "next_steps": {
            "zh-CN": "改用受支持扩展名后再导入。",
            "en": "Rename to a supported extension and import again.",
        },
        "does_not_prove": {
            "zh-CN": "与内容是否有效无关。",
            "en": "This says nothing about the content's validity.",
        },
    },
    "INPUT_TOO_LARGE": {
        "observed": {
            "zh-CN": "输入超过大小上限（配置256KiB/流8MiB）。",
            "en": "The input exceeds the size limit (config 256KiB / stream 8MiB).",
        },
        "meaning": {
            "zh-CN": "为保护本机内存，超限输入直接拒绝。",
            "en": "Over-limit input is rejected to protect local memory.",
        },
        "next_steps": {
            "zh-CN": "裁剪到相关片段后重试。",
            "en": "Trim to the relevant portion and retry.",
        },
        "does_not_prove": {
            "zh-CN": "大小限制不是内容判断。",
            "en": "The size limit is not a content judgment.",
        },
    },
    "INPUT_UNREADABLE": {
        "observed": {
            "zh-CN": "无法读取输入文件。",
            "en": "The input file could not be read.",
        },
        "meaning": {
            "zh-CN": "文件缺失、无权限或不是普通文件；路径永不回显。",
            "en": "Missing, no permission, or not a regular file; paths are never echoed.",
        },
        "next_steps": {
            "zh-CN": "确认文件存在且可读后重试。",
            "en": "Confirm the file exists and is readable, then retry.",
        },
        "does_not_prove": {
            "zh-CN": "与文件内容无关。",
            "en": "This says nothing about the content.",
        },
    },
    # ---- stream module codes ----
    "NORMAL_TERMINATION": {
        "observed": {
            "zh-CN": "观察到正常finish且收到[DONE]。",
            "en": "A normal finish was observed and [DONE] was received.",
        },
        "meaning": {
            "zh-CN": "就本捕获而言结束证据齐全：观察到正常finish，也收到[DONE]。",
            "en": "Terminal evidence is complete for this capture: a normal finish was observed and [DONE] was received.",
        },
        "next_steps": {
            "zh-CN": "可作为“流完整走到结束”的证据粘贴给协助者；若答案本身有问题，请继续查其他证据。",
            "en": "Share it as evidence that the stream reached a proper end; if the answer itself is wrong, look at other evidence.",
        },
        "does_not_prove": {
            "zh-CN": "不证明答案正确、完整或内容安全。",
            "en": "This does not prove the answer is correct, complete, or safe.",
        },
    },
    "FINISH_WITHOUT_DONE": {
        "observed": {
            "zh-CN": "观察到finish_reason，但捕获中未出现[DONE]。",
            "en": "A finish_reason was observed, but no [DONE] appears in the capture.",
        },
        "meaning": {
            "zh-CN": "应用层终止标记缺失；可能是抓取不完整，也可能是上游/网关确实未发。",
            "en": "The application-level termination marker is missing; the capture may be incomplete or the upstream/gateway never sent it.",
        },
        "next_steps": {
            "zh-CN": "重新抓一次完整流对比；若仍缺失，把本卡与捕获起止说明一起发给协助者。",
            "en": "Capture the stream again and compare; if still missing, share this card together with the capture boundaries.",
        },
        "does_not_prove": {
            "zh-CN": "无法定位是哪一跳吞掉了标记，也不代表数据丢失。",
            "en": "The tool cannot tell which hop dropped the marker, and this does not mean data was lost.",
        },
    },
    "DONE_WITHOUT_FINISH": {
        "observed": {
            "zh-CN": "收到[DONE]，但捕获中未出现finish_reason。",
            "en": "[DONE] was received, but no finish_reason appears in the capture.",
        },
        "meaning": {
            "zh-CN": "就这段捕获而言，终止帧先于结束原因出现；工具无法看到捕获之外发生了什么。",
            "en": "Within this capture the termination frame arrived before any finish reason; the tool cannot see beyond the capture.",
        },
        "next_steps": {
            "zh-CN": "检查网关/SDK是否改写或过滤了chunk结构，再抓一次对比。",
            "en": "Check whether your gateway/SDK rewrites or filters chunk structure, then capture again to compare.",
        },
        "does_not_prove": {
            "zh-CN": "不证明连接如何关闭，也不定位provider、网关或SDK的责任。",
            "en": "This does not prove how the connection closed and does not assign responsibility to the provider, gateway, or SDK.",
        },
    },
    "NO_TERMINAL_EVIDENCE": {
        "observed": {
            "zh-CN": "有数据事件，但既无finish也无[DONE]。",
            "en": "Data events exist, but neither a finish nor [DONE] was seen.",
        },
        "meaning": {
            "zh-CN": "流在两种结束证据都缺失的情况下中断。",
            "en": "The stream ended with both kinds of terminal evidence missing.",
        },
        "next_steps": {
            "zh-CN": "检查客户端是否在流结束前断开/超时，并记录当时的网络与错误日志一并分享。",
            "en": "Check whether the client disconnected/timed out before the stream ended, and share the network/error logs from that moment.",
        },
        "does_not_prove": {
            "zh-CN": "EOF本身不能说明中断原因。",
            "en": "EOF alone does not explain why the stream stopped.",
        },
    },
    "NO_DATA": {
        "observed": {
            "zh-CN": "没有可分派的数据事件。",
            "en": "No dispatchable data events.",
        },
        "meaning": {
            "zh-CN": "捕获为空或只包含注释/心跳。",
            "en": "The capture is empty or contains only comments/heartbeats.",
        },
        "next_steps": {
            "zh-CN": "确认抓取起点与过滤条件，重新抓取。",
            "en": "Verify the capture start point and filters, then capture again.",
        },
        "does_not_prove": {
            "zh-CN": "不代表上游无响应。",
            "en": "This does not mean the upstream sent nothing.",
        },
    },
    "UNTERMINATED_EVENT": {
        "observed": {
            "zh-CN": "流在事件中途结束：末尾data块没有空行分派。",
            "en": "The stream ends mid-event: the trailing data block has no blank-line dispatch.",
        },
        "meaning": {
            "zh-CN": "SSE以空行结束一个事件；没有空行的尾部内容不计入已接收事件。",
            "en": "SSE ends an event with a blank line; trailing content without one does not count as received.",
        },
        "next_steps": {
            "zh-CN": "抓取可能被截断：延长抓取窗口或检查客户端是否提前退出，再对比一次。",
            "en": "The capture may be truncated: extend the capture window or check for early client exit, then compare.",
        },
        "does_not_prove": {
            "zh-CN": "尾部内容不能当作已收到的[DONE]或事件。",
            "en": "The tail cannot be treated as a received event or [DONE].",
        },
    },
    "LIMIT_STOP": {
        "observed": {
            "zh-CN": "finish_reason=length。",
            "en": "finish_reason=length.",
        },
        "meaning": {
            "zh-CN": "生成因长度上限停止，属于非正常结束证据。",
            "en": "Generation stopped at a length limit; this is non-normal terminal evidence.",
        },
        "next_steps": {
            "zh-CN": "人工核对当前模型的输出上限设置（max_tokens/上下文预算）后调整重试。",
            "en": "Review the model's output-limit settings (max_tokens/context budget) and adjust by hand.",
        },
        "does_not_prove": {
            "zh-CN": "不是网络故障的证据，也不判断内容质量。",
            "en": "This is not evidence of a network fault and does not judge content quality.",
        },
    },
    "FILTER_STOP": {
        "observed": {
            "zh-CN": "finish_reason=content_filter。",
            "en": "finish_reason=content_filter.",
        },
        "meaning": {
            "zh-CN": "生成被内容过滤停止。",
            "en": "Generation stopped via a content filter.",
        },
        "next_steps": {
            "zh-CN": "结合你的输入与供应商策略人工判断；必要时更换提示重试。",
            "en": "Review your input against the provider's policy and adjust the prompt if needed.",
        },
        "does_not_prove": {
            "zh-CN": "工具不评估具体内容，不判断策略是否恰当。",
            "en": "The tool does not evaluate the content or the policy decision.",
        },
    },
    "UPSTREAM_ERROR": {
        "observed": {
            "zh-CN": "流中包含错误事件（错误正文不回显）。",
            "en": "The stream contains an error event (the error body is never echoed).",
        },
        "meaning": {
            "zh-CN": "provider/网关在流内报告了错误。",
            "en": "The provider/gateway reported an error inside the stream.",
        },
        "next_steps": {
            "zh-CN": "在你的网关/供应商控制台按时间点查对应错误日志（正文留在你那边）。",
            "en": "Look up the corresponding error in your gateway/provider console by time (the body stays with you).",
        },
        "does_not_prove": {
            "zh-CN": "工具不回显也不解释错误正文。",
            "en": "The tool neither echoes nor interprets the error body.",
        },
    },
    "DATA_AFTER_DONE": {
        "observed": {
            "zh-CN": "[DONE]之后仍收到已分派的数据事件。",
            "en": "Dispatched data arrived after [DONE].",
        },
        "meaning": {
            "zh-CN": "终止帧后出现残留数据，常见于网关复用/拼接流。",
            "en": "Residual data follows the terminal frame, often from gateway reuse/splicing.",
        },
        "next_steps": {
            "zh-CN": "检查网关/代理是否复用连接或拼接了多次响应。",
            "en": "Check whether your gateway/proxy reuses connections or splices multiple responses.",
        },
        "does_not_prove": {
            "zh-CN": "不判断残留数据的来源。",
            "en": "The source of the residual data is not judged.",
        },
    },
    "UNSUPPORTED_PROFILE": {
        "observed": {
            "zh-CN": "事件结构不符合chat-completions-v1支持范围。",
            "en": "An event does not match the supported chat-completions-v1 shape.",
        },
        "meaning": {
            "zh-CN": "多choices/非0 index/未知结构等，本工具不猜测兼容。",
            "en": "Multiple choices, non-zero index, or unknown structures; this tool does not guess compatibility.",
        },
        "next_steps": {
            "zh-CN": "确认捕获是否来自其他API形态；如是，另用对应工具/人工分析。",
            "en": "Check whether the capture uses another API shape; if so, analyze it with the matching tool or by hand.",
        },
        "does_not_prove": {
            "zh-CN": "不评估其他API形态的正确性。",
            "en": "The correctness of other API shapes is not evaluated.",
        },
    },
    "UNSUPPORTED_EVENT": {
        "observed": {
            "zh-CN": "出现本profile不支持的SSE event类型（值不回显）。",
            "en": "An SSE event type outside this profile was seen (its value is not echoed).",
        },
        "meaning": {
            "zh-CN": "该事件被跳过计数，不参与结束判定。",
            "en": "The event is skipped but still counted; it does not drive the verdict.",
        },
        "next_steps": {
            "zh-CN": "确认你的网关是否注入了自定义事件类型。",
            "en": "Check whether your gateway injects custom event types.",
        },
        "does_not_prove": {
            "zh-CN": "不评估自定义事件的语义。",
            "en": "The semantics of custom events are not evaluated.",
        },
    },
    "UNSUPPORTED_FINISH": {
        "observed": {
            "zh-CN": "finish_reason不是受支持枚举（原值不回显）。",
            "en": "finish_reason is not one of the supported values (the raw value is not echoed).",
        },
        "meaning": {
            "zh-CN": "可能是新/私有的结束原因。",
            "en": "This may be a new or private finish reason.",
        },
        "next_steps": {
            "zh-CN": "在抓包原文中人工查看该值（原文在你那边），对照provider文档。",
            "en": "Look at the value in your own capture text and compare it with the provider's documentation.",
        },
        "does_not_prove": {
            "zh-CN": "工具不猜测未列出的结束原因含义。",
            "en": "The tool does not guess the meaning of unlisted finish reasons.",
        },
    },
    "INVALID_EVENT_JSON": {
        "observed": {
            "zh-CN": "已分派的事件data不是合法JSON。",
            "en": "A dispatched event's data is not valid JSON.",
        },
        "meaning": {
            "zh-CN": "该事件被标记错误，可能来自损坏的捕获或非JSON流。",
            "en": "The event is flagged; the capture may be damaged or the stream may not be JSON.",
        },
        "next_steps": {
            "zh-CN": "确认抓取完整且来自chat-completions流；截断/转码常会造成此类事件。",
            "en": "Confirm the capture is complete and from a chat-completions stream; truncation/transcoding often causes this.",
        },
        "does_not_prove": {
            "zh-CN": "不回显事件内容。",
            "en": "Event content is never echoed.",
        },
    },
    # stream input errors share names with config; entries above cover them.
}

# No-finding / positive states that are not per-finding codes.
STATE_NEXT_STEPS: dict[str, dict[str, dict[str, str]]] = {
    "config": {
        "STRUCTURE_CHECK_COMPLETE": {
            "observed": {
                "zh-CN": "已知字段的presence/type符合结构要求。",
                "en": "Known fields' presence/types match the structural requirements.",
            },
            "meaning": {
                "zh-CN": "没有结构层面的发现，但仅此而已。",
                "en": "No structural findings — and that is all.",
            },
            "next_steps": {
                "zh-CN": "结合一次真实运行验证；如需分享，说明这是结构检查结果。",
                "en": "Verify with one real run; when sharing, state that this is a structure-check result.",
            },
            "does_not_prove": {
                "zh-CN": "不表示配置安全、可运行或兼容。",
                "en": "This does not mean the config is safe, runnable, or compatible.",
            },
        },
    },
    "stream": {},
}

_GENERIC: dict[str, dict[str, str]] = {
    "observed": {
        "zh-CN": "观察到一项结构发现。",
        "en": "A structural finding was observed.",
    },
    "meaning": {
        "zh-CN": "该发现基于固定结构规则。",
        "en": "The finding is based on fixed structural rules.",
    },
    "next_steps": {
        "zh-CN": "结合预览中的结构事实人工核对。",
        "en": "Review the structural facts in the preview by hand.",
    },
    "does_not_prove": {
        "zh-CN": "不构成根因判断或运行验证。",
        "en": "This is not a root-cause verdict or a runtime check.",
    },
}


def next_steps_for(code: str, language: str) -> dict[str, str] | None:
    """Fixed bilingual guidance for one finding code.

    Unknown codes get the safe generic entry (no echo of the unknown value).
    """
    if language not in LANGUAGES:
        raise KeyError(language)
    entry = NEXT_STEPS.get(code)
    if entry is None:
        entry = _GENERIC
    return {
        "observed": entry["observed"][language],
        "meaning": entry["meaning"][language],
        "next_steps": entry["next_steps"][language],
        "does_not_prove": entry["does_not_prove"][language],
    }


def state_next_steps(module: str, state: str, language: str) -> dict[str, str] | None:
    module_map = STATE_NEXT_STEPS.get(module, {})
    entry = module_map.get(state)
    if entry is None:
        return None
    return {
        "observed": entry["observed"][language],
        "meaning": entry["meaning"][language],
        "next_steps": entry["next_steps"][language],
        "does_not_prove": entry["does_not_prove"][language],
    }
