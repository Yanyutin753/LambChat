# 发版自动化回归与可选真机工具

正式版和测试版出包后运行：

```sh
make -j1 release-regression RELEASE_TAG=v2.15.3-dev.5
```

填写本次实际 tag。默认只执行服务器已有的 `/root/disttest/run-all.sh`，包含图片真实存储/API 检查，以及桌面、Android、iOS 浏览器模拟。它不连接或安装任何真机，不创建 tag、不重新打包、不晋升稳定通道，也不修改生产部署。

Mac、Windows、手机真机检查均可选，未测不影响发布。报告明确区分自动化、浏览器模拟、打包冒烟和真机证据，未测不能标为通过。

## 默认自动化入口

本机需要项目 `uv` 环境和可访问生产服务器的 SSH/SCP；生产服务器沿用已有 disttest、Node/Playwright 与 k3s 环境。测试会产生少量真实模型费用，正常结束时由既有脚本回收测试会话和图片。中断时保留失败日志，并完成该轮测试资源清理。

默认服务器 SSH 别名为 `yang`，可用 `--server-ssh` 覆盖，或在仓库外 `~/.config/lambchat/release-tests.json` 配置 `server_ssh`。配置应仅当前用户可读，SSH 密钥沿用 SSH 配置，不写进仓库。`LAMBCHAT_RELEASE_TEST_CONFIG` 可指定另一私有配置文件。

入口使用非阻塞共享验证锁、串行运行，在远端锁释放前把生产结果复制为本轮独立快照，避免另一轮覆盖。报告和日志默认保存在 `~/.cache/lambchat/release-tests/<tag>/<本轮编号>/`；缺少完整自动化结果或出现失败时报告失败。

## 可选 Windows 真机工具

需要时显式运行；默认发版命令不会调用它：

```sh
python3 scripts/run_validation.py uv run python scripts/test_windows_device.py v2.15.3-dev.5
```

额外依赖：

- 已登录的 `gh`、Node.js 和现有 Playwright。优先使用 Codex bundled runtime，普通环境可通过 `NODE_PATH` 提供已安装的 Playwright。
- 官方 [7-Zip](https://www.7-zip.org/download.html) 的 `7zz` 或 `7z`，用于从已核验的 NSIS 包提取主程序作为安装后的哈希基准，不能以便携版 EXE 代替。
- Windows 需要 Python 3.12+、交互桌面和可注册当前用户计划任务的 SSH 账号；开始前关闭 LambChat，脚本不替用户关闭正在使用的应用。

私有配置示例：

```json
{
  "server_ssh": "your-production-ssh-alias",
  "windows_ssh": "your-windows-ssh-alias",
  "sevenzip": "/absolute/path/to/7zz"
}
```

检查包含：明确 tag、签名清单与源码 SHA、安装包大小和 SHA256、NSIS 内主程序与安装后程序一致、daemon 签名资产和既有数据保留；真实 WebView2 中正常零代理、存储故障回退、私有图片鉴权与原图查看，以及打包设置/文件/聊天页面、草稿和按需加载。

Windows 验证锁覆盖安装、原生检查和清理；使用独立 WebView 和 daemon 目录。结束后回收本轮客户端、计划任务、调试监听、临时 PAT/机器、凭据及合成图片/会话；清理失败明确失败，失败安装备份保留在本轮 Windows 临时目录供恢复，成功后删除大体积临时安装文件。报告绑定 tag、签名源码 SHA 和本轮编号，临时凭据不进入最终报告。

该工具是按需诊断工具，不是发布门禁。尚未重跑的真机路径如实标为未验证；GitHub 托管 runner 不需要访问局域网真机，也未新增后台任务或自托管 runner。
