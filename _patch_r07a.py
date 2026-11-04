import pathlib

# ---- R07: next_steps wording accuracy ----
p = pathlib.Path("agent_evidence_kit/next_steps.py")
s = p.read_text(encoding="utf-8")

old = '''    "DONE_WITHOUT_FINISH": {
        "observed": {
            "zh-CN": "收到[DONE]，但捕获中未出现finish_reason。",
            "en": "[DONE] was received, but no finish_reason appears in the capture.",
        },
        "meaning": {
            "zh-CN": "连接收尾正常，但provider未给出结束原因。",
            "en": "The connection closed normally, but the provider never reported a finish reason.",
        },
        "next_steps": {
            "zh-CN": "检查网关/SDK是否改写或过滤chunk结构，再抓一次对比。",
            "en": "Check whether your gateway/SDK rewrites or filters chunk structure, then capture again to compare.",
        },
        "does_not_prove": {
            "zh-CN": "不判断是provider、网关还是SDK的责任。",
            "en": "Responsibility between provider/gateway/SDK is not judged.",
        },
    },'''
new = '''    "DONE_WITHOUT_FINISH": {
        "observed": {
            "zh-CN": "捕获中观察到[DONE]，未观察到finish_reason。",
            "en": "The capture shows [DONE] and no finish_reason.",
        },
        "meaning": {
            "zh-CN": "就这段捕获而言，终止帧先于结束原因出现；工具无法看到捕获之外发生了什么。",
            "en": "Within this capture the termination frame arrived before any finish reason; the tool cannot see beyond the capture.",
        },
        "next_steps": {
            "zh-CN": "检查网关/SDK是否改写或过滤chunk结构，再抓一次对比。",
            "en": "Check whether your gateway/SDK rewrites or filters chunk structure, then capture again to compare.",
        },
        "does_not_prove": {
            "zh-CN": "不证明连接如何关闭，也不定位provider、网关或SDK的责任。",
            "en": "This does not prove how the connection closed and does not assign responsibility to the provider, gateway, or SDK.",
        },
    },'''
assert old in s
s = s.replace(old, new)

old = '''        "meaning": {
            "zh-CN": "该profile下结束证据齐全：provider报告了结束原因，应用层终止帧也到达。",
            "en": "Terminal evidence is complete for this profile: the provider reported a finish reason and the application-level termination frame arrived.",
        },'''
new = '''        "meaning": {
            "zh-CN": "就本捕获而言结束证据齐全：观察到正常finish，也收到[DONE]。",
            "en": "Terminal evidence is complete for this capture: a normal finish was observed and [DONE] was received.",
        },'''
assert old in s
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("next_steps accuracy patched")
