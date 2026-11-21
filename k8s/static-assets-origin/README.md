# 单节点静态资源源站

单节点发布器在 API 滚动前把 Vite 资源合并到宿主机的 `/data/lambchat-k8s/static-assets`。本服务只读挂载同一目录，监听宿主机回环地址。旧页面使用的 hash 文件继续可读，新版本无需再次发布静态文件。

1. 将本目录安装到发布机。在同目录的私有 `.env` 中将 `OPENRESTY_IMAGE` 设为已核验的 OpenResty 镜像摘要。镜像需提供配置所引用的 OpenResty 可执行文件及 MIME 表。
2. 执行 `docker compose config -q`、`docker compose run --rm assets -t -c /etc/assets.conf` 和 `docker compose up -d`。用当前 HTML 引用的 JS、CSS 访问 `127.0.0.1:18085`，检查字节、MIME、`X-LambChat-Asset-Origin: retained` 和不存在文件的 404。
3. 在 staging 站点现有的 `location /assets/` 中将上游改为 `http://127.0.0.1:18085`。保留当前缓存头；用命名 location 在源站连接错误或 502/503/504 时回退该环境的原 Service。执行 `nginx -t` 和平滑 reload。
4. 用独立会话和冷浏览器缓存验证 Android 图片直连、阻断对象存储后的代理回退、私有图片鉴权。检查页面加载的 JS/CSS 均成功。通过后在生产源站应用同一配置。其他边缘节点只将 `/assets/` 的缓存未命中流量转到生产源站的固定 HTTPS 地址，核验生产域名的 SNI 和证书，保留旧缓存和回退。
5. 验证每条边缘线路、当前资源与保留的历史资源，并运行完整生产回归。回滚时先恢复各站点原 `/assets/` 路由并 reload，再移除静态服务。API、图片上传与私有文件请求继续走原有鉴权路径。
