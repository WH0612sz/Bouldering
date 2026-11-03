# Bouldering · 攀岩复盘

用于记录和回看攀岩视频的微信小程序。项目包含小程序前端、浏览器联调页面和 FastAPI 后端。浏览器版可以独立体验上传、裁剪、保存和播放。

配置本地姿态模型后，详情页可显示骨架、髋部二维轨迹和五轨动作时序。识别条件不足的区间标为“无法判断”。「AI建议」置灰，点击显示「敬请期待」。

## 本地运行

需要 Python 3.12。以下命令在仓库根目录运行。

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
./scripts/start-local.sh
```

打开 [本地体验页](http://127.0.0.1:8000/dev/)。选择视频并确认范围，点击「开始分析」保存，然后从「我的」查看记录。数据库和媒体文件存放在 `backend/var/`，重启服务后仍可查看。开发身份仅用于本机联调。

### 启用动作识别

在独立的 Python 环境安装模型依赖，并下载 MediaPipe Pose Landmarker Full 权重。

```sh
python3.12 -m venv .local/pose-venv
.local/pose-venv/bin/python -m pip install mediapipe==1.2.0 opencv-contrib-python==5.0.0.93 numpy==2.5.4
curl -fL https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task -o .local/pose_landmarker_full.task
```

```sh
POSE_PYTHON="$PWD/.local/pose-venv/bin/python" \
POSE_MODEL="$PWD/.local/pose_landmarker_full.task" \
./scripts/start-local.sh
```

新记录转码后会自动排队识别。已有记录可在详情页点击「识别动作」。后台使用裁剪后的播放视频处理，识别期间可先回看视频。

### 构建微信小程序

需要 Node.js、pnpm 和微信开发者工具。

```sh
pnpm install --frozen-lockfile
pnpm build
```

在微信开发者工具中导入仓库根目录，工程会读取 `project.config.json`，加载 `build/miniprogram/`。默认接口地址为 `http://127.0.0.1:8000`，适用于同机开发者工具联调。真实微信登录需在服务端配置 `WECHAT_APPID` 和 `WECHAT_APPSECRET`，并在 `miniprogram/config.ts` 切换到微信登录模式。AppSecret 通过环境变量提供。真机需使用手机可访问的后端地址，发布前需配置 HTTPS 和小程序合法域名。

## 测试

```sh
(cd backend && .venv/bin/python -m pytest -q)
pnpm build
pnpm test:miniprogram
```

后端测试覆盖上传、转码、重复提交、记录归属、删除及姿态结果清理。小程序测试检查页面状态和保存、返回逻辑。微信登录、相机权限和视频叠层仍需真机验收。

## 代码结构

| 目录 | 内容 |
| --- | --- |
| `miniprogram/` | 小程序页面、组件和接口封装 |
| `backend/app/` | API、数据库、媒体处理和后台识别任务 |
| `backend/devclient/` | 浏览器联调前端 |
| `backend/tests/` | 后端回归测试 |
| `scripts/` | 启动、构建和小程序逻辑测试 |

目前支持本地记录、保存、回看及基础动作复盘。精确帧标记、时序人工校正和同线路对比待接入。`compose.yaml` 提供 API、后台进程、PostgreSQL 和持久卷的部署模板。配置参考 `.env.example`。
