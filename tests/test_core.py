# -*- coding: utf-8 -*-
"""仓库自测：不碰网络、不碰浏览器，只用造假数据验证解析与计划合成的逻辑。

    python tests/test_core.py

覆盖：
  parse_quiz.parse        —— 单选 / 多选 / 判断三种卷面结构
  quiz.build_plan         —— 有答案 / 缺答案兜底 / 考试卷选对表
  state.video_done        —— 视频完成判定
  state.summarize         —— 摘要格式
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ehx.parse_quiz import parse
from ehx.quiz import build_plan, submit_plan
from ehx.state import summarize, video_done

# 一张三种题型混排的卷面，结构照抄 e会学 的 layui table
SAMPLE_HTML = """
<html><body>
<table class="layui-table tableone" id="exam246499">
  <tr><td>1</td><td>创造力的核心是（ ）</td></tr>
  <tr><td>A</td><td>发散思维</td><td><input type="radio" name="sq_246499" value="A"></td></tr>
  <tr><td>B</td><td>记忆能力</td><td><input type="radio" name="sq_246499" value="B"></td></tr>
  <tr><td>C</td><td>计算能力</td><td><input type="radio" name="sq_246499" value="C"></td></tr>
  <tr><td>D</td><td>语言能力</td><td><input type="radio" name="sq_246499" value="D"></td></tr>
  <input type="hidden" name="answer[246499]" attr1="1">
</table>

<table class="layui-table tableone" id="exam246500">
  <tr><td>2</td><td>属于创新思维方法的有（ ）</td></tr>
  <tr><td>A</td><td>头脑风暴</td><td><input type="checkbox" name="mq_246500" value="A"></td></tr>
  <tr><td>B</td><td>5W1H</td><td><input type="checkbox" name="mq_246500" value="B"></td></tr>
  <tr><td>C</td><td>死记硬背</td><td><input type="checkbox" name="mq_246500" value="C"></td></tr>
  <input type="hidden" name="answer[246500]" attr1="2">
</table>

<table class="layui-table tableone" id="exam246501">
  <tr><td>3</td><td>创造力是天生的。</td></tr>
  <tr><td><input type="radio" name="pd_246501" value="1" title="正确"></td></tr>
  <tr><td><input type="radio" name="pd_246501" value="2" title="错误"></td></tr>
  <input type="hidden" name="answer[246501]" attr1="3">
</table>
</body></html>
"""


class TestParse(unittest.TestCase):
    def test_三种题型都解析出来(self):
        qs = parse(SAMPLE_HTML)
        self.assertEqual(len(qs), 3)

        single = [q for q in qs if q["qtype"] == "1"][0]
        self.assertEqual(single["qid"], "246499")
        self.assertEqual(len(single["opts"]), 4)
        self.assertEqual([o[0] for o in single["opts"]], ["A", "B", "C", "D"])
        self.assertIn("创造力的核心", single["stem"])

        multi = [q for q in qs if q["qtype"] == "2"][0]
        self.assertEqual(len(multi["opts"]), 3)

        judge = [q for q in qs if q["qtype"] == "3"][0]
        self.assertEqual([o[0] for o in judge["opts"]], ["1", "2"])
        self.assertEqual(judge["opts"][0][1], "正确")

    def test_空输入不炸(self):
        self.assertEqual(parse("<html></html>"), [])


class TestBuildPlan(unittest.TestCase):
    def _papers(self):
        return {"1001": {"seid": "s1", "html": SAMPLE_HTML}}

    def test_答案表命中(self):
        # 用真实答案表里存在的题号做不到（样本是造的），临时塞一份假表
        import ehx.quiz as quiz_mod

        old = quiz_mod.PRACTISE
        quiz_mod.PRACTISE = {"246499": "A", "246500": "A,B", "246501": "2"}
        try:
            plan = build_plan(self._papers(), exam_eids=(), log=lambda *a: None)
        finally:
            quiz_mod.PRACTISE = old
        self.assertEqual(plan["1001"]["seid"], "s1")
        self.assertEqual(plan["1001"]["ans"]["246499"]["ans"], "A")
        self.assertEqual(plan["1001"]["ans"]["246500"]["ans"], "A,B")
        self.assertEqual(plan["1001"]["ans"]["246501"]["ans"], "2")

    def test_缺答案走兜底并报出来(self):
        # 清空答案表，保证样本里三题必然「查不到」
        import ehx.quiz as quiz_mod

        old_p, old_e = quiz_mod.PRACTISE, quiz_mod.EXAM
        quiz_mod.PRACTISE, quiz_mod.EXAM = {}, {}
        logs = []
        try:
            plan = build_plan({"1002": {"seid": "s2", "html": SAMPLE_HTML}},
                              exam_eids=(), log=logs.append)
        finally:
            quiz_mod.PRACTISE, quiz_mod.EXAM = old_p, old_e
        self.assertEqual(plan["1002"]["ans"]["246499"]["ans"], "A")   # 单选 → A
        self.assertEqual(plan["1002"]["ans"]["246500"]["ans"], "A")   # 多选 → A
        self.assertEqual(plan["1002"]["ans"]["246501"]["ans"], "1")   # 判断 → 1
        self.assertTrue(any("没有答案" in line for line in logs))

    def test_考试卷用EXAM表(self):
        import ehx.quiz as quiz_mod

        old_p, old_e = quiz_mod.PRACTISE, quiz_mod.EXAM
        quiz_mod.PRACTISE = {"246499": "A"}
        quiz_mod.EXAM = {"246499": "D"}
        try:
            plan = build_plan(self._papers(), exam_eids=("1001",), log=lambda *a: None)
        finally:
            quiz_mod.PRACTISE, quiz_mod.EXAM = old_p, old_e
        self.assertEqual(plan["1001"]["ans"]["246499"]["ans"], "D")

    def test_抓取失败的卷子被跳过(self):
        plan = build_plan({"1003": {"err": "boom"}}, log=lambda *a: None)
        self.assertEqual(plan, {})

    def test_交卷顺序把考试放最后(self):
        calls = []

        class FakePage:
            def evaluate(self, js, payload):
                calls.append(payload["eid"])
                return "提交成功"

            def wait_for_timeout(self, ms):
                pass

        plan = {
            "20": {"seid": "a", "ans": {}},
            "10": {"seid": "b", "ans": {}},
            "99": {"seid": "c", "ans": {}},
        }
        submit_plan(FakePage(), plan, exam_eids=("99",), wait_ms=0, log=lambda *a: None)
        self.assertEqual(calls, ["10", "20", "99"])


class TestState(unittest.TestCase):
    def test_视频完成判定(self):
        self.assertTrue(video_done({"total": 100, "cum": 100}))
        self.assertTrue(video_done({"total": 100, "cum": 120}))
        self.assertFalse(video_done({"total": 100, "cum": 99}))
        self.assertFalse(video_done({"total": 0, "cum": 0}))  # 时长未知不算完成

    def test_摘要格式(self):
        st = {
            "videos": [{"total": 10, "cum": 10}, {"total": 10, "cum": 0}],
            "practises": [{"lock": "0"}],
            "exams": [{"lock": "0"}],
            "studied": {"progress": 50, "ave_video": 100, "ave_test": 81,
                        "ave_exam": 88, "num_comtest": 1, "num_comexam": 0},
        }
        out = summarize(st)
        self.assertIn("视频 1/2 已完成", out)
        self.assertIn("进度 50%", out)
        self.assertIn("练习均分 81", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)