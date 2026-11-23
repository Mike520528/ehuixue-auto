"""刷视频：上报学习时长，让服务端把视频判定为已完成。

不播放、不解码、不占带宽。原理是 study_recording 接口接受 `isover=1&timer=999`，
服务端据此把 cumulative 直接累加到 view_length 之上。
"""

import time

from .dom import JS_LOAD_TASK, JS_REPORT_VIDEO
from .state import snapshot, video_done


def run_video(
    page,
    max_rounds=200,
    retries=6,
    load_wait_ms=4000,
    retry_wait_ms=1200,
    reload_wait_ms=6000,
    log=print,
):
    """把当前课程里所有已解锁的视频刷完。

    每轮重新 snapshot 一次——服务端会回写进度，不重读就看不到最新状态。
    遇到锁住的视频时整页 reload 再试，因为解锁状态要刷新页面才会更新。

    返回 dict：{"done": 完成数, "total": 视频总数, "rounds": 实际轮数, "exhausted": 是否卡住}
    """
    rounds = 0
    while True:
        rounds += 1
        state = snapshot(page)
        vids = state["videos"]
        todo = [v for v in vids if not video_done(v)]
        unlocked = [v for v in todo if str(v.get("lock")) == "0"]
        log(
            "[第 {r} 轮] 视频 {t} 个，已完成 {d}，待刷 {x}，已解锁 {u}".format(
                r=rounds, t=len(vids), d=len(vids) - len(todo), x=len(todo), u=len(unlocked)
            )
        )

        if not todo:
            log("全部视频已完成")
            return {"done": len(vids), "total": len(vids), "rounds": rounds, "exhausted": False}
        if rounds > max_rounds:
            log("达到轮数上限 {}，停止".format(max_rounds))
            return {
                "done": len(vids) - len(todo),
                "total": len(vids),
                "rounds": rounds,
                "exhausted": True,
            }
        if not unlocked:
            log("剩下的视频都锁着，刷新页面找解锁")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(reload_wait_ms)
            continue

        target = unlocked[0]
        page.evaluate(JS_LOAD_TASK, target["id"] if "id" in target else target["task_id"])
        page.wait_for_timeout(load_wait_ms)

        ok = False
        for _ in range(retries):
            r = page.evaluate(JS_REPORT_VIDEO, target["task_id"])
            if r.get("status") == 100 and (r.get("cum") or 0) >= (target["total"] or 1):
                ok = True
                log("  {} 完成 {}/{}".format(target["task_id"], r["cum"], target["total"]))
                break
            page.wait_for_timeout(retry_wait_ms)
        if not ok:
            log("  {} 上报后仍是未完成，刷新重试".format(target["task_id"]))
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(reload_wait_ms)