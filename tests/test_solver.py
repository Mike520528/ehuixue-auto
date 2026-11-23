# -*- coding: utf-8 -*-
"""solver 的离线测试：不联网，用假的 _post 替换真实接口。

    python tests/test_solver.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import ehx.solver as solver


def q(qid, qtype, stem, opts):
    return {"qid": qid, "qtype": qtype, "stem": stem, "opts": opts}


SINGLE = q("11", "1", "创造力的核心是（ ）",
           [("A", "发散思维"), ("B", "记忆能力"), ("C", "计算能力")])
MULTI = q("12", "2", "属于创新方法的有（ ）",
          [("A", "头脑风暴"), ("B", "5W1H"), ("C", "死记硬背")])
JUDGE = q("13", "3", "创造力是天生的。", [("1", "正确"), ("2", "错误")])


class TestFingerprint(unittest.TestCase):
    def test_选项顺序变了指纹不变(self):
        shuffled = q("99", "1", "创造力的核心是（ ）",
                     [("C", "计算能力"), ("A", "发散思维"), ("B", "记忆能力")])
        self.assertEqual(solver.fingerprint(SINGLE), solver.fingerprint(shuffled))

    def test_题号不算进指纹(self):
        self.assertEqual(solver.fingerprint(SINGLE),
                         solver.fingerprint(dict(SINGLE, qid="777")))

    def test_题干变了指纹就变(self):
        other = q("11", "1", "创造力的核心是什么", SINGLE["opts"])
        self.assertNotEqual(solver.fingerprint(SINGLE), solver.fingerprint(other))


class TestNormalize(unittest.TestCase):
    def test_单选(self):
        self.assertEqual(solver._normalize("b", SINGLE), "B")
        self.assertEqual(solver._normalize(" B ", SINGLE), "B")
        self.assertEqual(solver._normalize("答案：C", SINGLE), "C")

    def test_单选给多个只取第一个(self):
        self.assertEqual(solver._normalize("A,C", SINGLE), "A")

    def test_多选排序去重(self):
        self.assertEqual(solver._normalize("C,A", MULTI), "A,C")
        self.assertEqual(solver._normalize("A,A,C", MULTI), "A,C")

    def test_判断(self):
        self.assertEqual(solver._normalize("2", JUDGE), "2")
        self.assertEqual(solver._normalize("错误", JUDGE), "2")

    def test_非法答案报错(self):
        with self.assertRaises(solver.SolverError):
            solver._normalize("Z", SINGLE)
        with self.assertRaises(solver.SolverError):
            solver._normalize("", SINGLE)


class TestExtractJson(unittest.TestCase):
    def test_去掉代码围栏(self):
        self.assertEqual(solver._extract_json('```json\n{"11":"A"}\n```'), {"11": "A"})

    def test_夹在文字里也能取(self):
        self.assertEqual(solver._extract_json('好的：{"11":"A"} 完毕'), {"11": "A"})

    def test_没有json报错(self):
        with self.assertRaises(solver.SolverError):
            solver._extract_json("我不知道")


class TestSolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "cache.json")
        self.calls = []
        self._orig = solver._post

        def fake_post(url, payload, api_key, timeout=120):
            self.calls.append(payload)
            return {"choices": [{"message": {"content": '{"11":"A","12":"A,C","13":"2"}'}}]}

        solver._post = fake_post

    def tearDown(self):
        solver._post = self._orig

    def test_一次答三题并写缓存(self):
        got = solver.solve([SINGLE, MULTI, JUDGE], api_key="k", cache_path=self.cache,
                           log=lambda *a: None)
        self.assertEqual(got, {"11": "A", "12": "A,C", "13": "2"})
        self.assertEqual(len(self.calls), 1)
        cache = solver.load_cache(self.cache)
        self.assertEqual(len(cache), 3)

    def test_第二次全命中缓存不再请求(self):
        solver.solve([SINGLE, MULTI, JUDGE], api_key="k", cache_path=self.cache,
                     log=lambda *a: None)
        n = len(self.calls)
        got = solver.solve([SINGLE, MULTI, JUDGE], api_key="k", cache_path=self.cache,
                           log=lambda *a: None)
        self.assertEqual(len(self.calls), n)
        self.assertEqual(got["12"], "A,C")

    def test_没有key且缓存空时明确报错(self):
        old = {k: os.environ.pop(k, None) for k in ("EHUEXUE_API_KEY", "DEEPSEEK_API_KEY")}
        try:
            with self.assertRaises(solver.SolverError) as ctx:
                solver.solve([SINGLE], api_key=None, cache_path=self.cache, log=lambda *a: None)
            self.assertIn("API key", str(ctx.exception))
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_模型漏答的题不打进结果(self):
        solver._post = lambda *a, **k: {"choices": [{"message": {"content": '{"11":"A"}'}}]}
        got = solver.solve([SINGLE, MULTI], api_key="k", cache_path=self.cache,
                           log=lambda *a: None)
        self.assertIn("11", got)
        self.assertNotIn("12", got)


if __name__ == "__main__":
    unittest.main(verbosity=2)