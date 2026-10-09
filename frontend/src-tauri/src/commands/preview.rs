//! Isolated read-only HTML previews, independent of Agent execution.
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Manager, WebviewWindow};

const MAX_HTML_BYTES: usize = 8 * 1024 * 1024;
#[derive(Default)]
pub struct PreviewManager(Mutex<Option<PreviewServer>>);

// Read-only isolated HTML rendering; this loopback origin has no native capability.
// A separate origin preserves interactive previews while the main CSP forbids scripts.
struct PreviewServer {
    port: u16,
    pages: Arc<Mutex<std::collections::VecDeque<(String, std::time::Instant, String)>>>,
    stopped: Arc<std::sync::atomic::AtomicBool>,
}
impl PreviewServer {
    fn new() -> Result<Self, String> {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0))
            .map_err(|_| "html_preview_unavailable")?;
        let port = listener
            .local_addr()
            .map_err(|_| "html_preview_unavailable")?
            .port();
        listener
            .set_nonblocking(true)
            .map_err(|_| "html_preview_unavailable")?;
        let pages: Arc<Mutex<std::collections::VecDeque<(String, std::time::Instant, String)>>> =
            Arc::new(Mutex::new(std::collections::VecDeque::new()));
        let reader_pages = pages.clone();
        let stopped = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let reader_stopped = stopped.clone();
        std::thread::spawn(move || {
            while !reader_stopped.load(std::sync::atomic::Ordering::Relaxed) {
                let Ok((mut stream, _)) = listener.accept() else {
                    std::thread::sleep(Duration::from_millis(20));
                    continue;
                };
                let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
                let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
                let mut raw = [0u8; 8192];
                let size = stream.read(&mut raw).unwrap_or(0);
                let request = std::str::from_utf8(&raw[..size]).unwrap_or("");
                let fields: Vec<_> = request
                    .lines()
                    .next()
                    .unwrap_or("")
                    .split_whitespace()
                    .collect();
                let (status, content) = if fields.len() != 3 || fields[0] != "GET" {
                    ("405 Method Not Allowed", String::new())
                } else {
                    let mut pages = reader_pages.lock().unwrap_or_else(|p| p.into_inner());
                    pages.retain(|(_, created, _)| created.elapsed() < Duration::from_secs(600));
                    let content = pages
                        .iter()
                        .find(|(id, _, _)| fields[1] == format!("/{id}"))
                        .map(|(_, _, html)| html.clone());
                    match content {
                        Some(html) => ("200 OK", html),
                        None => ("404 Not Found", String::new()),
                    }
                };
                let headers = format!("HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n", content.len());
                let _ = stream
                    .write_all(headers.as_bytes())
                    .and_then(|_| stream.write_all(content.as_bytes()));
            }
        });
        Ok(Self {
            port,
            pages,
            stopped,
        })
    }
    fn insert(&self, content: String) -> Result<String, String> {
        if content.len() > MAX_HTML_BYTES {
            return Err("html_preview_too_large".into());
        }
        let id = uuid::Uuid::new_v4().to_string();
        let mut pages = self.pages.lock().unwrap_or_else(|p| p.into_inner());
        if pages.len() >= 8 {
            pages.pop_front();
        }
        pages.push_back((id.clone(), std::time::Instant::now(), content));
        Ok(format!("http://127.0.0.1:{}/{id}", self.port))
    }
}
impl Drop for PreviewServer {
    fn drop(&mut self) {
        self.stopped
            .store(true, std::sync::atomic::Ordering::Relaxed);
    }
}

#[tauri::command]
pub fn preview_html(
    window: WebviewWindow,
    app: AppHandle,
    content: String,
) -> Result<String, String> {
    check_window(&window)?;
    let manager = app.state::<PreviewManager>();
    let mut server = manager.0.lock().unwrap_or_else(|p| p.into_inner());
    if server.is_none() {
        *server = Some(PreviewServer::new()?);
    }
    server
        .as_ref()
        .ok_or("html_preview_unavailable")?
        .insert(content)
}

fn trusted_origin(label: &str, raw: &str) -> bool {
    let Ok(url) = tauri::Url::parse(raw) else {
        return false;
    };
    label == "main"
        && ((url.scheme() == "tauri" && url.host_str() == Some("localhost"))
            || (matches!(url.scheme(), "http" | "https")
                && url.host_str() == Some("tauri.localhost"))
            || (cfg!(debug_assertions)
                && url.scheme() == "http"
                && url.host_str() == Some("localhost")
                && url.port() == Some(3001)))
}
fn check_window(window: &WebviewWindow) -> Result<(), String> {
    if trusted_origin(
        window.label(),
        window
            .url()
            .map_err(|_| "html_preview_unavailable")?
            .as_str(),
    ) {
        Ok(())
    } else {
        Err("html_preview_unavailable".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_preview_rejects_other_windows_and_remote_origins() {
        assert!(trusted_origin("main", "tauri://localhost/chat"));
        assert!(!trusted_origin("other", "tauri://localhost/chat"));
        assert!(!trusted_origin("main", "https://lambchat.com/chat"));
        assert!(!trusted_origin("main", "http://127.0.0.1:3047/preview"));
    }

    #[test]
    fn preview_content_and_retained_pages_are_bounded() {
        let server = PreviewServer::new().unwrap();
        assert!(server.insert("x".repeat(MAX_HTML_BYTES + 1)).is_err());
        for _ in 0..9 {
            server.insert("synthetic".into()).unwrap();
        }
        assert_eq!(server.pages.lock().unwrap().len(), 8);
    }

    #[test]
    fn preview_server_serves_only_known_read_only_pages() {
        let server = PreviewServer::new().unwrap();
        let url = server.insert("<p>synthetic</p>".into()).unwrap();
        let parsed = tauri::Url::parse(&url).unwrap();
        let fetch = |method: &str, path: &str| {
            let mut stream = std::net::TcpStream::connect(("127.0.0.1", server.port)).unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            write!(
                stream,
                "{method} {path} HTTP/1.1\r\nHost: localhost\r\n\r\n"
            )
            .unwrap();
            let mut result = String::new();
            stream.read_to_string(&mut result).unwrap();
            result
        };
        let html = fetch("GET", parsed.path());
        assert!(html.starts_with("HTTP/1.1 200 OK"));
        assert!(html.ends_with("<p>synthetic</p>"));
        assert!(fetch("GET", "/unknown").starts_with("HTTP/1.1 404"));
        assert!(fetch("POST", parsed.path()).starts_with("HTTP/1.1 405"));
    }
}
