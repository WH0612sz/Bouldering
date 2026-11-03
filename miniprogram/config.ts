// 本地联调：开发者工具使用127.0.0.1；真机需改为电脑局域网IP并同网。
// 正式发布必须改为HTTPS、配置微信合法域名，并将authMode设为wechat。
export const config = { apiBase: 'http://127.0.0.1:8000', authMode: 'development' as 'development' | 'wechat', devIdentity: 'local-climber', maxSeconds: 180, maxBytes: 300 * 1024 * 1024 };
