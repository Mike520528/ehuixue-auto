"""接管一个已经开着调试端口的浏览器。

本工具不自己启动浏览器、不新建无头上下文：登录态（cookie）在你自己那个窗口里，
只有接管它才能复用。启动方式见 README 的「准备浏览器」。
"""

from contextlib import contextmanager

from playwright.sync_api import sync_playwright

DEFAULT_PORT = 9222
SITE = "https://www.ehuixue.cn"
COURSE_URL = SITE + "/index/study/index?cid={cid}"


class BrowserError(RuntimeError):
    pass


@contextmanager
def cdp_page(port=DEFAULT_PORT, cid=None, page_timeout=60000, settle_ms=6000):
    """接上调试端口，返回一个指向课程学习页的 page。

    找页顺序：URL 里同时含 ehuixue 与 cid 的 → URL 含 ehuixue 的 → 新开一个。
    cid 为 None 时用前两条规则。
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        except Exception as exc:  # noqa: BLE001
            raise BrowserError(
                f"连不上 127.0.0.1:{port}，确认浏览器是用 --remote-debugging-port={port} 启动的"
            ) from exc
        if not browser.contexts:
            raise BrowserError("调试浏览器里没有浏览器上下文，先手动打开一个窗口")
        ctx = browser.contexts[0]

        page = None
        if cid:
            for cand in ctx.pages:
                if "ehuixue" in cand.url and str(cid) in cand.url:
                    page = cand
                    break
        if page is None:
            for cand in ctx.pages:
                if "ehuixue" in cand.url:
                    page = cand
                    break
        if page is None:
            if not cid:
                raise BrowserError("浏览器里没有 ehuixue 页面，先手动打开课程页")
            page = ctx.new_page()
            page.goto(COURSE_URL.format(cid=cid), wait_until="domcontentloaded", timeout=page_timeout)
            page.wait_for_timeout(settle_ms)

        yield page


def is_logged_in(page):
    """页面上有 Vue 实例且 $data 里有 partinfo，说明课程页正常加载、登录态有效。"""
    return bool(
        page.evaluate(
            "()=>{const el=document.querySelector('#app');"
            "const vm=el&&el.__vue__;return !!(vm&&vm.$data&&vm.$data.partinfo);}"
        )
    )