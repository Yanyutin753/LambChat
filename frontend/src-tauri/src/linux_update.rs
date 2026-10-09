//! Linux 桌面端更新安装：安装来源检测 + deb/rpm 包管理器安装。
//!
//! 背景：tauri-plugin-updater 在 Linux 只支持 AppImage（已停发）；`.deb`/
//! `.rpm` 安装的壳跑 `update.install()` 时会因 `/usr/bin/lambchat` 归 root
//! 所有而权限失败（2.10.0 → 2.10.2 的实际报错）。本模块承担 Linux 全部
//! 更新链路（对齐主流发行版客户端的 deb 自更新模式）：
//!
//! - [`get_linux_install_source`]：检测当前程序来源（AppImage / deb / rpm /
//!   unknown），前端据此分流——deb/rpm 走本模块，其余回落下载页；
//! - [`download_linux_package`]：流式下载到版本化缓存目录
//!   （`~/.cache/lambchat/updates/<资产名>`，`.part` 落盘原子改名——目录里
//!   存在终名文件即完整可复用，重复检查/重试绝不重复下载）；
//! - [`install_linux_package`]：从缓存取包，`pkcon install-local` →
//!   `pkexec apt|dnf install` → `pkexec dpkg -i / rpm -U` 三级回退安装
//!   （polkit GUI 授权），成功后清空缓存、前端 relaunch。
//!
//! 检测序：AppImage 扩展名 → `dpkg -S` / `rpm -qf` 包归属反查（权威）→
//! 系统前缀 + 本机包管理器启发式（保守，双装/都没有判 unknown）。

use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;
use crate::release_signature::{SignedAsset, verify_release, verify_package, MAX_MANIFEST_BYTES};
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

/// deb/rpm 对应的系统安装器调用链（逐级回退；纯函数便于单测）。
/// pkcon（PackageKit）会话级授权体验最好且无需终端，不打 pkexec；apt/dnf/
/// dpkg/rpm 都要提权，由 pkexec 前缀拉起 polkit GUI 授权。
fn installer_argv_chain(kind: &str, package_path: &Path) -> Option<Vec<Vec<String>>> {
    let path = package_path.to_string_lossy().into_owned();
    match kind {
        SOURCE_DEB => Some(vec![
            vec![
                "pkcon".into(),
                "install-local".into(),
                "-y".into(),
                path.clone(),
            ],
            vec![
                "pkexec".into(),
                "apt".into(),
                "install".into(),
                "-y".into(),
                path.clone(),
            ],
            vec!["pkexec".into(), "dpkg".into(), "-i".into(), path],
        ]),
        SOURCE_RPM => Some(vec![
            vec![
                "pkcon".into(),
                "install-local".into(),
                "-y".into(),
                path.clone(),
            ],
            vec![
                "pkexec".into(),
                "dnf".into(),
                "install".into(),
                "-y".into(),
                path.clone(),
            ],
            vec![
                "pkexec".into(),
                "rpm".into(),
                "-U".into(),
                "--replacepkgs".into(),
                path,
            ],
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

/// 更新包缓存目录：`$XDG_CACHE_HOME/lambchat/updates`（默认
/// `~/.cache/lambchat/updates`），取不到家目录时回落系统临时目录。
/// 版本化资产名即缓存键——同一版本只下载一次，装完清空。
fn update_cache_dir() -> PathBuf {
    let base = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .or_else(|| {
            std::env::var_os("HOME")
                .map(|h| PathBuf::from(h).join(".cache"))
        })
        .unwrap_or_else(std::env::temp_dir);
    base.join("lambchat").join("updates")
}

/// 清空缓存目录里的更新包（安装成功后调用；目录不存在为幂等成功）。
fn clear_update_cache(dir: &Path) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            let _ = std::fs::remove_file(&path);
        }
    }
}

/// 下载完成后清掉其它版本的残留包（只保留刚下好的这份）。
fn remove_stale_packages(dir: &Path, keep: &Path) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() && path != keep {
            let _ = std::fs::remove_file(&path);
        }
    }
}

fn package_version(asset: &str, arch: &str) -> Result<String, String> {
    let version_and_suffix = asset.strip_prefix("LambChat-v").ok_or("Invalid update asset")?;
    for kind in [SOURCE_DEB, SOURCE_RPM] {
        if let Some(version) = version_and_suffix.strip_suffix(&format!("-Linux-{arch}.{kind}")) {
            crate::release_signature::version_parts(version)?;
            return Ok(version.into());
        }
    }
    Err("Update asset does not match this Linux architecture".into())
}

fn signed_metadata_urls(url: &str, asset: &str, version: &str) -> Result<(reqwest::Url, reqwest::Url), String> {
    let url = reqwest::Url::parse(url).map_err(|_| "Invalid update URL")?;
    let loopback = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]" | "::1"));
    if (url.scheme() != "https" && !(cfg!(debug_assertions) && loopback && url.scheme() == "http")) || url.host_str().is_none() || !url.username().is_empty() || url.password().is_some() || url.fragment().is_some() {
        return Err("Update URL requires HTTPS".into());
    }
    let path = format!("/api/version/assets/{asset}/download");
    let prefix = url.path().strip_suffix(&path).ok_or("Invalid release proxy URL")?;
    let params: Vec<_> = url.query_pairs().collect();
    if params.len() != 1 || params[0].0 != "tag" || params[0].1 != format!("v{version}") {
        return Err("Update URL must select the exact release tag".into());
    }
    let mut manifest = url.clone();
    manifest.set_path(&format!("{prefix}/api/version/assets/release-security.json/download"));
    let mut signature = url.clone();
    signature.set_path(&format!("{prefix}/api/version/assets/release-security.json.sig/download"));
    Ok((manifest, signature))
}

fn update_http_client(url: &reqwest::Url) -> Result<reqwest::Client, String> {
    ensure_rustls_provider();
    let origin = url.origin();
    reqwest::Client::builder()
        .user_agent(concat!("LambChatDesktop/", env!("CARGO_PKG_VERSION")))
        .connect_timeout(Duration::from_secs(30))
        .timeout(DOWNLOAD_TIMEOUT)
        .redirect(reqwest::redirect::Policy::custom(move |attempt| {
            let target = attempt.url();
            let github = target.scheme() == "https" && target.port_or_known_default() == Some(443) && matches!(target.host_str(), Some("github.com" | "api.github.com" | "objects.githubusercontent.com" | "release-assets.githubusercontent.com"));
            if attempt.previous().len() >= 5 || !target.username().is_empty() || target.password().is_some() || !(target.origin() == origin || github) {
                attempt.error("Untrusted update redirect")
            } else {
                attempt.follow()
            }
        }))
        .build().map_err(|_| "Failed to build update client".into())
}

async fn fetch_release_metadata(client: &reqwest::Client, url: reqwest::Url, limit: usize) -> Result<Vec<u8>, String> {
    let mut response = client.get(url).send().await.map_err(|_| "Release metadata request failed")?;
    if !response.status().is_success() { return Err(format!("Release metadata HTTP {}", response.status())); }
    if response.content_length().is_some_and(|length| length > limit as u64) { return Err("Release metadata too large".into()); }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "Release metadata stream failed")? {
        if bytes.len() + chunk.len() > limit { return Err("Release metadata too large".into()); }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}

fn read_cached_metadata(path: &Path, limit: usize) -> Result<Vec<u8>, String> {
    let metadata = std::fs::symlink_metadata(path).map_err(|_| "Signed release metadata not cached")?;
    if !metadata.is_file() || metadata.len() > limit as u64 { return Err("Invalid cached release metadata".into()); }
    let file = std::fs::File::open(path).map_err(|_| "Cannot read signed release metadata")?;
    let mut bytes = Vec::new();
    file.take(limit as u64 + 1).read_to_end(&mut bytes).map_err(|_| "Cannot read signed release metadata")?;
    if bytes.len() > limit { return Err("Release metadata too large".into()); }
    Ok(bytes)
}

struct PartialDownload(PathBuf);

impl Drop for PartialDownload {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

/// 流式下载并验证签名中的大小和哈希，完成后原子改名；只复用验证通过的缓存。
/// 下载核心与 Tauri 事件解耦，便于用本地 HTTP 服务做单测。
async fn download_update_package<F>(
    url: &str,
    cache_dir: &Path,
    file_name: &str,
    signed: &SignedAsset,
    mut on_progress: F,
) -> Result<(PathBuf, bool), String>
where
    F: FnMut(u64, u64),
{
    std::fs::create_dir_all(cache_dir)
        .map_err(|e| format!("create {}: {e}", cache_dir.display()))?;
    let path = cache_dir.join(file_name);
    if path.is_file() && verify_package(&path, signed).is_ok() {
        // Only verified cached bytes may be reused.
        // 缓存命中：推一次终值进度（UI 直接到 100%），不发网络请求
        let size = path
            .metadata()
            .map(|m| m.len())
            .unwrap_or(0);
        on_progress(size, size);
        return Ok((path, false));
    }

    let source = reqwest::Url::parse(url).map_err(|_| "Invalid update URL")?;
    let client = update_http_client(&source)?;
    let mut resp = client
        .get(url)
        .send()
        .await
        .map_err(|_| "Update download request failed")?;
    if !resp.status().is_success() {
        return Err(format!("download failed: HTTP {}", resp.status()));
    }
    if resp.content_length().is_some_and(|size| size != signed.size) {
        return Err("Update package size does not match signed release".into());
    }
    let content_length = signed.size;
    let part_path = cache_dir.join(format!("{file_name}.{}.part", uuid::Uuid::new_v4()));
    let _partial = PartialDownload(part_path.clone());
    let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(&part_path)
        .map_err(|e| format!("create {}: {e}", part_path.display()))?;

    let mut downloaded: u64 = 0;
    let mut wrote_any = false;
    let mut last_emit: Option<Instant> = None;
    while let Some(chunk) = resp
        .chunk()
        .await
        .map_err(|_| "Update download stream failed")?
    {
        if chunk.is_empty() {
            continue;
        }
        if downloaded + chunk.len() as u64 > signed.size {
            drop(file);
            let _ = std::fs::remove_file(&part_path);
            return Err("Update package exceeds signed size".into());
        }
        file.write_all(&chunk)
            .map_err(|e| format!("write {}: {e}", part_path.display()))?;
        downloaded += chunk.len() as u64;
        wrote_any = true;
        if last_emit.is_none_or(|t| t.elapsed() >= PROGRESS_THROTTLE) {
            on_progress(downloaded, content_length);
            last_emit = Some(Instant::now());
        }
    }
    if !wrote_any {
        let _ = std::fs::remove_file(&part_path);
        return Err("download produced no content".into());
    }
    file.flush()
        .map_err(|e| format!("flush {}: {e}", part_path.display()))?;
    drop(file);
    if let Err(error) = verify_package(&part_path, signed) {
        let _ = std::fs::remove_file(&part_path);
        return Err(error);
    }
    // 完整落盘后才改终名（= 完整性标记），并顺手清掉旧版本残留包
    std::fs::rename(&part_path, &path)
        .map_err(|e| format!("finalize {}: {e}", path.display()))?;
    remove_stale_packages(cache_dir, &path);
    // 收尾事件：让 UI 的 downloaded/content_length 落到终值
    on_progress(downloaded, content_length);
    Ok((path, true))
}

/// 调起安装器（argv[0] 为程序名：pkcon 直接跑，apt/dnf 等由 pkexec 拉起）。
///
/// stderr 由独立线程持续排空（dnf 进度输出可超管道缓冲，不排空会写阻塞
/// → 安装挂死）；stdout 丢弃（GUI 壳无处展示）。超时 kill 兜底。
fn run_pkexec_installer(argv: &[String]) -> Result<(), String> {
    let mut child = Command::new(&argv[0])
        .args(&argv[1..])
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| {
            format!(
                "failed to spawn {} ({e}); 系统缺少 polkit 授权组件，\
                 请从下载页手动安装新版安装包",
                argv[0]
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

/// 下载 deb/rpm 更新包到版本化缓存（进度经 linux-update-progress 事件）。
/// 重新验证发布签名与缓存哈希；缓存命中不重复下载安装包，返回 false。
#[tauri::command]
pub async fn download_linux_package(
    app: AppHandle,
    url: String,
    asset_name: String,
) -> Result<bool, String> {
    let arch = release_asset_arch().ok_or("Unsupported Linux architecture")?;
    let version = package_version(&asset_name, arch)?;
    let (manifest_url, signature_url) = signed_metadata_urls(&url, &asset_name, &version)?;
    let client = update_http_client(&manifest_url)?;
    let manifest = fetch_release_metadata(&client, manifest_url, MAX_MANIFEST_BYTES).await?;
    let signature = fetch_release_metadata(&client, signature_url, 64).await?;
    let signed = verify_release(&manifest, &signature, &version, &asset_name, env!("CARGO_PKG_VERSION"))?;
    let app_for_progress = app.clone();
    let (_path, downloaded) = download_update_package(
        &url,
        &update_cache_dir(),
        &asset_name,
        &signed,
        move |downloaded, content_length| {
            let _ = app_for_progress.emit(
                PROGRESS_EVENT,
                ProgressPayload {
                    downloaded,
                    content_length,
                },
            );
        },
    )
    .await?;
    let cache = update_cache_dir();
    std::fs::write(cache.join(format!("{asset_name}.security.json")), manifest).map_err(|_| "Cannot cache release signature")?;
    std::fs::write(cache.join(format!("{asset_name}.security.sig")), signature).map_err(|_| "Cannot cache release signature")?;
    Ok(downloaded)
}

/// 从缓存安装 deb/rpm 更新包（pkcon → pkexec 包管理器 → 底层工具三级
/// 回退；成功后清空缓存，调用方 relaunch 进新版）。
#[tauri::command]
pub async fn install_linux_package(asset_name: String, kind: String) -> Result<(), String> {
    if kind != SOURCE_DEB && kind != SOURCE_RPM {
        return Err(format!("unsupported package kind: {kind}"));
    }
    let arch = release_asset_arch().ok_or("Unsupported Linux architecture")?;
    let version = package_version(&asset_name, arch)?;
    if !asset_name.ends_with(&format!(".{kind}")) { return Err("Update package kind mismatch".into()); }
    let cache = update_cache_dir();
    let manifest = read_cached_metadata(&cache.join(format!("{asset_name}.security.json")), MAX_MANIFEST_BYTES)?;
    let signature = read_cached_metadata(&cache.join(format!("{asset_name}.security.sig")), 64)?;
    let signed = verify_release(&manifest, &signature, &version, &asset_name, env!("CARGO_PKG_VERSION"))?;
    let path = cache.join(&asset_name);
    verify_package(&path, &signed)?;

    let chains = installer_argv_chain(&kind, &path)
        .ok_or_else(|| format!("unsupported package kind: {kind}"))?;
    let mut last_err = String::new();
    for argv in chains {
        // pkexec/pkcon 授权是阻塞轮询（≤20min 授权窗口），挪出 async 线程
        let argv_clone = argv.clone();
        let result =
            tauri::async_runtime::spawn_blocking(move || run_pkexec_installer(&argv_clone))
                .await;
        match result {
            Ok(Ok(())) => {
                // 装完即清：新版本已生效，缓存使命完成
                clear_update_cache(&update_cache_dir());
                return Ok(());
            }
            Ok(Err(e)) => last_err = e,
            Err(e) => last_err = format!("installer task failed: {e}"),
        }
    }
    Err(format!("all install attempts failed; last: {last_err}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn linux_release_identity_rejects_wrong_arch_and_paths() {
        assert_eq!(package_version("LambChat-v2.15.0-Linux-arm64.deb", "arm64").unwrap(), "2.15.0");
        for asset in ["LambChat-v2.15.0-Linux-x86_64.deb", "../package.deb", "LambChat-vbad-Linux-arm64.deb", "LambChat-v2.15.0-Linux-arm64.exe"] {
            assert!(package_version(asset, "arm64").is_err());
        }
    }

    #[test]
    fn signature_urls_keep_exact_package_release_and_proxy_path() {
        let asset = "LambChat-v2.15.0-Linux-arm64.deb";
        let url = format!("https://lambchat.com/api/version/assets/{asset}/download?tag=v2.15.0");
        let urls = signed_metadata_urls(&url, asset, "2.15.0").unwrap();
        assert_eq!(urls.0.as_str(), "https://lambchat.com/api/version/assets/release-security.json/download?tag=v2.15.0");
        assert_eq!(urls.1.as_str(), "https://lambchat.com/api/version/assets/release-security.json.sig/download?tag=v2.15.0");
        for url in [format!("http://evil.example/api/version/assets/{asset}/download?tag=v2.15.0"), format!("https://lambchat.com/api/version/assets/{asset}/download?tag=v2.14.0"), format!("https://lambchat.com/arbitrary?tag=v2.15.0"), format!("https://user:pass@lambchat.com/api/version/assets/{asset}/download?tag=v2.15.0")] {
            assert!(signed_metadata_urls(&url, asset, "2.15.0").is_err());
        }
    }

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
    fn installer_argv_chain_falls_back_pkcon_then_manager_then_lowlevel() {
        let deb = installer_argv_chain(SOURCE_DEB, Path::new("/cache/lambchat-update.deb")).unwrap();
        assert_eq!(
            deb[0],
            vec!["pkcon", "install-local", "-y", "/cache/lambchat-update.deb"]
        );
        assert_eq!(
            deb[1],
            vec!["pkexec", "apt", "install", "-y", "/cache/lambchat-update.deb"]
        );
        assert_eq!(
            deb[2],
            vec!["pkexec", "dpkg", "-i", "/cache/lambchat-update.deb"]
        );
        let rpm = installer_argv_chain(SOURCE_RPM, Path::new("/cache/x.rpm")).unwrap();
        assert_eq!(rpm[0][0], "pkcon");
        assert_eq!(rpm[1], vec!["pkexec", "dnf", "install", "-y", "/cache/x.rpm"]);
        assert_eq!(
            rpm[2],
            vec!["pkexec", "rpm", "-U", "--replacepkgs", "/cache/x.rpm"]
        );
        assert!(installer_argv_chain(SOURCE_APPIMAGE, Path::new("/tmp/x")).is_none());
        assert!(installer_argv_chain("exe", Path::new("/tmp/x")).is_none());
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

    /// 每个用例独立的缓存目录（测试不污染真实 ~/.cache，也不互相干扰）。
    fn test_cache_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "lambchat-rs-test-{}-{}-{tag}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn async_runtime_block_on_works_in_test_harness() {
        assert_eq!(tauri::async_runtime::block_on(async { 7 }), 7);
    }

    fn signed_asset(body: &[u8]) -> crate::release_signature::SignedAsset {
        crate::release_signature::SignedAsset {
            size: body.len() as u64,
            sha256: ring::digest::digest(&ring::digest::SHA256, body).as_ref().iter().map(|b| format!("{b:02x}")).collect(),
        }
    }

    #[test]
    fn download_rejects_unsigned_bytes_and_oversize_body() {
        for body in [b"evil".as_slice(), b"good-plus".as_slice()] {
            let url = spawn_chunked_http_server("HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n", body);
            let dir = test_cache_dir("forged");
            assert!(tauri::async_runtime::block_on(download_update_package(&url, &dir, "package.deb", &signed_asset(b"good"), |_, _| {})).is_err());
            assert!(!dir.join("package.deb").exists());
            let _ = std::fs::remove_dir_all(dir);
        }
    }

    #[test]
    fn interrupted_download_removes_partial_file() {
        let url = spawn_chunked_http_server("HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\n", b"short");
        let dir = test_cache_dir("interrupted");
        assert!(tauri::async_runtime::block_on(download_update_package(&url, &dir, "package.deb", &signed_asset(b"package"), |_, _| {})).is_err());
        assert_eq!(std::fs::read_dir(&dir).unwrap().count(), 0, "failed stream must not leave partial bytes");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn download_streams_to_cache_and_clears_stale_versions() {
        let body: Vec<u8> = (0..100_000u32).map(|i| (i % 251) as u8).collect();
        let head = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nContent-Type: application/vnd.debian.binary-package\r\nConnection: close\r\n\r\n",
            body.len()
        );
        let url = spawn_chunked_http_server(&head, &body);
        let dir = test_cache_dir("download");
        // 旧版本残留包：新包下载完成后应被清掉
        let stale = dir.join("LambChat-v9.9.9-Linux-x86_64.deb");
        std::fs::write(&stale, b"stale").unwrap();

        let (path, downloaded) = tauri::async_runtime::block_on(download_update_package(
            &url,
            &dir,
            "LambChat-v2.99.0-Linux-x86_64.deb",
            &signed_asset(&body),
            |d, c| {
                assert!(c == body.len() as u64, "content_length mismatch");
                let _ = d;
            },
        ))
        .expect("download should succeed");
        assert!(downloaded, "fresh download must report downloaded=true");

        let written = std::fs::read(&path).expect("cached file readable");
        assert_eq!(written, body, "downloaded bytes must match served body");
        assert!(!dir.join("LambChat-v2.99.0-Linux-x86_64.deb.part").exists());
        assert!(!stale.exists(), "stale version package must be removed");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn cached_package_skips_download_without_network() {
        // 不起 HTTP 服务：缓存命中路径必须零网络请求（起服务反而掩盖不了——
        // 连接必然失败，测试即红）
        let dir = test_cache_dir("cache-hit");
        let cached = dir.join("LambChat-v2.99.0-Linux-x86_64.deb");
        std::fs::write(&cached, b"cached-bytes").unwrap();

        let mut progress_calls = 0u32;
        let (path, downloaded) = tauri::async_runtime::block_on(download_update_package(
            "http://127.0.0.1:1/never-reached",
            &dir,
            "LambChat-v2.99.0-Linux-x86_64.deb",
            &signed_asset(b"cached-bytes"),
            |_d, _c| progress_calls += 1,
        ))
        .expect("cache hit must succeed without network");
        assert!(!downloaded, "cache hit must report downloaded=false");
        assert_eq!(path, cached);
        assert!(progress_calls >= 1, "cache hit still emits final progress");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn download_surfaces_http_error_status_and_keeps_no_partial() {
        let head = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        let url = spawn_chunked_http_server(head, b"");
        let dir = test_cache_dir("404");
        let err = tauri::async_runtime::block_on(download_update_package(
            &url,
            &dir,
            "LambChat-v2.99.0-Linux-x86_64.deb",
            &signed_asset(b"package"),
            |_, _| {},
        ))
        .expect_err("404 must fail");
        assert!(err.contains("404"), "error should carry status: {err}");
        assert!(
            !dir.join("LambChat-v2.99.0-Linux-x86_64.deb").exists(),
            "failed download must not leave a finalized package"
        );
        let _ = std::fs::remove_dir_all(&dir);
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
