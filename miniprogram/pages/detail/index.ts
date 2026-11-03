import { api,message } from '../../services/api';
import { Attempt, PosePoint, PoseResult } from '../../services/types';
Page({data:{item:null as Attempt|null,url:'',error:'',loading:true,poseState:'',poseError:'',skeleton:false,hip:false,tracks:[] as {name:string;spans:{start:number;left:number;width:number;unknown:boolean}[]}[],windowLabel:'',cursor:0},pose:null as PoseResult|null,poseTimer:0,position:0,id:'',timer:0,leaving:false,alive:true,
 onLoad(q:{id?:string}){this.id=q.id||'';void this.load();},
 async load(){try{const item=await api<Attempt>('/v1/attempts/'+this.id);if(!this.alive)return;this.setData({item,loading:false,error:''});if(item.state==='PLAYABLE'){const p=await api<{url:string}>('/v1/attempts/'+this.id+'/playback');if(this.alive){this.setData({url:p.url});void this.loadPose();}}else if(item.state==='PREPARING')this.timer=setTimeout(()=>void this.load(),2000) as unknown as number;}catch(e){if(this.alive)this.setData({error:message(e),loading:false});}},
 aiSoon(){wx.showToast({title:'敬请期待',icon:'none'});},
 async loadPose(){
   try{
     const result=await api<PoseResult|{state:string}>('/v1/attempts/'+this.id+'/pose');
     if(!this.alive)return;
     if('version' in result){
       this.pose=result;
       this.setData({poseState:'READY',poseError:''});
       this.updatePose();
     }else{
       this.setData({poseState:result.state,poseError:''});
       if(['QUEUED','RUNNING'].includes(result.state)){
         this.poseTimer=setTimeout(()=>void this.loadPose(),2000) as unknown as number;
       }
     }
   }catch(e){if(this.alive)this.setData({poseError:message(e)});}
 },
 async startPose(){
   this.setData({poseError:''});
   try{await api('/v1/attempts/'+this.id+'/pose','POST');void this.loadPose();}
   catch(e){if(this.alive)this.setData({poseError:message(e)});}
 },
 videoTime(e:WechatMiniprogram.CustomEvent<{currentTime:number}>){
   this.position=e.detail.currentTime;
   this.updatePose();
 },
 toggleSkeleton(e:WechatMiniprogram.CustomEvent<{value:boolean}>){
   this.setData({skeleton:e.detail.value},()=>this.updatePose());
 },
 toggleHip(e:WechatMiniprogram.CustomEvent<{value:boolean}>){
   this.setData({hip:e.detail.value},()=>this.updatePose());
 },
 seekMotion(e:WechatMiniprogram.TouchEvent){
   const player=wx.createVideoContext('analysis-video',this);
   const target=Number(e.currentTarget.dataset.start);
   player.pause();
   player.seek(target);
   this.position=target;
   this.updatePose();
 },
 updatePose(){
   const pose=this.pose;
   if(!pose)return;
   const time=this.position;
   const start=Math.max(0,Math.min(time-2,pose.duration-5));
   const end=Math.min(pose.duration,start+5), span=end-start;
   if(span<=0)return;
   const tracks=pose.tracks.map(track=>({name:track.name,spans:track.spans
     .filter(s=>s.end>start&&s.start<end&&s.state!=='NO_CLEAR_MOVEMENT')
     .map(s=>({start:s.start,left:(Math.max(start,s.start)-start)/span*100,
       width:(Math.min(end,s.end)-Math.max(start,s.start))/span*100,unknown:s.state==='UNKNOWN'}))}));
   this.setData({tracks,windowLabel:`${start.toFixed(1)} – ${end.toFixed(1)} 秒`,
     cursor:Math.max(0,Math.min(100,(time-start)/span*100))});
   if(!this.data.skeleton&&!this.data.hip)return;
   wx.createSelectorQuery().in(this).select('#pose-canvas').boundingClientRect(rect=>{
     if(!rect||Array.isArray(rect)||!this.alive)return;
     const ctx=wx.createCanvasContext('pose-canvas',this);
     const scale=Math.min(rect.width/pose.width,rect.height/pose.height);
     const w=pose.width*scale,h=pose.height*scale;
     const x=(rect.width-w)/2,y=(rect.height-h)/2;
     const frames=pose.frames;
     let index=frames.length-1;
     while(index>=0&&frames[index].t>time+.01)index--;
     const line=(points:PosePoint[],color:string)=>{
       if(points.length<2)return;
       ctx.beginPath();
       ctx.setLineWidth(2);
       ctx.setStrokeStyle(color);
       points.forEach(([px,py],i)=>{if(i===0)ctx.moveTo(x+px*w,y+py*h);else ctx.lineTo(x+px*w,y+py*h);});
       ctx.stroke();
     };
     if(index>=0&&time-frames[index].t<=.25){
       if(this.data.skeleton){
         const points=frames[index].points;
         for(const [a,b] of pose.edges){
           if(points[a]&&points[b])line([points[a],points[b]],'#dcf1cf');
         }
       }
       if(this.data.hip){
         const trail:PosePoint[]=[];
         for(let i=index;i>=0&&time-frames[i].t<=3;i--){
           const hip=frames[i].hip;
           if(!hip)break;
           trail.unshift(hip);
         }
         line(trail,'#e4bd6d');
       }
     }
     ctx.draw();
   }).exec();
 },
 async retry(){try{await api('/v1/attempts/'+this.id+'/retry','POST');void this.load();}catch(e){wx.showToast({title:message(e),icon:'none'});}},
 playbackError(){this.setData({error:'视频播放失败，可点击重新加载'});},refresh(){clearTimeout(this.timer);void this.load();},
 back(){this.leaving=true;wx.switchTab({url:'/pages/record/index'});},
 onHide(){clearTimeout(this.timer);clearTimeout(this.poseTimer);},onShow(){if(this.data.url&&!this.pose)void this.loadPose();else if(this.data.item&&!this.data.url)void this.load();},
 onUnload(){this.alive=false;clearTimeout(this.timer);clearTimeout(this.poseTimer);if(!this.leaving)wx.switchTab({url:'/pages/record/index'});}
});
