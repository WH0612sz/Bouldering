import { config } from '../config';
let loginTask: Promise<string> | null = null;
export function message(e: unknown): string { return e instanceof Error ? e.message : '操作失败，请重试'; }
function raw<T>(path: string, method: WechatMiniprogram.RequestOption['method'], data?: object, token?: string): Promise<T> {
  return new Promise((resolve,reject)=>wx.request({ url: config.apiBase+path, method, data, timeout: 30000, header: token ? {Authorization:'Bearer '+token}: {}, success: r=>{if(r.statusCode>=200&&r.statusCode<300)resolve(r.data as T);else {const d=r.data as {message?:string};reject(Object.assign(new Error(d.message||'服务请求失败'),{status:r.statusCode}));}},fail:()=>reject(new Error('连接失败，请检查本地服务和网络配置')) }));
}
export async function login(): Promise<string> {
  const saved=wx.getStorageSync('climb_token');if(saved)return saved;
  if(loginTask)return loginTask;
  loginTask=(async()=>{let result:{token:string};if(config.authMode==='development')result=await raw('/v1/auth/dev','POST',{identity:config.devIdentity});else {const code=await new Promise<string>((resolve,reject)=>wx.login({success:r=>resolve(r.code),fail:reject}));result=await raw('/v1/auth/wechat','POST',{code});}wx.setStorageSync('climb_token',result.token);return result.token;})();
  try{return await loginTask;}finally{loginTask=null;}
}
export async function api<T>(path:string, method:WechatMiniprogram.RequestOption['method']='GET',data?:object):Promise<T>{
  try{return await raw<T>(path,method,data,await login());}catch(e){if((e as {status?:number}).status===401){wx.removeStorageSync('climb_token');return raw<T>(path,method,data,await login());}throw e;}
}
export async function upload(path:string,filePath:string,onProgress:(n:number)=>void,onTask:(task:WechatMiniprogram.UploadTask)=>void):Promise<void>{
  const token=await login();return new Promise((resolve,reject)=>{const task=wx.uploadFile({url:config.apiBase+path,filePath,name:'file',header:{Authorization:'Bearer '+token},timeout:600000,success:r=>{if(r.statusCode>=200&&r.statusCode<300)resolve();else {let m='上传失败';try{m=JSON.parse(r.data).message||m;}catch{}reject(new Error(m));}},fail:()=>reject(new Error('上传中断，可在此页重试'))});onTask(task);task.onProgressUpdate(r=>onProgress(r.progress));});
}
export async function privacy():Promise<void>{return new Promise((resolve,reject)=>{if(wx.requirePrivacyAuthorize)wx.requirePrivacyAuthorize({success:()=>resolve(),fail:()=>reject(new Error('请先同意隐私保护指引'))});else resolve();});}
export const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
