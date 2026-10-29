//! Native receipts for File objects delivered by the trusted Windows WebView.

use serde::Deserialize;

fn expected_url(config: &tauri::Config, development: bool) -> Option<String> {
    let main = config
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")?;
    match &main.url {
        tauri::WebviewUrl::External(url) => Some(url.to_string()),
        tauri::WebviewUrl::App(_) => {
            if development {
                if let Some(url) = &config.build.dev_url {
                    return Some(url.to_string());
                }
            }
            Some(if main.use_https_scheme {
                "https://tauri.localhost/".into()
            } else {
                "http://tauri.localhost/".into()
            })
        }
        _ => None,
    }
}

fn trusted_source(source: &str, initial_url: &str) -> bool {
    let (Ok(source), Ok(initial)) = (tauri::Url::parse(source), tauri::Url::parse(initial_url))
    else {
        return false;
    };
    [&source, &initial].iter().all(|url| {
        matches!(url.scheme(), "http" | "https")
            && url.host_str().is_some()
            && url.username().is_empty()
            && url.password().is_none()
    }) && source.origin() == initial.origin()
}

fn request_id(message: &str) -> Option<String> {
    #[derive(Deserialize)]
    #[serde(rename_all = "camelCase", deny_unknown_fields)]
    struct DropRequest {
        kind: String,
        request_id: String,
    }
    if message.len() > 512 {
        return None;
    }
    let request: DropRequest = serde_json::from_str(message).ok()?;
    (request.kind == "lambchat-file-drop"
        && request.request_id.len() == 32
        && request
            .request_id
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)))
    .then_some(request.request_id)
}

fn valid_count(count: u32) -> bool {
    (1..=100).contains(&count)
}

#[cfg(windows)]
pub use platform::install;

#[cfg(windows)]
mod platform {
    use super::*;
    use crate::commands::attachments;
    use std::path::PathBuf;
    use tauri::{Emitter, EventTarget, Manager, WebviewWindow};
    use webview2_com::{
        take_pwstr,
        Microsoft::Web::WebView2::Win32::{
            ICoreWebView2File, ICoreWebView2WebMessageReceivedEventArgs,
            ICoreWebView2WebMessageReceivedEventArgs2,
        },
        WebMessageReceivedEventHandler,
    };
    use windows::core::{Interface, PWSTR};

    fn file_paths(
        args: &ICoreWebView2WebMessageReceivedEventArgs,
    ) -> Result<Vec<Option<PathBuf>>, ()> {
        // Extract owned paths on the COM thread before any filesystem work is dispatched.
        unsafe {
            let objects = args
                .cast::<ICoreWebView2WebMessageReceivedEventArgs2>()
                .map_err(|_| ())?
                .AdditionalObjects()
                .map_err(|_| ())?;
            let mut count = 0;
            objects.Count(&mut count).map_err(|_| ())?;
            if !valid_count(count) {
                return Err(());
            }
            (0..count)
                .map(|index| {
                    let file = objects
                        .GetValueAtIndex(index)
                        .map_err(|_| ())?
                        .cast::<ICoreWebView2File>()
                        .map_err(|_| ())?;
                    let mut value = PWSTR::null();
                    file.Path(&mut value).map_err(|_| ())?;
                    let value = take_pwstr(value);
                    if value.is_empty() {
                        return Ok(None);
                    }
                    let path = PathBuf::from(value);
                    if !path.is_absolute() {
                        return Err(());
                    }
                    Ok(Some(path))
                })
                .collect()
        }
    }

    fn emit_result(
        window: &WebviewWindow,
        initial_url: &str,
        id: &str,
        files: Result<Vec<Option<attachments::DesktopFile>>, ()>,
    ) {
        // A navigation while receipts are being created must not receive their metadata.
        if !window
            .url()
            .is_ok_and(|url| trusted_source(url.as_str(), initial_url))
        {
            return;
        }
        let payload = match files {
            Ok(files) => serde_json::json!({"requestId": id, "files": files}),
            Err(()) => serde_json::json!({"requestId": id, "files": [], "error": true}),
        };
        let _ = window.emit_to(
            EventTarget::webview_window("main"),
            "desktop-drop-resolved",
            payload,
        );
    }

    pub fn install(window: &WebviewWindow) -> tauri::Result<()> {
        if window.label() != "main" {
            return Ok(());
        }
        // Pin configuration, not Source: the WebView may still be on about:blank in setup.
        let Some(initial_url) = expected_url(window.app_handle().config(), tauri::is_dev()) else {
            return Ok(());
        };
        let window = window.clone();
        window.clone().with_webview(move |platform| unsafe {
            let result = (|| -> windows::core::Result<()> {
                let core = platform.controller().CoreWebView2()?;
                // CoreWebView2 raises this for the top-level document; frame events are separate.
                let handler = WebMessageReceivedEventHandler::create(Box::new(move |_, args| {
                    let Some(args) = args else {
                        return Ok(());
                    };
                    let mut source = PWSTR::null();
                    args.Source(&mut source)?;
                    if !trusted_source(&take_pwstr(source), &initial_url) {
                        return Ok(());
                    }
                    let mut message = PWSTR::null();
                    args.WebMessageAsJson(&mut message)?;
                    let Some(id) = request_id(&take_pwstr(message)) else {
                        return Ok(());
                    };
                    let paths = match file_paths(&args) {
                        Ok(paths) => paths,
                        Err(()) => {
                            emit_result(&window, &initial_url, &id, Err(()));
                            return Ok(());
                        }
                    };
                    let window = window.clone();
                    let initial_url = initial_url.clone();
                    tauri::async_runtime::spawn_blocking(move || {
                        let files = paths
                            .into_iter()
                            .map(|path| {
                                path.map(|path| attachments::register(window.app_handle(), &path))
                                    .transpose()
                                    .map_err(|_| ())
                            })
                            .collect();
                        emit_result(&window, &initial_url, &id, files);
                    });
                    Ok(())
                }));
                core.add_WebMessageReceived(&handler, &mut 0)?;
                Ok(())
            })();
            if result.is_err() {
                crate::daemon::emit_stderr_line("[lambchat] Windows file-drop bridge unavailable");
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_origin_comes_from_configuration_even_before_the_webview_loads() {
        let mut config = tauri::Config::default();
        config.app.windows = vec![tauri::utils::config::WindowConfig::default()];
        config.build.dev_url = Some(tauri::Url::parse("http://localhost:3001/").unwrap());
        assert_eq!(
            expected_url(&config, true).as_deref(),
            Some("http://localhost:3001/")
        );
        assert_eq!(
            expected_url(&config, false).as_deref(),
            Some("http://tauri.localhost/")
        );
        config.app.windows[0].use_https_scheme = true;
        assert_eq!(
            expected_url(&config, false).as_deref(),
            Some("https://tauri.localhost/")
        );
        config.build.dev_url = None;
        assert_eq!(
            expected_url(&config, true).as_deref(),
            Some("https://tauri.localhost/")
        );
    }

    #[test]
    fn an_explicit_external_main_url_is_pinned_in_development_and_production() {
        let mut config = tauri::Config::default();
        let mut main = tauri::utils::config::WindowConfig::default();
        main.url =
            tauri::WebviewUrl::External(tauri::Url::parse("https://trusted.example/app").unwrap());
        config.app.windows = vec![main];
        config.build.dev_url = Some(tauri::Url::parse("http://localhost:3001/").unwrap());
        for development in [true, false] {
            assert_eq!(
                expected_url(&config, development).as_deref(),
                Some("https://trusted.example/app")
            );
        }
    }

    #[test]
    fn missing_main_configuration_never_trusts_another_window() {
        let mut config = tauri::Config::default();
        let mut other = tauri::utils::config::WindowConfig::default();
        other.label = "preview".into();
        config.app.windows = vec![other];
        assert!(expected_url(&config, false).is_none());
    }

    #[test]
    fn accepts_only_the_initial_application_origin() {
        assert!(trusted_source(
            "http://tauri.localhost/chat/a",
            "http://tauri.localhost/"
        ));
        assert!(trusted_source(
            "http://localhost:3001/chat/a",
            "http://localhost:3001/"
        ));
        for source in [
            "https://tauri.localhost/",
            "http://tauri.localhost.evil/",
            "http://localhost:3002/",
            "https://lambchat.com/",
            "null",
            "data:text/html,app",
            "http://attacker@tauri.localhost/",
        ] {
            assert!(
                !trusted_source(source, "http://tauri.localhost/"),
                "{source}"
            );
        }
        assert!(!trusted_source("null", "null"));
        assert!(!trusted_source("about:blank", "about:blank"));
    }

    #[test]
    fn requires_a_bounded_request_id_and_never_accepts_text_paths() {
        let id = "0123456789abcdef0123456789abcdef";
        assert_eq!(
            request_id(&format!(
                r#"{{"kind":"lambchat-file-drop","requestId":"{id}"}}"#
            )),
            Some(id.into())
        );
        for value in ["", "a", "0123456789ABCDEF0123456789ABCDEF", "../../file"] {
            assert!(request_id(&format!(
                r#"{{"kind":"lambchat-file-drop","requestId":"{value}"}}"#
            ))
            .is_none());
        }
        assert!(request_id(&format!(r#"{{"kind":"other","requestId":"{id}"}}"#)).is_none());
        assert!(request_id(&format!(
            r#"{{"kind":"lambchat-file-drop","requestId":"{id}","path":"C:\\secret"}}"#
        ))
        .is_none());
        assert!(request_id("not-json").is_none());
    }

    #[test]
    fn bounds_the_number_of_native_file_objects() {
        assert!(valid_count(1));
        assert!(valid_count(100));
        assert!(!valid_count(0));
        assert!(!valid_count(101));
        assert!(!valid_count(u32::MAX));
    }
}
