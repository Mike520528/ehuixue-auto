# e会学 课程自动化

自动完成 [e会学](https://www.ehuixue.cn) 网课的**视频学习**与**练习/考试**，跑在你自己的浏览器里，不下载视频、不解码、不占带宽。

> 只在你自己有权限完成的学习任务上用。脚本用你自己的登录态提交，成绩记在你账号上。

## 它怎么工作

e会学 是 Vue2 单页应用，学习进度全部挂在页面 Vue 实例的 `$data` 上。脚本接管一个开了调试端口的浏览器，直接在页面上下文里发请求：

| 动作 | 接口 |
|---|---|
| 刷视频 | `POST /index/study/study_recording`（`isover=1&timer=999` 让服务端把已看时长加到总时长之上） |
| 进卷 | `GET /index/study/joinquiz?eid=` → `seid` |
| 拉卷面 | `GET /index/study/quizscore?eid=&seid=` |
| 交卷 | `POST /index/study/examsheet` |

所以视频不需要真的播放，练习也不需要真的点——但答案要你自己提供（见下）。

## 准备浏览器

脚本**不启动**浏览器，它接管你已经登录的那个窗口：

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --remote-debugging-port=9222 --user-data-dir=C:\edge-debug2
```

在这个窗口里登录 e会学，打开课程学习页（地址形如
`https://www.ehuixue.cn/index/study/index?cid=43390`），然后：

```bash
curl http://127.0.0.1:9222/json/version    # 有 JSON 返回就说明端口通了
```

注意域名是 **ehuixue.cn**，`.com` 会证书报错。

## 安装

```bash
pip install playwright
```

不需要 `playwright install`——我们连的是你现成的浏览器，不是自己起的。

## 用法

```bash
python ehx.py --cid 43390 state          # 课程结构 + 进度
python ehx.py --cid 43390 video          # 刷完视频
python ehx.py --cid 43390 quiz --dry-run # 抓卷 + 对答案，不提交
python ehx.py --cid 43390 quiz           # 交卷
python ehx.py --cid 43390 progress       # 总进度 / 平均分
python ehx.py --cid 43390 all            # 视频 + 练习 + 考试
```

`--cid` 在课程页 URL 的 `?cid=` 后面。`--port` 默认 9222。

## 答案表

`ehx/answers.py` 里存的是**特定课程**的答案，按题目 `qid` 索引：

- `PRACTISE`：34 套练习
- `EXAM`：1 套考试（40 题）

换课程（cid 变了）这张表就失效。先用 `quiz --dry-run` 看它报哪些 `missing`，
再按题目把答案补进去。**没有答案的题会拿兜底值（单选 A、判断 1）交上去**，
所以看到 missing 就要停下来补，不要直接提交。

## 输出长什么样

```
视频 51/51 已完成
练习 34 个，考试 1 个
进度 100%  视频均分 100  练习均分 80.74  考试均分 88.00  已交练习 34 已交考试 1
```

## 目录

```
ehx.py              命令行入口
SKILL.md            给 AI agent 的调用说明
ehx/browser.py      接管调试浏览器
ehx/dom.py          页面里执行的 JS 片段
ehx/state.py        导出节点树与进度
ehx/video.py        刷视频
ehx/quiz.py         抓卷 / 对答案 / 交卷
ehx/parse_quiz.py   卷面 HTML 解析
ehx/answers.py      答案表（课程相关）
ehx/progress.py     读进度
docs/交接文档.md     接口细节、数据模型、当初怎么试出来的
```

## 已知限制

- 视频被锁（前面没看完 / 未到开放时间）时刷不动，脚本会反复 reload 直到轮数用尽。
- 同一份卷子重复提交会覆盖成绩，别反复跑 `quiz`。
- 只处理单选、多选、判断三类客观题；填空/主观题不在解析范围内（`parse_quiz` 只解析 `input` 选项）。
- Windows 控制台输出中文如果乱码，`set PYTHONIOENCODING=utf-8` 再跑。