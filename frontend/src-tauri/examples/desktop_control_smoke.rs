//! Local native acceptance fixture. Uses an isolated app identity and no real input.
#[path = "../src/commands/desktop_control.rs"]
mod desktop_control;
use tauri::Manager;

struct FixtureChild(std::sync::Mutex<std::process::Child>);
struct FixtureToken(String);
fn finish(app: &tauri::AppHandle, code: i32) {
    if let Some(child) = app.try_state::<FixtureChild>() {
        if let Ok(mut child) = child.0.lock() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    app.exit(code);
}

#[tauri::command(rename = "desktop_control_status")]
fn fixture_status(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    ready: bool,
    report: Option<serde_json::Value>,
) -> Result<String, String> {
    if let Some(report) = report {
        eprintln!("control-fixture-report {report}");
        if let Some(ok) = report["ok"].as_bool() {
            let monitors = app.available_monitors().map_err(|e| e.to_string())?;
            let overlays: Vec<_> = app
                .webview_windows()
                .into_iter()
                .filter(|(label, _)| label.starts_with("cua-overlay-"))
                .collect();
            let geometry_ok = overlays.len() == monitors.len()
                && monitors.iter().enumerate().all(|(index, monitor)| {
                    app.get_webview_window(&format!("cua-overlay-{index}"))
                        .is_some_and(|window| {
                            window.outer_position().ok().as_ref() == Some(monitor.position())
                                && window.inner_size().ok().as_ref() == Some(monitor.size())
                        })
                });
            for (label, window) in &overlays {
                eprintln!(
                    "control-surface-geometry {label} position={:?} size={:?} visible={:?}",
                    window.outer_position(),
                    window.inner_size(),
                    window.is_visible()
                );
            }
            for monitor in &monitors {
                eprintln!(
                    "control-monitor-geometry position={:?} size={:?}",
                    monitor.position(),
                    monitor.size()
                );
            }
            let token = app.state::<FixtureToken>();
            desktop_control::receive(&app, &token.0, serde_json::json!({"state":"ended"}));
            let handle = app.clone();
            app.run_on_main_thread(move || {
                let hidden = handle.webview_windows().iter().filter(|(label, _)| label.starts_with("cua-"))
                    .all(|(_, window)| window.is_visible().ok() == Some(false));
                eprintln!("control-surface-report displays={} geometry={geometry_ok} terminal_hidden={hidden}", monitors.len());
                finish(&handle, if ok && geometry_ok && hidden { 0 } else { 1 });
            }).map_err(|e| e.to_string())?;
        }
        return Ok("reported".into());
    }
    desktop_control::desktop_control_status(window, app, ready)
}

fn main() {
    let root = std::env::var("LAMBCHAT_CONTROL_TEST_ROOT").expect("test repository root required");
    let python = std::env::var("LAMBCHAT_CONTROL_TEST_PYTHON").expect("test Python required");
    let mut context = tauri::generate_context!();
    context.config_mut().identifier = "com.lambchat.control-acceptance".into();
    // Keep the real main WebView options: Windows shares its browser process with the toolbar.
    for window in &mut context.config_mut().app.windows {
        window.url = tauri::WebviewUrl::External("about:blank".parse().unwrap());
        window.visible = false;
    }
    tauri::Builder::default()
        .manage(desktop_control::DesktopControl::default())
        .invoke_handler(tauri::generate_handler![
            fixture_status,
            desktop_control::desktop_control_set_paused
        ])
        .setup(move |app| {
            assert!(app.get_webview_window("main").is_some());
            let token = uuid::Uuid::new_v4().to_string();
            app.manage(FixtureToken(token.clone()));
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
            app.manage(FixtureChild(std::sync::Mutex::new(child)));
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
                desktop_control::detached(&handle, &token);
            });
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_secs(180));
                finish(&handle, 1);
            });
            Ok(())
        })
        .on_page_load(|window, payload| {
            eprintln!(
                "control-page-load window={} event={:?} time={:?}",
                window.label(),
                payload.event(),
                std::time::SystemTime::now()
            );
            if window.label() == "cua-control"
                && payload.event() == tauri::webview::PageLoadEvent::Finished
                && std::env::var_os("LAMBCHAT_CONTROL_AUTOMATED").is_some()
            {
                let _ = window.eval(include_str!(
                    "../../../scripts/release_tests/desktop-control-smoke.js"
                ));
            }
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
