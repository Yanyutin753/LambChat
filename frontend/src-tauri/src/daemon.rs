//! LambChat 本地沙箱 daemon 的生命周期托管。
//!
//! 启动优先级：
//! 1. 环境变量 `LAMBCHAT_DAEMON_BIN` 指向的外部可执行（dev 回退路径）；
//! 2. 打包内 sidecar（`bundle.externalBin` 落位在主程序同目录、名去 triple，
//!    见 [`sidecar_candidates`]）。
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

/// 意外退出后的自动重启次数上限。
const MAX_RESTARTS: u8 = 3;

/// 稳定运行阈值：这代进程稳定运行超过该时长后意外退出，重启预算恢复
/// （cloudflared 模式：早夭连崩有上限，稳定运行过的不受早夭计数牵连——
/// 否则 daemon 早期连不上服务器连崩 3 次后就永久放弃，需重启客户端）。
const STABLE_RESET: Duration = Duration::from_secs(300);

/// 稳定运行时长是否应恢复重启预算（纯函数，便于单测）。
fn should_reset_restart_budget(uptime: Duration) -> bool {
    uptime >= STABLE_RESET
}

/// 第 N 次（0-based）重启前的退避间隔：1s、2s、4s、8s、16s，封顶 30s
/// （纯函数，便于单测；防抖避免崩溃风暴打满 CPU/日志）。
fn restart_backoff(restarts_before: u8) -> Duration {
    let shift = restarts_before.min(5) as u32;
    Duration::from_secs(1u64 << shift).min(Duration::from_secs(30))
}

/// daemon 托管状态变化事件名（Tauri event，前端订阅替代轮询）。
pub const STATUS_EVENT: &str = "sandbox-daemon-status";

/// 监视线轮询间隔（env 直启 try_wait / sidecar kill(pid,0) 探活共用）。
const ENV_POLL_INTERVAL: Duration = Duration::from_millis(500);

/// 主动 stop 的优雅宽限：SIGTERM 后等待 daemon 自行退出的上限（daemon 侧
/// 走 post_offline + 审计落盘的优雅退出路径，M4 T8）；超时仍存活由调用方
/// SIGKILL 兜底。
const STOP_GRACE: Duration = Duration::from_secs(3);

/// 宽限期内的探活间隔。
const STOP_POLL_INTERVAL: Duration = Duration::from_millis(100);

/// 桌面端持久日志：`~/.lambchat/logs/desktop.log`（1MB 截断重开，防无界增长）。
/// GUI 壳的 stderr 不可见（windows_subsystem="windows" 句柄无效 / mac 从
/// Finder 启动无控制台）——daemon 托管的启动/退出/重启与排空输出此前完全
/// 无迹可查，用户报「启动不了」时只能盲猜。写失败静默（日志绝不能反噬主流程）。
fn append_desktop_log(line: &str) {
    use std::io::Write;
    let Ok(home) = sandbox_home() else { return };
    let dir = home.join("logs");
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    let path = dir.join("desktop.log");
    if let Ok(meta) = std::fs::metadata(&path) {
        if meta.len() > 1024 * 1024 {
            let _ = std::fs::rename(&path, dir.join("desktop.log.1"));
        }
    }
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(f, "[{ts}] {line}");
    }
}

macro_rules! warn_log {
    ($($arg:tt)*) => {{
        let msg = format!("[lambchat-daemon] {}", format!($($arg)*));
        eprintln!("{msg}");
        crate::daemon::append_desktop_log(&msg);
    }};
}

/// 当前托管的 daemon 子进程：command-group 的 [`GroupChild`]——
/// Unix 进程组 / Windows Job Object（CREATE_NEW_PROCESS_GROUP + 任务对象），
/// 进程树信号与整树终止由 crate 跨平台实现（替代手搓 killpg/taskkill）。
enum DaemonChild {
    Group(command_group::GroupChild),
}

/// daemon 生命周期状态（挂到 Tauri managed state）。
pub struct DaemonManager {
    child: Mutex<Option<DaemonChild>>,
    /// 当前代进程的启动时刻（稳定运行判定用；槽位空时为 None）。
    started_at: Mutex<Option<std::time::Instant>>,
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
    /// `child` 槽位非空的原子镜像：状态类 IPC（`daemon_process_status`）在
    /// **主线程**同步执行，绝不可等 `child` 互斥锁——start 持锁跨越整个
    /// spawn（Windows AV 扫 PyInstaller 可达数秒），auto-pair 重启进行中
    /// 进偏好设置会把主线程锁死（v2.9.2 前置版本实测卡死残留路径）。
    /// 写点与槽位变更同锁内（真值由锁序保证），读侧无锁即时返回。
    running: AtomicBool,
}

impl Default for DaemonManager {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            started_at: Mutex::new(None),
            restarts: AtomicU8::new(0),
            generation: AtomicU64::new(0),
            unsupported: AtomicBool::new(false),
            running: AtomicBool::new(false),
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
        let mut slot = lock_ok(&self.child);
        if self.generation.load(Ordering::SeqCst) != generation {
            return None;
        }
        let taken = slot.take();
        self.running.store(taken.is_some(), Ordering::SeqCst);
        taken
    }
}

/// 毒锁容忍：任一线程曾持锁 panic 后，后续 `.lock().unwrap()` 会连环 panic——
/// 状态类 IPC 命令在主线程 panic 即整窗冻结（v2.9.1 卡死嫌疑路径之一）。
/// 锁中毒说明临界区已不在一致状态，但 daemon 槽位语义可安全重建（take 走
/// 默认空槽即 stopped），恢复可用性优先于保守放弃。
fn lock_ok<T>(m: &std::sync::Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
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
    let mut slot = lock_ok(&manager.child);
    if slot.is_some() {
        return Ok(());
    }
    let generation = manager.generation.fetch_add(1, Ordering::SeqCst) + 1;

    // 统一经 command-group 组启动（Unix 进程组 / Windows Job Object）：
    // 1. dev 回退：LAMBCHAT_DAEMON_BIN 外部可执行；
    // 2. 常规：随包分发的 sidecar（主程序同目录，externalBin 打包落位，
    //    见 [`sidecar_candidates`]）。不再经 plugin-shell spawn——插件句柄
    //    无进程组语义，Windows 只能退化为 taskkill；组启动让停止/整树清理
    //    由 command-group 跨平台完成。
    let mut command = if let Some(env_bin) = std::env::var_os("LAMBCHAT_DAEMON_BIN") {
        warn_log!(
            "daemon from LAMBCHAT_DAEMON_BIN={}",
            env_bin.to_string_lossy()
        );
        std::process::Command::new(&env_bin)
    } else {
        let bin = sidecar_binary_path(app).ok_or_else(|| {
            manager.unsupported.store(true, Ordering::SeqCst);
            "lambchat-daemon sidecar binary not available".to_string()
        })?;
        std::process::Command::new(bin)
    };
    command
        .arg("run")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    #[cfg(windows)]
    use command_group::builder::CommandGroupBuilder;
    use command_group::CommandGroup;
    let mut group = command.group();
    // Windows 弹终端根因（v2.9.0 回归）：GUI 子系统壳（windows_subsystem="windows"）
    // spawn 控制台子系统 daemon 必开新控制台窗口——旧 plugin-shell 内部带
    // CREATE_NO_WINDOW，换 command-group 后丢失。注意 command-group 的 spawn 会
    // 以 builder 自身标志**整体覆盖** Command 的 creation_flags（源码
    // `creation_flags(self.creation_flags | CREATE_SUSPENDED)`），必须经
    // builder 传入而非 Command::creation_flags。
    #[cfg(windows)]
    group.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let mut child = group.spawn().map_err(|e| {
        manager.unsupported.store(true, Ordering::SeqCst);
        format!("failed to spawn lambchat-daemon: {e}")
    })?;
    let pid = child.id();
    warn_log!("daemon started in process group (pid {pid})");
    // 排空 stdout/stderr 管道（防缓冲写满阻塞 daemon；日志进壳 stderr）
    if let Some(out) = child.inner().stdout.take() {
        std::thread::spawn(move || {
            use std::io::Read;
            let mut buf = [0u8; 4096];
            let mut out = out;
            loop {
                match out.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        // 写失败必须忽略：windows_subsystem="windows" 的壳 stderr
                        // 句柄无效，eprint! 会 panic 杀死排空线程——管道再无人读，
                        // daemon 写满 stdout 后永久阻塞（表现为沙箱假死）
                        use std::io::Write;
                        let _ = std::io::stderr().write_all(&buf[..n]);
                        append_desktop_log(&format!(
                            "[daemon:out] {}",
                            String::from_utf8_lossy(&buf[..n]).trim_end()
                        ));
                    }
                }
            }
        });
    }
    if let Some(err) = child.inner().stderr.take() {
        std::thread::spawn(move || {
            use std::io::Read;
            let mut buf = [0u8; 4096];
            let mut err = err;
            loop {
                match err.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        use std::io::Write;
                        let _ = std::io::stderr().write_all(&buf[..n]);
                        append_desktop_log(&format!(
                            "[daemon:err] {}",
                            String::from_utf8_lossy(&buf[..n]).trim_end()
                        ));
                    }
                }
            }
        });
    }

    *slot = Some(DaemonChild::Group(child));
    manager.running.store(true, Ordering::SeqCst);
    manager.unsupported.store(false, Ordering::SeqCst);
    *lock_ok(&manager.started_at) = Some(std::time::Instant::now());
    spawn_group_monitor(app.clone(), generation);
    emit_status(app);
    Ok(())
}

/// 当前平台 target triple（与 build-daemon.sh / fetch-pbs.py 分发词汇表对齐）。
fn current_target_triple() -> Option<&'static str> {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("linux", "x86_64") => Some("x86_64-unknown-linux-gnu"),
        ("linux", "aarch64") => Some("aarch64-unknown-linux-gnu"),
        ("macos", "x86_64") => Some("x86_64-apple-darwin"),
        ("macos", "aarch64") => Some("aarch64-apple-darwin"),
        ("windows", "x86_64") => Some("x86_64-pc-windows-msvc"),
        _ => None,
    }
}

/// sidecar 可执行后缀（Windows 为 .exe）。
fn sidecar_exe_suffix() -> &'static str {
    if cfg!(windows) {
        ".exe"
    } else {
        ""
    }
}

/// sidecar 候选路径（按优先级，纯函数便于单测）：
/// 1. 主程序同目录 `lambchat-daemon`——`bundle.externalBin` 打包的**真实
///    落位**（deb/rpm/AppImage/MSI/macOS .app 一致：与主程序同级，triple
///    后缀被打包剥掉）。v2.9.0 曾误找 `resource_dir/binaries/
///    lambchat-daemon-<triple>`（目录与文件名双双不中），打包产物里
///    restartDaemon 必败、配对全挂——本候选是防回归锚点。
/// 2. 主程序同目录带 triple（未剥后缀的手工放位兼容）。
/// 3. `resource_dir/binaries/lambchat-daemon-<triple>`（旧约定兜底）。
fn sidecar_candidates(exe_dir: &Path, resource_dir: Option<&Path>) -> Vec<PathBuf> {
    let exe = sidecar_exe_suffix();
    let mut candidates = vec![exe_dir.join(format!("lambchat-daemon{exe}"))];
    if let Some(triple) = current_target_triple() {
        candidates.push(exe_dir.join(format!("lambchat-daemon-{triple}{exe}")));
        if let Some(res) = resource_dir {
            candidates.push(
                res.join("binaries")
                    .join(format!("lambchat-daemon-{triple}{exe}")),
            );
        }
    }
    candidates
}

/// sidecar 可执行路径：按 [`sidecar_candidates`] 顺序取第一个存在的文件。
/// 主程序目录来自 `current_exe`（AppImage 挂载点/macOS .app 内均正确）。
fn sidecar_binary_path(app: &AppHandle) -> Option<PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let resource_dir = app.path().resource_dir().ok();
    sidecar_candidates(&exe_dir, resource_dir.as_deref())
        .into_iter()
        .find(|p| p.is_file())
}

/// 托管状态变化事件：前端订阅（替代 10s 轮询 daemon_process_status），
/// 载荷 {running, unsupported, generation, restarts}。发送失败仅告警——
/// 事件是加速信号，前端仍有初始 invoke 兜底。emit_status 必须在
/// started_at/child 状态落定后调用。
fn emit_status(app: &AppHandle) {
    use tauri::Emitter;
    let manager = app.state::<DaemonManager>();
    let running = manager.running.load(Ordering::SeqCst);
    let payload = serde_json::json!({
        "running": running,
        "unsupported": manager.unsupported.load(Ordering::SeqCst),
        "generation": manager.generation.load(Ordering::SeqCst),
        "restarts": manager.restarts.load(Ordering::SeqCst),
    });
    if let Err(e) = app.emit(STATUS_EVENT, payload) {
        warn_log!("failed to emit {STATUS_EVENT}: {e}");
    }
}

/// 停止 daemon：SIGTERM 优雅终止（宽限 [`STOP_GRACE`]）→ 仍存活再 SIGKILL
/// 兜底 → 清理句柄、重启计数归零。幂等。
///
/// 优雅序（M4 T8）：daemon 侧 SIGTERM → post_offline（服务端注册表即刻
/// 下线，status 窗口从心跳/TTL 的 15-35s 收敛到一次 RTT）→ 审计 shutdown
/// → 退出。旧实现的直接 SIGKILL 让 daemon 无从优雅下线。
/// kill 后的有界收尸宽限：超时放弃句柄（见 [`reap_bounded`]）。
const REAP_GRACE: std::time::Duration = std::time::Duration::from_secs(2);

/// 有界收尸：deadline 内轮询 try_wait，返回是否等到退出。
///
/// command-group 的 `wait()` 在 Windows 上阻塞到 Job Object 全组退出，组内
/// 残留子进程会令其永久挂起——调用方（同步 IPC 命令/主线程）不可承受。
/// 纯轮询实现便于单测（真实子进程，Linux CI 可跑）。
fn reap_bounded(child: &mut command_group::GroupChild, grace: std::time::Duration) -> bool {
    let deadline = std::time::Instant::now() + grace;
    while std::time::Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) | Err(_) => return true,
            Ok(None) => std::thread::sleep(STOP_POLL_INTERVAL),
        }
    }
    false
}

pub fn stop(app: &AppHandle) {
    let manager = app.state::<DaemonManager>();
    // 持锁递增 generation 并取走槽位（与 start 一致）：generation 的全部变更点
    // 都在 child 锁内，handle_exit 的持锁复检（take_if_current）才能成立。
    // 锁在等待**之前**释放：优雅宽限最长 3s，持锁等待会卡住 IPC。
    let child = {
        let mut slot = lock_ok(&manager.child);
        manager.generation.fetch_add(1, Ordering::SeqCst);
        slot.take()
    };
    if let Some(DaemonChild::Group(mut child)) = child {
        warn_log!("stopping daemon group (pid {})", child.id());
        #[cfg(unix)]
        {
            use command_group::UnixChildExt;
            let _ = child.signal(command_group::Signal::SIGTERM);
            let deadline = std::time::Instant::now() + STOP_GRACE;
            while std::time::Instant::now() < deadline {
                match child.try_wait() {
                    Ok(Some(_)) | Err(_) => break,
                    Ok(None) => std::thread::sleep(STOP_POLL_INTERVAL),
                }
            }
        }
        // Windows：Job Object 整树终止（组 kill，等价 unix killpg）；daemon 的
        // 优雅下线（post_offline）由 SIGBREAK 侧与断流清理兜底——组 kill 后
        // 服务端 SSE 断流 → unregister + presence 推送，感知仍为毫秒级。
        if !matches!(child.try_wait(), Ok(Some(_))) {
            if let Err(e) = child.kill() {
                warn_log!("failed to kill daemon group: {e}");
            }
        }
        // 有界收尸：Windows 的 GroupChild::wait() 要等 Job Object 内**全部**
        // 进程退出（含 daemon 派生的 PBS 运行时子进程），残留即无限阻塞——
        // stop 由同步命令调用时曾把主线程整个挂死（v2.9.1 偏好设置卡死）。
        // 超时放弃句柄：kill 已发，残留收尸交 OS（Job 终止语义兜底）。
        if !reap_bounded(&mut child, REAP_GRACE) {
            warn_log!(
                "daemon group not reaped within {:?}; abandoning handle",
                REAP_GRACE
            );
        }
    }
    manager.restarts.store(0, Ordering::SeqCst);
    manager.running.store(false, Ordering::SeqCst);
    *lock_ok(&manager.started_at) = None;
    emit_status(app);
}

/// 进程状态：`"running" | "stopped" | "unsupported"`。
pub fn status(app: &AppHandle) -> &'static str {
    let manager = app.state::<DaemonManager>();
    // 读原子镜像而非 child 锁：本函数被主线程同步 IPC 调用，锁竞争会把
    // UI 挂死（见 DaemonManager::running 注释）
    if manager.running.load(Ordering::SeqCst) {
        "running"
    } else if manager.unsupported.load(Ordering::SeqCst) {
        "unsupported"
    } else {
        "stopped"
    }
}

/// 组子进程监视线：500ms `try_wait` 轮询（command-group 句柄语义，跨平台，
/// 替代 kill(pid,0)/tasklist 探活），退出走 [`handle_exit`]。
fn spawn_group_monitor(app: AppHandle, generation: u64) {
    tauri::async_runtime::spawn_blocking(move || {
        loop {
            std::thread::sleep(ENV_POLL_INTERVAL);
            let manager = app.state::<DaemonManager>();
            if manager.generation.load(Ordering::SeqCst) != generation {
                return; // 槽位已被新一轮 start/stop 接管
            }
            let mut slot = lock_ok(&manager.child);
            match slot.as_mut() {
                Some(DaemonChild::Group(child)) => match child.try_wait() {
                    Ok(Some(_)) | Err(_) => break,
                    Ok(None) => {}
                },
                _ => return, // 形态变化（不可能在同代发生，防御性退出）
            }
        }
        handle_exit(&app, generation);
    });
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
    let uptime = manager
        .started_at
        .lock()
        .unwrap()
        .map(|started| started.elapsed())
        .unwrap_or_default();
    *lock_ok(&manager.started_at) = None;
    emit_status(app); // 槽位已空：先广播 stopped，重启成功后会再广播 running

    if should_reset_restart_budget(uptime) {
        warn_log!(
            "daemon ran stably for {}s before exit; restart budget restored",
            uptime.as_secs()
        );
        manager.restarts.store(0, Ordering::SeqCst);
    }
    let restarts = manager.restarts.fetch_add(1, Ordering::SeqCst);
    if restarts >= MAX_RESTARTS {
        warn_log!(
            "daemon exited unexpectedly and restart budget ({MAX_RESTARTS}) exhausted; giving up"
        );
        return;
    }
    let backoff = restart_backoff(restarts);
    warn_log!(
        "daemon exited unexpectedly; restarting in {:?} ({}/{MAX_RESTARTS})",
        backoff,
        restarts + 1
    );
    if !backoff.is_zero() {
        // 监视线（spawn_blocking）上睡：退避窗口内用户手动 restart_daemon 会
        // 先装满槽位，随后的 start() 幂等 no-op，不会双实例
        std::thread::sleep(backoff);
    }
    if let Err(e) = start(app) {
        warn_log!("daemon restart failed: {e}");
    }
}

// ---------------------------------------------------------------------------
// invoke 命令（配对 / 配置 / 启停 / 开目录）
// ---------------------------------------------------------------------------

/// daemon 数据根：`LAMBCHAT_HOME` 优先，缺省 `~/.lambchat`（lib.rs 的 PBS
/// 归档落位与 append_desktop_log 均复用）。
///
/// `LAMBCHAT_HOME`（非空白）即数据根本身，两侧（Python `paths.home_root()`）
/// 读同一个变量——迁移沙箱根时两进程解析到同一目录；未设时：`$HOME` 优先
/// （unix / git-bash dev），Windows 常规进程无 `HOME` 回退 `%USERPROFILE%`，
/// 与 daemon 侧 Python `Path.home()` 的 Windows 语义一致（M4 T9：恢复
/// Windows 打包矩阵的前置，两进程必须解析到同一目录）。
/// daemon 由壳 spawn 继承环境：用户级环境变量改动需重启壳生效。
pub(crate) fn sandbox_home() -> Result<PathBuf, String> {
    if let Some(custom) = std::env::var_os("LAMBCHAT_HOME") {
        if !custom.to_string_lossy().trim().is_empty() {
            return Ok(PathBuf::from(custom));
        }
    }
    default_sandbox_home()
        .ok_or_else(|| "neither $HOME nor %USERPROFILE% is set; cannot locate ~/.lambchat".to_string())
}

/// 缺省根 `~/.lambchat`（未设 `LAMBCHAT_HOME` 时的解析结果，供"是否自定义"
/// 比较复用）：`$HOME` 优先（unix / git-bash dev），Windows 常规进程回退
/// `%USERPROFILE%`，与 daemon 侧 Python `Path.home()` 的 Windows 语义一致。
fn default_sandbox_home() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(|home| PathBuf::from(home).join(".lambchat"))
}

/// 写入敏感文件：unix 下以 0600 模式原子创建（`OpenOptions::mode` 在 create
/// 时生效，消除 write→chmod 之间的宽松权限窗口）。
/// 写入配置文件时先写同目录临时文件，再原子替换目标，避免 daemon 重启
/// 恰好读到截断 JSON（Windows/macOS 的进程重启竞态尤其容易复现）。
fn write_atomic_file(path: &Path, contents: &[u8]) -> Result<(), String> {
    let parent = path.parent().ok_or_else(|| {
        format!("cannot determine parent directory for {}", path.display())
    })?;
    let file_name = path
        .file_name()
        .ok_or_else(|| format!("cannot determine file name for {}", path.display()))?
        .to_string_lossy();
    let tmp = parent.join(format!(".{file_name}.{}.tmp", std::process::id()));
    std::fs::write(&tmp, contents)
        .map_err(|e| format!("failed to write {}: {e}", tmp.display()))?;
    if let Err(e) = std::fs::rename(&tmp, path) {
        #[cfg(windows)]
        {
            // Windows rename cannot replace an existing file. Remove only after
            // the complete temp write succeeds, then perform the short swap.
            if path.exists() {
                std::fs::remove_file(path).map_err(|remove_err| {
                    let _ = std::fs::remove_file(&tmp);
                    format!("failed to replace {}: {remove_err}", path.display())
                })?;
                if let Err(rename_err) = std::fs::rename(&tmp, path) {
                    let _ = std::fs::remove_file(&tmp);
                    return Err(format!("failed to replace {}: {rename_err}", path.display()));
                }
                return Ok(());
            }
        }
        let _ = std::fs::remove_file(&tmp);
        return Err(format!("failed to replace {}: {e}", path.display()));
    }
    Ok(())
}

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
/// - `~/.lambchat/sandbox.json`：server_url / data_root / confirm_policy / pat_id，
///   与 client/lambchat_sandbox/config.py 的字段与校验规则保持一致，
///   已存在的 `data_root` 原样保留（不覆盖用户自定义）；
/// - `pat_id`：配对回执（PAT 记录 id）。Python config 侧可回读；
///   `None`/空白 → 不写键（兼容旧形态）。
#[tauri::command]
pub fn save_pairing(
    server_url: String,
    pat: String,
    confirm_policy: String,
    pat_id: Option<String>,
) -> Result<(), String> {
    let pat_id = pat_id
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty());
    write_pairing_files(
        &sandbox_home()?,
        &server_url,
        &pat,
        &confirm_policy,
        pat_id.as_deref(),
    )
}

/// 文件层配对写入（可测试核心：home 由调用方注入）。
fn write_pairing_files(
    home: &Path,
    server_url: &str,
    pat: &str,
    confirm_policy: &str,
    pat_id: Option<&str>,
) -> Result<(), String> {
    if !(server_url.starts_with("http://") || server_url.starts_with("https://")) {
        return Err("server_url must start with http:// or https://".to_string());
    }
    if !matches!(confirm_policy, "all" | "commands" | "none") {
        return Err("confirm_policy must be one of all/commands/none".to_string());
    }
    if pat.trim().is_empty() {
        return Err("pat must not be empty".to_string());
    }

    std::fs::create_dir_all(home)
        .map_err(|e| format!("failed to create {}: {e}", home.display()))?;

    let pat_file = home.join("pat");
    // 新建即 0600；若 pat 已存在（历史遗留宽松权限）再显式收紧一次，失败上抛。
    write_private_file(&pat_file, pat.as_bytes())?;
    restrict_to_owner(&pat_file)?;

    // 保留既有 data_root（配置文件可能被用户手工定制过），以及 daemon 生成的
    // 机器身份（machine_id / machine_name）——重新配对不得轮换机器身份，否则
    // 服务端注册表堆积幽灵机器、前端"当前设备"标识失效。
    let config_path = home.join("sandbox.json");
    let default_data_root = home.join("workspaces");
    let existing: Option<serde_json::Value> = std::fs::read_to_string(&config_path)
        .ok()
        .and_then(|raw| serde_json::from_str::<serde_json::Value>(&raw).ok());
    let data_root = existing
        .as_ref()
        .and_then(|cfg| {
            cfg.get("data_root")
                .and_then(|v| v.as_str())
                .filter(|s| !s.trim().is_empty())
                .map(str::to_string)
        })
        .unwrap_or_else(|| default_data_root.to_string_lossy().into_owned());

    let mut payload = serde_json::json!({
        "server_url": server_url,
        "data_root": data_root,
        "confirm_policy": confirm_policy,
    });
    for key in ["machine_id", "machine_name"] {
        let value = existing.as_ref().and_then(|cfg| cfg.get(key));
        if let Some(v) = value {
            if v.as_str().map(|s| !s.trim().is_empty()).unwrap_or(false) {
                payload[key] = v.clone();
            }
        }
    }
    if let Some(id) = pat_id {
        payload["pat_id"] = serde_json::Value::String(id.to_string());
    }
    let mut body = serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("failed to serialize sandbox config: {e}"))?;
    body.push('\n');
    write_atomic_file(&config_path, body.as_bytes())?;
    Ok(())
}

/// 只写 sandbox.json 的 confirm_policy，保留其余全部字段（含 pat_id / data_root /
/// embedded_python）。策略切换用——不重铸 PAT、不碰凭据文件。
#[tauri::command]
pub fn write_confirm_policy(policy: String) -> Result<(), String> {
    write_policy_only(&sandbox_home()?, &policy)
}

/// 读 sandbox.json 的机器身份 machine_id（daemon 首启生成并持久化）。前端用于
/// 在机器列表上标注"当前设备"。未配对 / daemon 未写过 → Ok(None)（非错误）；
/// 仅配置文件损坏时报错。
#[tauri::command]
pub fn read_machine_id() -> Result<Option<String>, String> {
    read_machine_id_from(&sandbox_home()?)
}

/// 文件层机器身份读取（可测试核心：home 由调用方注入）。
fn read_machine_id_from(home: &Path) -> Result<Option<String>, String> {
    let config_path = home.join("sandbox.json");
    let raw = match std::fs::read_to_string(&config_path) {
        Ok(raw) => raw,
        Err(_) => return Ok(None), // 未配对 / 尚未落盘：无机器身份
    };
    let cfg: serde_json::Value = serde_json::from_str(&raw)
        .map_err(|e| format!("invalid JSON in {}: {e}", config_path.display()))?;
    Ok(cfg
        .get("machine_id")
        .and_then(|v| v.as_str())
        .filter(|s| !s.trim().is_empty())
        .map(str::to_string))
}

/// 文件层策略独立写（可测试核心：home 由调用方注入）。
///
/// 配置文件不存在时拒绝：没有配对就没有可改的策略（避免凭空造出半份配置）。
fn write_policy_only(home: &Path, confirm_policy: &str) -> Result<(), String> {
    if !matches!(confirm_policy, "all" | "commands" | "none") {
        return Err("confirm_policy must be one of all/commands/none".to_string());
    }
    let config_path = home.join("sandbox.json");
    let raw = std::fs::read_to_string(&config_path)
        .map_err(|e| format!("failed to read {}: {e}", config_path.display()))?;
    let mut cfg: serde_json::Value = serde_json::from_str(&raw)
        .map_err(|e| format!("invalid JSON in {}: {e}", config_path.display()))?;
    let obj = cfg.as_object_mut().ok_or_else(|| {
        format!(
            "config root must be a JSON object: {}",
            config_path.display()
        )
    })?;
    obj.insert(
        "confirm_policy".to_string(),
        serde_json::Value::String(confirm_policy.to_string()),
    );
    let mut body = serde_json::to_string_pretty(&cfg)
        .map_err(|e| format!("failed to serialize sandbox config: {e}"))?;
    body.push('\n');
    write_atomic_file(&config_path, body.as_bytes())?;
    Ok(())
}

/// 取消配对：停 daemon + 删 `~/.lambchat/pat` + 移除 sandbox.json 的 `pat_id` 键
/// （其余配置保留，重新配对时可复用 server_url / data_root / 策略）。
/// 服务端的 PAT 吊销由前端用读出的 PAT 调 `DELETE /api/auth/pat/current` 完成。
#[tauri::command]
pub async fn clear_pairing(app: AppHandle) -> Result<(), String> {
    // stop/start 含 SIGTERM 宽限与进程 spawn（Windows 上 AV 扫描 PyInstaller
    // 可执行可达秒级）——同步命令跑主线程会把 UI 整个挂死（v2.9.1 偏好设置
    // 卡死根因之一：进入即触发 auto-pair → restart_daemon）。挪 spawn_blocking。
    tauri::async_runtime::spawn_blocking(move || {
        stop(&app);
        clear_pairing_files(&sandbox_home()?)
    })
    .await
    .map_err(|e| format!("clear_pairing task failed: {e}"))?
}

/// 文件层取消配对（可测试核心：home 由调用方注入）。幂等：文件不存在不报错。
fn clear_pairing_files(home: &Path) -> Result<(), String> {
    let pat_file = home.join("pat");
    match std::fs::remove_file(&pat_file) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(e) => return Err(format!("failed to remove {}: {e}", pat_file.display())),
    }

    let config_path = home.join("sandbox.json");
    let raw = match std::fs::read_to_string(&config_path) {
        Ok(raw) => raw,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(format!("failed to read {}: {e}", config_path.display())),
    };
    let mut cfg: serde_json::Value = serde_json::from_str(&raw)
        .map_err(|e| format!("invalid JSON in {}: {e}", config_path.display()))?;
    if let Some(obj) = cfg.as_object_mut() {
        obj.remove("pat_id");
    }
    let mut body = serde_json::to_string_pretty(&cfg)
        .map_err(|e| format!("failed to serialize sandbox config: {e}"))?;
    body.push('\n');
    write_atomic_file(&config_path, body.as_bytes())?;
    Ok(())
}

/// 读回配对 PAT（取消配对时前端拿它调服务端自删端点）。
/// 文件缺失 → `Ok(None)`（未配对）。
#[tauri::command]
pub fn read_pairing_pat() -> Result<Option<String>, String> {
    read_pat_file(&sandbox_home()?)
}

/// 文件层读 PAT（可测试核心：home 由调用方注入）。
fn read_pat_file(home: &Path) -> Result<Option<String>, String> {
    let pat_file = home.join("pat");
    match std::fs::read_to_string(&pat_file) {
        Ok(raw) => {
            let trimmed = raw.trim();
            if trimmed.is_empty() {
                Ok(None)
            } else {
                Ok(Some(trimmed.to_string()))
            }
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("failed to read {}: {e}", pat_file.display())),
    }
}

/// 重启托管的 daemon（stop → start）。
#[tauri::command]
pub async fn restart_daemon(app: AppHandle) -> Result<(), String> {
    // 同 clear_pairing：阻塞的 stop/start 必须离开主线程
    tauri::async_runtime::spawn_blocking(move || {
        stop(&app);
        start(&app)
    })
    .await
    .map_err(|e| format!("restart task failed: {e}"))?
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
/// 白名单：`~/.lambchat/workspaces`、`~/.lambchat/audit` 与 `~/.lambchat/logs`
/// 之下（含目录本身）。
/// 接受两种输入：
/// - 逻辑名 `"workspaces"` / `"audit"` / `"logs"`（托盘与设置页按钮使用）；
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
        "workspaces" | "audit" | "logs" => home.join(raw),
        _ => PathBuf::from(raw),
    };
    let bases = [
        home.join("workspaces"),
        home.join("audit"),
        home.join("logs"),
    ];

    if let Ok(canonical_target) = std::fs::canonicalize(&expanded) {
        for base in &bases {
            if let Ok(canonical_base) = std::fs::canonicalize(base) {
                if canonical_target.starts_with(&canonical_base) {
                    return Ok(canonical_target);
                }
            }
        }
        return Err(format!(
            "path must be inside ~/.lambchat/workspaces, ~/.lambchat/audit or ~/.lambchat/logs, got: {raw}"
        ));
    }

    // 回退：目标不存在，词法规范化（解析 `..` 与 `.`，不触碰文件系统）后校验。
    let normalized = normalize_lexically(&expanded);
    if bases.iter().any(|base| normalized.starts_with(base)) {
        return Ok(normalized);
    }

    Err(format!(
        "path must be inside ~/.lambchat/workspaces, ~/.lambchat/audit or ~/.lambchat/logs, got: {raw}"
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

// ---------------------------------------------------------------------------
// 沙箱数据根：设置页读写（LAMBCHAT_HOME 壳级覆盖文件）
// ---------------------------------------------------------------------------

/// 壳级覆盖文件名，落在 app_config_dir（`%APPDATA%/com.lambchat.app` 等，
/// 随应用安装而非随沙箱数据根）——根迁移后壳仍能找到它。用户级环境变量
/// 在 GUI 进程里没有可靠的跨平台持久化写法（Windows 注册表 / macOS
/// launchctl 各一套且互不兼容），统一收敛到这份文件：壳启动时把它注入为
/// `LAMBCHAT_HOME`（见 [`apply_sandbox_home_override`]），daemon 由壳 spawn
/// 继承同一变量，两侧（Python `paths.home_root()`）解析到同一目录。
const SANDBOX_HOME_OVERRIDE_FILE: &str = "sandbox-home.json";

fn sandbox_home_override_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("failed to resolve app config dir: {e}"))?;
    Ok(dir.join(SANDBOX_HOME_OVERRIDE_FILE))
}

/// 覆盖文件内容 → 自定义根（损坏 JSON / 缺 `home` 键 / 空白值 → None）。
fn parse_sandbox_home_override(raw: &str) -> Option<String> {
    let parsed = serde_json::from_str::<serde_json::Value>(raw).ok()?;
    let home = parsed.get("home")?.as_str()?.trim().to_string();
    if home.is_empty() {
        None
    } else {
        Some(home)
    }
}

/// 读覆盖文件里的自定义根（文件缺失/不可读 → None，仅此而已——损坏降级
/// 等价未自定义，绝不阻断启动）。
fn read_sandbox_home_override(app: &AppHandle) -> Option<String> {
    let path = sandbox_home_override_path(app).ok()?;
    let raw = std::fs::read_to_string(&path).ok()?;
    parse_sandbox_home_override(&raw)
}

/// 壳启动注入（lib.rs setup 最先调用）：覆盖文件存在且外部未显式设置
/// `LAMBCHAT_HOME` 时注入环境变量——此后 `sandbox_home()`、daemon spawn、
/// PBS 播种全部自动跟随。显式环境变量优先（手工启动调试场景不被覆盖）。
pub(crate) fn apply_sandbox_home_override(app: &AppHandle) {
    let Some(home) = read_sandbox_home_override(app) else { return };
    if let Some(existing) = std::env::var_os("LAMBCHAT_HOME") {
        if !existing.to_string_lossy().trim().is_empty() {
            return;
        }
    }
    std::env::set_var("LAMBCHAT_HOME", &home);
}

/// 新根合法性（纯校验，便于单测）：非空、绝对路径、不等于当前根、与当前
/// 根互不嵌套（新根在旧根内部，迁移会把目录搬进自己；旧根在新根内部，
/// 迁移语义退化为"旧根整树搬进新根后仍套在新根里"的递归混乱）。
fn validate_new_sandbox_home(raw: &str, current: &Path) -> Result<PathBuf, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("path is empty".to_string());
    }
    let new_home = PathBuf::from(trimmed);
    if !new_home.is_absolute() {
        return Err(format!("path is not absolute: {trimmed}"));
    }
    if new_home == current {
        return Err(format!("path is already the sandbox home: {trimmed}"));
    }
    if new_home.starts_with(current) || current.starts_with(&new_home) {
        return Err(format!(
            "new sandbox home must not overlap the current one: {trimmed} vs {}",
            current.display()
        ));
    }
    Ok(new_home)
}

/// 递归拷贝目录（跨卷 rename 失败后的回退路径：copy + remove）。
fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dst)
        .map_err(|e| format!("failed to create {}: {e}", dst.display()))?;
    let entries = std::fs::read_dir(src)
        .map_err(|e| format!("failed to read {}: {e}", src.display()))?;
    for entry in entries {
        let entry =
            entry.map_err(|e| format!("failed to read entry in {}: {e}", src.display()))?;
        let from = entry.path();
        let to = dst.join(entry.file_name());
        if from.is_dir() {
            copy_dir_recursive(&from, &to)?;
        } else {
            std::fs::copy(&from, &to).map_err(|e| {
                format!("failed to copy {} -> {}: {e}", from.display(), to.display())
            })?;
        }
    }
    Ok(())
}

/// 旧根顶层条目迁移到新根：先 rename（同盘零拷贝），跨卷失败回退递归
/// copy + remove；目标已存在则跳过（部分失败后重跑幂等，绝不覆盖新根
/// 已有内容）。旧根不存在（全新安装）直接 0 迁移。返回迁移条目数。
fn migrate_root_entries(old_root: &Path, new_root: &Path) -> Result<usize, String> {
    let entries = match std::fs::read_dir(old_root) {
        Ok(entries) => entries,
        Err(_) => return Ok(0), // 旧根不存在：无需迁移
    };
    let mut moved = 0usize;
    for entry in entries.flatten() {
        let from = entry.path();
        let to = new_root.join(entry.file_name());
        if to.exists() {
            continue; // 幂等：已在新根的条目跳过，不覆盖
        }
        if std::fs::rename(&from, &to).is_err() {
            // 跨卷（不同盘符/挂载点）rename 失败 → copy + remove 回退
            copy_dir_recursive(&from, &to)?;
            if from.is_dir() {
                std::fs::remove_dir_all(&from).map_err(|e| {
                    format!("failed to remove {}: {e}", from.display())
                })?;
            } else {
                std::fs::remove_file(&from)
                    .map_err(|e| format!("failed to remove {}: {e}", from.display()))?;
            }
        }
        moved += 1;
    }
    Ok(moved)
}

/// 沙箱数据根状态（设置页"数据位置"卡片）。
#[derive(serde::Serialize)]
pub struct SandboxDataLocation {
    /// 当前生效根（LAMBCHAT_HOME 或缺省 ~/.lambchat）
    pub root: String,
    /// 当前根非缺省（覆盖文件或外部环境变量生效）
    pub customized: bool,
    /// 壳级覆盖文件存在（"恢复默认"按钮可用；仅外部环境变量生效时 false）
    pub override_configured: bool,
}

/// 读取沙箱数据根。
#[tauri::command]
pub fn sandbox_data_location(app: AppHandle) -> Result<SandboxDataLocation, String> {
    let root = sandbox_home()?;
    let override_configured = read_sandbox_home_override(&app).is_some();
    let customized = Some(&root) != default_sandbox_home().as_ref();
    Ok(SandboxDataLocation {
        root: root.to_string_lossy().into_owned(),
        customized,
        override_configured,
    })
}

/// 更改沙箱数据根（设置页"更改位置"）。校验 → 停 daemon（迁移前释放
/// audit/workspaces 文件句柄）→ 可选迁移旧根顶层条目 → 写覆盖文件 →
/// 本进程 `set_var` 即时生效。**前端成功后须引导重启壳**：PBS 播种等
/// 启动期逻辑与托盘状态在 relaunch 后才彻底换根。async：跨盘迁移数百
/// MB（PBS 运行时）耗时长，不阻塞主线程命令通道。
#[tauri::command]
pub async fn set_sandbox_data_location(
    app: AppHandle,
    path: String,
    migrate_data: bool,
) -> Result<(), String> {
    let current = sandbox_home()?;
    let new_home = validate_new_sandbox_home(&path, &current)?;
    std::fs::create_dir_all(&new_home)
        .map_err(|e| format!("failed to create {}: {e}", new_home.display()))?;

    stop(&app);

    if migrate_data {
        migrate_root_entries(&current, &new_home)?;
    }

    let override_path = sandbox_home_override_path(&app)?;
    if let Some(parent) = override_path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
    }
    let payload = serde_json::json!({ "home": new_home.to_string_lossy() });
    let raw = serde_json::to_string(&payload)
        .map_err(|e| format!("failed to serialize override: {e}"))?;
    write_atomic_file(&override_path, raw.as_bytes())?;

    std::env::set_var("LAMBCHAT_HOME", &new_home);
    emit_status(&app); // daemon 已停：状态行即时翻转，不等事件
    Ok(())
}

/// 恢复缺省根（设置页"恢复默认"）：删覆盖文件 + 清本进程变量。已有数据
/// 留在原处不搬回（前端文案明示）；重启壳后回落 `~/.lambchat`。
#[tauri::command]
pub fn clear_sandbox_data_location(app: AppHandle) -> Result<(), String> {
    let override_path = sandbox_home_override_path(&app)?;
    if override_path.exists() {
        std::fs::remove_file(&override_path).map_err(|e| {
            format!("failed to remove {}: {e}", override_path.display())
        })?;
    }
    std::env::remove_var("LAMBCHAT_HOME");
    Ok(())
}


#[cfg(test)]
mod sandbox_home_override_tests {
    use super::*;

    /// 覆盖文件解析：合法值、空白值、缺键、损坏 JSON 各自落位——除合法
    /// 值外一律 None（损坏降级等价未自定义，不阻断启动）。
    #[test]
    fn parse_override_handles_valid_blank_missing_and_corrupt() {
        assert_eq!(
            parse_sandbox_home_override(r#"{"home":"D:\\lambchat"}"#),
            Some("D:\\lambchat".to_string())
        );
        assert_eq!(parse_sandbox_home_override(r#"{"home":"  "}"#), None);
        assert_eq!(parse_sandbox_home_override(r#"{"other":1}"#), None);
        assert_eq!(parse_sandbox_home_override("not json"), None);
    }

    /// 新根校验：空/相对路径/同根/双向嵌套拒绝，无关绝对路径（含首尾
    /// 空白）放行。路径用 temp_dir 推导保证跨平台绝对路径语义。
    #[test]
    fn validate_rejects_empty_relative_same_and_overlapping() {
        let tmp = std::env::temp_dir();
        let current = tmp.join("lc-home-current");

        assert!(validate_new_sandbox_home("", &current).is_err());
        assert!(validate_new_sandbox_home("   ", &current).is_err());
        assert!(validate_new_sandbox_home("relative/path", &current).is_err());
        assert!(validate_new_sandbox_home(
            current.to_string_lossy().as_ref(),
            &current
        )
        .is_err());
        // 新根嵌在当前根内 → 拒绝
        assert!(validate_new_sandbox_home(
            current.join("sub").to_string_lossy().as_ref(),
            &current
        )
        .is_err());
        // 当前根嵌在新根内 → 拒绝
        let bigger = tmp.join("lc-home-bigger");
        assert!(validate_new_sandbox_home(
            bigger.to_string_lossy().as_ref(),
            &bigger.join("nested")
        )
        .is_err());
        // 无关绝对路径放行；首尾空白容忍
        let other = tmp.join("lc-home-other").to_string_lossy().into_owned();
        assert!(validate_new_sandbox_home(&other, &current).is_ok());
        assert!(validate_new_sandbox_home(&format!("  {other}  "), &current).is_ok());
    }

    /// 顶层条目迁移：全部搬走（目录递归 + 文件）、重跑幂等（目标已存在
    /// 跳过不覆盖）、旧根不存在返回 0。
    #[test]
    fn migrate_root_entries_moves_top_level_and_is_idempotent() {
        let tmp = std::env::temp_dir().join(format!("lc-migrate-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        let old_root = tmp.join("old");
        let new_root = tmp.join("new");
        std::fs::create_dir_all(old_root.join("audit")).unwrap();
        std::fs::write(old_root.join("audit").join("a.jsonl"), "log").unwrap();
        std::fs::write(old_root.join("sandbox.json"), "{}").unwrap();

        let moved = migrate_root_entries(&old_root, &new_root).unwrap();
        assert_eq!(moved, 2);
        assert!(new_root.join("audit").join("a.jsonl").exists());
        assert!(!old_root.join("sandbox.json").exists());

        // 重跑幂等：旧根重新出现同名条目，但新根已存在 → 跳过（不覆盖）
        std::fs::write(old_root.join("sandbox.json"), "stale").unwrap();
        let moved_again = migrate_root_entries(&old_root, &new_root).unwrap();
        assert_eq!(moved_again, 0);
        assert!(new_root.join("sandbox.json").exists());
        // 跳过的旧条目留在原地（内容未被动过）
        assert_eq!(
            std::fs::read_to_string(old_root.join("sandbox.json")).unwrap(),
            "stale"
        );

        // 旧根不存在（全新安装）→ 0 迁移
        let absent = migrate_root_entries(&tmp.join("nope"), &new_root).unwrap();
        assert_eq!(absent, 0);

        let _ = std::fs::remove_dir_all(&tmp);
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::sync::Arc;

    /// 稳定运行 ≥ 5 分钟后预算恢复；不足则维持（cloudflald 模式的恢复窗口）。
    #[test]
    fn restart_budget_resets_after_stable_run() {
        assert!(!should_reset_restart_budget(Duration::from_secs(0)));
        assert!(!should_reset_restart_budget(Duration::from_secs(299)));
        assert!(should_reset_restart_budget(Duration::from_secs(300)));
        assert!(should_reset_restart_budget(Duration::from_secs(3600)));
    }

    /// 重启退避：1s 起步按 2 的幂增长，封顶 30s。
    #[test]
    fn restart_backoff_grows_then_caps() {
        assert_eq!(restart_backoff(0), Duration::from_secs(1));
        assert_eq!(restart_backoff(1), Duration::from_secs(2));
        assert_eq!(restart_backoff(2), Duration::from_secs(4));
        assert_eq!(restart_backoff(3), Duration::from_secs(8));
        assert_eq!(restart_backoff(4), Duration::from_secs(16));
        assert_eq!(restart_backoff(5), Duration::from_secs(30));
        assert_eq!(restart_backoff(200), Duration::from_secs(30));
    }

    /// sidecar 解析（v2.9.0 打包回归锚点）：externalBin 真实落位——主程序
    /// 同目录、无 triple 后缀——必须排候选首位。打包产物（deb/AppImage/
    /// macOS .app）实测 daemon 与主程序同级、名叫 lambchat-daemon；旧解析
    /// 找 resource_dir/binaries/lambchat-daemon-<triple> 两者皆不中，
    /// 打包后 restartDaemon 必败 → 配对失败。
    #[test]
    fn sidecar_candidates_prefer_bundled_exe_adjacent_name() {
        let tmp =
            std::env::temp_dir().join(format!("lambchat-sidecar-cand-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        let exe_dir = tmp.join("bin");
        let res_dir = tmp.join("resources");
        std::fs::create_dir_all(&exe_dir).unwrap();
        std::fs::create_dir_all(res_dir.join("binaries")).unwrap();

        // 打包真实布局：主程序同目录 lambchat-daemon（externalBin 剥 triple）
        let bundled = exe_dir.join(format!("lambchat-daemon{}", sidecar_exe_suffix()));
        std::fs::write(&bundled, b"daemon").unwrap();
        // 旧约定同放一份：真实布局必须优先
        if let Some(triple) = current_target_triple() {
            std::fs::write(
                res_dir
                    .join("binaries")
                    .join(format!("lambchat-daemon-{triple}{}", sidecar_exe_suffix())),
                b"daemon",
            )
            .unwrap();
        }
        let candidates = sidecar_candidates(&exe_dir, Some(&res_dir));
        assert_eq!(candidates.first(), Some(&bundled));
        assert!(candidates.len() >= 3);

        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// 无打包布局时保留 resource_dir/binaries 旧约定兜底（候选顺序锁死）。
    #[test]
    fn sidecar_candidates_fall_back_to_resource_binaries() {
        let tmp = std::env::temp_dir().join(format!(
            "lambchat-sidecar-fallback-test-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&tmp);
        let exe_dir = tmp.join("bin");
        let res_dir = tmp.join("resources");
        std::fs::create_dir_all(&exe_dir).unwrap();

        let candidates = sidecar_candidates(&exe_dir, Some(&res_dir));
        assert_eq!(
            candidates.first(),
            Some(&exe_dir.join(format!("lambchat-daemon{}", sidecar_exe_suffix())))
        );
        if let Some(triple) = current_target_triple() {
            assert_eq!(
                candidates.get(2),
                Some(
                    &res_dir
                        .join("binaries")
                        .join(format!("lambchat-daemon-{triple}{}", sidecar_exe_suffix()))
                )
            );
        }

        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// running 原子镜像（主线程零锁状态查询）：槽位取走即翻 false——
    /// 状态 IPC 绝不等 child 锁（auto-pair 重启持锁 spawn 期间进偏好设置
    /// 曾把主线程锁死）。
    #[test]
    fn running_mirror_tracks_slot_occupancy() {
        let manager = DaemonManager::default();
        assert!(!manager.running.load(Ordering::SeqCst));
        // 模拟 start 装槽（无法无 AppHandle 真跑 start：直接验证镜像契约）
        manager.running.store(true, Ordering::SeqCst);
        assert!(manager.running.load(Ordering::SeqCst));
        // take_if_current 取走空槽（generation 匹配）→ 镜像复位
        manager.generation.store(1, Ordering::SeqCst);
        assert!(manager.take_if_current(1).is_none());
        assert!(!manager.running.load(Ordering::SeqCst));
        // generation 不匹配 → 镜像不动
        manager.running.store(true, Ordering::SeqCst);
        assert!(manager.take_if_current(999).is_none());
        assert!(manager.running.load(Ordering::SeqCst));
    }

    /// 有界收尸（v2.9.1 偏好设置卡死回归锚点）：kill 后快速等到退出。
    #[test]
    fn reap_bounded_returns_after_kill() {
        use command_group::CommandGroup;
        let mut child = std::process::Command::new("sleep")
            .arg("30")
            .group_spawn()
            .expect("spawn sleep");
        let _ = child.kill();
        let t0 = std::time::Instant::now();
        assert!(reap_bounded(&mut child, std::time::Duration::from_secs(2)));
        assert!(t0.elapsed() < std::time::Duration::from_secs(2));
    }

    /// 活着不退的进程：宽限到点必须返回 false（放弃句柄而非无限等）。
    #[test]
    fn reap_bounded_gives_up_at_deadline() {
        use command_group::CommandGroup;
        let mut child = std::process::Command::new("sleep")
            .arg("30")
            .group_spawn()
            .expect("spawn sleep");
        let t0 = std::time::Instant::now();
        assert!(!reap_bounded(
            &mut child,
            std::time::Duration::from_millis(300)
        ));
        assert!(t0.elapsed() < std::time::Duration::from_secs(2));
        let _ = child.kill();
    }

    /// 配对文件生命周期：save_pairing 落盘 pat_id → 策略独立写保留其余字段
    /// → clear_pairing 删 pat 文件并移除 pat_id 键（M4 T7）。
    ///
    /// 单一测试函数内串行断言（共享同一 tmp 目录，无 $HOME 竞争）。
    #[test]
    fn pairing_files_lifecycle_pat_id_policy_and_clear() {
        let tmp = std::env::temp_dir().join(format!(
            "lambchat-daemon-pairing-test-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&tmp);
        let home = tmp.join("home");
        let sandbox = home.join(".lambchat");
        let config_path = sandbox.join("sandbox.json");
        let pat_path = sandbox.join("pat");

        // ---- save_pairing：pat_id 落盘 ----
        write_pairing_files(
            &sandbox,
            "https://lc.example",
            "lc_pat_secret",
            "all",
            Some("pat-uuid-1"),
        )
        .unwrap();
        let cfg: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert_eq!(cfg["pat_id"], "pat-uuid-1");
        assert_eq!(cfg["server_url"], "https://lc.example");
        assert_eq!(cfg["confirm_policy"], "all");
        // data_root 缺省落到 home 下 workspaces
        assert_eq!(
            cfg["data_root"].as_str().unwrap(),
            sandbox.join("workspaces").to_string_lossy()
        );
        // pat 文件内容为明文 PAT
        assert_eq!(std::fs::read_to_string(&pat_path).unwrap(), "lc_pat_secret");

        // ---- save_pairing：pat_id 为 None → 不写键（旧形态） ----
        write_pairing_files(
            &sandbox,
            "https://lc.example",
            "lc_pat_secret2",
            "none",
            None,
        )
        .unwrap();
        let cfg: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert!(cfg.get("pat_id").is_none());

        // ---- write_policy_only：只改 confirm_policy，保留其余字段（含 pat_id） ----
        write_pairing_files(
            &sandbox,
            "https://lc.example",
            "lc_pat_secret3",
            "commands",
            Some("pat-uuid-2"),
        )
        .unwrap();
        // 用户手工定制过的 data_root 必须保留
        let mut custom: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        custom["data_root"] = "/custom/ws".into();
        custom["embedded_python"] = false.into();
        std::fs::write(&config_path, serde_json::to_string_pretty(&custom).unwrap()).unwrap();

        write_policy_only(&sandbox, "none").unwrap();
        let cfg: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert_eq!(cfg["confirm_policy"], "none");
        assert_eq!(cfg["pat_id"], "pat-uuid-2");
        assert_eq!(cfg["data_root"], "/custom/ws");
        assert_eq!(cfg["embedded_python"], false);

        // ---- read_pat_file：读回配对 PAT ----
        assert_eq!(
            read_pat_file(&sandbox).unwrap().as_deref(),
            Some("lc_pat_secret3")
        );

        // ---- clear_pairing：删 pat 文件 + 移除 pat_id 键，其余保留 ----
        clear_pairing_files(&sandbox).unwrap();
        assert!(!pat_path.exists());
        let cfg: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert!(cfg.get("pat_id").is_none());
        assert_eq!(cfg["server_url"], "https://lc.example");
        assert_eq!(cfg["confirm_policy"], "none");
        assert_eq!(read_pat_file(&sandbox).unwrap(), None);

        // ---- 校验失败路径 ----
        assert!(write_pairing_files(&sandbox, "ftp://bad", "p", "all", None).is_err());
        assert!(write_pairing_files(&sandbox, "https://ok", "p", "yolo", None).is_err());
        assert!(write_pairing_files(&sandbox, "https://ok", "  ", "all", None).is_err());
        assert!(write_policy_only(&sandbox, "yolo").is_err());

        // ---- clear_pairing 幂等：文件不存在也不报错 ----
        let _ = std::fs::remove_dir_all(&sandbox);
        clear_pairing_files(&sandbox).unwrap();

        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// 机器身份链路：read_machine_id 读回本机身份；重新配对（write_pairing_files
    /// 整写配置）必须保留 daemon 生成的 machine_id/machine_name——否则换 PAT 就
    /// 换身份，服务端注册表堆积幽灵机器、前端"当前设备"标识失效。
    #[test]
    fn machine_identity_survives_repairing_and_is_readable() {
        let tmp = std::env::temp_dir().join(format!(
            "lambchat-daemon-machine-id-test-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&tmp);
        let sandbox = tmp.join(".lambchat");
        let config_path = sandbox.join("sandbox.json");

        // 未配对 / 配置不存在：无身份，Ok(None) 而非报错
        assert_eq!(read_machine_id_from(&sandbox).unwrap(), None);

        // 首次配对：配置里还没有 machine_id
        write_pairing_files(&sandbox, "https://lc.example", "p", "all", None).unwrap();
        assert_eq!(read_machine_id_from(&sandbox).unwrap(), None);

        // daemon 首启生成并持久化身份（模拟 client/lambchat_sandbox/config.py 落盘）
        let mut cfg: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        cfg["machine_id"] = "abc123def456".into();
        cfg["machine_name"] = "Yang 的 MacBook".into();
        std::fs::write(&config_path, serde_json::to_string_pretty(&cfg).unwrap()).unwrap();
        assert_eq!(
            read_machine_id_from(&sandbox).unwrap().as_deref(),
            Some("abc123def456")
        );

        // 重新配对（换 server/PAT/策略）：身份保留，其余字段照常更新
        write_pairing_files(
            &sandbox,
            "https://lc2.example",
            "p2",
            "none",
            Some("pat-uuid-x"),
        )
        .unwrap();
        let cfg: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert_eq!(cfg["machine_id"], "abc123def456");
        assert_eq!(cfg["machine_name"], "Yang 的 MacBook");
        assert_eq!(cfg["server_url"], "https://lc2.example");
        assert_eq!(
            read_machine_id_from(&sandbox).unwrap().as_deref(),
            Some("abc123def456")
        );

        // 空白身份视为无（Python 侧默认 "" 不落成幽灵值）
        let mut blank: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        blank["machine_id"] = "".into();
        std::fs::write(&config_path, serde_json::to_string_pretty(&blank).unwrap()).unwrap();
        assert_eq!(read_machine_id_from(&sandbox).unwrap(), None);

        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// 白名单路径解析：真实路径放行、符号链接逃逸与 `..` 逃逸拒绝。
    ///
    /// 注意：本仓库 Rust 侧以 `cargo build` 为验证主线，此测试是
    /// `resolve_openable_path` 安全语义的回归锚点（`cargo test` 本地跑，未接 CI）。
    /// 单一测试函数内串行断言，避免 `$HOME` 环境变量并发竞争。
    #[test]
    fn resolve_openable_path_blocks_symlink_escape_and_dotdot() {
        let tmp =
            std::env::temp_dir().join(format!("lambchat-daemon-path-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        let home = tmp.join("home");
        let sandbox = home.join(".lambchat");
        std::fs::create_dir_all(sandbox.join("workspaces")).unwrap();
        std::fs::create_dir_all(sandbox.join("audit")).unwrap();
        std::fs::create_dir_all(sandbox.join("logs")).unwrap();
        std::fs::write(sandbox.join("workspaces").join("note.txt"), "x").unwrap();
        // 白名单内的符号链接指向敏感路径——逃逸载体。
        std::os::unix::fs::symlink("/etc/passwd", sandbox.join("workspaces").join("evil")).unwrap();

        let original_home = std::env::var_os("HOME");
        std::env::set_var("HOME", &home);

        // 白名单内的真实路径放行（canonicalize 后前缀校验通过）。
        assert!(resolve_openable_path("workspaces").is_ok());
        assert!(resolve_openable_path("audit").is_ok());
        // logs（desktop.log 所在目录）同属白名单。
        assert!(resolve_openable_path("logs").is_ok());
        assert!(resolve_openable_path(&sandbox.join("audit").to_string_lossy()).is_ok());
        assert!(
            resolve_openable_path(&sandbox.join("workspaces/note.txt").to_string_lossy()).is_ok()
        );

        // 符号链接逃逸：词法上在 workspaces 内，canonical 指向 /etc/passwd——必须拒绝。
        // （词法校验优先的旧实现在此会错误放行。）
        assert!(resolve_openable_path(&sandbox.join("workspaces/evil").to_string_lossy()).is_err());

        // `..` 词法逃逸拒绝。
        assert!(
            resolve_openable_path(&sandbox.join("workspaces/../../etc").to_string_lossy()).is_err()
        );
        // 兄弟目录前缀（组件级 starts_with）拒绝。
        assert!(resolve_openable_path(&sandbox.join("workspaces-evil").to_string_lossy()).is_err());
        // 白名单外绝对路径拒绝。
        assert!(resolve_openable_path("/etc/passwd").is_err());

        // LAMBCHAT_HOME 优先于 HOME/USERPROFILE（沙箱根可迁移；与 Python
        // paths.home_root() 同语义）。仍在 HOME 已设的本测试函数内断言——
        // env 竞争纪律：本模块所有 env 断言集中在此串行函数。
        std::env::set_var("LAMBCHAT_HOME", tmp.join("custom-root"));
        assert_eq!(sandbox_home().unwrap(), tmp.join("custom-root"));
        // 空白值视同未设：回落 HOME 下的 .lambchat（此刻 HOME 仍指向 tmp/home）。
        std::env::set_var("LAMBCHAT_HOME", "   ");
        assert_eq!(sandbox_home().unwrap(), home.join(".lambchat"));
        std::env::remove_var("LAMBCHAT_HOME");

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
        use command_group::CommandGroup;
        let mut child_gen1 = std::process::Command::new("sleep")
            .arg("30")
            .group_spawn()
            .unwrap();
        let pid_gen1 = child_gen1.id();
        let child_gen3 = std::process::Command::new("sleep")
            .arg("30")
            .group_spawn()
            .unwrap();

        // 主线程持锁：装入 gen=1 的子进程（start 的落点效果）。
        let mut slot = lock_ok(&manager.child);
        manager.generation.store(1, Ordering::SeqCst);
        *slot = Some(DaemonChild::Group(child_gen1));

        // 监视线线程：此刻 generation 仍为 1（主线程持锁且尚未递增）。
        // 旧实现在锁外通过检查后，会阻塞在主线程持有的 child 锁上。
        let stale_manager = Arc::clone(&manager);
        let stale_exit = std::thread::spawn(move || stale_manager.take_if_current(1));

        // 给监视线足够时间完成锁外检查并阻塞在锁上（50ms ≫ 线程启动）。
        std::thread::sleep(std::time::Duration::from_millis(50));

        // restart_daemon 交错（修复后纪律：generation 变更全程持锁）——
        // stop：gen→2、取走并 kill 旧子进程；start：gen→3、装入新子进程。
        manager.generation.fetch_add(1, Ordering::SeqCst);
        if let Some(DaemonChild::Group(mut old)) = slot.take() {
            let _ = old.kill();
            let _ = old.wait();
        }
        manager.generation.fetch_add(1, Ordering::SeqCst);
        *slot = Some(DaemonChild::Group(child_gen3));
        drop(slot);

        match stale_exit.join().unwrap() {
            // 正确：迟到的 gen=1 退出事件不得触碰新一代槽位。
            None => {}
            // 理论上仅当交错未发生（gen 仍为 1 时取走原槽位）才会走到这里，
            // 此时取到的必须是 gen=1 的子进程本身；取到新代 pid 即竞窗实锤。
            Some(DaemonChild::Group(mut c)) => {
                let pid = c.id();
                let _ = c.kill();
                let _ = c.wait();
                assert_eq!(
                    pid, pid_gen1,
                    "stale exit handler took the child of a newer generation"
                );
            }
        }

        // 新代子进程必须仍在槽内（未被迟到的退出事件 take 掉）。
        let mut final_slot = lock_ok(&manager.child);
        match final_slot.take() {
            Some(DaemonChild::Group(mut c)) => {
                let _ = c.kill();
                let _ = c.wait();
            }
            _ => panic!("new-generation child was taken by the stale exit handler"),
        }
    }
}
