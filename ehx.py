#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""e会学课程自动化命令行入口。

    python ehx.py --cid 43390 state            # 看课程结构和进度
    python ehx.py --cid 43390 video            # 刷完所有视频
    python ehx.py --cid 43390 quiz --dry-run   # 抓卷 + 解题，只看不交
    python ehx.py --cid 43390 quiz             # 解题并交卷
    python ehx.py --cid 43390 all              # 视频 + 练习 + 考试

前置条件：浏览器用 --remote-debugging-port=9222 启动，且已经在这个浏览器里登录过 ehuixue.cn。
解题默认走大模型，需要 API key（--api-key 或环境变量 EHUEXUE_API_KEY / DEEPSEEK_API_KEY）。
"""

import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ehx.browser import DEFAULT_PORT, cdp_page, is_logged_in
from ehx.progress import read_progress
from ehx.quiz import DEFAULT_EXAM_EIDS, build_plan, grab_papers, submit_plan
from ehx.state import snapshot, summarize
from ehx.video import run_video


def build_parser():
    p = argparse.ArgumentParser(description="e会学课程自动化：刷视频 + 刷练习/考试")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="调试端口，默认 9222")
    p.add_argument("--cid", required=True, help="课程 id，例如 43390")
    p.add_argument("--json", action="store_true", help="输出原始 JSON 而不是摘要")
    p.add_argument("--solver", choices=("model", "table"), default="model",
                   help="怎么出答案：model=大模型解题（默认，需要 key），table=旧的 qid 答案表")
    p.add_argument("--api-key", default=None, help="模型 API key，也可以放环境变量 EHUEXUE_API_KEY")
    p.add_argument("--model", default="deepseek-chat", help="模型名，默认 deepseek-chat")
    p.add_argument("--base", default="https://api.deepseek.com", help="接口地址")
    p.add_argument("--cache", default=".ehx-answers.json", help="答案缓存文件（按题目内容指纹）")
    p.add_argument("--hint", default="", help="课程背景，会拼进提示词，例如《创造学与创新创业能力开发》")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state", help="导出课程节点树与进度")
    v = sub.add_parser("video", help="刷完所有视频")
    v.add_argument("--max-rounds", type=int, default=200)

    q = sub.add_parser("quiz", help="抓卷 → 解题 → 交卷")
    q.add_argument("--dry-run", action="store_true", help="只抓卷和解题，不提交")
    q.add_argument("--show", action="store_true", help="把每道题的题目和答案打印出来")
    q.add_argument("--exam-eid", action="append", default=None, help="哪张卷算考试，可重复，默认 473305")

    sub.add_parser("progress", help="只看进度")

    a = sub.add_parser("all", help="视频 + 练习 + 考试一条龙")
    a.add_argument("--max-rounds", type=int, default=200)
    a.add_argument("--exam-eid", action="append", default=None)
    return p


def dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def make_solver(args):
    """返回 solve_fn；--solver table 时返回 None（build_plan 会退回答案表）。"""
    if args.solver == "table":
        return None
    from ehx.solver import solve

    def solve_fn(questions, hint):
        return solve(questions, api_key=args.api_key, model=args.model,
                     base=args.base, cache_path=args.cache,
                     course_hint=hint or args.hint)

    return solve_fn


def report_plan(plan, papers, exam_eids):
    """把每题的题干和答案打出来，方便人工抽查。"""
    from ehx.parse_quiz import parse

    exam_set = {str(e) for e in exam_eids}
    for eid in sorted(plan, key=lambda x: int(x)):
        tag = "考试" if str(eid) in exam_set else "练习"
        print("\n[{} {}]".format(tag, eid))
        qs = parse(papers[eid]["html"])
        for q in qs:
            ans = plan[eid]["ans"].get(q["qid"], {}).get("ans", "?")
            print("  {} {}".format(ans.ljust(4), q["stem"][:70]))
            if q["qtype"] == "2":
                for val, text in q["opts"]:
                    mark = "*" if val in ans.split(",") else " "
                    print("        {} {}. {}".format(mark, val, text[:60]))


def run_quiz(page, args, exam_eids, dry_run):
    from ehx.solver import SolverError

    st = snapshot(page)
    eids = [p["about_id"] for p in st["practises"]] + [e["about_id"] for e in st["exams"]]
    print("练习 {} 个，考试 {} 个".format(len(st["practises"]), len(st["exams"])))
    if not eids:
        print("没有待做的练习/考试")
        return 0

    papers = grab_papers(page, eids)
    try:
        plan = build_plan(papers, exam_eids=exam_eids, solve_fn=make_solver(args))
    except SolverError as exc:
        print("解题失败：{}".format(exc))
        return 2

    total_q = sum(len(v["ans"]) for v in plan.values())
    print("卷子 {} 张，共 {} 题".format(len(plan), total_q))
    if getattr(args, "show", False) or args.json:
        report_plan(plan, papers, exam_eids)
    if args.json:
        dump({eid: {"seid": v["seid"], "ans": v["ans"]} for eid, v in plan.items()})
    if dry_run:
        print("dry-run：没有提交")
        return 0

    results = submit_plan(page, plan, exam_eids=exam_eids)
    bad = [k for k, v in results.items() if not v["ok"]]
    print("提交完成：成功 {} / 失败 {}".format(len(results) - len(bad), len(bad)))
    if bad:
        print("失败：", ", ".join(map(str, bad)))
        return 1
    print(summarize(snapshot(page)))
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    exam_eids = tuple(args.exam_eid) if getattr(args, "exam_eid", None) else DEFAULT_EXAM_EIDS

    with cdp_page(port=args.port, cid=args.cid) as page:
        if not is_logged_in(page):
            raise SystemExit("课程页没加载出来（Vue 上没有 partinfo）：先在这个浏览器里登录并打开课程页")

        if args.cmd == "state":
            st = snapshot(page)
            dump(st) if args.json else print(summarize(st))
            return 0

        if args.cmd == "progress":
            st = read_progress(page, cid=args.cid)
            dump(st) if args.json else print(summarize(snapshot(page)))
            return 0

        if args.cmd == "video":
            res = run_video(page, max_rounds=args.max_rounds)
            print(summarize(snapshot(page)))
            if res["exhausted"]:
                print("注意：还有未完成的视频（被锁或上报失败），跑第二轮或检查开放时间")
            dump(res) if args.json else None
            return 0

        if args.cmd == "quiz":
            return run_quiz(page, args, exam_eids, args.dry_run)

        if args.cmd == "all":
            print("=== 刷视频 ===")
            run_video(page, max_rounds=args.max_rounds)
            print(summarize(snapshot(page)))
            print("=== 刷练习/考试 ===")
            return run_quiz(page, args, exam_eids, False)
    return 0


if __name__ == "__main__":
    sys.exit(main())