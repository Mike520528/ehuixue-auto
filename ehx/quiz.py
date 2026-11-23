"""刷练习 / 考试。

四步：
    1. grab_papers  —— 对每个练习/考试 eid 调 joinquiz 拿 seid，再拉卷面 HTML
    2. parse        —— 从 HTML 里解出 qid / 题型 / 题干 / 选项
    3. build_plan   —— 把题目交给解题器（默认大模型）拼成提交用的 plan
    4. submit_plan  —— 调 examsheet 一次性交卷

为什么不靠 qid 答案表：e会学 每次进卷会重排题号和选项顺序，写死的
`{qid: "A"}` 换一次快照就可能对错题。默认走 ehx.solver 按「题干+选项」
的内容指纹解题并缓存；answers.py 里的老表只在 `solve_fn=None` 时兜底用。
"""

import json

from .answers import EXAM, PRACTISE
from .dom import JS_GRAB_PAPER, JS_SUBMIT_PAPER
from .parse_quiz import parse

# 默认认为 eid 473305 是考试卷，其余是练习。换课程用 exam_eids 覆盖。
DEFAULT_EXAM_EIDS = ("473305",)


def grab_papers(page, eids, wait_ms=400, log=print):
    """逐个 eid 抓卷面，返回 {eid: {seid, html}}；抓失败的记 {eid: {err: ...}}。"""
    papers = {}
    for eid in eids:
        try:
            r = page.evaluate(JS_GRAB_PAPER, str(eid))
        except Exception as exc:  # noqa: BLE001
            papers[eid] = {"err": str(exc)}
            log("{} 抓取异常：{}".format(eid, exc))
            continue
        if r.get("stage") == "ok":
            papers[eid] = {"seid": r["seid"], "html": r["html"]}
            log("{} 卷面 {} 字节，seid={}".format(eid, r["len"], r["seid"]))
        else:
            papers[eid] = {"err": r}
            log("{} 进卷失败：status={} msg={}".format(eid, r.get("st"), r.get("msg")))
        page.wait_for_timeout(wait_ms)
    return papers


def build_plan(papers, exam_eids=DEFAULT_EXAM_EIDS, solve_fn=None,
               course_hint="", log=print):
    """把卷面和答案合成提交计划：{eid: {seid, ans: {qid: {ans, qtype, qid}}}}。

    solve_fn(questions, course_hint) -> {qid: "A"} 是解题器；给了就全交给它（推荐）。
    没给则退回 answers.py 的老表，按 qid 查——换过卷子后题号可能错位，只适合复核旧快照。
    两条路都没答案的题会兜底成固定值（单选 A、判断 1）并在日志里报出来。
    """
    exam_set = {str(e) for e in exam_eids}
    parsed = {}
    flat = []          # [(eid, question)]
    for eid, paper in papers.items():
        if "html" not in paper:
            continue
        qs = parse(paper["html"])
        parsed[eid] = qs
        flat.extend((eid, q) for q in qs)

    if not flat:
        log("没有解析出任何题目（卷面里可能只有主观题，或选择器不匹配）")
        return {}

    if solve_fn is not None:
        log("交给解题器：共 {} 题".format(len(flat)))
        answers = solve_fn([q for _, q in flat], course_hint)
    else:
        log("未提供解题器，退回 qid 答案表（注意：卷子重排后题号可能已错位）")
        answers = {}
        for eid, q in flat:
            table = EXAM if str(eid) in exam_set else PRACTISE
            if q["qid"] in table:
                answers[q["qid"]] = table[q["qid"]]

    plan, missing = {}, []
    for eid, q in flat:
        ans = answers.get(q["qid"])
        if ans is None:
            missing.append((eid, q["qid"], q["qtype"], q["stem"][:40]))
            ans = "A" if q["qtype"] in ("1", "2") else "1"
        plan.setdefault(eid, {"seid": papers[eid]["seid"], "ans": {}})
        plan[eid]["ans"][q["qid"]] = {"ans": ans, "qtype": q["qtype"], "qid": int(q["qid"])}

    if missing:
        log("有 {} 道题没拿到答案（已用兜底值，交上去大概率错）".format(len(missing)))
        for m in missing:
            log("  缺 {} qid={} 题型={} {}".format(*m))
    return plan


def submit_plan(page, plan, exam_last=True, wait_ms=800, exam_eids=DEFAULT_EXAM_EIDS, log=print):
    """按 eid 升序交卷；exam_last=True 时把考卷放到最后交。

    exam_eids 要和 build_plan 用同一个，否则 --exam-eid 指定的考卷不会被排到最后。
    返回 {eid: {"ok": bool, "raw": 响应片段}}。
    """
    exam_set = {str(e) for e in exam_eids}
    order = sorted(plan, key=lambda x: int(x))
    if exam_last:
        order = [e for e in order if str(e) not in exam_set] + [
            e for e in order if str(e) in exam_set
        ]

    results = {}
    for eid in order:
        item = plan[eid]
        payload = {
            "eid": eid,
            "seid": item["seid"],
            "ans": json.dumps(item["ans"], ensure_ascii=False),
        }
        try:
            raw = page.evaluate(JS_SUBMIT_PAPER, payload)
        except Exception as exc:  # noqa: BLE001
            results[eid] = {"ok": False, "raw": str(exc)}
            log("{} 提交异常：{}".format(eid, exc))
            continue
        ok = "提交成功" in raw
        results[eid] = {"ok": ok, "raw": raw[:200]}
        log("{} {} 题数={} {}".format("OK " if ok else "BAD", eid, len(item["ans"]), raw[:100].replace("\\n", " ")))
        page.wait_for_timeout(wait_ms)
    return results