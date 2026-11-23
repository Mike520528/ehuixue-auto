"""在页面里执行的 JS 片段。

这些片段是在真实课程页上跑通的版本，改之前先读 docs/交接文档.md 的「数据模型」一节：
课程页是 Vue2 SPA，所有状态挂在 `document.querySelector('#app').__vue__.$data`，
节点树在 `partinfo`，而且必须同时递归 `children` 与 `leaf` 两个字段才能走全。
"""

# 导出所有节点：视频（含已看时长/总时长）、练习、考试（含 eid）
JS_SNAPSHOT = r"""()=>{
 const el=document.querySelector('#app');
 if(!el||!el.__vue__) return {err:'no vue',url:location.href,body:document.body.innerText.slice(0,200)};
 const vm=el.__vue__; const d=vm.$data;
 const vids=[],prac=[],exams=[];
 function w(ns){for(const n of ns||[]){
   const t=String(n.task_type);
   if(t==='video'){
     const rec=(d.record||{})[n.task_id]||null;
     const pt=(d.ptmap||{})[n.task_id]||null;
     vids.push({task_id:String(n.task_id),deep:n.deep,lock:n.tasklock,
       cum:rec?+rec.cumulative:0,total:pt?+pt.cw_length:0});
   } else if(t==='practise'){
     prac.push({task_id:String(n.task_id),about_id:String(n.about_id),deep:n.deep,lock:n.tasklock});
   } else if(t==='exam'){
     exams.push({task_id:String(n.task_id),about_id:String(n.about_id),deep:n.deep,lock:n.tasklock});
   }
   if(n.children)w(n.children); if(n.leaf)w(n.leaf);
 }}
 w(d.partinfo);
 return {videos:vids,practises:prac,exams:exams,taskStartTime:d.taskStartTime,
   studied:d.studied?{progress:d.studied.progress,ave_video:d.studied.ave_video,ave_test:d.studied.ave_test,
     ave_exam:d.studied.ave_exam,num_comtest:d.studied.num_comtest,num_comexam:d.studied.num_comexam}:null};
}"""

# 在 SPA 里切到某个任务（不改 URL，直接调组件方法）
JS_LOAD_TASK = r"""(tid)=>{
 const vm=document.querySelector('#app').__vue__; let hit=null;
 function w(ns){for(const n of ns||[]){if(String(n.task_id)===String(tid))hit=n;if(n.children)w(n.children);if(n.leaf)w(n.leaf);}}
 w(vm.$data.partinfo); if(!hit)return {err:'notfound'};
 vm.viewtask(hit); return {ok:1};
}"""

# 上报视频学习时长。timer=999 + isover=1 会让服务端把 cumulative 直接加到 view_length 之上，
# 不需要真的播。返回体里的 data 是服务端回写的最新 record，必须刷回 $data 才看得到新进度。
JS_REPORT_VIDEO = r"""(tid)=>{
 const vm=document.querySelector('#app').__vue__; let hit=null;
 function w(ns){for(const n of ns||[]){if(String(n.task_id)===String(tid))hit=n;if(n.children)w(n.children);if(n.leaf)w(n.leaf);}}
 w(vm.$data.partinfo);
 const body='position=0&taskid='+tid+'&isover=1&deep='+(hit?hit.deep:'0')+'&starttime='+encodeURIComponent(vm.$data.taskStartTime)+'&timer=999';
 return fetch('/index/study/study_recording',{method:'POST',credentials:'include',
   headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body})
 .then(r=>r.text()).then(t=>{
   let st=null,data=null; try{const j=JSON.parse(t);st=j.status;data=j.data}catch(e){}
   if(data){for(const k in data){vm.$data.record[k]=data[k];}}
   const rec=(vm.$data.record||{})[tid]||null;
   return {status:st,cum:rec?+rec.cumulative:null};
 });
}"""

# 进卷子：joinquiz 拿 seid，再拉 quizscore 的 HTML（题目全在这份 HTML 里）
JS_GRAB_PAPER = r"""(eid)=>{
 return fetch('/index/study/joinquiz?eid='+eid,{credentials:'include'}).then(r=>r.json()).then(j=>{
   if(j.status!==100) return {stage:'join',st:j.status,msg:j.msg||''};
   const seid=j.data.seid;
   return fetch('/index/study/quizscore?eid='+eid+'&seid='+seid,{credentials:'include'})
     .then(r=>r.text()).then(html=>({stage:'ok',seid:seid,len:html.length,html:html}));
 });
}"""

# 交卷：answer 是 {qid: {ans, qtype, qid}} 的 JSON 串
JS_SUBMIT_PAPER = r"""async (o)=>{
 const body='temp=0&eid='+o.eid+'&seid='+o.seid+'&answer='+encodeURIComponent(o.ans);
 const t=await fetch('/index/study/examsheet',{method:'POST',credentials:'include',
   headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body}).then(r=>r.text());
 return t;
}"""

# 总进度页（studied 里是各项平均分与完成数）
JS_STUDIED = r"""()=>{const vm=document.querySelector('#app').__vue__;const d=vm&&vm.$data;const s=d&&d.studied;return s?JSON.parse(JSON.stringify(s)):null;}"""


def js(name):
    """按名字取一个 JS 片段，名字对应本模块里 JS_ 开头的常量。"""
    const_name = "JS_" + name.upper()
    try:
        return globals()[const_name]
    except KeyError as exc:
        raise KeyError(f"没有这个 JS 片段: {name}") from exc