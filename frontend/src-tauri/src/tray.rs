//! 系统托盘：显示主窗口 / 打开工作区目录 / 打开审计目录 / 退出。
//!
//! 菜单文案按系统 locale 本地化（M4 T8）：en / zh / ja / ko / ru 五张表，
//! 无法识别或未覆盖的语言缺省英文。构建失败（如 Linux 缺 appindicator
//! 运行库）仅告警，不影响主窗口。

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

use crate::daemon;

/// 托盘菜单文案表（静态：菜单构建时一次性取用）。
struct TrayLabels {
    show: &'static str,
    workspaces: &'static str,
    audit: &'static str,
    quit: &'static str,
}

const LABELS_EN: TrayLabels = TrayLabels {
    show: "Show Main Window",
    workspaces: "Open Workspaces Folder",
    audit: "Open Audit Folder",
    quit: "Quit",
};

const LABELS_ZH: TrayLabels = TrayLabels {
    show: "显示主窗口",
    workspaces: "打开工作区目录",
    audit: "打开审计目录",
    quit: "退出",
};

const LABELS_JA: TrayLabels = TrayLabels {
    show: "メインウィンドウを表示",
    workspaces: "ワークスペースフォルダを開く",
    audit: "監査フォルダを開く",
    quit: "終了",
};

const LABELS_KO: TrayLabels = TrayLabels {
    show: "메인 창 표시",
    workspaces: "워크스페이스 폴더 열기",
    audit: "감사 폴더 열기",
    quit: "종료",
};

const LABELS_RU: TrayLabels = TrayLabels {
    show: "Показать главное окно",
    workspaces: "Открыть папку рабочих областей",
    audit: "Открыть папку аудита",
    quit: "Выход",
};

/// 按系统 locale 选语言表：取主语言子标签（`zh-CN` / `zh_CN` / `ja` →
/// `zh` / `ja`），命中 en/zh/ja/ko/ru 之一；缺省（含无法识别）英文。
fn labels_for_locale(locale: Option<&str>) -> &'static TrayLabels {
    let primary = locale
        .and_then(|tag| tag.split(['-', '_']).next())
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase();
    match primary.as_str() {
        "zh" => &LABELS_ZH,
        "ja" => &LABELS_JA,
        "ko" => &LABELS_KO,
        "ru" => &LABELS_RU,
        _ => &LABELS_EN,
    }
}

/// 初始化托盘；任何失败都不阻塞壳启动。
pub fn init(app: &AppHandle) {
    if let Err(e) = build_tray(app) {
        eprintln!("[lambchat-tray] tray unavailable (main window unaffected): {e}");
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let labels = labels_for_locale(sys_locale::get_locale().as_deref());
    let show = MenuItem::with_id(app, "show", labels.show, true, None::<&str>)?;
    let workspaces = MenuItem::with_id(app, "open-workspaces", labels.workspaces, true, None::<&str>)?;
    let audit = MenuItem::with_id(app, "open-audit", labels.audit, true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", labels.quit, true, None::<&str>)?;
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

#[cfg(test)]
mod tests {
    use super::*;

    /// locale → 语言表映射：主子标签命中五语，其余/缺失缺省英文。
    #[test]
    fn locale_selects_five_language_tables() {
        let zh = labels_for_locale(Some("zh-CN"));
        assert_eq!(zh.show, "显示主窗口");
        assert_eq!(zh.quit, "退出");
        assert_eq!(labels_for_locale(Some("zh_CN.utf8")).workspaces, "打开工作区目录");
        assert_eq!(labels_for_locale(Some("ja_JP")).show, "メインウィンドウを表示");
        assert_eq!(labels_for_locale(Some("ko-KR")).quit, "종료");
        assert_eq!(labels_for_locale(Some("ru_RU")).audit, "Открыть папку аудита");
    }

    /// 缺省与未覆盖语言回落英文表。
    #[test]
    fn unknown_or_missing_locale_falls_back_to_english() {
        let en = labels_for_locale(None);
        assert_eq!(en.show, "Show Main Window");
        assert_eq!(labels_for_locale(Some("fr-FR")).quit, "Quit");
        assert_eq!(labels_for_locale(Some("")).workspaces, "Open Workspaces Folder");
        // 大小写与空白容错
        assert_eq!(labels_for_locale(Some(" ZH-cn ")).show, "显示主窗口");
    }
}
