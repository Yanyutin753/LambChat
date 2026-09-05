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

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicU8, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// 意外退出后的自动重启次数上限。
const MAX_RESTARTS: u8 = 3;

/// 监视线轮询间隔（env 直启 try_wait / sidecar kill(pid,0) 探活共用）。
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
    /// 每次 start/stop 递增（**一律持有 `child` 锁**，stop 亦然——递增点
    /// 必须与 [`DaemonManager::take_if_current`] 的持锁复检配对，否则迟到
    /// 的退出事件可在锁缝里 take 掉新代子进程）；监视线据此判断退出事件
    /// 是否仍属于"当前这代"进程，避免 stop 之后的迟到退出事件被误判为
    /// 意外退出而触发重启。
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

impl DaemonManager {
    /// 子进程退出事件的归属判定：**持锁复检** generation 后取走槽位。
    ///
    /// 返回 `Some(child)` 表示退出事件确属该代（槽位已取走）；`None` 表示
    /// 已被新一轮 start/stop 接管（或同代槽位已被处理过），调用方不得动
    /// 槽位也不得重启。
    ///
    /// 并发正确性：generation 的所有递增点（start/stop）都持有 `child` 锁，
    /// 因此「读 generation + take 槽位」必须同样全程持锁——若在锁外读
    /// generation、锁内才 take（旧写法），restart_daemon 恰好落在两步之间时
    /// （stop 清槽递增、start 装入新子进程再递增），迟到的 handle_exit 会
    /// take 掉**新代**子进程的句柄：新进程从此无人 stop 成为孤儿，随后的
    /// 重启逻辑再拉起一个 daemon——双实例。持锁复检后，generation 仍等于
    /// 该代就意味着锁的互斥性保证没有任何 start/stop 发生过，槽位必然
    /// 属于这一代（回归锚点：tests::take_if_current_never_takes_slot_of_newer_generation）。
    fn take_if_current(&self, generation: u64) -> Option<DaemonChild> {
        let mut slot = self.child.lock().unwrap();
        if self.generation.load(Ordering::SeqCst) != generation {
            return None;
        }
        slot.take()
    }
}

/// 启动 daemon。已在运行时为幂等 no-op。
///
/// 需在 tokio 运行时上下文中调用（sidecar spawn 依赖 runtime）。
///
/// 并发正确性（单一临界区）：「空槽检查 + spawn + 记录 + 启动监视线」全程
/// 持有 `child` 锁。若只在检查时短暂持锁（曾经的写法），`restart_daemon`
/// 命令（IPC 线程）与意外退出的监视线（tokio worker）可能同时进入 start、
/// 都观察到空槽而各自 spawn——后写者覆盖先写者的 `CommandChild` 句柄，
/// 被覆盖的 daemon 进程从此无人 stop，成为孤儿。锁内没有任何 await 或
/// 长阻塞：spawn 是同步调用，两个监视线（async / spawn_blocking）都是
/// fire-and-forget，且它们回到这把锁之前必须先观察到进程退出事件，
/// 最多在锁上短暂等待本临界区返回，不会死锁。
pub fn start(app: &AppHandle) -> Result<(), String> {
    let manager = app.state::<DaemonManager>();
    let mut slot = manager.child.lock().unwrap();
    if slot.is_some() {
        return Ok(());
    }
    let generation = manager.generation.fetch_add(1, Ordering::SeqCst) + 1;

    // 优先 dev 回退：外部可执行（如 uv 包装脚本）。子命令 `run` = 常驻 daemon 模式。
    if let Some(env_bin) = std::env::var_os("LAMBCHAT_DAEMON_BIN") {
        return match std::process::Command::new(&env_bin).arg("run").spawn() {
            Ok(child) => {
                warn_log!(
                    "daemon started from LAMBCHAT_DAEMON_BIN={} (pid {})",
                    env_bin.to_string_lossy(),
                    child.id()
                );
                *slot = Some(DaemonChild::Env(child));
                manager.unsupported.store(false, Ordering::SeqCst);
                spawn_env_monitor(app.clone(), generation);
                Ok(())
            }
            Err(e) => {
                manager.unsupported.store(true, Ordering::SeqCst);
                Err(format!(
                    "failed to spawn LAMBCHAT_DAEMON_BIN={}: {e}",
                    env_bin.to_string_lossy()
                ))
            }
        };
    }

    // 常规路径：随壳分发的 sidecar（经 shell 插件解析 target-triple 后 spawn）。
    // 子命令 `run` = 常驻 daemon 模式（未配对时 daemon 自行快速退出，
    // 由重启上限收敛；配对完成后的 restart_daemon 会再次拉起）。
    let spawn_result = app
        .shell()
        .sidecar("lambchat-daemon")
        .map_err(|e| format!("sidecar binary not available: {e}"))?
        .args(["run"])
        .spawn();
    let (mut rx, child) = match spawn_result {
        Ok(pair) => pair,
        Err(e) => {
            manager.unsupported.store(true, Ordering::SeqCst);
            return Err(format!("failed to spawn lambchat-daemon sidecar: {e}"));
        }
    };
    warn_log!("daemon sidecar started (pid {})", child.pid());
    let pid = child.pid();
    *slot = Some(DaemonChild::Sidecar(child));
    manager.unsupported.store(false, Ordering::SeqCst);

    // 退出检测不走插件事件通道（原因见 spawn_sidecar_monitor 注释）。
    spawn_sidecar_monitor(app.clone(), generation, pid);

    // 仅排空插件事件通道（stdout/stderr 事件），防止管道缓冲写满阻塞插件内部线程。
    // 注意绝不能 drop rx：读端关闭会让仍在运行的 daemon 写 stdout 时收到 EPIPE。
    tauri::async_runtime::spawn(async move {
        while (rx.recv().await).is_some() {}
    });
    Ok(())
}

/// 停止 daemon：kill 子进程、清理句柄、重启计数归零。幂等。
pub fn stop(app: &AppHandle) {
    let manager = app.state::<DaemonManager>();
    let mut slot = manager.child.lock().unwrap();
    // 持锁递增 generation（与 start 一致）：generation 的全部变更点都在
    // child 锁内，handle_exit 的持锁复检（take_if_current）才能成立。递增后，
    // 在飞行的监视线即便刚通过锁外的快速检查，也会在 handle_exit 的锁内
    // 复检被拦下，不会把这次主动 stop 误判为意外退出而触发重启。
    manager.generation.fetch_add(1, Ordering::SeqCst);
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

/// sidecar 子进程的监视线：每 500ms `kill(pid, 0)` 探活，退出走 [`handle_exit`]。
///
/// 为什么不用插件事件（`CommandEvent::Terminated`）：tauri-plugin-shell 2.3.6
/// 中 Terminated 由内部 wait 线程在拿到 guard **写锁**后投递，而 stdout/stderr
/// 管道 reader 线程持有 guard **读锁**直到管道 EOF。PyInstaller onefile 的
/// 内层进程**继承管道写端**——SIGKILL 外层 wrapper 后内层仍存活，管道永不
/// EOF，wait 线程永久阻塞在写锁上：Terminated 永不投递，且 sender 未释放
/// 导致 rx 也永不关闭，事件监听协程随之永久挂起（T8 实测复现）。故 sidecar
/// 与 env 直启统一采用 spawn_blocking 轮询模式。
fn spawn_sidecar_monitor(app: AppHandle, generation: u64, pid: u32) {
    tauri::async_runtime::spawn_blocking(move || {
        loop {
            std::thread::sleep(ENV_POLL_INTERVAL);
            let manager = app.state::<DaemonManager>();
            if manager.generation.load(Ordering::SeqCst) != generation {
                return; // 槽位已被新一轮 start/stop 接管
            }
            let slot = manager.child.lock().unwrap();
            match slot.as_ref() {
                Some(DaemonChild::Sidecar(current)) if current.pid() == pid => {
                    if !process_alive(pid) {
                        break;
                    }
                }
                // 槽位已不属于这一代（形态或 pid 变化）
                _ => return,
            }
        }
        handle_exit(&app, generation);
    });
}

/// 进程探活：`kill(pid, 0)` 只做存在性/权限校验，不发送实际信号。
/// 仅 ESRCH（不存在）返回 false；EPERM（存在但属主不同）仍视为存活。
/// 注：pid 复用理论上可能误判存活——只会延迟退出检测（500ms 轮询窗口内
/// 无关进程恰好拿到同 pid 的概率极低），由重启计数语义兜底，不影响正确性。
fn process_alive(pid: u32) -> bool {
    #[cfg(unix)]
    {
        let rc = unsafe { libc::kill(pid as libc::pid_t, 0) };
        rc == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
    }
    #[cfg(not(unix))]
    {
        // TODO(M4): Windows 用 OpenProcess 探活；当前发布矩阵仅 unix。
        let _ = pid;
        true
    }
}

/// 子进程退出后的统一处理：仅当退出事件仍属于当前 generation 时才视为意外退出。
///
/// 归属判定经 [`DaemonManager::take_if_current`] **持锁复检** generation
/// （推理见其注释）：旧写法在锁外读 generation、锁内才 take，restart_daemon
/// 落在两步之间时会 take 掉新代子进程（孤儿 + 双实例）。锁在进入重启流程前
/// 已释放，下方 start 内部重新获取，无死锁。
fn handle_exit(app: &AppHandle, generation: u64) {
    let manager = app.state::<DaemonManager>();
    if manager.take_if_current(generation).is_none() {
        return; // 已被 stop() 或新一轮 start() 接管（或同代槽位已处理过），交由新逻辑负责
    }

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

// ---------------------------------------------------------------------------
// invoke 命令（配对 / 配置 / 启停 / 开目录）
// ---------------------------------------------------------------------------

/// daemon 数据根 `~/.lambchat`。
///
/// TODO(M4): Windows 下 `$HOME` 通常不存在，改用已知目录 API（如 `dirs::home_dir`
/// 或 `%USERPROFILE%`）后再放开 Windows 打包。
fn sandbox_home() -> Result<PathBuf, String> {
    std::env::var_os("HOME")
        .map(|home| PathBuf::from(home).join(".lambchat"))
        .ok_or_else(|| "$HOME is not set; cannot locate ~/.lambchat".to_string())
}

/// 写入敏感文件：unix 下以 0600 模式原子创建（`OpenOptions::mode` 在 create
/// 时生效，消除 write→chmod 之间的宽松权限窗口）。
fn write_private_file(path: &Path, contents: &[u8]) -> Result<(), String> {
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(path)
        .map_err(|e| format!("failed to open {}: {e}", path.display()))?;
    std::io::Write::write_all(&mut file, contents)
        .map_err(|e| format!("failed to write {}: {e}", path.display()))
}

/// 收紧既有文件权限到 0600（用于纠正 create 之前就已存在的旧文件）。
fn restrict_to_owner(path: &Path) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))
            .map_err(|e| format!("failed to chmod 0600 {}: {e}", path.display()))?;
    }
    // TODO(M4): Windows 侧等价 ACL 收紧。
    #[cfg(not(unix))]
    let _ = path;
    Ok(())
}

/// 校验并写入配对凭据与 daemon 配置。
///
/// - `~/.lambchat/pat`：PAT 明文（0600），与 client/lambchat_sandbox/auth.py 的
///   文件回退后端一致；
/// - `~/.lambchat/sandbox.json`：server_url / data_root / confirm_policy，
///   与 client/lambchat_sandbox/config.py 的字段与校验规则保持一致，
///   已存在的 `data_root` 原样保留（不覆盖用户自定义）。
#[tauri::command]
pub fn save_pairing(
    server_url: String,
    pat: String,
    confirm_policy: String,
) -> Result<(), String> {
    if !(server_url.starts_with("http://") || server_url.starts_with("https://")) {
        return Err("server_url must start with http:// or https://".to_string());
    }
    if !matches!(confirm_policy.as_str(), "all" | "commands" | "none") {
        return Err("confirm_policy must be one of all/commands/none".to_string());
    }
    if pat.trim().is_empty() {
        return Err("pat must not be empty".to_string());
    }

    let home = sandbox_home()?;
    std::fs::create_dir_all(&home)
        .map_err(|e| format!("failed to create {}: {e}", home.display()))?;

    let pat_file = home.join("pat");
    // 新建即 0600；若 pat 已存在（历史遗留宽松权限）再显式收紧一次，失败上抛。
    write_private_file(&pat_file, pat.as_bytes())?;
    restrict_to_owner(&pat_file)?;

    // 保留既有 data_root（配置文件可能被用户手工定制过）。
    let config_path = home.join("sandbox.json");
    let default_data_root = home.join("workspaces");
    let data_root = std::fs::read_to_string(&config_path)
        .ok()
        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok())
        .and_then(|cfg| {
            cfg.get("data_root")
                .and_then(|v| v.as_str())
                .filter(|s| !s.trim().is_empty())
                .map(str::to_string)
        })
        .unwrap_or_else(|| default_data_root.to_string_lossy().into_owned());

    let payload = serde_json::json!({
        "server_url": server_url,
        "data_root": data_root,
        "confirm_policy": confirm_policy,
    });
    let mut body = serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("failed to serialize sandbox config: {e}"))?;
    body.push('\n');
    std::fs::write(&config_path, body)
        .map_err(|e| format!("failed to write {}: {e}", config_path.display()))?;
    Ok(())
}

/// 重启托管的 daemon（stop → start）。
#[tauri::command]
pub fn restart_daemon(app: AppHandle) -> Result<(), String> {
    stop(&app);
    start(&app)
}

/// daemon 进程状态：`"running" | "stopped" | "unsupported"`。
#[tauri::command]
pub fn daemon_process_status(app: AppHandle) -> String {
    status(&app).to_string()
}

/// 词法规范化路径（解析 `.` 与 `..`，不触碰文件系统）。
fn normalize_lexically(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            std::path::Component::CurDir => {}
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

/// 解析可打开的本地路径。
///
/// 白名单：`~/.lambchat/workspaces` 与 `~/.lambchat/audit` 之下（含目录本身）。
/// 接受两种输入：
/// - 逻辑名 `"workspaces"` / `"audit"`（托盘与设置页按钮使用）；
/// - 绝对路径。
///
/// 校验顺序（防符号链接逃逸的关键）：
/// 1. **存在的路径先 canonicalize，对 canonical 结果做前缀校验**——白名单
///    目录内的符号链接若指向任意路径（如 `/etc/passwd`），其 canonical
///    路径不在白名单前缀之下，直接拒绝（`Path::starts_with` 按组件比较，
///    `workspaces-evil` 这类兄弟目录也不会误过）。
/// 2. 仅当目标不存在（canonicalize 失败）时回退词法校验：此时路径尚未被
///    创建，opener 打开它只会报错，词法前缀放行是安全的。
pub(crate) fn resolve_openable_path(raw: &str) -> Result<PathBuf, String> {
    let home = sandbox_home()?;
    let expanded = match raw {
        "workspaces" | "audit" => home.join(raw),
        _ => PathBuf::from(raw),
    };
    let bases = [home.join("workspaces"), home.join("audit")];

    if let Ok(canonical_target) = std::fs::canonicalize(&expanded) {
        for base in &bases {
            if let Ok(canonical_base) = std::fs::canonicalize(base) {
                if canonical_target.starts_with(&canonical_base) {
                    return Ok(canonical_target);
                }
            }
        }
        return Err(format!(
            "path must be inside ~/.lambchat/workspaces or ~/.lambchat/audit, got: {raw}"
        ));
    }

    // 回退：目标不存在，词法规范化（解析 `..` 与 `.`，不触碰文件系统）后校验。
    let normalized = normalize_lexically(&expanded);
    if bases.iter().any(|base| normalized.starts_with(base)) {
        return Ok(normalized);
    }

    Err(format!(
        "path must be inside ~/.lambchat/workspaces or ~/.lambchat/audit, got: {raw}"
    ))
}

/// 打开本地目录（白名单校验后交由系统 opener）。
#[tauri::command]
pub fn open_local_path(app: AppHandle, path: String) -> Result<(), String> {
    let resolved = resolve_openable_path(&path)?;
    app.opener()
        .open_path(resolved.to_string_lossy(), None::<&str>)
        .map_err(|e| format!("failed to open {}: {e}", resolved.display()))
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::sync::Arc;

    /// 白名单路径解析：真实路径放行、符号链接逃逸与 `..` 逃逸拒绝。
    ///
    /// 注意：本仓库 Rust 侧以 `cargo build` 为验证主线，此测试是
    /// `resolve_openable_path` 安全语义的回归锚点（`cargo test` 本地跑，未接 CI）。
    /// 单一测试函数内串行断言，避免 `$HOME` 环境变量并发竞争。
    #[test]
    fn resolve_openable_path_blocks_symlink_escape_and_dotdot() {
        let tmp = std::env::temp_dir().join(format!(
            "lambchat-daemon-path-test-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&tmp);
        let home = tmp.join("home");
        let sandbox = home.join(".lambchat");
        std::fs::create_dir_all(sandbox.join("workspaces")).unwrap();
        std::fs::create_dir_all(sandbox.join("audit")).unwrap();
        std::fs::write(sandbox.join("workspaces").join("note.txt"), "x").unwrap();
        // 白名单内的符号链接指向敏感路径——逃逸载体。
        std::os::unix::fs::symlink("/etc/passwd", sandbox.join("workspaces").join("evil"))
            .unwrap();

        let original_home = std::env::var_os("HOME");
        std::env::set_var("HOME", &home);

        // 白名单内的真实路径放行（canonicalize 后前缀校验通过）。
        assert!(resolve_openable_path("workspaces").is_ok());
        assert!(resolve_openable_path("audit").is_ok());
        assert!(
            resolve_openable_path(&sandbox.join("audit").to_string_lossy()).is_ok()
        );
        assert!(
            resolve_openable_path(&sandbox.join("workspaces/note.txt").to_string_lossy())
                .is_ok()
        );

        // 符号链接逃逸：词法上在 workspaces 内，canonical 指向 /etc/passwd——必须拒绝。
        // （词法校验优先的旧实现在此会错误放行。）
        assert!(
            resolve_openable_path(&sandbox.join("workspaces/evil").to_string_lossy())
                .is_err()
        );

        // `..` 词法逃逸拒绝。
        assert!(
            resolve_openable_path(&sandbox.join("workspaces/../../etc").to_string_lossy())
                .is_err()
        );
        // 兄弟目录前缀（组件级 starts_with）拒绝。
        assert!(
            resolve_openable_path(&sandbox.join("workspaces-evil").to_string_lossy())
                .is_err()
        );
        // 白名单外绝对路径拒绝。
        assert!(resolve_openable_path("/etc/passwd").is_err());

        match original_home {
            Some(h) => std::env::set_var("HOME", h),
            None => std::env::remove_var("HOME"),
        }
        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// handle_exit 竞窗回归锚点（M3 终审 F3）：迟到的退出事件不得取走
    /// 新一代子进程的句柄。
    ///
    /// 场景回放：gen=1 的监视线在锁外读完 generation（仍为 1）后阻塞在
    /// child 锁上；restart_daemon 随后完整交错——stop 清槽递增 generation、
    /// start 放入新子进程再递增。旧实现（锁外检查、锁内才 take）此刻醒来
    /// 会 take 掉新代子进程：句柄被无人 kill 地丢弃 → 孤儿进程，随后
    /// handle_exit 的重启逻辑再拉一个 daemon → 双实例。
    ///
    /// 构造方式：主线程自装入 gen=1 子进程起持续持有 child 锁（与修复后
    /// start/stop 的持锁纪律一致），监视线线程的锁外检查读到的必然仍是
    /// generation==1；主线程在锁内完成 stop+start 的等效交错后放锁。
    /// 修复后的 take_if_current 持锁复检 generation，只能返回 None；
    /// 若返回 Some，其子进程必须是 gen=1 的那个（pid 相等），绝不可能是
    /// 新装入的子进程。
    #[test]
    fn take_if_current_never_takes_slot_of_newer_generation() {
        let manager = Arc::new(DaemonManager::default());
        let child_gen1 = std::process::Command::new("sleep").arg("30").spawn().unwrap();
        let pid_gen1 = child_gen1.id();
        let child_gen3 = std::process::Command::new("sleep").arg("30").spawn().unwrap();

        // 主线程持锁：装入 gen=1 的子进程（start 的落点效果）。
        let mut slot = manager.child.lock().unwrap();
        manager.generation.store(1, Ordering::SeqCst);
        *slot = Some(DaemonChild::Env(child_gen1));

        // 监视线线程：此刻 generation 仍为 1（主线程持锁且尚未递增）。
        // 旧实现在锁外通过检查后，会阻塞在主线程持有的 child 锁上。
        let stale_manager = Arc::clone(&manager);
        let stale_exit = std::thread::spawn(move || stale_manager.take_if_current(1));

        // 给监视线足够时间完成锁外检查并阻塞在锁上（50ms ≫ 线程启动）。
        std::thread::sleep(std::time::Duration::from_millis(50));

        // restart_daemon 交错（修复后纪律：generation 变更全程持锁）——
        // stop：gen→2、取走并 kill 旧子进程；start：gen→3、装入新子进程。
        manager.generation.fetch_add(1, Ordering::SeqCst);
        if let Some(DaemonChild::Env(mut old)) = slot.take() {
            let _ = old.kill();
            let _ = old.wait();
        }
        manager.generation.fetch_add(1, Ordering::SeqCst);
        *slot = Some(DaemonChild::Env(child_gen3));
        drop(slot);

        match stale_exit.join().unwrap() {
            // 正确：迟到的 gen=1 退出事件不得触碰新一代槽位。
            None => {}
            // 理论上仅当交错未发生（gen 仍为 1 时取走原槽位）才会走到这里，
            // 此时取到的必须是 gen=1 的子进程本身；取到新代 pid 即竞窗实锤。
            Some(DaemonChild::Env(mut c)) => {
                let pid = c.id();
                let _ = c.kill();
                let _ = c.wait();
                assert_eq!(
                    pid, pid_gen1,
                    "stale exit handler took the child of a newer generation"
                );
            }
            Some(DaemonChild::Sidecar(_)) => panic!("unexpected sidecar child in test"),
        }

        // 新代子进程必须仍在槽内（未被迟到的退出事件 take 掉）。
        let mut final_slot = manager.child.lock().unwrap();
        match final_slot.take() {
            Some(DaemonChild::Env(mut c)) => {
                let _ = c.kill();
                let _ = c.wait();
            }
            _ => panic!("new-generation child was taken by the stale exit handler"),
        }
    }
}
