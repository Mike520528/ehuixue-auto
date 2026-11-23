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

所以视频不需要真的播放。题目则交给大模型现场作答——**不靠写死的答案表**，因为
e会学 每次进卷都会重排题号和选项顺序，`{qid: "A"}` 这种表换个快照就会答错题。

模型答案按「题干 + 选项内容」的指纹缓存（`.ehx-answers.json`），同一道题第二次
出现不再重复请求，重排也不影响命中。

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

## 给其他 agent 用

仓库根目录本身就是一份 skill：`SKILL.md` 说明什么时候用、前置条件、命令表和数据模型，
`ehx.py` 是可直接执行的入口。三种接法：

```bash
# 1) 塞进 agent 的 skills 目录（Claude Code / Codex / DSH 都认这个位置）
git clone https://github.com/Mike520528/ehuixue-auto.git ~/.agents/skills/ehuixue-auto

# 2) 只是临时用一下，clone 到任意目录，读 SKILL.md 照着跑
git clone https://github.com/Mike520528/ehuixue-auto.git && cd ehuixue-auto

# 3) 作为子模块挂进别的项目
git submodule add https://github.com/Mike520528/ehuixue-auto.git tools/ehuixue-auto
```

**这个仓库是私有的**，别的机器上先 `gh auth login` 让 git 拿到凭据，或者
`git clone https://<token>@github.com/Mike520528/ehuixue-auto.git`。

给 agent 的原话可以很短：

> 照 `ehuixue-auto/SKILL.md` 把 `--cid 43390` 这门课的视频刷完、练习和考试做完。

agent 自己会去读前置条件（调试端口、登录态、`EHUEXUE_API_KEY`）。

## 用法

```bash
python ehx.py --cid 43390 state          # 课程结构 + 进度
python ehx.py --cid 43390 video          # 刷完视频
python ehx.py --cid 43390 quiz --dry-run --show   # 抓卷 + 解题，打印看看
python ehx.py --cid 43390 quiz           # 解题并交卷
python ehx.py --cid 43390 progress       # 总进度 / 平均分
python ehx.py --cid 43390 all            # 视频 + 练习 + 考试
```

`--cid` 在课程页 URL 的 `?cid=` 后面。`--port` 默认 9222。

## 答案是怎么来的

默认用大模型逐题作答（`ehx/solver.py`）：

```bash
export EHUEXUE_API_KEY=sk-...        # 或 DEEPSEEK_API_KEY
# 也可以每次传：--api-key sk-...
python ehx.py --cid 43390 quiz --dry-run --show
```

`--show` 会把每道题的题干和模型给的答案打出来，先看一遍再决定交不交。

- 单选题返回一个字母，多选题返回 `A,C`，判断题返回 `1`（正确）/`2`（错误）。
- 缓存文件 `.ehx-answers.json` 已在 `.gitignore` 里，属于本地产物。
- 嫌模型慢或想省钱，可以 `--solver table` 退回 `ehx/answers.py` 里那份 2026-10 的旧表——
  但**那张表只对应那一次的快照**，题号重排后基本不可用，只适合复核历史记录。
- 想换模型：`--model` 和 `--base` 都支持 OpenAI 兼容接口。

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
ehx/quiz.py         抓卷 / 组卷 / 交卷
ehx/solver.py       调大模型解题（按内容指纹缓存）
ehx/parse_quiz.py   卷面 HTML 解析
ehx/answers.py      旧答案表（--solver table 时才用）
ehx/progress.py     读进度
tests/              离线单元测试，不需要浏览器和网络
docs/交接文档.md     接口细节、数据模型、当初怎么试出来的
```

## 已知限制

- 视频被锁（前面没看完 / 未到开放时间）时刷不动，脚本会反复 reload 直到轮数用尽。
- 同一份卷子重复提交会覆盖成绩，别反复跑 `quiz`。
- 解题要联网调模型；没有 key 且缓存为空时会直接报错，不会静默提交兜底值。
- 只处理单选、多选、判断三类客观题；填空/主观题不在解析范围内（`parse_quiz` 只解析 `input` 选项）。
- Windows 控制台输出中文如果乱码，`set PYTHONIOENCODING=utf-8` 再跑。