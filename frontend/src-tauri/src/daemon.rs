//! LambChat 本地沙箱 daemon 的生命周期托管。
//!
//! 启动优先级：
//! 1. 环境变量 `LAMBCHAT_DAEMON_BIN` 指向的外部可执行（dev 回退路径）；
//! 2. 打包内 sidecar（`binaries/lambchat-daemon-<target-triple>`，由
//!    `tauri.conf.json` 的 `bundle.externalBin` 打入）。
//!
//! 两者皆不可用时壳照常运行（仅告警），前端通过 `daemon_process_status`
//! 展示"未运行"引导。意外退出自动重启，上限 [`MAX_RESTARTS`] 次；
//! 主动 [`stop`] 不触发重启。

use std::sync::atomic::{AtomicBool, AtomicU64, AtomicU8, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// 意外退出后的自动重启次数上限。
const MAX_RESTARTS: u8 = 3;

/// env 直启监视线轮询子进程存活的间隔。
const ENV_POLL_INTERVAL: Duration = Duration::from_millis(500);

macro_rules! warn_log {
    ($($arg:tt)*) => {
        eprintln!("[lambchat-daemon] {}", format!($($arg)*))
    };
}

/// 当前托管的 daemon 子进程（env 直启或 sidecar 两种形态）。
enum DaemonChild {
    /// `LAMBCHAT_DAEMON_BIN` 直启（dev 回退），标准库句柄。
    Env(std::process::Child),
    /// shell 插件托管的 sidecar 句柄。
    Sidecar(CommandChild),
}

/// daemon 生命周期状态（挂到 Tauri managed state）。
pub struct DaemonManager {
    child: Mutex<Option<DaemonChild>>,
    /// 意外退出后的已重启次数。
    restarts: AtomicU8,
    /// 每次 start/stop 递增；监视线据此判断退出事件是否仍属于"当前这代"进程，
    /// 避免 stop 之后的迟到退出事件被误判为意外退出而触发重启。
    generation: AtomicU64,
    /// 无任何可用 daemon 可执行（无 env 覆盖且 sidecar 缺失）时置位。
    unsupported: AtomicBool,
}

impl Default for DaemonManager {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            restarts: AtomicU8::new(0),
            generation: AtomicU64::new(0),
            unsupported: AtomicBool::new(false),
        }
    }
}

/// 启动 daemon。已在运行时为幂等 no-op。
///
/// 需在 tokio 运行时上下文中调用（sidecar spawn 依赖 runtime）。
pub fn start(app: &AppHandle) -> Result<(), String> {
    let manager = app.state::<DaemonManager>();
    {
        let child = manager.child.lock().unwrap();
        if child.is_some() {
            return Ok(());
        }
    }
    let generation = manager.generation.fetch_add(1, Ordering::SeqCst) + 1;

    // 优先 dev 回退：外部可执行（如 uv 包装脚本）。
    if let Some(env_bin) = std::env::var_os("LAMBCHAT_DAEMON_BIN") {
        match std::process::Command::new(&env_bin).spawn() {
            Ok(child) => {
                warn_log!(
                    "daemon started from LAMBCHAT_DAEMON_BIN={} (pid {})",
                    env_bin.to_string_lossy(),
                    child.id()
                );
                *manager.child.lock().unwrap() = Some(DaemonChild::Env(child));
                manager.unsupported.store(false, Ordering::SeqCst);
                spawn_env_monitor(app.clone(), generation);
                return Ok(());
            }
            Err(e) => {
                manager.unsupported.store(true, Ordering::SeqCst);
                return Err(format!(
                    "failed to spawn LAMBCHAT_DAEMON_BIN={}: {e}",
                    env_bin.to_string_lossy()
                ));
            }
        }
    }

    // 常规路径：随壳分发的 sidecar（经 shell 插件解析 target-triple 后 spawn）。
    let spawn_result = app
        .shell()
        .sidecar("lambchat-daemon")
        .map_err(|e| format!("sidecar binary not available: {e}"))?
        .spawn();
    let (mut rx, child) = match spawn_result {
        Ok(pair) => pair,
        Err(e) => {
            manager.unsupported.store(true, Ordering::SeqCst);
            return Err(format!("failed to spawn lambchat-daemon sidecar: {e}"));
        }
    };
    warn_log!("daemon sidecar started (pid {})", child.pid());
    *manager.child.lock().unwrap() = Some(DaemonChild::Sidecar(child));
    manager.unsupported.store(false, Ordering::SeqCst);

    let monitor_app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if matches!(event, CommandEvent::Terminated { .. }) {
                break;
            }
        }
        handle_exit(&monitor_app, generation);
    });
    Ok(())
}

/// 停止 daemon：kill 子进程、清理句柄、重启计数归零。幂等。
pub fn stop(app: &AppHandle) {
    let manager = app.state::<DaemonManager>();
    // 先递增 generation，使在飞行的监视线失效（不触发重启）。
    manager.generation.fetch_add(1, Ordering::SeqCst);
    let mut slot = manager.child.lock().unwrap();
    match slot.take() {
        Some(DaemonChild::Env(mut child)) => {
            warn_log!("stopping daemon (pid {})", child.id());
            let _ = child.kill();
            let _ = child.wait();
        }
        Some(DaemonChild::Sidecar(child)) => {
            warn_log!("stopping daemon sidecar (pid {})", child.pid());
            if let Err(e) = child.kill() {
                warn_log!("failed to kill daemon sidecar: {e}");
            }
        }
        None => {}
    }
    manager.restarts.store(0, Ordering::SeqCst);
}

/// 进程状态：`"running" | "stopped" | "unsupported"`。
pub fn status(app: &AppHandle) -> &'static str {
    let manager = app.state::<DaemonManager>();
    if manager.child.lock().unwrap().is_some() {
        "running"
    } else if manager.unsupported.load(Ordering::SeqCst) {
        "unsupported"
    } else {
        "stopped"
    }
}

/// env 直启子进程的监视线：轮询 `try_wait`，退出后走统一的 [`handle_exit`]。
fn spawn_env_monitor(app: AppHandle, generation: u64) {
    tauri::async_runtime::spawn_blocking(move || {
        loop {
            std::thread::sleep(ENV_POLL_INTERVAL);
            let manager = app.state::<DaemonManager>();
            if manager.generation.load(Ordering::SeqCst) != generation {
                return; // 槽位已被新一轮 start/stop 接管
            }
            let mut slot = manager.child.lock().unwrap();
            match slot.as_mut() {
                Some(DaemonChild::Env(child)) => match child.try_wait() {
                    Ok(Some(_)) | Err(_) => break,
                    Ok(None) => {}
                },
                // 槽位形态变化（不可能在同代发生，防御性退出）
                _ => return,
            }
        }
        handle_exit(&app, generation);
    });
}

/// 子进程退出后的统一处理：仅当退出事件仍属于当前 generation 时才视为意外退出。
fn handle_exit(app: &AppHandle, generation: u64) {
    let manager = app.state::<DaemonManager>();
    if manager.generation.load(Ordering::SeqCst) != generation {
        return; // 已被 stop() 或新一轮 start() 接管，交由新逻辑负责
    }
    manager.child.lock().unwrap().take();

    let restarts = manager.restarts.fetch_add(1, Ordering::SeqCst);
    if restarts >= MAX_RESTARTS {
        warn_log!(
            "daemon exited unexpectedly and restart budget ({MAX_RESTARTS}) exhausted; giving up"
        );
        return;
    }
    warn_log!(
        "daemon exited unexpectedly; restarting ({}/{MAX_RESTARTS})",
        restarts + 1
    );
    if let Err(e) = start(app) {
        warn_log!("daemon restart failed: {e}");
    }
}
