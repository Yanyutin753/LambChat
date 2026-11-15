//! Local native acceptance fixture. Uses an isolated app identity and no real input.
#[path = "../src/commands/desktop_control.rs"]
mod desktop_control;
use tauri::Manager;

#[tauri::command]
fn fixture_report(app: tauri::AppHandle, report: serde_json::Value) {
    eprintln!("control-fixture-report {report}");
    if let Some(ok) = report["ok"].as_bool() {
        app.exit(if ok { 0 } else { 1 });
    }
}

fn main() {
    let root = std::env::var("LAMBCHAT_CONTROL_TEST_ROOT").expect("test repository root required");
    let python = std::env::var("LAMBCHAT_CONTROL_TEST_PYTHON").expect("test Python required");
    let mut context = tauri::generate_context!();
    context.config_mut().identifier = "com.lambchat.control-acceptance".into();
    context.config_mut().app.windows.clear();
    tauri::Builder::default()
        .manage(desktop_control::DesktopControl::default())
        .invoke_handler(tauri::generate_handler![
            desktop_control::desktop_control_status,
            desktop_control::desktop_control_set_paused,
            fixture_report
        ])
        .setup(move |app| {
            let token = uuid::Uuid::new_v4().to_string();
            let mut child = std::process::Command::new(&python)
                .arg(format!(
                    "{root}/scripts/release_tests/desktop-control-fixture.py"
                ))
                .env("PYTHONPATH", format!("{root}/client"))
                .env("LAMBCHAT_DESKTOP_CONTROL", &token)
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::piped())
                .spawn()?;
            desktop_control::attach(app.handle(), token.clone(), child.stdin.take().unwrap());
            let out = child.stdout.take().unwrap();
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                use std::io::{BufRead, BufReader};
                let prefix = format!("LAMBCHAT_CUA:{token}:");
                for line in BufReader::new(out).lines().map_while(Result::ok) {
                    if let Some(raw) = line.strip_prefix(&prefix) {
                        if let Ok(event) = serde_json::from_str(raw) {
                            eprintln!("control-fixture {raw}");
                            desktop_control::receive(&handle, &token, event);
                        }
                    }
                }
                let _ = child.wait();
            });
            if std::env::var_os("LAMBCHAT_CONTROL_AUTOMATED").is_some() {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    for _ in 0..100 {
                        std::thread::sleep(std::time::Duration::from_millis(100));
                        if let Some(window) = handle.get_webview_window("cua-control") {
                            let _ = window.eval(include_str!("../../../scripts/release_tests/desktop-control-smoke.js"));
                            break;
                        }
                    }
                });
            }
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_secs(180));
                handle.exit(1);
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = desktop_control::set_paused(window.app_handle(), true);
            }
        })
        .run(context)
        .expect("native control fixture failed");
}
