"""刷练习 / 考试。

四步：
    1. grab_papers  —— 对每个练习/考试 eid 调 joinquiz 拿 seid，再拉卷面 HTML
    2. parse        —— 从 HTML 里解出 qid / 题型 / 题干 / 选项
    3. build_plan   —— 用 answers.py 里的答案表拼成提交用的 plan
    4. submit_plan  —— 调 examsheet 一次性交卷

答案表按 qid 索引，和课程绑定。换课程要重新抓卷子、重新核对答案，
answers.py 里的 PRACTISE / EXAM 才有效。
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


def build_plan(papers, exam_eids=DEFAULT_EXAM_EIDS, log=print):
    """把卷面和答案表合成提交计划：{eid: {seid, ans: {qid: {ans, qtype, qid}}}}。

    答案表里查不到的题会兜底成一个固定值（单选题 A、判断题 1），并在 missing 里报出来——
    兜底值大概率是错的，出现 missing 就说明该补 answers.py 了。
    """
    exam_set = {str(e) for e in exam_eids}
    plan, missing = {}, []
    for eid, paper in papers.items():
        if "html" not in paper:
            continue
        table = EXAM if str(eid) in exam_set else PRACTISE
        answers = {}
        for q in parse(paper["html"]):
            qid = q["qid"]
            a = table.get(qid)
            if a is None:
                missing.append((eid, qid, q["qtype"], q["stem"][:40]))
                a = "A" if q["qtype"] in ("1", "2") else "1"
            answers[qid] = {"ans": a, "qtype": q["qtype"], "qid": int(qid)}
        plan[eid] = {"seid": paper["seid"], "ans": answers}

    if missing:
        log("有 {} 道题在答案表里没有答案（已用兜底值，需要人工补）".format(len(missing)))
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
        log("{} {} 题数={} {}".format("OK " if ok else "BAD", eid, len(item["ans"]), raw[:100].replace("\n", " ")))
        page.wait_for_timeout(wait_ms)
    return results