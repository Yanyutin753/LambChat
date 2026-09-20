# LambChat 全站多端截图套件

一条命令把 LambChat **全部前端页面 × 桌面/平板/手机 × 亮/暗/护眼主题**截成 PNG,给 AI 阅读、视觉走查、回归对比。

基于 [Playwright](https://playwright.dev)(经 shot-scraper 安装、自动复用其环境),主入口是 [capture_all.py](capture_all.py)。

## 安装(一次性)

```bash
uv tool install shot-scraper   # 借道装 playwright
shot-scraper install           # 下载 headless Chromium(~115MB)
```

## 一键全量

```bash
cd scripts/site-screenshots
export STG_PASSWORD='…'  # staging 测试账号密码只放本地环境，禁止写进仓库
python3 capture_all.py --base https://test.lambchat.com \
    --username stg_verify_0828 --password "$STG_PASSWORD"
```

默认 **34 个页面 × 3 端(desktop 1440 / tablet 834 / mobile 390)× 2 主题(light+dark)= 204 张**,
16 个浏览器并行,约 **1.5 分钟**跑完(本机 26GB 内存实测峰值 ~16GB、余量充足;内存小的机器降到 `--jobs 8`)。

**每页都等到真正加载完才按快门**:`load` → `networkidle`(网络静默,长连接页最多等 8 秒后放行)→ 字体就绪 → DOM 连续 900ms 无变化 → 截图;整页截图前还会先滚到底再回顶,触发懒加载图片。

常用变体:

```bash
--themes light,dark,sepia     # 三主题全跑(~306 张,约 3 分钟)
--themes dark --devices mobile   # 只要暗色移动端,快速抽检
--jobs 8                      # 降低并行(内存小的机器;默认 16,每路约占 300-400MB)
--no-seed                     # 不抓真实会话(跳过 /chat/<id> 详情页)
```

本地开发环境把 `--base` 换成 `http://127.0.0.1:3001` 即可。

## 它自动做了什么

1. `POST /api/auth/login` 拿 token
2. `GET /api/sessions` 抓一个真实会话 ID,给 `/chat/<sessionId>` 灌真实数据
3. 解析 `frontend/src/App.tsx` 的 `<Route path>` 路由表(**前端加新页面零维护,自动纳入**)
4. 生成 主题×设备 全矩阵任务,8 个 Playwright 浏览器并行执行(登录态+主题经 storage_state 在页面加载前注入)
5. 每页等待"网络空闲+字体就绪+DOM 稳定"后截图:公开页整页截图(先滚动触发懒加载),应用页视口截图
6. 生成 `out/index.html` 缩略目录页(按主题→设备分组)

## 产物

```
out/<theme>/<device>/<页面>.png    # 如 out/dark/mobile/settings.png
out/index.html                     # 目录页,浏览器打开即翻全部
```

## 当前覆盖与留白

- 覆盖:落地页族 8 + 认证页 6 + 应用页 19 + `/chat/<真实会话>` = 34 页
- 留白(带参详情页,暂无公开 API 可灌数据,需要时在 `capture_all.py` 的 `route_urls()` 里扩展):`/channels/<type>/<id>`、`/scheduled-tasks/<id>`、`/shared/<shareId>`
- 排除:OAuth 回调页、`/dev/*` 演示页

## 辅助脚本

- [make_auth.py](make_auth.py):只生成登录态 `auth.json`(手动跑单张 `shot-scraper <url> -a auth.json` 时用)
- 主题原理:`lambchat-theme` localStorage 键(light/dark/sepia)随登录态一起在页面加载前注入,应用启动即按主题渲染

## 勿提交

`auth-*.json` / `auth.json`(含有效 token)与 `out/`(构建产物)。
