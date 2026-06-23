# OpenCap 管理后端

把视频上传到 OpenCap 官网 → 云端 WHAM + OpenSim 处理 → 下载 3D 运动学结果 → TCP 发给 Windows 接收端播放。

---

## 目录结构

```
sender/
├── main.py              # FastAPI 后端 (8个接口)
├── opencap_client.py    # OpenCap API 客户端
├── marker_sender.py     # TCP marker 发送 (支持 .trc / .json)
├── json_store.py        # JSON 文件读写
├── static/
│   └── index.html       # 简易管理页面
└── data/
    ├── token.json        # OpenCap 登录 token (90天有效)
    ├── sessions.json     # 本地 session 记录
    ├── active_config.json
    ├── videos/           # 上传的视频
    └── sessions/         # 下载的结果 (含 .mot .trc .osim)
```

---

## 启动

```bash
cd ~/open-campus-demo-v3
conda activate opencap-mono-slim

# 首次使用：缓存 token (输入邮箱验证码)
python -c "from sender.opencap_client import login_interactive; login_interactive()"

# 启动后端
uvicorn sender.main:app --reload --host 0.0.0.0 --port 8056
```

浏览器打开 `http://100.111.140.103:8056/`

---

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 管理页面 |
| POST | `/videos/upload` | 上传 .mp4/.mov |
| POST | `/sessions/{id}/process-opencap` | 调 OpenCap API 处理 (后台线程) |
| GET | `/sessions` | 列出本地所有 session |
| DELETE | `/sessions/{id}` | 删除本地 + OpenCap 官网 |
| POST | `/sessions/pull-remote` | 从官网拉取 + 自动下载结果 |
| POST | `/sessions/sync-all` | 以官网状态为准同步 |
| GET | `/sessions/{id}/files` | 列出 .mot .trc .osim 文件 |
| GET/POST | `/active-file` | 获取/设置当前发送配置 |
| POST | `/send-active-file` | TCP 发送给 receiver |

---

## 使用流程

1. **上传视频** → 页面选文件点上传
2. **OpenCap 处理** → 点 session 旁的 "OpenCap" 按钮，后台线程处理
3. **等待完成** → 点 Sessions 旁的"刷新"（自动同步官网状态）
4. **选择文件** → 点 session 旁的"文件"，点具体文件设为 active
5. **发送** → Windows 先启动 `receive_and_play.py 0.0.0.0 5005`，页面点"发送"

也支持从官网直接拉取已有的 session：点"刷新"时自动拉取 + 下载结果。

---

## receiver 端

Windows 运行：
```powershell
python testv3/receive_and_play.py
```
监听 `0.0.0.0:5005`，收到 marker 帧后跑 OpenSim IK → 3D 骨骼可视化。

---

## 数据流

```
浏览器上传视频
     │
     ▼
FastAPI 后端 (sender/main.py)
     │
     ├─→ OpenCap API (api.opencap.ai)
     │      └→ 云端 WHAM + OpenSim 处理
     │
     ├─→ 下载结果 zip → 解压到 data/sessions/{id}/
     │
     └─→ marker_sender.py 读 .trc → TCP JSON Lines
              │
              ▼
         Windows receiver (:5005)
              │
              └→ OpenSim IK → 3D 骨骼动画
```

---

## 已知问题

1. **首次使用需终端登录**：`login_interactive()` 必须在终端跑一次输入 OTP 验证码。token 缓存到 `data/token.json`，90 天后过期需重新跑。
2. **远程 session 下载偶发失败**：OpenCap 的 async-download 偶尔不返回 URL，session 状态可能停留在 "processing"。点"刷新"可重试。
3. **下拉远程 session 无视频文件**：从官网拉取的 session 只有 .mot/.trc 结果，没有原始视频。
4. **`/sessions/` 接口超时**：测试期间创建了太多 session，官网 `/sessions/` 接口超时。改用 `/sessions/valid/` 解决。

---

## 环境依赖

```bash
conda activate opencap-mono-slim
pip install fastapi uvicorn python-multipart requests
```
