//! In-process Windows toast actions. Cold-launch activation is not registered.

use super::notification::NotificationPayload;
use std::collections::HashMap;

fn xml_text(value: &str) -> Result<String, String> {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            '"' => escaped.push_str("&quot;"),
            '\'' => escaped.push_str("&apos;"),
            '\t'
            | '\n'
            | '\r'
            | '\u{20}'..='\u{d7ff}'
            | '\u{e000}'..='\u{fffd}'
            | '\u{10000}'..='\u{10ffff}' => escaped.push(character),
            _ => return Err("native_notification_invalid_payload".into()),
        }
    }
    Ok(escaped)
}

fn toast_xml(payload: &NotificationPayload) -> Result<String, String> {
    payload.validate()?;
    let title = xml_text(&payload.title)?;
    let body = xml_text(payload.body.as_deref().unwrap_or(""))?;
    Ok(format!("<toast><visual><binding template=\"ToastGeneric\"><text>{title}</text><text>{body}</text></binding></visual></toast>"))
}

fn action_payload(payload: &NotificationPayload) -> Result<Option<serde_json::Value>, String> {
    payload.validate()?;
    Ok(payload.route.as_ref().map(|route| {
        serde_json::json!({
            "route": route,
            "ownerUserId": payload.owner_user_id,
        })
    }))
}

fn retain_after_dismissal(reason: i32) -> bool {
    // TimedOut (2) only removes the banner; Notification Center remains clickable.
    // Unknown reasons conservatively retain, within the fixed capacity.
    !matches!(reason, 0 | 1)
}

fn permission_from_setting(setting: i32) -> Result<String, String> {
    match setting {
        0 => Ok("granted".into()),
        1..=3 => Ok("denied".into()),
        _ => Err("native_notification_unsupported".into()),
    }
}

struct RetainedNotifications<T> {
    entries: HashMap<String, T>,
    capacity: usize,
}

impl<T> RetainedNotifications<T> {
    fn new(capacity: usize) -> Self {
        Self {
            entries: HashMap::new(),
            capacity,
        }
    }

    // Return the uninserted value so native callbacks can be detached after
    // releasing the registry mutex, never while holding it across a COM call.
    fn insert(&mut self, key: String, value: T) -> Result<(), T> {
        if self.entries.len() >= self.capacity || self.entries.contains_key(&key) {
            return Err(value);
        }
        self.entries.insert(key, value);
        Ok(())
    }

    fn remove(&mut self, key: &str) -> Option<T> {
        self.entries.remove(key)
    }
}

#[cfg(target_os = "windows")]
pub use native::{install, permission, send, supports_actions};

#[cfg(target_os = "windows")]
mod native {
    use super::*;
    use std::sync::{Mutex, OnceLock};
    use tauri::{AppHandle, Emitter};
    use windows::{
        core::{IInspectable, HSTRING},
        Data::Xml::Dom::XmlDocument,
        Foundation::TypedEventHandler,
        UI::Notifications::{
            ToastDismissedEventArgs, ToastFailedEventArgs, ToastNotification,
            ToastNotificationManager, ToastNotifier,
        },
    };

    const MAX_RETAINED_NOTIFICATIONS: usize = 128;
    static RETAINED: OnceLock<Mutex<RetainedNotifications<RetainedToast>>> = OnceLock::new();

    struct RetainedToast {
        toast: ToastNotification,
        activated: Option<i64>,
        dismissed: Option<i64>,
        failed: Option<i64>,
    }

    impl Drop for RetainedToast {
        fn drop(&mut self) {
            if let Some(token) = self.activated {
                let _ = self.toast.RemoveActivated(token);
            }
            if let Some(token) = self.dismissed {
                let _ = self.toast.RemoveDismissed(token);
            }
            if let Some(token) = self.failed {
                let _ = self.toast.RemoveFailed(token);
            }
        }
    }

    fn retained() -> &'static Mutex<RetainedNotifications<RetainedToast>> {
        RETAINED.get_or_init(|| Mutex::new(RetainedNotifications::new(MAX_RETAINED_NOTIFICATIONS)))
    }

    fn retire(identity: &str) {
        let removed = {
            match retained().lock() {
                Ok(mut state) => state.remove(identity),
                Err(_) => None,
            }
        };
        drop(removed);
    }

    fn notifier(app: &AppHandle) -> Result<ToastNotifier, String> {
        // NSIS must register this exact identifier on the installed Start Menu
        // shortcut. Never impersonate PowerShell or the user's other app install.
        ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(
            app.config().identifier.as_str(),
        ))
        .map_err(|_| "native_notification_unavailable".into())
    }

    pub fn supports_actions() -> bool {
        true
    }

    pub fn install(_app: &AppHandle) {
        let _ = retained();
    }

    pub fn permission(app: &AppHandle) -> Result<String, String> {
        let setting = notifier(app)?
            .Setting()
            .map_err(|_| "native_notification_unavailable".to_string())?;
        permission_from_setting(setting.0)
    }

    pub fn send(app: &AppHandle, payload: NotificationPayload) -> Result<(), String> {
        let xml = toast_xml(&payload)?;
        let action = action_payload(&payload)?;
        let notifier = notifier(app)?;
        let setting = notifier
            .Setting()
            .map_err(|_| "native_notification_unavailable".to_string())?;
        if permission_from_setting(setting.0)? != "granted" {
            return Err("native_notification_permission_denied".into());
        }
        let document =
            XmlDocument::new().map_err(|_| "native_notification_unavailable".to_string())?;
        document
            .LoadXml(&HSTRING::from(xml))
            .map_err(|_| "native_notification_invalid_payload".to_string())?;
        let toast = ToastNotification::CreateToastNotification(&document)
            .map_err(|_| "native_notification_unavailable".to_string())?;
        let mut entry = RetainedToast {
            toast: toast.clone(),
            activated: None,
            dismissed: None,
            failed: None,
        };
        let identity = uuid::Uuid::new_v4().to_string();
        let activated_identity = identity.clone();
        let app = app.clone();
        entry.activated = Some(
            toast
                .Activated(&TypedEventHandler::<ToastNotification, IInspectable>::new(
                    move |_, _| {
                        // Capture the validated original target, never callback-supplied input.
                        // JS checks the current account before navigation and native focus.
                        if let Some(action) = &action {
                            let _ = app.emit("desktop-notification-action", action);
                        }
                        retire(&activated_identity);
                        Ok(())
                    },
                ))
                .map_err(|_| "native_notification_unavailable".to_string())?,
        );
        let dismissed_identity = identity.clone();
        entry.dismissed = Some(
            toast
                .Dismissed(&TypedEventHandler::<
                    ToastNotification,
                    ToastDismissedEventArgs,
                >::new(move |_, args| {
                    let reason = args
                        .as_ref()
                        .and_then(|args| args.Reason().ok())
                        .map(|value| value.0)
                        .unwrap_or(-1);
                    if !retain_after_dismissal(reason) {
                        retire(&dismissed_identity);
                    }
                    Ok(())
                }))
                .map_err(|_| "native_notification_unavailable".to_string())?,
        );
        let failed_identity = identity.clone();
        entry.failed = Some(
            toast
                .Failed(
                    &TypedEventHandler::<ToastNotification, ToastFailedEventArgs>::new(
                        move |_, _| {
                            retire(&failed_identity);
                            Ok(())
                        },
                    ),
                )
                .map_err(|_| "native_notification_unavailable".to_string())?,
        );
        let inserted = {
            let mut state = retained()
                .lock()
                .map_err(|_| "native_notification_unavailable".to_string())?;
            state.insert(identity.clone(), entry)
        };
        if let Err(unretained) = inserted {
            drop(unretained);
            return Err("native_notification_capacity_reached".into());
        }
        if notifier.Show(&toast).is_err() {
            retire(&identity);
            return Err("native_notification_delivery_failed".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod windows_notification_contract {
    use super::*;
    use crate::commands::notification::NotificationPayload;

    fn payload() -> NotificationPayload {
        NotificationPayload {
            title: "Build <ready> & \"quoted\" 'text'".into(),
            body: Some("Body <&>\n第二行 🟢".into()),
            route: Some("/chat/session?run_id=run-1".into()),
            owner_user_id: Some("owner-1".into()),
        }
    }

    #[test]
    fn toast_xml_escapes_original_text_without_injecting_actions() {
        let mut value = payload();
        value.title = "</text><actions><action content=\"unsafe\"/></actions>".into();
        let xml = toast_xml(&value).unwrap();
        assert!(xml.contains("&lt;/text&gt;&lt;actions&gt;"));
        assert!(xml.contains("&quot;unsafe&quot;"));
        assert!(xml.contains("Body &lt;&amp;&gt;\n第二行 🟢"));
        assert!(!xml.contains("<actions>"));
        assert!(!xml.contains("owner-1"));
        assert!(!xml.contains("/chat/"));
    }

    #[test]
    fn toast_xml_preserves_quotes_and_rejects_invalid_xml_control_characters() {
        let mut value = payload();
        assert!(toast_xml(&value)
            .unwrap()
            .contains("&amp; &quot;quoted&quot; &apos;text&apos;"));
        value.body = Some("not\u{0}xml".into());
        assert!(toast_xml(&value).is_err());
    }

    #[test]
    fn activation_retains_exact_run_and_original_owner() {
        let action = action_payload(&payload()).unwrap().unwrap();
        assert_eq!(action["route"], "/chat/session?run_id=run-1");
        assert_eq!(action["ownerUserId"], "owner-1");
        assert_eq!(action.as_object().unwrap().len(), 2);
    }

    #[test]
    fn activation_refuses_unowned_or_external_targets() {
        let mut value = payload();
        value.owner_user_id = None;
        assert!(action_payload(&value).is_err());
        value.owner_user_id = Some("owner-1".into());
        value.route = Some("https://unrelated.example".into());
        assert!(action_payload(&value).is_err());
        value.route = None;
        assert!(action_payload(&value).unwrap().is_none());
    }

    #[test]
    fn banner_timeout_keeps_notification_center_activation_alive() {
        assert!(retain_after_dismissal(2));
        assert!(retain_after_dismissal(99));
        assert!(!retain_after_dismissal(0));
        assert!(!retain_after_dismissal(1));
    }

    #[test]
    fn capacity_refuses_new_toast_without_dropping_older_click_targets() {
        let mut retained = RetainedNotifications::new(2);
        retained.insert("first".into(), "owner-a").unwrap();
        retained.insert("second".into(), "owner-b").unwrap();
        assert!(retained.insert("third".into(), "owner-c").is_err());
        assert_eq!(retained.remove("first"), Some("owner-a"));
        retained.insert("third".into(), "owner-c").unwrap();
        assert_eq!(retained.remove("second"), Some("owner-b"));
        assert_eq!(retained.remove("third"), Some("owner-c"));
    }

    #[test]
    fn duplicate_retention_identity_never_replaces_the_original_owner() {
        let mut retained = RetainedNotifications::new(2);
        retained.insert("same".into(), "owner-a").unwrap();
        assert!(retained.insert("same".into(), "owner-b").is_err());
        assert_eq!(retained.remove("same"), Some("owner-a"));
    }

    #[test]
    fn permission_reports_actual_disabled_and_unsupported_settings() {
        assert_eq!(permission_from_setting(0).unwrap(), "granted");
        for setting in [1, 2, 3] {
            assert_eq!(permission_from_setting(setting).unwrap(), "denied");
        }
        assert!(permission_from_setting(4).is_err());
        assert!(permission_from_setting(99).is_err());
    }
}
