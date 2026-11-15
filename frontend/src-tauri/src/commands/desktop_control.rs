//! The local user owns takeover. Only the dedicated bundled control window can resume.
use std::io::Write;
use std::process::ChildStdin;
use std::sync::Mutex;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

const LABEL: &str = "cua-control";
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
}

impl Control {
    fn send(&mut self, mut message: serde_json::Value) -> Result<(), String> {
        message["token"] = self.token.clone().into();
        let pipe = self.input.as_mut().ok_or("desktop_control_disconnected")?;
        writeln!(pipe, "{message}").map_err(|_| "desktop_control_disconnected".to_string())
    }
    fn permit(&mut self) -> Result<(), String> {
        if self.ready && self.shown {
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
    }
}

pub fn receive(app: &AppHandle, token: &str, event: serde_json::Value) {
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if control.token != token {
        return;
    }
    match event["state"].as_str() {
        Some("request") => {
            let Some(request) = event["request"].as_str().filter(|s| s.len() == 32) else {
                return;
            };
            control.pending = Some(request.into());
            control.ready = false;
            control.shown = false;
            control.state = if control.paused { "paused" } else { "waiting" }.into();
            drop(control);
            let handle = app.clone();
            let generation = token.to_string();
            let _ = app.run_on_main_thread(move || {
                let manager = handle.state::<DesktopControl>();
                if manager.0.lock().unwrap_or_else(|p| p.into_inner()).token != generation { return; }
                let shown = show(&handle);
                let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
                if shown.is_err() {
                    control.state = "unavailable".into();
                    if let Some(request) = control.pending.take() {
                        let _ = control.send(serde_json::json!({"action":"permit", "request":request, "allowed":false}));
                    }
                } else {
                    control.shown = true;
                    if control.permit().is_err() { control.state = "disconnected".into(); }
                }
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
        }
        _ => {}
    }
}

fn show(app: &AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(LABEL) {
        return window.show().map_err(|e| e.to_string());
    }
    WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("cua-control.html".into()))
        .title("LambChat")
        .inner_size(420.0, 188.0)
        .min_inner_size(320.0, 188.0)
        .position(24.0, 48.0)
        .decorations(false)
        .resizable(true)
        .always_on_top(true)
        .visible_on_all_workspaces(true)
        .content_protected(true)
        .skip_taskbar(true)
        .focused(false)
        .build()
        .map(|_| ())
        .map_err(|e| e.to_string())
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
    check(&window)?;
    let manager = app.state::<DesktopControl>();
    let mut control = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if ready {
        control.ready = true;
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
