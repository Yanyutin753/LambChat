use std::fs;
use std::path::{Path, PathBuf};
use tauri::Manager;

mod daemon;
mod tray;

/// SIGTERM 停机旗标：信号处理器只做原子置位（async-signal-safe 的唯一动作），
/// 专用线程轮询后经 `app.exit(0)` 走正常退出路径（M4 T8）。
#[cfg(unix)]
static SIGTERM_SEEN: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

#[cfg(unix)]
extern "C" fn handle_sigterm(_sig: libc::c_int) {
    SIGTERM_SEEN.store(true, std::sync::atomic::Ordering::SeqCst);
}

/// 注册 SIGTERM 处理器（`sigaction` + SA_RESTART，与 glibc `signal` 语义一致）。
#[cfg(unix)]
fn arm_sigterm_handler() {
    let handler = handle_sigterm as *const () as libc::sighandler_t;
    unsafe {
        let mut action: libc::sigaction = std::mem::zeroed();
        action.sa_sigaction = handler;
        action.sa_flags = libc::SA_RESTART;
        if libc::sigaction(libc::SIGTERM, &action, std::ptr::null_mut()) != 0 {
            let err = std::io::Error::last_os_error();
            eprintln!("[lambchat] failed to arm SIGTERM handler: {err}");
        }
    }
}

/// 注册 SIGTERM 处理器（unix）：`kill -TERM` 壳 → 与关窗同一条优雅退出路径。
///
/// Tauri v2 无内置 POSIX 信号钩子（v2 核心没有 signal API），常规做法是
/// ctrlc/signal-hook crate——这里用已有的 libc 依赖（sigaction + 原子旗标 +
/// 100ms 轮询线程）零新增依赖实现（T8 自测发现 kill -TERM 壳时 daemon 树
/// 存活，本函数补齐该路径）。信号处理器只做原子置位（async-signal-safe 的
/// 唯一动作）；`app.exit(0)` → RunEvent::Exit → `daemon::stop`（SIGTERM
/// 优雅停 daemon），随后进程退出——与窗口关闭/托盘退出共用同一出口。
/// Windows GUI 进程无 SIGTERM 语义，整体不挂载。
///
/// 实测（M4 T8）：SIGTERM → 壳内 0.1s 检出 → daemon post_offline → 服务端
/// status 在 **0.14s** 内翻 offline（旧路径：壳默认终止、daemon 孤儿存活）。
#[cfg(unix)]
fn install_sigterm_handler(app: tauri::AppHandle) {
    use std::sync::atomic::Ordering;
    arm_sigterm_handler();
    std::thread::Builder::new()
        .name("lambchat-sigterm".to_string())
        .spawn(move || loop {
            if SIGTERM_SEEN.load(Ordering::SeqCst) {
                eprintln!("[lambchat] SIGTERM received; stopping daemon and exiting");
                app.exit(0);
                return;
            }
            std::thread::sleep(std::time::Duration::from_millis(100));
        })
        .expect("failed to spawn SIGTERM watcher thread");
}

/// 当前平台的 PBS 平台标签（与 `client/scripts/fetch-pbs.py` 的
/// `PLATFORM_TRIPLES` 键一一对应；每个发布包只内嵌当前平台的归档）。
fn current_platform_tag() -> Option<&'static str> {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("linux", "x86_64") => Some("linux-x86_64"),
        ("linux", "aarch64") => Some("linux-aarch64"),
        ("windows", "x86_64") => Some("windows-x86_64"),
        ("macos", "aarch64") => Some("macos-arm64"),
        ("macos", "x86_64") => Some("macos-x64"),
        _ => None,
    }
}

/// 在壳 resources 里定位 PBS 归档（纯路径逻辑，可测试）。
///
/// 优先平台子目录布局 `resources/python/<platform-tag>/python.tar.gz`
/// （`bundle.resources = ["resources/python/"]` 打包时保相对结构分发，
/// fetch-pbs.py 的产物即此布局）；回退扁平 `resources/python/python.tar.gz`
/// （dev 手工放位 / 旧约定兼容）。均缺失返回 `None`。
fn pbs_resource_archive(resource_dir: &Path) -> Option<PathBuf> {
    let python_dir = resource_dir.join("resources").join("python");
    if let Some(tag) = current_platform_tag() {
        let tagged = python_dir.join(tag).join("python.tar.gz");
        if tagged.is_file() {
            return Some(tagged);
        }
    }
    let flat = python_dir.join("python.tar.gz");
    flat.is_file().then_some(flat)
}

/// 把随包分发的 PBS 归档落位到 daemon 约定读取的位置（M4 T4 约定 / T8 补齐 /
/// T9 对齐平台子目录布局 + 原子落位）。
///
/// - 源：[`pbs_resource_archive`]（平台子目录优先，扁平回退）——dev 与打包
///   形态同构；
/// - 目标：`~/.lambchat/resources/python/python.tar.gz`（daemon 侧
///   `pbs.DEFAULT_RESOURCES_DIR` 只认这里，daemon 不感知壳的 resources 路径）；
/// - 落位原子性：先拷贝到同目录 `.part` 再 rename——归档 ~111MB，非原子
///   fs::copy 半途崩溃会留下截断文件被 daemon 当真归档（T8 审查 Low）；
/// - 幂等：目标已在或源缺失（dev 未 fetch / 纯净安装）时 no-op，daemon 回退
///   系统 PATH；升级换新归档由打包/升级流程负责清目录。
fn seed_pbs_runtime_resource(app: &tauri::AppHandle) {
    let resource_dir = match app.path().resource_dir() {
        Ok(dir) => dir,
        Err(e) => {
            eprintln!("[lambchat] resource dir unavailable ({e}); skipping PBS runtime seed");
            return;
        }
    };
    let src = match pbs_resource_archive(&resource_dir) {
        Some(src) => src,
        None => return, // 无归档：静默跳过（daemon 回退系统 PATH）
    };
    let home = match daemon::sandbox_home() {
        Ok(home) => home,
        Err(e) => {
            eprintln!("[lambchat] {e}; skipping PBS runtime seed");
            return;
        }
    };
    let dest = home
        .join("resources")
        .join("python")
        .join("python.tar.gz");
    if dest.exists() {
        return; // 已落位：幂等
    }
    if let Some(parent) = dest.parent() {
        if let Err(e) = fs::create_dir_all(parent) {
            eprintln!("[lambchat] failed to create {}: {e}", parent.display());
            return;
        }
    }
    // 同目录 .part 中转 + rename 原子可见（与 fetch-pbs.py 的下载落位同款约定）
    let tmp = dest.with_file_name("python.tar.gz.part");
    match fs::copy(&src, &tmp)
        .and_then(|bytes| fs::rename(&tmp, &dest).map(|_| bytes))
    {
        Ok(bytes) => eprintln!(
            "[lambchat] seeded PBS runtime archive to {} ({bytes} bytes)",
            dest.display()
        ),
        Err(e) => {
            let _ = fs::remove_file(&tmp); // 半截中转文件不留
            eprintln!(
                "[lambchat] failed to seed PBS runtime archive to {}: {e}",
                dest.display()
            );
        }
    }
}

/// On version upgrade, clean webview data so the user starts fresh.
fn clean_on_version_upgrade(app_handle: &tauri::AppHandle) {
    let app_dir = app_handle
        .path()
        .app_data_dir()
        .expect("failed to resolve app data dir");
    let version_file = app_dir.join(".installed-version");
    let current_version = env!("CARGO_PKG_VERSION");

    let should_clean = if version_file.exists() {
        match fs::read_to_string(&version_file) {
            Ok(prev) if prev.trim() != current_version => true,
            Ok(_) => false,
            Err(_) => true,
        }
    } else {
        true
    };

    if should_clean {
        let _ = fs::create_dir_all(&app_dir);
        if let Ok(entries) = fs::read_dir(&app_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                // Remove everything except the version file itself
                if path.file_name().map_or(false, |n| {
                    n != ".installed-version"
                }) {
                    let _ = fs::remove_dir_all(&path);
                }
            }
        }
    }

    // Always write current version
    let _ = fs::write(&version_file, current_version);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        // process 插件：updater 安装完成后前端 `relaunch()` 重启壳
        // （useAutoUpdate 依赖；缺此注册 + capability，更新后自动重启会失败）。
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            clean_on_version_upgrade(app.handle());
            app.manage(daemon::DaemonManager::default());
            // SIGTERM 优雅退出路径（unix）：kill -TERM → app.exit(0) → Exit 事件
            // → daemon::stop（与关窗路径同一出口）。
            #[cfg(unix)]
            install_sigterm_handler(app.handle().clone());
            // daemon 托管启动：失败仅告警，不阻塞壳（前端展示"未运行"引导）。
            // PBS 归档先落位（一次性），daemon 首启即可解压装配内嵌运行时。
            let handle = app.handle().clone();
            tauri::async_runtime::spawn_blocking(move || {
                seed_pbs_runtime_resource(&handle);
                if let Err(e) = daemon::start(&handle) {
                    eprintln!("[lambchat-daemon] failed to start daemon: {e}");
                }
            });
            // 托盘：构建失败（如缺 appindicator 运行库）仅告警，不影响主窗口。
            tray::init(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            daemon::save_pairing,
            daemon::write_confirm_policy,
            daemon::clear_pairing,
            daemon::read_pairing_pat,
            daemon::restart_daemon,
            daemon::daemon_process_status,
            daemon::open_local_path
        ])
        .build(tauri::generate_context!())
        .expect("error while building LambChat desktop app")
        .run(|app_handle, event| {
            // 退出路径：托管 kill daemon（窗口关闭 / 托盘退出 / app.exit 均会走到）。
            if let tauri::RunEvent::Exit = event {
                daemon::stop(app_handle);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    /// PBS 归档定位：平台子目录布局优先，扁平布局回退（M4 T9 对齐
    /// fetch-pbs.py 产物随 bundle.resources 保相对结构分发的真实链路）。
    #[test]
    fn pbs_resource_archive_prefers_platform_subdir_then_flat() {
        let tmp = std::env::temp_dir().join(format!(
            "lambchat-pbs-lookup-test-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&tmp);

        // 空目录：无归档
        fs::create_dir_all(tmp.join("resources").join("python")).unwrap();
        assert!(pbs_resource_archive(&tmp).is_none());

        // 平台子目录布局（fetch-pbs.py → tauri bundle 的真实形态）
        if let Some(tag) = current_platform_tag() {
            let tagged = tmp.join("resources").join("python").join(tag).join("python.tar.gz");
            fs::create_dir_all(tagged.parent().unwrap()).unwrap();
            fs::write(&tagged, b"tagged").unwrap();
            assert_eq!(pbs_resource_archive(&tmp), Some(tagged));
        } else {
            // 未映射平台不得误报
            assert!(pbs_resource_archive(&tmp).is_none());
        }

        // 扁平布局回退（dev 手工放位 / 旧约定兼容）
        let _ = fs::remove_dir_all(tmp.join("resources"));
        let flat = tmp.join("resources").join("python").join("python.tar.gz");
        fs::create_dir_all(flat.parent().unwrap()).unwrap();
        fs::write(&flat, b"flat").unwrap();
        assert_eq!(pbs_resource_archive(&tmp), Some(flat));

        let _ = fs::remove_dir_all(&tmp);
    }

    /// 平台标签映射：与 fetch-pbs.py 的 PLATFORM_TRIPLES 键一致（五平台词汇表）。
    #[test]
    fn current_platform_tag_matches_fetch_pbs_vocabulary() {
        let expected = if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
            "linux-x86_64"
        } else if cfg!(all(target_os = "linux", target_arch = "aarch64")) {
            "linux-aarch64"
        } else if cfg!(all(target_os = "windows", target_arch = "x86_64")) {
            "windows-x86_64"
        } else if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
            "macos-arm64"
        } else if cfg!(all(target_os = "macos", target_arch = "x86_64")) {
            "macos-x64"
        } else {
            panic!("unsupported target for platform tag test");
        };
        assert_eq!(current_platform_tag(), Some(expected));
    }
}
