//! Linux 桌面端更新安装：安装来源检测 + deb/rpm 包管理器安装。
//!
//! 背景：tauri-plugin-updater 在 Linux 只支持 AppImage——`.deb`/`.rpm` 安装的
//! 壳跑 `update.install()` 时会因 `/usr/bin/lambchat` 归 root 所有而权限失败
//! （2.10.0 → 2.10.2 的实际报错）。本模块补齐系统包路径：
//!
//! - [`get_linux_install_source`]：检测当前程序来源（AppImage / deb / rpm /
//!   unknown），前端据此分流——AppImage 走 updater 替换重启，deb/rpm 走本
//!   模块「下载 + pkexec 提权安装」，unknown 回落下载页；
//! - [`install_linux_package`]：流式下载 deb/rpm 到临时目录（进度事件推送），
//!   `pkexec apt|dnf install` 安装（polkit GUI 授权），成功后前端 relaunch。
//!
//! 检测序：AppImage 扩展名 → `dpkg -S` / `rpm -qf` 包归属反查（权威）→
//! 系统前缀 + 本机包管理器启发式（保守，双装/都没有判 unknown）。

use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter};

/// 前端消费的安装来源词汇表（invoke 返回值；unknown 回落下载页）。
pub const SOURCE_DEB: &str = "deb";
pub const SOURCE_RPM: &str = "rpm";
pub const SOURCE_APPIMAGE: &str = "appimage";
pub const SOURCE_UNKNOWN: &str = "unknown";

/// 下载进度事件名（Tauri event；payload 为 [`ProgressPayload`]）。
pub const PROGRESS_EVENT: &str = "linux-update-progress";

/// 进度事件节流间隔：大包逐块 IPC 全量推送会打爆 webview。
const PROGRESS_THROTTLE: Duration = Duration::from_millis(200);

/// pkexec 授权 + 包管理器安装的整体上限：polkit 密码框无人操作时兜底退出，
/// 不让更新任务无限挂死。
const INSTALL_TIMEOUT: Duration = Duration::from_secs(20 * 60);

/// 下载整体超时：慢网络 100MB 包的宽容上限（连接超时另计 30s）。
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(30 * 60);

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ProgressPayload {
    pub downloaded: u64,
    pub content_length: u64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LinuxInstallInfo {
    pub source: String,
    /// 资产命名的 arch 段（app-release.yml 词汇：x86_64 | arm64）；未知架构
    /// 为 None，前端不再拼 deb/rpm 资产名（回落下载页）。
    pub arch: Option<String>,
}

/// 可执行文件是否是 AppImage（按扩展名；AppImage 自包含、不归包管理器）。
fn is_appimage_path(exe: &Path) -> bool {
    exe.extension()
        .and_then(|e| e.to_str())
        .is_some_and(|e| e.eq_ignore_ascii_case("appimage"))
}

/// 命令是否存在且可执行（`--version` 探测；找不到二进制自然为 false）。
fn command_exists(name: &str) -> bool {
    Command::new(name)
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// `dpkg -S` / `rpm -qf` 反查路径归属的包管理器（权威信号；先查 dpkg——
/// 混装系统里 deb 包由 dpkg 收录优先命中）。非 Linux 平台两个命令都不存在，
/// 自然返回 None。
fn owning_package_manager(exe: &Path) -> Option<&'static str> {
    let run = |argv: [&str; 3]| -> bool {
        Command::new(argv[0])
            .arg(argv[1])
            .arg(argv[2])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    };
    if run(["dpkg", "-S", &exe.to_string_lossy()]) {
        Some(SOURCE_DEB)
    } else if run(["rpm", "-qf", &exe.to_string_lossy()]) {
        Some(SOURCE_RPM)
    } else {
        None
    }
}

/// 包归属反查不可用时的保守启发式：系统前缀（/usr、/opt）安装 + 本机包
/// 管理器唯一时按其判定；双装（alien 混装）或都没有判 unknown，宁可让
/// 用户走下载页也不装错包格式。
fn fallback_install_source(exe: &Path, has_dpkg: bool, has_rpm: bool) -> &'static str {
    let is_system_install = exe.starts_with("/usr/") || exe.starts_with("/opt/");
    if !is_system_install {
        return SOURCE_UNKNOWN;
    }
    match (has_dpkg, has_rpm) {
        (true, false) => SOURCE_DEB,
        (false, true) => SOURCE_RPM,
        _ => SOURCE_UNKNOWN,
    }
}

/// 综合判定安装来源（检测序见模块注释）。
pub fn detect_install_source(exe: &Path) -> &'static str {
    if is_appimage_path(exe) {
        return SOURCE_APPIMAGE;
    }
    if let Some(pm) = owning_package_manager(exe) {
        return pm;
    }
    fallback_install_source(exe, command_exists("dpkg"), command_exists("rpm"))
}

/// 与 app-release.yml 资产命名的 arch 段一致（前端拼 deb/rpm 资产名用）。
fn release_asset_arch() -> Option<&'static str> {
    match std::env::consts::ARCH {
        "x86_64" => Some("x86_64"),
        "aarch64" => Some("arm64"),
        _ => None,
    }
}

/// deb/rpm 对应的系统安装器调用参数（pkexec 之后的部分；纯函数便于单测）。
fn installer_argv(kind: &str, package_path: &Path) -> Option<Vec<String>> {
    let path = package_path.to_string_lossy().into_owned();
    match kind {
        SOURCE_DEB => Some(vec![
            "apt".into(),
            "install".into(),
            "-y".into(),
            path,
        ]),
        SOURCE_RPM => Some(vec![
            "dnf".into(),
            "install".into(),
            "-y".into(),
            path,
        ]),
        _ => None,
    }
}

/// 进程级安装 ring crypto provider（幂等：已装则忽略 Err）。
///
/// reqwest 走 `rustls-no-provider`（复用 updater 插件编入的 ring，避免
/// aws-lc-sys 原生构建），构 Client 前必须有进程级 provider，否则直接
/// panic（reqwest 0.13 显式校验）。
fn ensure_rustls_provider() {
    let _ = rustls::crypto::ring::default_provider().install_default();
}

/// 流式下载安装包到临时目录（200ms 节流回调进度；返回落盘路径）。
/// 下载核心与 Tauri 事件解耦，便于用本地 HTTP 服务做单测。
async fn download_to_temp<F>(url: &str, ext: &str, mut on_progress: F) -> Result<PathBuf, String>
where
    F: FnMut(u64, u64),
{
    ensure_rustls_provider();
    let client = reqwest::Client::builder()
        .user_agent(concat!("LambChatDesktop/", env!("CARGO_PKG_VERSION")))
        .connect_timeout(Duration::from_secs(30))
        .timeout(DOWNLOAD_TIMEOUT)
        .build()
        .map_err(|e| format!("failed to build http client: {e}"))?;
    let mut resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("download request failed: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("download failed: HTTP {}", resp.status()));
    }
    let content_length = resp.content_length().unwrap_or(0);
    let path = std::env::temp_dir().join(format!("lambchat-update.{ext}"));
    let mut file =
        std::fs::File::create(&path).map_err(|e| format!("create {}: {e}", path.display()))?;

    let mut downloaded: u64 = 0;
    let mut wrote_any = false;
    let mut last_emit: Option<Instant> = None;
    while let Some(chunk) = resp
        .chunk()
        .await
        .map_err(|e| format!("download stream failed: {e}"))?
    {
        if chunk.is_empty() {
            continue;
        }
        file.write_all(&chunk)
            .map_err(|e| format!("write {}: {e}", path.display()))?;
        downloaded += chunk.len() as u64;
        wrote_any = true;
        if last_emit.is_none_or(|t| t.elapsed() >= PROGRESS_THROTTLE) {
            on_progress(downloaded, content_length);
            last_emit = Some(Instant::now());
        }
    }
    if !wrote_any {
        let _ = std::fs::remove_file(&path);
        return Err("download produced no content".into());
    }
    file.flush()
        .map_err(|e| format!("flush {}: {e}", path.display()))?;
    // 收尾事件：让 UI 的 downloaded/content_length 落到终值
    on_progress(downloaded, content_length);
    Ok(path)
}

/// pkexec 调用系统包管理器安装本地包文件。
///
/// stderr 由独立线程持续排空（dnf 进度输出可超管道缓冲，不排空会写阻塞
/// → 安装挂死）；stdout 丢弃（GUI 壳无处展示）。超时 kill 兜底。
fn run_pkexec_installer(argv: &[String]) -> Result<(), String> {
    let mut child = Command::new("pkexec")
        .args(argv)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| {
            format!(
                "failed to spawn pkexec ({e}); 系统缺少 polkit 授权组件，\
                 请从下载页手动安装新版安装包"
            )
        })?;

    // stderr 排空线程：try_wait 轮询期间子进程的输出不能积压在管道里
    let mut stderr_pipe = child
        .stderr
        .take()
        .expect("stderr piped above");
    let stderr_buf: Arc<Mutex<Vec<u8>>> = Arc::new(Mutex::new(Vec::new()));
    let buf_clone = Arc::clone(&stderr_buf);
    let drain = std::thread::spawn(move || {
        let mut chunk = [0u8; 4096];
        loop {
            match stderr_pipe.read(&mut chunk) {
                Ok(0) | Err(_) => break,
                Ok(n) => buf_clone.lock().unwrap().extend_from_slice(&chunk[..n]),
            }
        }
    });

    let deadline = Instant::now() + INSTALL_TIMEOUT;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    let _ = drain.join();
                    return Err(format!(
                        "installer timed out after {}s（polkit 授权未完成？），请重试或手动安装",
                        INSTALL_TIMEOUT.as_secs()
                    ));
                }
                std::thread::sleep(Duration::from_millis(200));
            }
            Err(e) => return Err(format!("wait installer failed: {e}")),
        }
    };
    let _ = drain.join();
    if status.success() {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&stderr_buf.lock().unwrap()).trim().to_string();
    if stderr.is_empty() {
        Err(format!("installer exited with {status}（polkit 授权被取消？）"))
    } else {
        Err(format!("installer exited with {status}: {stderr}"))
    }
}

/// 检测当前安装来源与资产 arch（前端更新分流依据）。
#[tauri::command]
pub fn get_linux_install_source() -> LinuxInstallInfo {
    let source = std::env::current_exe()
        .map(|p| detect_install_source(&p).to_string())
        .unwrap_or_else(|_| SOURCE_UNKNOWN.to_string());
    LinuxInstallInfo {
        source,
        arch: release_asset_arch().map(str::to_string),
    }
}

/// 下载 deb/rpm 安装包并以 pkexec 提权安装（成功后前端 relaunch 进新版）。
#[tauri::command]
pub async fn install_linux_package(
    app: AppHandle,
    url: String,
    kind: String,
) -> Result<(), String> {
    if kind != SOURCE_DEB && kind != SOURCE_RPM {
        return Err(format!("unsupported package kind: {kind}"));
    }
    let app_for_progress = app.clone();
    let ext = kind.clone();
    let path = download_to_temp(&url, &ext, move |downloaded, content_length| {
        let _ = app_for_progress.emit(
            PROGRESS_EVENT,
            ProgressPayload {
                downloaded,
                content_length,
            },
        );
    })
    .await?;

    // pkexec 安装是阻塞轮询（≤20min 授权窗口），挪出 async 线程
    let argv = installer_argv(&kind, &path)
        .ok_or_else(|| format!("unsupported package kind: {kind}"))?;
    let result =
        tauri::async_runtime::spawn_blocking(move || run_pkexec_installer(&argv)).await;
    // 装完即清；失败也清（重试走完整重新下载，不残留半包）
    let _ = std::fs::remove_file(&path);
    result.map_err(|e| format!("installer task failed: {e}"))?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn appimage_detection_by_extension_only() {
        assert!(is_appimage_path(Path::new(
            "/home/user/Applications/LambChat.AppImage"
        )));
        // 大小写不敏感（手工改名常见）
        assert!(is_appimage_path(Path::new("/opt/lambchat.appimage")));
        // deb/rpm 安装路径与裸二进制都不是 AppImage
        assert!(!is_appimage_path(Path::new("/usr/bin/lambchat")));
        assert!(!is_appimage_path(Path::new("/usr/bin/lambchat.deb")));
        assert!(!is_appimage_path(Path::new("/home/user/lambchat")));
    }

    #[test]
    fn fallback_source_needs_system_prefix_and_unique_manager() {
        let deb = Path::new("/usr/bin/lambchat");
        // 系统前缀 + 唯一包管理器 → 判定对应来源
        assert_eq!(fallback_install_source(deb, true, false), SOURCE_DEB);
        assert_eq!(fallback_install_source(deb, false, true), SOURCE_RPM);
        assert_eq!(
            fallback_install_source(Path::new("/usr/lib/lambchat/lambchat"), true, false),
            SOURCE_DEB
        );
        assert_eq!(
            fallback_install_source(Path::new("/opt/LambChat/lambchat"), false, true),
            SOURCE_RPM
        );
        // 用户目录（AppImage 检测漏网时的手动解包等）不猜
        assert_eq!(
            fallback_install_source(Path::new("/home/user/bin/lambchat"), true, false),
            SOURCE_UNKNOWN
        );
        // 混装 / 双缺：保守判 unknown（宁可走下载页也不装错格式）
        assert_eq!(fallback_install_source(deb, true, true), SOURCE_UNKNOWN);
        assert_eq!(fallback_install_source(deb, false, false), SOURCE_UNKNOWN);
    }

    #[test]
    fn installer_argv_maps_deb_to_apt_and_rpm_to_dnf() {
        let deb = installer_argv(SOURCE_DEB, Path::new("/tmp/lambchat-update.deb")).unwrap();
        assert_eq!(deb, vec!["apt", "install", "-y", "/tmp/lambchat-update.deb"]);
        let rpm = installer_argv(SOURCE_RPM, Path::new("/tmp/lambchat-update.rpm")).unwrap();
        assert_eq!(rpm, vec!["dnf", "install", "-y", "/tmp/lambchat-update.rpm"]);
        assert!(installer_argv(SOURCE_APPIMAGE, Path::new("/tmp/x")).is_none());
        assert!(installer_argv("exe", Path::new("/tmp/x")).is_none());
    }

    #[test]
    fn release_asset_arch_matches_workflow_vocabulary() {
        // 本机构建机必在受支持架构内；词汇表与 app-release.yml 一致
        let arch = release_asset_arch().expect("host arch must be supported");
        assert!(arch == "x86_64" || arch == "arm64", "unexpected arch {arch}");
    }

    /// 起一个单连接本地 HTTP 服务：回指定状态行/头 + 分两段写 body
    /// （模拟流式分块），返回请求 URL。
    fn spawn_chunked_http_server(status_and_headers: &str, body: &[u8]) -> String {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        let head = status_and_headers.as_bytes().to_vec();
        let body = body.to_vec();
        std::thread::spawn(move || {
            let Ok((mut stream, _)) = listener.accept() else { return };
            // 读完请求头再响应，避免立刻回写导致对端 RST。
            // 注意：先追加再判帧——读到请求头后对端不会再发数据，
            // 判旧缓冲会永久阻塞在第二次 read（首次集成即踩中）
            let mut buf = [0u8; 4096];
            let mut req = Vec::new();
            loop {
                let n = stream.read(&mut buf).unwrap_or(0);
                if n == 0 {
                    break;
                }
                req.extend_from_slice(&buf[..n]);
                if req.windows(4).any(|w| w == b"\r\n\r\n") {
                    break;
                }
            }
            let _ = stream.write_all(&head);
            let _ = stream.write_all(&body[..body.len() / 2]);
            let _ = stream.flush();
            std::thread::sleep(Duration::from_millis(50));
            let _ = stream.write_all(&body[body.len() / 2..]);
            let _ = stream.flush();
        });
        format!("http://{addr}/lambchat-update.test")
    }

    #[test]
    fn http_server_fixture_serves_bytes_via_plain_tcp() {
        let url = spawn_chunked_http_server(
            "HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\n",
            b"hello",
        );
        let addr = url
            .trim_start_matches("http://")
            .split('/')
            .next()
            .unwrap();
        let mut stream = std::net::TcpStream::connect(addr).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(10)))
            .unwrap();
        stream
            .write_all(b"GET /lambchat-update.test HTTP/1.1\r\nHost: x\r\n\r\n")
            .unwrap();
        let mut resp = Vec::new();
        stream.read_to_end(&mut resp).unwrap();
        let resp = String::from_utf8_lossy(&resp);
        assert!(resp.starts_with("HTTP/1.1 200"), "{resp}");
        assert!(resp.ends_with("hello"), "{resp}");
    }

    #[test]
    fn async_runtime_block_on_works_in_test_harness() {
        assert_eq!(tauri::async_runtime::block_on(async { 7 }), 7);
    }

    #[test]
    fn download_to_temp_streams_file_and_progress() {
        let body: Vec<u8> = (0..100_000u32).map(|i| (i % 251) as u8).collect();
        let head = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nContent-Type: application/vnd.debian.binary-package\r\nConnection: close\r\n\r\n",
            body.len()
        );
        let url = spawn_chunked_http_server(&head, &body);
        let path = tauri::async_runtime::block_on(download_to_temp(&url, "test-pkg", |d, c| {
            // 进度单调不回退，总量不超 content-length
            assert!(c == body.len() as u64, "content_length mismatch");
            let _ = d;
        }))
        .expect("download should succeed");
        let written = std::fs::read(&path).expect("temp file readable");
        assert_eq!(written, body, "downloaded bytes must match served body");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn download_to_temp_surfaces_http_error_status() {
        let head = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        let url = spawn_chunked_http_server(head, b"");
        let err = tauri::async_runtime::block_on(download_to_temp(&url, "test-pkg-404", |_, _| {}))
            .expect_err("404 must fail");
        assert!(err.contains("404"), "error should carry status: {err}");
    }

    /// e2e（scripts/e2e_linux_update.py）专用：打印本机检测结果供人工核对。
    /// 平时跳过——CI/单测环境的「正确值」随安装方式而变，不可断言。
    #[test]
    #[ignore]
    fn detect_current_machine_source() {
        let exe = std::env::current_exe().unwrap();
        let info = get_linux_install_source();
        println!(
            "[e2e] exe={} source={} arch={:?}",
            exe.display(),
            info.source,
            info.arch
        );
    }
}
