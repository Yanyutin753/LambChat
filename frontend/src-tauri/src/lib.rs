use std::fs;
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

/// 把随包分发的 PBS 归档落位到 daemon 约定读取的位置（M4 T4 约定 / T8 补齐）。
///
/// - 源：`resource_dir()/resources/python/python.tar.gz`——`bundle.resources =
///   ["resources/python/"]` 经 tauri-build（dev：copy 到 target/<profile>）与
///   bundler（打包：保相对路径进 $RESOURCE）落在同一相对结构，dev 与打包
///   形态同构；
/// - 目标：`~/.lambchat/resources/python/python.tar.gz`（daemon 侧
///   `pbs.DEFAULT_RESOURCES_DIR` 只认这里，daemon 不感知壳的 resources 路径）；
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
    let src = resource_dir
        .join("resources")
        .join("python")
        .join("python.tar.gz");
    if !src.is_file() {
        return; // 无归档：静默跳过（daemon 回退系统 PATH）
    }
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
    match fs::copy(&src, &dest) {
        Ok(bytes) => eprintln!(
            "[lambchat] seeded PBS runtime archive to {} ({bytes} bytes)",
            dest.display()
        ),
        Err(e) => eprintln!(
            "[lambchat] failed to seed PBS runtime archive to {}: {e}",
            dest.display()
        ),
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
