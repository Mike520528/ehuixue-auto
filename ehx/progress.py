"""读学习进度。

studied 是课程页 $data 上现成的对象，不用另外开进度页：
    progress    总进度百分比
    ave_video   视频平均分
    ave_test    练习平均分
    ave_exam    考试平均分
    num_comtest 已交练习数
    num_comexam 已交考试数
"""

from .browser import COURSE_URL
from .dom import JS_STUDIED


def read_studied(page):
    """读当前页的 studied；页面上没有就返回 None。"""
    return page.evaluate(JS_STUDIED)


def read_progress(page, cid=None, wait_ms=6000):
    """读进度；给了 cid 且当前页不是它，就先跳过去。"""
    if cid and str(cid) not in page.url:
        page.goto(COURSE_URL.format(cid=cid), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)
    studied = read_studied(page)
    if studied is None:
        raise RuntimeError(
            "读不到进度：当前页 {url} 上没有 Vue studied 对象，先打开课程学习页".format(url=page.url)
        )
    return studied