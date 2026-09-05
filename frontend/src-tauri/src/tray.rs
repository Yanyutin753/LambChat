//! 系统托盘：显示主窗口 / 打开工作区目录 / 打开审计目录 / 退出。
//!
//! 构建失败（如 Linux 缺 appindicator 运行库）仅告警，不影响主窗口。

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

use crate::daemon;

/// 初始化托盘；任何失败都不阻塞壳启动。
pub fn init(app: &AppHandle) {
    if let Err(e) = build_tray(app) {
        eprintln!("[lambchat-tray] tray unavailable (main window unaffected): {e}");
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let workspaces =
        MenuItem::with_id(app, "open-workspaces", "打开工作区目录", true, None::<&str>)?;
    let audit = MenuItem::with_id(app, "open-audit", "打开审计目录", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &workspaces, &audit, &quit])?;

    let mut builder = TrayIconBuilder::with_id("lambchat-tray")
        .tooltip("LambChat")
        .menu(&menu)
        // 左键点击恢复主窗口（菜单只在右键弹出）。
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            "open-workspaces" => open_sandbox_dir(app, "workspaces"),
            "open-audit" => open_sandbox_dir(app, "audit"),
            "quit" => {
                daemon::stop(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// 复用 daemon::resolve_openable_path 的白名单校验后经 opener 打开。
fn open_sandbox_dir(app: &AppHandle, name: &str) {
    use tauri_plugin_opener::OpenerExt;

    match daemon::resolve_openable_path(name) {
        Ok(path) => {
            if let Err(e) = app
                .opener()
                .open_path(path.to_string_lossy(), None::<&str>)
            {
                eprintln!("[lambchat-tray] failed to open {}: {e}", path.display());
            }
        }
        Err(e) => eprintln!("[lambchat-tray] refused to open {name}: {e}"),
    }
}
