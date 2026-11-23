"""导出课程节点树。

一次 snapshot 就是一次全量对账：拿到所有 video / practise / exam 节点，
以及视频的 cum（已看秒数）和 total（总秒数）。
"""

from .dom import JS_SNAPSHOT


class StateError(RuntimeError):
    pass


def snapshot(page):
    """返回 {videos, practises, exams, taskStartTime, studied}。

    page 必须是课程学习页（/index/study/index?cid=...），否则 Vue 实例上没有 partinfo。
    """
    raw = page.evaluate(JS_SNAPSHOT)
    if raw.get("err"):
        raise StateError(
            "读不到课程数据：{err}（当前页 {url}）\n"
            "常见原因：页面还停在登录页，或者 cid 不对，或者不是学习页".format(
                err=raw.get("err"), url=raw.get("url")
            )
        )
    return raw


def video_done(v):
    """视频是否已完成：总时长已知且已看时长不小于总时长。"""
    return v["total"] > 0 and v["cum"] >= v["total"]


def summarize(state):
    """一行摘要，CLI 和日志都用它。"""
    vids = state["videos"]
    done = sum(1 for v in vids if video_done(v))
    done_prac = sum(1 for p in state["practises"] if str(p.get("lock")) == "0")
    lines = [
        "视频 {}/{} 已完成".format(done, len(vids)),
        "练习 {} 个，考试 {} 个".format(len(state["practises"]), len(state["exams"])),
    ]
    studied = state.get("studied") or {}
    if studied:
        lines.append(
            "进度 {p}%  视频均分 {av}  练习均分 {at}  考试均分 {ae}  已交练习 {nct} 已交考试 {nce}".format(
                p=studied.get("progress"),
                av=studied.get("ave_video"),
                at=studied.get("ave_test"),
                ae=studied.get("ave_exam"),
                nct=studied.get("num_comtest"),
                nce=studied.get("num_comexam"),
            )
        )
    return "\n".join(lines)