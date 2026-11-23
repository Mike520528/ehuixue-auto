"""e会学（ehuixue.cn）课程自动化：刷视频 + 刷练习/考试。

模块划分：
    browser   —— 接管一个开着 --remote-debugging-port 的 Chrome/Edge
    dom       —— 页面里执行的 JS 片段（已验证可用的原样搬运）
    state     —— 导出课程节点树（视频/练习/考试及其完成度）
    video     —— 上报学习时长，让视频判定为已完成
    quiz      —— 抓卷子 → 解析题目 → 合并答案 → 提交
    progress  —— 读课程总进度
"""

from .state import snapshot
from .video import run_video
from .quiz import grab_papers, build_plan, submit_plan
from .progress import read_progress, read_studied

__all__ = [
    "snapshot",
    "run_video",
    "grab_papers",
    "build_plan",
    "submit_plan",
    "read_progress",
    "read_studied",
]