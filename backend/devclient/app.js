const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token=localStorage.getItem('climb_service_token'),draft=null,page='record',active=null,poll=0,uploadTask=null,busy=false,abandoned=false,cameraStream=null,recorder=null,recordChunks=[];let cursor=null,items=[],filter='',routes=[],view='videos',routeFilter='',cameraFacing='environment',recordTimer=0,recordStarted=0;
$('#back').innerHTML=icon('ChevronLeft');$('#status-icons').innerHTML=icon('Wifi')+icon('BatteryFull','battery');document.querySelector('[data-page=record]').insertAdjacentHTML('afterbegin',icon('ScanLine'));document.querySelector('[data-page=mine]').insertAdjacentHTML('afterbegin',icon('Layers'));
async function login(){if(!token){const r=await fetch('/v1/auth/dev',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity:'local-climber'})});const d=await r.json();if(!r.ok)throw Error(d.message);token=d.token;localStorage.setItem('climb_service_token',token);}return token;}
async function api(path,method='GET',body){const auth=await login();const r=await fetch('/v1'+path,{method,headers:{Authorization:'Bearer '+auth,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});const d=await r.json();if(r.status===401){token=null;localStorage.removeItem('climb_service_token');throw Error('登录过期，请重试');}if(!r.ok)throw Error(d.message||'请求失败');return d;}
function err(e){const target=$('#error');if(target)target.textContent=e.message;else alert(e.message);}
function cleanupCamera(){clearInterval(recordTimer);cameraStream?.getTracks().forEach(t=>t.stop());cameraStream=null;}
async function go(next){clearTimeout(poll);if(page==='confirm'&&!abandoned&&!busy&&draft&&!draft.saved)await cancelDraft();if(next!=='record')cleanupCamera();page=next;$('#title').textContent={record:'记录',mine:'我的',confirm:'确认视频',detail:'视频记录'}[next];const root=['record','mine'].includes(next);$('#nav').hidden=!root;$('#back').hidden=root;$('#page').className=root?'tabbed':'';$('#page').scrollTop=0;$('#nav').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.page===next));({record:recordPage,mine:minePage,confirm:confirmPage,detail:detailPage}[next])();}
$('#nav').onclick=e=>{const b=e.target.closest('[data-page]');if(b)void go(b.dataset.page);};
function recordPage(){$('#page').innerHTML=`${localStorage.getItem('climb_service_pending')?'<button id="recover" class="full recover-banner">恢复上次尚未确认的提交 ›</button>':''}<div class="camera-view" id="camera"><video id="camera-preview" autoplay playsinline muted></video><div class="camera-placeholder" id="camera-hint"><strong>准备记录你的攀爬</strong><span>请允许使用相机和麦克风</span><button id="enable-camera">开启相机</button></div><div class="camera-top"><span class="camera-live">● VIDEO</span><span id="camera-time">00:00</span></div><div class="camera-bottom"><p id="camera-label">视频</p><div class="camera-actions"><button id="album" aria-label="从相册上传视频">${icon('Image')}<small>相册</small></button><button id="shoot" class="shutter" aria-label="开始录制"><i></i></button><button id="flip" aria-label="切换摄像头">↻<small>翻转</small></button></div></div><p id="error" class="camera-error"></p></div>`;$('#album').onclick=()=>{$('#file').value='';$('#file').click();};async function startCamera(){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:cameraFacing},audio:true});if(page!=='record'){stream.getTracks().forEach(t=>t.stop());return;}cleanupCamera();cameraStream=stream;$('#camera-preview').srcObject=stream;$('#camera-hint').hidden=true;}catch(e){if(page==='record')$('#camera-hint span').textContent='无法使用相机，请检查权限或从相册上传视频';}}$('#enable-camera').onclick=startCamera;$('#flip').onclick=()=>{if(recorder?.state==='recording')return;cameraFacing=cameraFacing==='environment'?'user':'environment';void startCamera();};$('#shoot').onclick=()=>{if(!cameraStream){$('#file').setAttribute('capture','environment');$('#file').click();$('#file').removeAttribute('capture');return;}if(recorder?.state==='recording'){recorder.stop();return;}recordChunks=[];recorder=new MediaRecorder(cameraStream);recorder.ondataavailable=e=>{if(e.data.size)recordChunks.push(e.data);};recorder.onstop=()=>{clearInterval(recordTimer);$('#nav').hidden=false;acceptFile(new File(recordChunks,'攀爬录像.webm',{type:recorder.mimeType}));};recorder.start();recordStarted=Date.now();$('#shoot').classList.add('recording');$('#camera-label').textContent='录制中';$('#nav').hidden=true;recordTimer=setInterval(()=>{if(page!=='record')return;const n=Math.floor((Date.now()-recordStarted)/1000);$('#camera-time').textContent=String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');if(n>=180&&recorder.state==='recording')recorder.stop();},1000);};if($('#recover'))$('#recover').onclick=recover;void startCamera();}
$('#file').onchange=e=>{const file=e.target.files[0];e.target.value='';if(file)acceptFile(file);};
async function acceptFile(file){const url=URL.createObjectURL(file),v=document.createElement('video');v.preload='metadata';v.src=url;v.onloadedmetadata=()=>{if(!Number.isFinite(v.duration)||v.duration<=0){err(Error('视频时长无法读取，请选择MP4视频'));return;}if(v.duration>180.2||file.size>300*1024*1024){URL.revokeObjectURL(url);err(Error('请选择3分钟、300MB以内的视频'));return;}draft={file,url,duration:v.duration,submission_id:crypto.randomUUID(),saved:false};abandoned=false;void go('confirm');};v.onerror=()=>err(Error('此视频无法预览，请更换视频'));}
function confirmPage(){if(!draft){void go('record');return;}$('#page').innerHTML=`<video class="preview" src="${draft.url||''}" controls></video><label class="section" style="display:block">名称<input id="name" maxlength="80" value="${esc(draft.file?.name.replace(/\.[^.]+$/,'')||draft.payload?.name||'攀爬记录')}"></label><div class="row section"><label class="half">开始（秒）<input id="start" type="number" min="0" step="0.1" value="${draft.payload?.trim_start||0}"></label><label class="half">结束（秒）<input id="end" type="number" min="0" step="0.1" value="${draft.payload?.trim_end||draft.duration.toFixed(2)}"></label></div><label class="section" style="display:block">攀爬日期<input id="date" type="date" value="${draft.payload?.climb_date||new Date().toLocaleDateString('en-CA')}"></label><label class="section" style="display:block">新线路名称（可选）<input id="route" maxlength="60" value="${esc(draft.payload?.route_name||'')}" placeholder="暂不归组"></label><p class="note">点击开始分析后上传源视频，服务端按所选范围准备播放和动作分析。</p><progress id="progress" value="0" max="100"></progress><p id="phase" class="muted">尚未保存</p><p id="error" class="error"></p><button id="save" class="primary full">开始分析</button>`;$('#back').onclick=async()=>{if(busy&&!confirm('放弃尚未完成上传？如果服务端已提交，记录仍保留在“我的”。'))return;abandoned=true;uploadTask?.abort();await cancelDraft();busy=false;void go('record');};$('#save').onclick=save;if(draft.uploadId)lockFields();}
function lockFields(){['name','start','end','date','route'].forEach(id=>{if($('#'+id))$('#'+id).disabled=true;});}
async function save(){if(busy||!draft)return;const d=draft;const payload=d.payload||{submission_id:d.submission_id,name:$('#name').value.trim()||'攀爬记录',climb_date:$('#date').value,trim_start:Number($('#start').value),trim_end:Number($('#end').value),...($('#route').value.trim()?{route_name:$('#route').value.trim()}:{})};if(payload.trim_start<0||payload.trim_end<=payload.trim_start||payload.trim_end>d.duration+.15){err(Error('请设置有效起止范围'));return;}d.payload=payload;busy=true;$('#save').disabled=true;$('#error').textContent='';try{let u=d.uploadId?await api('/uploads/'+d.uploadId):await api('/uploads','POST',payload);d.uploadId=u.id;localStorage.setItem('climb_service_pending',JSON.stringify({uploadId:d.uploadId,payload,duration:d.duration}));if(abandoned){await cancelDraft();return;}lockFields();if(u.state!=='COMMITTED'){if(u.state!=='UPLOADED'){if(!d.file)throw Error('临时视频已失效，请放弃后重新选择');$('#phase').textContent='上传中';await sendFile(u.id,d.file);}if(abandoned){await cancelDraft();return;}$('#phase').textContent='服务端校验并保存中';const r=await api('/uploads/'+u.id+'/commit','POST');u={state:'COMMITTED',attempt_id:r.attempt_id};}d.saved=true;localStorage.removeItem('climb_service_pending');active=u.attempt_id;if(!abandoned)void go('detail');}catch(e){if(!abandoned)err(e);}finally{busy=false;if($('#save'))$('#save').disabled=false;}}
async function sendFile(id,file){const t=await login();return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();uploadTask=xhr;xhr.open('POST','/v1/uploads/'+id+'/content');xhr.setRequestHeader('Authorization','Bearer '+t);xhr.timeout=600000;xhr.upload.onprogress=e=>{if(e.lengthComputable&&$('#progress'))$('#progress').value=e.loaded/e.total*100;};xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300)resolve();else{let m='上传失败';try{m=JSON.parse(xhr.responseText).message;}catch{}reject(Error(m));}};xhr.onerror=xhr.ontimeout=xhr.onabort=()=>reject(Error('上传中断，请重试'));const form=new FormData();form.append('file',file);xhr.send(form);});}
async function cancelDraft(){const d=draft;if(d?.uploadId&&!d.saved){try{await api('/uploads/'+d.uploadId,'DELETE');localStorage.removeItem('climb_service_pending');}catch{}}if(d?.url)URL.revokeObjectURL(d.url);draft=null;}
async function recover(){try{const d=JSON.parse(localStorage.getItem('climb_service_pending'));const u=await api('/uploads/'+d.uploadId);if(u.state==='COMMITTED'){localStorage.removeItem('climb_service_pending');active=u.attempt_id;void go('detail');return;}draft={...d,saved:false,submission_id:d.payload.submission_id};abandoned=false;void go('confirm');}catch(e){err(e);}}
async function detailPage(){$('#page').innerHTML='<div id="detail"></div><p class="error" id="error"></p>';$('#back').onclick=()=>void go('record');await refreshDetail();}
async function refreshDetail(){
  if(page!=='detail')return;
  const id=active;
  try{
    const r=await api('/attempts/'+id);
    if(page!=='detail'||active!==id)return;
    const player=r.state==='PLAYABLE'
      ? '<div class="player pose-player"><video id="playback" controls playsinline></video><svg class="motion-layer" id="pose-overlay" aria-hidden="true"></svg></div>'
      : `<div class="media-pending"><strong>${r.state==='FAILED'?'视频准备失败':'视频已保存，正在准备播放'}</strong><span>可以返回，处理将在服务端继续</span></div>`;
    $('#detail').innerHTML=`${player}<h2>${esc(r.name)}</h2>
      <p>${esc(r.climb_date)} · ${esc(r.route_name||'未归组')} · ${esc(r.completion)}</p>
      <div class="layer-switches" hidden id="pose-switches">
        <label><span>骨架</span><input type="checkbox" id="pose-skeleton"><i></i></label>
        <label><span>髋部轨迹</span><input type="checkbox" id="pose-hip"><i></i></label>
      </div>
      <div class="tabs"><button class="active">动作分析</button><button class="upcoming-tab" id="ai-tab">AI建议</button></div>
      <section id="actions"><p class="muted" id="pose-state">等待视频准备完成</p><div id="pose-timeline"></div></section>
      ${r.state==='FAILED'?'<button id="retry" class="primary full section">重试视频处理</button>':''}`;
    $('#ai-tab').onclick=showComingSoon;
    if(r.state==='PLAYABLE'){
      const playback=await api('/attempts/'+id+'/playback');
      if(page!=='detail'||active!==id)return;
      $('#playback').src=playback.url;
      void loadPose(id);
    }else if(r.state==='PREPARING')poll=setTimeout(refreshDetail,1800);
    if($('#retry'))$('#retry').onclick=async()=>{try{await api('/attempts/'+id+'/retry','POST');void refreshDetail();}catch(e){err(e);}};
  }catch(e){err(e);}
}
let toastTimer;
function showComingSoon(){
  const toast=$('#toast');
  toast.textContent='敬请期待';
  toast.style.display='block';
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>{toast.style.display='none';},1800);
}
async function loadPose(id){
  const status=$('#pose-state');
  if(page!=='detail'||active!==id||!status)return;
  try{
    const result=await api('/attempts/'+id+'/pose');
    if(!status.isConnected)return;
    if(result.version){
      status.textContent='绿色为明显移动，灰色为无法判断。轨迹为髋部二维位置。';
      $('#pose-switches').hidden=false;
      wirePose(result);
      return;
    }
    if(['QUEUED','RUNNING'].includes(result.state)){
      status.textContent='正在识别动作，可先回看视频。';
      poll=setTimeout(()=>loadPose(id),2000);
      return;
    }
    const retry=result.state==='FAILED';
    status.textContent=retry?'动作识别失败，可以重试。':'查看骨架、髋部轨迹和动作时序。';
    const button=document.createElement('button');
    button.className='plain section';
    button.textContent=retry?'重试动作识别':'识别动作';
    status.append(button);
    button.onclick=async()=>{
      button.disabled=true;
      try{await api('/attempts/'+id+'/pose','POST');void loadPose(id);}
      catch(e){if(status.isConnected){status.firstChild.textContent=e.message;button.disabled=false;}}
    };
  }catch(e){if(status.isConnected)status.textContent=e.message;}
}
function wirePose(result){
  const video=$('#playback'), svg=$('#pose-overlay'), timeline=$('#pose-timeline');
  const skeleton=$('#pose-skeleton'), hip=$('#pose-hip');
  const {frames,width,height,duration,tracks,edges}=result;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  function render(){
    const time=video.currentTime;
    let low=0,high=frames.length;
    while(low<high){
      const mid=(low+high)>>1;
      if(frames[mid].t<=time+.01)low=mid+1;
      else high=mid;
    }
    const frame=frames[low-1];
    let overlay='';
    if(frame&&time-frame.t<=.25){
      if(skeleton.checked){
        for(const [a,b] of edges){
          const start=frame.points[a],end=frame.points[b];
          if(start&&end)overlay+=`<line x1="${start[0]*width}" y1="${start[1]*height}" x2="${end[0]*width}" y2="${end[1]*height}"/>`;
        }
      }
      if(hip.checked){
        const points=[];
        for(let i=low-1;i>=0&&frames[i].hip&&time-frames[i].t<=3;i--){
          const [x,y]=frames[i].hip;
          points.unshift(`${x*width},${y*height}`);
        }
        if(points.length>1)overlay+=`<polyline class="hip-path" points="${points.join(' ')}"/>`;
      }
    }
    svg.innerHTML=overlay;
    const start=Math.max(0,Math.min(time-2,Math.max(0,duration-5)));
    const end=Math.min(duration,start+5), span=end-start;
    if(span<=0)return;
    timeline.innerHTML=`<div class="between section muted"><span>动作时序</span><span>${start.toFixed(1)} – ${end.toFixed(1)} 秒</span></div>`+
      tracks.map(track=>`<div class="lane-row"><span class="lane-label">${esc(track.name)}</span><div class="lane">
        ${track.spans.filter(s=>s.end>start&&s.start<end&&s.state!=='NO_CLEAR_MOVEMENT').map(s=>{
          const left=(Math.max(start,s.start)-start)/span*100;
          const size=(Math.min(end,s.end)-Math.max(start,s.start))/span*100;
          return `<button class="bar ${s.state==='UNKNOWN'?'unknown':''}" data-seek="${s.start}" aria-label="${s.start.toFixed(1)} 秒" style="left:${left}%;width:${size}%"></button>`;
        }).join('')}
        <i class="cursor" style="left:${Math.min(100,Math.max(0,(time-start)/span*100))}%"></i>
      </div></div>`).join('');
  }
  video.addEventListener('timeupdate',render);
  video.addEventListener('seeked',render);
  skeleton.onchange=hip.onchange=render;
  timeline.onclick=e=>{const marker=e.target.closest('[data-seek]');if(marker){video.pause();video.currentTime=Number(marker.dataset.seek);}};
  render();
}

async function minePage(){$('#page').innerHTML='<p class="muted">加载服务端记录…</p><p id="error" class="error"></p>';try{const [me,list,groups]=await Promise.all([api('/me'),api('/attempts?'+new URLSearchParams({...filter?{completion:filter}:{},...routeFilter?{route_id:routeFilter}:{}})),api('/routes')]);if(page!=='mine')return;items=list.items;cursor=list.next_cursor;routes=groups.items;$('#page').innerHTML=`<div class="profile"><div class="profile-avatar">${me.avatar_url?`<img src="${esc(me.avatar_url)}" style="width:100%;height:100%;border-radius:50%">`:'攀'}</div><div class="profile-name"><strong>${esc(me.nickname)}</strong><span>记录每一次攀爬</span></div><button id="profile" class="plain muted">编辑 ›</button></div><div class="profile-stats"><div><b>${me.stats.videos}</b><span>分析视频</span></div><div><b>${me.stats.days}</b><span>记录天数</span></div><div><b>${me.stats.routes}</b><span>线路组</span></div></div><div class="between section"><h3>分析记录</h3></div><div class="tabs"><button data-view="videos" class="${view==='videos'?'active':''}">全部视频</button><button data-view="routes" class="${view==='routes'?'active':''}">按线路</button></div><div class="filters"><select id="filter" class="tag">${['','已完成','未完成','未标记'].map(x=>`<option value="${x}" ${filter===x?'selected':''}>${x||'全部完成情况'}</option>`).join('')}</select><span class="muted">最新在前 ↓</span></div><div id="list" class="section"></div><button id="more" class="full section" ${cursor?'':'hidden'}>加载更多</button><p id="error" class="error"></p>`;renderItems();document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;routeFilter='';void minePage();});$('#filter').onchange=e=>{filter=e.target.value;void minePage();};$('#more').onclick=async()=>{try{const r=await api('/attempts?'+new URLSearchParams({cursor,...filter?{completion:filter}:{},...routeFilter?{route_id:routeFilter}:{}}));items.push(...r.items);cursor=r.next_cursor;renderItems();$('#more').hidden=!cursor;}catch(e){err(e);}};$('#profile').onclick=()=>editProfile(me);}catch(e){err(e);}}
function renderItems(){if(view==='routes'){$('#list').innerHTML=routes.length?routes.map(r=>`<div class="item" data-route="${r.id}"><div class="thumb route-thumb">${icon('Folder')}</div><div class="body"><strong>${esc(r.name)}</strong><p class="muted">${r.count} 次尝试</p></div><span class="chev">›</span></div>`).join(''):'<div class="empty muted">暂无线路，编辑视频即可归组。</div>';$('#more').hidden=true;$('#list').onclick=e=>{const row=e.target.closest('[data-route]');if(row){routeFilter=row.dataset.route;view='videos';void minePage();}};return;}const visible=routeFilter?items.filter(x=>x.route_id===routeFilter):items;$('#list').innerHTML=visible.length?visible.map(r=>`<div class="item" data-open="${r.id}">${r.poster_url?`<img class="thumb" src="${esc(r.poster_url)}">`:'<div class="thumb"></div>'}<div class="body"><strong>${esc(r.name)}</strong><p class="muted">${esc(r.climb_date)} · ${esc(r.completion)}<br>${esc(r.route_name||'未归组')} · ${r.state==='PLAYABLE'?'已保存':r.state==='FAILED'?'准备失败':'准备播放中'}</p></div><button class="record-actions" data-edit="${r.id}" aria-label="管理记录">${icon('MoreHorizontal')}</button></div>`).join(''):'<div class="empty"><p>还没有符合条件的视频记录</p><button onclick="go(\'record\')" class="primary">去记录</button></div>';$('#list').onclick=e=>{const edit=e.target.closest('[data-edit]');if(edit){editItem(items.find(x=>x.id===edit.dataset.edit));return;}const row=e.target.closest('[data-open]');if(row){active=row.dataset.open;void go('detail');}};}
function sheet(html){$('#modal').innerHTML='<div class="sheet-mask"><div class="sheet"><div class="handle"></div>'+html+'<button class="full" id="close">取消</button><p id="sheet-error" class="error"></p></div></div>';$('#close').onclick=()=>$('#modal').innerHTML='';}
function editItem(r){sheet(`<h2>管理视频记录</h2><label>名称<input id="edit-name" value="${esc(r.name)}" maxlength="80"></label><label>日期<input id="edit-date" type="date" value="${r.climb_date}"></label><select id="edit-status">${['未标记','未完成','已完成'].map(x=>`<option ${x===r.completion?'selected':''}>${x}</option>`).join('')}</select><label>线路<select id="edit-group"><option value="">未归组</option>${routes.map(x=>`<option value="${x.id}" ${x.id===r.route_id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label><label>或新建线路<input id="edit-route" maxlength="60" placeholder="填写后使用新线路"></label><button id="edit-save" class="primary full">保存修改</button><button id="delete" class="danger full">删除视频</button>`);$('#edit-save').onclick=async()=>{try{await api('/attempts/'+r.id,'PUT',{revision:r.revision,name:$('#edit-name').value,climb_date:$('#edit-date').value,completion:$('#edit-status').value,...($('#edit-route').value.trim()?{route_name:$('#edit-route').value.trim()}:{route_id:$('#edit-group').value||null})});$('#modal').innerHTML='';void minePage();}catch(e){$('#sheet-error').textContent=e.message;}};$('#delete').onclick=async()=>{if(confirm('确认删除服务端视频？相册原文件不会修改。')){try{await api('/attempts/'+r.id,'DELETE');$('#modal').innerHTML='';void minePage();}catch(e){$('#sheet-error').textContent=e.message;}}};}
function editProfile(me){sheet(`<h2>编辑资料</h2><input id="nickname" value="${esc(me.nickname)}" maxlength="24"><button id="profile-save" class="primary full">保存</button>`);$('#profile-save').onclick=async()=>{try{await api('/me','PUT',{nickname:$('#nickname').value});$('#modal').innerHTML='';void minePage();}catch(e){$('#sheet-error').textContent=e.message;}};}
window.addEventListener('beforeunload',e=>{if(busy){e.preventDefault();e.returnValue='';}});void go('record');
