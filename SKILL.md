---
name: ehuixue-auto
description: 自动完成 e会学（ehuixue.cn）网课的视频学习与练习/考试。视频通过上报 study_recording 让服务端判定完成，不需要真的播放；练习与考试通过 joinquiz → quizscore 抓卷、按 qid 答案表作答、examsheet 交卷。用于「这门 e会学 网课帮我刷/挂完/做完」的请求，需要在用户自己已登录的调试浏览器里跑。
---

# e会学 课程自动化

## 什么时候用

用户说「e会学 的课帮我刷完 / 视频挂完 / 练习做完 / 换了个号再刷一遍」这类话，
并且他愿意用一台开着 `--remote-debugging-port` 的浏览器登录自己的账号。

## 前置条件（缺一不可）

1. **浏览器必须带调试端口启动**，登录态在它里面：

   ```powershell
   & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
     --remote-debugging-port=9222 --user-data-dir=C:\edge-debug2
   ```

   然后用这个窗口登录 `https://www.ehuixue.cn` 并打开课程学习页。
   不要用无头、不要新开 profile —— 新 profile 没有登录态。

2. **确认端口通了**：`curl http://127.0.0.1:9222/json/version`

3. **别用 ehuixue.com**：域名是 `www.ehuixue.cn`，`.com` 证书报错。

4. 依赖：`pip install playwright`（不需要 `playwright install`，因为我们接管现成的浏览器）。

## 怎么跑

```bash
python ehx.py --cid 43390 state        # 先看：多少视频、已完成多少、练习考试各几份
python ehx.py --cid 43390 video        # 刷视频
python ehx.py --cid 43390 quiz --dry-run   # 抓卷对答案，不提交（先看有没有漏答案）
python ehx.py --cid 43390 quiz         # 交卷
python ehx.py --cid 43390 progress     # 看总进度/平均分
python ehx.py --cid 43390 all          # 一条龙
```

`--cid` 是课程 id，在课程页 URL 的 `?cid=` 后面。

## 判断成功的标准

`state` / `progress` 的输出里：

- `视频 51/51 已完成`
- `练习均分 80.x`、`考试均分 88.x`（不同课程不同）
- `已交练习 34 已交考试 1`

视频没刷满就先跑 `video` 再跑 `quiz`；`quiz` 在 `--dry-run` 阶段如果打印
「有 N 道题在答案表里没有答案」，说明 `ehx/answers.py` 缺这几题，得先补上，
否则会拿兜底值（单选 A / 判断 1）交上去，分数会很难看。

## 答案表

`ehx/answers.py` 里是**特定课程**的答案：`PRACTISE` 按 qid 索引 34 套练习，
`EXAM` 是一份考试（40 题）。换课程（cid 变了）这份表就失效，要重新抓卷子重新核对。
抓卷可以在 `quiz --dry-run` 的输出里看，也可以直接改 `build_plan` 把 `missing` 打全。

## 数据结构速查（改代码时看）

课程页是 Vue2 SPA，全部状态在 `document.querySelector('#app').__vue__.$data`：

| 字段 | 含义 |
|---|---|
| `partinfo` | 节点树；递归要同时走 `children` 和 `leaf` 两个字段 |
| `record[task_id].cumulative` | 视频已看秒数 |
| `ptmap[task_id].cw_length` | 视频总秒数 |
| `taskStartTime` | 上报时要带的 starttime |
| `studied` | 总进度、各项平均分、已交份数 |

节点字段：`task_id`（数字，比较时统一 `str()`）、`task_type`（`video`/`practise`/`exam`）、
`about_id`（题卷 eid）、`deep`、`tasklock`。

## 四个接口

| 动作 | 请求 |
|---|---|
| 刷视频 | `POST /index/study/study_recording`，body `position=0&taskid=..&isover=1&deep=..&starttime=..&timer=999` |
| 进卷 | `GET /index/study/joinquiz?eid=..` → `data.seid` |
| 拉卷面 | `GET /index/study/quizscore?eid=..&seid=..`（HTML，题目在里面） |
| 交卷 | `POST /index/study/examsheet`，body `temp=0&eid=..&seid=..&answer=<JSON>` |

所有请求都带 `credentials:'include'`，在页面上下文里 `fetch`，所以自动带 cookie。

## 坑

- **页面必须停在课程学习页**：`/index/study/index?cid=..`。停在别的页取不到 `$data.partinfo`。
- **切任务不要改 URL**：调 `vm.viewtask(node)`，URL 不会变。
- **视频锁着**：说明前面的课没看完或没到开放时间，reload 再看；真锁着就刷不动。
- **交卷顺序**：练习按 eid 升序，考试放最后（`submit_plan(exam_last=True)`）。
- **同一份卷子重复交**会覆盖旧成绩，别反复跑 `quiz`。
- `timer=999` 是秒，别改成很小的值，服务端会当成"没看完"。