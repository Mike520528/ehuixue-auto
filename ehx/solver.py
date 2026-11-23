# -*- coding: utf-8 -*-
"""用大模型给客观题作答。

为什么需要它：e会学 每次进卷会重排题号和选项顺序，写死 qid→答案 的表只在
某一次的快照上成立。真正稳定的做法是把「题干 + 选项」交给模型判断，
所以答案按「题干+选项」的内容指纹缓存，而不是按 qid。

用 OpenAI 兼容接口（默认 DeepSeek），只依赖标准库。
"""

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

# 题型编号 → 人话
QTYPE_NAME = {"1": "单选", "2": "多选", "3": "判断"}

SYSTEM_PROMPT = (
    "你是大学课程的答题助教。用户会给你若干道客观题，每题有题干和选项。\n"
    "规则：\n"
    "1. 单选题返回一个选项字母，例如 \"B\"。\n"
    "2. 多选题返回多个字母，用逗号分隔且按字母序，例如 \"A,C\"。\n"
    "3. 判断题的选项固定是 1=正确、2=错误，返回数字，例如 \"1\"。\n"
    "4. 只输出一个 JSON 对象，键是题号字符串，值是答案字符串；不要解释、不要 markdown 代码块。\n"
    "5. 不确定时也要给出你认为最可能的答案，不要留空。\n"
    "示例：{\"101\": \"B\", \"102\": \"A,C\", \"103\": \"2\"}"
)


class SolverError(RuntimeError):
    pass


def fingerprint(q):
    """题目内容指纹：题干 + 所有选项文本。题号和选项顺序变了指纹也不变。"""
    parts = [re.sub(r"\s+", " ", q["stem"]).strip()]
    for val, text in sorted(q["opts"], key=lambda x: str(x[1])):
        parts.append("{}|{}".format(val, re.sub(r"\s+", " ", text).strip()))
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()


def load_cache(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def save_cache(path, cache):
    if not path:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)


def _render(q):
    lines = ["Q{} [{}] {}".format(q["qid"], QTYPE_NAME.get(q["qtype"], "未知"), q["stem"])]
    for val, text in q["opts"]:
        lines.append("  {}. {}".format(val, text))
    return "\n".join(lines)


def build_messages(questions, course_hint=""):
    body = "\n\n".join(_render(q) for q in questions)
    head = "课程背景：{}\n\n".format(course_hint) if course_hint else ""
    user = "{}共 {} 题：\n\n{}".format(head, len(questions), body)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _post(url, payload, api_key, timeout=120):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(api_key),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise SolverError("接口返回 {}：{}".format(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise SolverError("连不上模型接口：{}".format(exc.reason)) from exc


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise SolverError("模型没返回 JSON：{}".format(text[:200]))
    return json.loads(m.group(0))


def _normalize(answer, q):
    """把模型给的答案规范成提交格式，并校验是不是合法选项。"""
    valid = {str(v) for v, _ in q["opts"]}
    a = str(answer).strip().upper().replace(" ", "")
    if q["qtype"] == "3":
        digits = re.findall(r"[12]", a)
        if digits:
            return digits[0]
        # 模型可能直接写「正确 / 错误」
        if re.search(r"正确|正确|对|是|TRUE|T\b", a):
            return "1"
        if re.search(r"错误|错|否|FALSE|F\b", a):
            return "2"
        raise SolverError("判断题答案不合法：{}".format(answer))
    letters = re.findall(r"[A-Z]", a)
    if not letters:
        raise SolverError("选择题答案不合法：{}".format(answer))
    picked = []
    for ch in letters:
        if ch not in valid:
            raise SolverError("答案 {} 不在选项 {} 里".format(ch, sorted(valid)))
        if ch not in picked:
            picked.append(ch)
    if q["qtype"] != "2" and len(picked) > 1:
        picked = picked[:1]
    return ",".join(sorted(picked))


def solve(questions, api_key=None, model=DEFAULT_MODEL, base=DEFAULT_BASE,
          cache_path=None, course_hint="", log=print, batch_size=12):
    """给一批题返回 {qid: 答案字符串}。

    先查缓存（按内容指纹），命中的不再问模型；剩下的分批问，答完写回缓存。
    """
    api_key = api_key or os.environ.get("EHUEXUE_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    cache = load_cache(cache_path)
    result, todo = {}, []

    for q in questions:
        fp = fingerprint(q)
        if fp in cache:
            result[q["qid"]] = cache[fp]
        else:
            todo.append(q)

    if todo and not api_key:
        raise SolverError(
            "有 {} 道题没命中缓存，但没给 API key："
            "设置环境变量 EHUEXUE_API_KEY（或 DEEPSEEK_API_KEY），或用 --api-key 传入".format(len(todo))
        )

    for i in range(0, len(todo), batch_size):
        chunk = todo[i:i + batch_size]
        payload = {
            "model": model,
            "messages": build_messages(chunk, course_hint),
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = _post(base.rstrip("/") + "/chat/completions", payload, api_key)
            text = resp["choices"][0]["message"]["content"]
            answers = _extract_json(text)
        except (SolverError, KeyError, ValueError) as exc:
            log("第 {}-{} 题请求失败：{}".format(i + 1, i + len(chunk), exc))
            continue

        for q in chunk:
            raw = answers.get(q["qid"]) or answers.get(str(q["qid"]))
            if raw is None:
                log("模型漏答 qid={}：{}".format(q["qid"], q["stem"][:40]))
                continue
            try:
                ans = _normalize(raw, q)
            except SolverError as exc:
                log("qid={} 答案无效：{}".format(q["qid"], exc))
                continue
            result[q["qid"]] = ans
            cache[fingerprint(q)] = ans
        log("已答 {}/{}".format(min(i + batch_size, len(todo)), len(todo)))

    save_cache(cache_path, cache)
    return result