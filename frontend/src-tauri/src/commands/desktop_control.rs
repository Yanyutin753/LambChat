//! The local user owns takeover. Only the dedicated bundled control window can resume.
use std::collections::HashSet;
use std::io::Write;
use std::process::ChildStdin;
use std::sync::Mutex;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

const LABEL: &str = "cua-control";
const OVERLAY_PREFIX: &str = "cua-overlay-";
#[derive(Default)]
pub struct DesktopControl(Mutex<Control>);
#[derive(Default)]
struct Control {
    token: String,
    input: Option<ChildStdin>,
    state: String,
    ready: bool,
    shown: bool,
    paused: bool,
    pending: Option<String>,
    overlay_labels: Vec<String>,
    overlay_ready: HashSet<String>,
    revision: u64,
}

impl Control {
    fn surfaces_ready(&self) -> bool {
        self.ready
            && self.shown
            && !self.overlay_labels.is_empty()
            && self
                .overlay_labels
                .iter()
                .all(|label| self.overlay_ready.contains(label))
    }
    fn send(&mut self, mut message: serde_json::Value) -> Result<(), String> {
        message["token"] = self.token.clone().into();
        let pipe = self.input.as_mut().ok_or("desktop_control_disconnected")?;
        writeln!(pipe, "{message}").map_err(|_| "desktop_control_disconnected".to_string())
    }
    fn permit(&mut self) -> Result<(), String> {
        if self.surfaces_ready() {
            if let Some(request) = self.pending.take() {
                self.send(serde_json::json!({"action":"permit", "request":request, "allowed": !self.paused}))?;
            }
        }
        Ok(())
    }
}

pub fn attach(app: &AppHandle, token: String, input: ChildStdin) {
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    control.token = token;
    control.revision += 1;
    control.input = Some(input);
    control.pending = None;
    control.state = "idle".into();
    // Preserve a local takeover across daemon restarts.
    if control.paused {
        let _ = control.send(serde_json::json!({"action":"pause"}));
        control.state = "paused".into();
    }
}

pub fn detached(app: &AppHandle, token: &str) {
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if control.token == token {
        control.input = None;
        control.pending = None;
        control.state = "disconnected".into();
        control.revision += 1;
        drop(control);
        hide_surfaces(app, true);
    }
}

pub fn receive(app: &AppHandle, token: &str, event: serde_json::Value) {
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if control.token != token {
        return;
    }
    match event["state"].as_str() {
        Some("unavailable") => {
            control.revision += 1;
            control.paused = true;
            control.state = "unavailable".into();
            if let Some(request) = control.pending.take() {
                let _ = control.send(
                    serde_json::json!({"action":"permit", "request":request, "allowed":false}),
                );
            }
            drop(control);
            hide_surfaces(app, false);
        }
        Some("ended") => {
            control.revision += 1;
            control.pending = None;
            control.shown = false;
            control.state = "ended".into();
            drop(control);
            hide_surfaces(app, true);
        }
        Some("session") => {
            control.revision += 1;
            let revision = control.revision;
            if let Some(paused) = event["paused"].as_bool() {
                control.paused = paused;
            }
            control.state = if control.paused { "paused" } else { "waiting" }.into();
            drop(control);
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || {
                if handle
                    .state::<DesktopControl>()
                    .0
                    .lock()
                    .unwrap_or_else(|p| p.into_inner())
                    .revision
                    == revision
                {
                    let _ = show(&handle);
                }
            });
        }
        Some("request") => {
            let Some(request) = event["request"].as_str().filter(|s| s.len() == 32) else {
                return;
            };
            control.pending = Some(request.into());
            control.revision += 1;
            let revision = control.revision;
            control.ready = false;
            control.overlay_ready.clear();
            control.shown = false;
            control.state = if control.paused { "paused" } else { "waiting" }.into();
            drop(control);
            let handle = app.clone();
            let generation = token.to_string();
            let _ = app.run_on_main_thread(move || {
                let manager = handle.state::<DesktopControl>();
                {
                    let control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
                    if control.token != generation || control.revision != revision { return; }
                }
                let shown = show(&handle);
                let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
                if control.revision != revision || control.token != generation {
                    drop(control);
                    hide_surfaces(&handle, true);
                    return;
                }
                if let Err(error) = shown {
                    let _ = writeln!(std::io::stderr(), "[desktop-control] Cannot show toolbar: {error}");
                    control.state = "unavailable".into();
                    if let Some(request) = control.pending.take() {
                        let _ = control.send(serde_json::json!({"action":"permit", "request":request, "allowed":false}));
                    }
                } else {
                    control.shown = true;
                    if control.permit().is_err() { control.state = "disconnected".into(); }
                }
                let failed = matches!(control.state.as_str(), "unavailable" | "disconnected");
                drop(control);
                if failed { hide_surfaces(&handle, true); }
            });
        }
        Some(state @ ("active" | "idle" | "paused")) => {
            // The daemon acknowledges pause only after disposing of the active worker.
            if state == "paused" {
                control.paused = true;
            }
            control.state = if control.paused && state != "paused" {
                "stopping"
            } else {
                state
            }
            .into();
            if control.paused {
                drop(control);
                hide_surfaces(app, false);
            }
        }
        _ => {}
    }
}

fn takeover_position(
    area: tauri::PhysicalRect<i32, u32>,
    size: tauri::PhysicalSize<u32>,
    margin: i32,
) -> tauri::PhysicalPosition<i32> {
    tauri::PhysicalPosition::new(
        area.position.x + (area.size.width.saturating_sub(size.width) / 2) as i32,
        area.position.y + (area.size.height.saturating_sub(size.height) as i32 - margin).max(0),
    )
}

fn show(app: &AppHandle) -> Result<(), String> {
    let paused = app
        .state::<DesktopControl>()
        .0
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .paused;
    if !paused {
        show_overlays(app)?;
    }
    if let Some(window) = app.get_webview_window(LABEL) {
        return window.show().map_err(|e| e.to_string());
    }
    let mut builder =
        WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("cua-control.html".into()));
    // WebView2 rejects a shared browser process when window options differ.
    if let Some(args) = app
        .config()
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")
        .and_then(|window| window.additional_browser_args.as_deref())
    {
        builder = builder.additional_browser_args(args);
    }
    let monitor = app
        .get_webview_window("main")
        .and_then(|window| window.current_monitor().ok().flatten())
        .or_else(|| app.primary_monitor().ok().flatten())
        .ok_or("desktop_control_no_display")?;
    let window = builder
        .title("LambChat")
        .inner_size(460.0, 112.0)
        .min_inner_size(460.0, 112.0)
        .decorations(false)
        .resizable(true)
        .always_on_top(true)
        .visible_on_all_workspaces(true)
        .content_protected(true)
        .skip_taskbar(true)
        .focused(false)
        .visible(false)
        .build()
        .map_err(|e| e.to_string())?;
    window
        .set_position(takeover_position(
            *monitor.work_area(),
            window.outer_size().map_err(|e| e.to_string())?,
            (24.0 * monitor.scale_factor()).round() as i32,
        ))
        .map_err(|e| e.to_string())?;
    window.show().map_err(|e| e.to_string())
}

fn show_overlays(app: &AppHandle) -> Result<(), String> {
    let monitors = app.available_monitors().map_err(|e| e.to_string())?;
    if monitors.is_empty() {
        return Err("desktop_control_no_display".into());
    }
    let labels: Vec<String> = (0..monitors.len())
        .map(|index| format!("{OVERLAY_PREFIX}{index}"))
        .collect();
    for (label, monitor) in labels.iter().zip(monitors.iter()) {
        let window = if let Some(window) = app.get_webview_window(label) {
            window
        } else {
            let size = monitor.size().to_logical::<f64>(monitor.scale_factor());
            let position = monitor.position().to_logical::<f64>(monitor.scale_factor());
            let mut builder = WebviewWindowBuilder::new(
                app,
                label,
                WebviewUrl::App("cua-control.html?surface=overlay".into()),
            );
            if let Some(args) = app
                .config()
                .app
                .windows
                .iter()
                .find(|w| w.label == "main")
                .and_then(|w| w.additional_browser_args.as_deref())
            {
                builder = builder.additional_browser_args(args);
            }
            builder
                .title("LambChat Control Overlay")
                // GTK fixes a non-resizable window's size at its first configure event.
                .inner_size(size.width, size.height)
                .position(position.x, position.y)
                .transparent(true)
                .decorations(false)
                .shadow(false)
                .resizable(false)
                .always_on_top(true)
                .visible_on_all_workspaces(true)
                .content_protected(true)
                .skip_taskbar(true)
                .focused(false)
                .focusable(false)
                .visible(false)
                .build()
                .map_err(|e| e.to_string())?
        };
        window
            .set_size(*monitor.size())
            .map_err(|e| e.to_string())?;
        window
            .set_position(*monitor.position())
            .map_err(|e| e.to_string())?;
        window.show().map_err(|e| e.to_string())?;
        // GTK must realize the window before Tao can set its input shape.
        window
            .set_ignore_cursor_events(true)
            .map_err(|e| e.to_string())?;
    }
    for (label, window) in app.webview_windows() {
        if label.starts_with(OVERLAY_PREFIX) && !labels.contains(&label) {
            let _ = window.hide();
        }
    }
    app.state::<DesktopControl>()
        .0
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .overlay_labels = labels;
    Ok(())
}

fn hide_surfaces(app: &AppHandle, include_control: bool) {
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        {
            let manager = handle.state::<DesktopControl>();
            let control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
            if include_control
                && !matches!(
                    control.state.as_str(),
                    "ended" | "disconnected" | "unavailable"
                )
            {
                return;
            }
            if !include_control && !control.paused {
                return;
            }
        }
        for (label, window) in handle.webview_windows() {
            if label.starts_with(OVERLAY_PREFIX) || (include_control && label == LABEL) {
                let _ = window.hide();
            }
        }
    });
}

fn check(window: &WebviewWindow) -> Result<(), String> {
    if window.label() == LABEL {
        Ok(())
    } else {
        Err("desktop_control_window_required".into())
    }
}

#[tauri::command]
pub fn desktop_control_status(
    window: WebviewWindow,
    app: AppHandle,
    ready: bool,
) -> Result<String, String> {
    if window.label() != LABEL && !window.label().starts_with(OVERLAY_PREFIX) {
        return Err("desktop_control_window_required".into());
    }
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if ready {
        if window.label() == LABEL {
            control.ready = true;
        } else {
            control.overlay_ready.insert(window.label().to_string());
        }
        control.permit()?;
    }
    Ok(control.state.clone())
}

#[tauri::command]
pub fn desktop_control_set_paused(
    window: WebviewWindow,
    app: AppHandle,
    paused: bool,
) -> Result<(), String> {
    check(&window)?;
    set_paused(&app, paused)
}

pub fn set_paused(app: &AppHandle, paused: bool) -> Result<(), String> {
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if !paused && control.state != "paused" {
        return Err("desktop_control_not_paused".into());
    }
    control.send(serde_json::json!({"action": if paused {"pause"} else {"resume"}}))?;
    control.paused = paused;
    control.state = if paused { "stopping" } else { "waiting" }.into();
    let revision = control.revision;
    drop(control);
    if !paused {
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            if handle
                .state::<DesktopControl>()
                .0
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .revision
                == revision
            {
                let _ = show_overlays(&handle);
            }
        });
    }
    Ok(())
}

/// Bounded framing: ordinary daemon logs cannot grow an unbounded line buffer.
#[derive(Default)]
pub struct Events {
    line: Vec<u8>,
    overflow: bool,
}
impl Events {
    pub fn feed(&mut self, bytes: &[u8], prefix: &str) -> Vec<serde_json::Value> {
        let mut events = Vec::new();
        for byte in bytes {
            if *byte == b'\n' {
                if !self.overflow {
                    if let Ok(line) = std::str::from_utf8(&self.line) {
                        if let Some(json) = line.strip_prefix(prefix) {
                            if let Ok(event) = serde_json::from_str(json) {
                                events.push(event);
                            }
                        }
                    }
                }
                self.line.clear();
                self.overflow = false;
            } else if self.line.len() < 4096 && !self.overflow {
                self.line.push(*byte);
            } else {
                self.line.clear();
                self.overflow = true;
            }
        }
        events
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn takeover_position_stays_in_the_selected_work_area() {
        let area = tauri::PhysicalRect {
            position: tauri::PhysicalPosition::new(-1920, 24),
            size: tauri::PhysicalSize::new(1920, 1016),
        };
        assert_eq!(
            takeover_position(area, tauri::PhysicalSize::new(460, 112), 24),
            tauri::PhysicalPosition::new(-1190, 904)
        );
        let small = tauri::PhysicalRect {
            position: tauri::PhysicalPosition::new(0, 0),
            size: tauri::PhysicalSize::new(360, 180),
        };
        assert_eq!(
            takeover_position(small, tauri::PhysicalSize::new(460, 200), 24),
            tauri::PhysicalPosition::new(0, 0)
        );
    }
    #[test]
    fn every_display_must_acknowledge_before_input() {
        let mut control = Control {
            ready: true,
            shown: true,
            ..Control::default()
        };
        assert!(!control.surfaces_ready());
        control.overlay_labels = vec!["cua-overlay-0".into(), "cua-overlay-1".into()];
        control.overlay_ready.insert("cua-overlay-0".into());
        assert!(!control.surfaces_ready());
        control.overlay_ready.insert("cua-overlay-1".into());
        assert!(control.surfaces_ready());
        control.shown = false;
        assert!(!control.surfaces_ready());
    }
    #[test]
    fn framing_handles_chunks_and_rejects_other_generations_and_large_lines() {
        let mut parser = Events::default();
        assert!(parser
            .feed(b"LAMBCHAT_CUA:abc:{\"state\":", "LAMBCHAT_CUA:abc:")
            .is_empty());
        assert_eq!(
            parser.feed(b"\"active\"}\n", "LAMBCHAT_CUA:abc:")[0]["state"],
            "active"
        );
        assert!(parser
            .feed(
                b"LAMBCHAT_CUA:old:{\"state\":\"active\"}\n",
                "LAMBCHAT_CUA:abc:"
            )
            .is_empty());
        assert!(parser
            .feed(&vec![b'x'; 5000], "LAMBCHAT_CUA:abc:")
            .is_empty());
        assert!(parser.line.len() <= 4096);
        assert!(parser.feed(b"\n", "LAMBCHAT_CUA:abc:").is_empty());
    }
}
