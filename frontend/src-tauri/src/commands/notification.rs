//! macOS notifications retain a delegate for later Notification Center actions.
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NotificationPayload {
    pub title: String,
    pub body: Option<String>,
    pub route: Option<String>,
    pub owner_user_id: Option<String>,
}

impl NotificationPayload {
    pub(super) fn validate(&self) -> Result<(), String> {
        if self.title.len() > 512 || self.body.as_ref().is_some_and(|body| body.len() > 8192) {
            return Err("native_notification_invalid_payload".into());
        }
        if let Some(route) = &self.route {
            let owner = self.owner_user_id.as_deref().unwrap_or("");
            if owner.trim().is_empty() || owner.len() > 256 || !valid_route(route) {
                return Err("native_notification_invalid_target".into());
            }
        }
        Ok(())
    }
}

#[cfg(any(target_os = "macos", test))]
fn notification_presentation_options(modern: bool) -> usize {
    if modern {
        24
    } else {
        4
    }
}

fn valid_route(route: &str) -> bool {
    if route.len() > 2048
        || route.chars().any(|c| c.is_control() || c.is_whitespace())
        || route.contains('\\')
    {
        return false;
    }
    if route == "/notifications" {
        return true;
    }
    let (path, query) = route.split_once('?').unwrap_or((route, ""));
    let Some(session) = path.strip_prefix("/chat/") else {
        return false;
    };
    if session.is_empty()
        || session.contains('/')
        || session.contains('#')
        || session == "."
        || session == ".."
    {
        return false;
    }
    if route.contains('?')
        && (!query.starts_with("run_id=")
            || query.len() <= 7
            || query.contains('#')
            || query.contains('&'))
    {
        return false;
    }
    let Ok(parsed) = tauri::Url::parse(&format!("http://localhost{route}")) else {
        return false;
    };
    parsed.path() == path
}

#[tauri::command]
pub fn desktop_notification_supports_actions() -> bool {
    #[cfg(target_os = "macos")]
    {
        macos::available()
    }
    #[cfg(target_os = "windows")]
    {
        super::windows_notification::supports_actions()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        false
    }
}

#[tauri::command]
pub fn desktop_notification_focus(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window
            .show()
            .map_err(|_| "native_notification_focus_failed")?;
        window
            .unminimize()
            .map_err(|_| "native_notification_focus_failed")?;
        window
            .set_focus()
            .map_err(|_| "native_notification_focus_failed")?;
    }
    Ok(())
}

#[tauri::command]
pub async fn desktop_notification_permission(app: AppHandle) -> Result<String, String> {
    #[cfg(target_os = "macos")]
    {
        let _ = app;
        tauri::async_runtime::spawn_blocking(macos::permission)
            .await
            .map_err(|_| "native_notification_unavailable".to_string())?
    }
    #[cfg(target_os = "windows")]
    {
        tauri::async_runtime::spawn_blocking(move || super::windows_notification::permission(&app))
            .await
            .map_err(|_| "native_notification_unavailable".to_string())?
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = app;
        Err("native_notification_unsupported".into())
    }
}

#[tauri::command]
pub async fn desktop_notification_send(
    app: AppHandle,
    payload: NotificationPayload,
) -> Result<(), String> {
    payload.validate()?;
    #[cfg(target_os = "macos")]
    {
        let _ = app;
        tauri::async_runtime::spawn_blocking(move || macos::send(payload))
            .await
            .map_err(|_| "native_notification_unavailable".to_string())?
    }
    #[cfg(target_os = "windows")]
    {
        tauri::async_runtime::spawn_blocking(move || {
            super::windows_notification::send(&app, payload)
        })
        .await
        .map_err(|_| "native_notification_unavailable".to_string())?
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = app;
        Err("native_notification_unsupported".into())
    }
}

pub fn install(app: &AppHandle) {
    #[cfg(target_os = "macos")]
    macos::install(app);
    #[cfg(target_os = "windows")]
    super::windows_notification::install(app);
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let _ = app;
}

#[cfg(target_os = "macos")]
mod macos {
    use super::super::notification_macos_api::{
        default_action_identifier, UNMutableNotificationContent, UNNotification,
        UNNotificationPresentationOptions, UNNotificationRequest, UNNotificationResponse,
        UNUserNotificationCenter, UNUserNotificationCenterDelegate, UN_AUTHORIZATION_ALERT,
    };
    use super::*;
    use block2::{DynBlock, RcBlock};
    use objc2::{
        define_class, msg_send,
        rc::Retained,
        runtime::{Bool, ProtocolObject},
        AnyThread, DefinedClass,
    };
    use objc2_foundation::{
        ns_string, NSClassFromString, NSDictionary, NSError, NSObject, NSObjectProtocol,
        NSOperatingSystemVersion, NSProcessInfo, NSString,
    };
    use std::{cell::RefCell, sync::mpsc, time::Duration};
    use tauri::Emitter;

    struct DelegateIvars {
        app: AppHandle,
    }
    define_class!(
        // NSObject has no subclassing requirements. AppHandle is thread safe;
        // native callbacks only emit an event, leaving account approval to JS.
        #[unsafe(super = NSObject)]
        #[ivars = DelegateIvars]
        struct NotificationDelegate;
        unsafe impl NSObjectProtocol for NotificationDelegate {}
        unsafe impl UNUserNotificationCenterDelegate for NotificationDelegate {
            #[unsafe(method(userNotificationCenter:willPresentNotification:withCompletionHandler:))]
            fn will_present(
                &self,
                _center: &UNUserNotificationCenter,
                _notification: &UNNotification,
                completion: &DynBlock<dyn Fn(UNNotificationPresentationOptions)>,
            ) {
                let modern = NSProcessInfo::processInfo().isOperatingSystemAtLeastVersion(
                    NSOperatingSystemVersion {
                        majorVersion: 11,
                        minorVersion: 0,
                        patchVersion: 0,
                    },
                );
                completion.call((notification_presentation_options(modern),));
            }
            #[unsafe(method(userNotificationCenter:didReceiveNotificationResponse:withCompletionHandler:))]
            fn did_receive(
                &self,
                _center: &UNUserNotificationCenter,
                response: &UNNotificationResponse,
                completion: &DynBlock<dyn Fn()>,
            ) {
                // Dismissal is not a request to open a conversation. Apple owns
                // this immutable framework constant for the application's life.
                if default_action_identifier()
                    .is_none_or(|identifier| &*response.actionIdentifier() != identifier)
                {
                    completion.call(());
                    return;
                }
                let info = response.notification().request().content().userInfo();
                let text = |key: &NSString| -> Option<String> {
                    info.objectForKey(key.as_ref()).and_then(|value| {
                        value
                            .downcast_ref::<NSString>()
                            .map(|value| value.to_string())
                    })
                };
                if let (Some(route), Some(owner)) =
                    (text(ns_string!("route")), text(ns_string!("ownerUserId")))
                {
                    let payload = NotificationPayload {
                        title: String::new(),
                        body: None,
                        route: Some(route.clone()),
                        owner_user_id: Some(owner.clone()),
                    };
                    if payload.validate().is_ok() {
                        let _ = self.ivars().app.emit(
                            "desktop-notification-action",
                            serde_json::json!({"route":route,"ownerUserId":owner}),
                        );
                    }
                }
                completion.call(());
            }
        }
    );
    thread_local! {
        // UNUserNotificationCenter.delegate is weak; retain for the entire app life.
        static DELEGATE: RefCell<Option<Retained<NotificationDelegate>>> = const { RefCell::new(None) };
    }
    pub fn available() -> bool {
        NSClassFromString(ns_string!("UNUserNotificationCenter")).is_some()
    }
    pub fn install(app: &AppHandle) {
        if !available() {
            return;
        }
        DELEGATE.with(|stored| {
            if stored.borrow().is_some() {
                return;
            }
            let delegate =
                NotificationDelegate::alloc().set_ivars(DelegateIvars { app: app.clone() });
            // NSObject initialization is valid for this subclass and owns its ivars.
            let delegate: Retained<NotificationDelegate> =
                unsafe { msg_send![super(delegate), init] };
            UNUserNotificationCenter::currentNotificationCenter()
                .setDelegate(Some(ProtocolObject::from_ref(&*delegate)));
            *stored.borrow_mut() = Some(delegate);
        });
    }

    pub fn permission() -> Result<String, String> {
        if !available() {
            return Err("native_notification_unsupported".into());
        }
        let (sender, receiver) = mpsc::sync_channel(1);
        let callback = RcBlock::new(move |granted: Bool, error: *mut NSError| {
            let _ = sender.try_send(granted.as_bool() && error.is_null());
        });
        UNUserNotificationCenter::currentNotificationCenter()
            .requestAuthorizationWithOptions_completionHandler(UN_AUTHORIZATION_ALERT, &callback);
        receiver
            .recv_timeout(Duration::from_secs(60))
            .map(|granted| if granted { "granted" } else { "denied" }.into())
            .map_err(|_| "native_notification_permission_timeout".into())
    }

    pub fn send(payload: NotificationPayload) -> Result<(), String> {
        if !available() {
            return Err("native_notification_unsupported".into());
        }
        let content = UNMutableNotificationContent::new();
        content.setTitle(&NSString::from_str(&payload.title));
        content.setBody(&NSString::from_str(payload.body.as_deref().unwrap_or("")));
        if let (Some(route), Some(owner)) = (&payload.route, &payload.owner_user_id) {
            let route = NSString::from_str(route);
            let owner = NSString::from_str(owner);
            let info = NSDictionary::from_slices(
                &[ns_string!("route"), ns_string!("ownerUserId")],
                &[&*route, &*owner],
            );
            // Erasing covariant NSString dictionary types is safe; all values are
            // immutable property-list strings required by UNNotificationContent.
            let info: Retained<NSDictionary> = unsafe { Retained::cast_unchecked(info) };
            unsafe { content.setUserInfo(&info) };
        }
        let identifier = NSString::from_str(&uuid::Uuid::new_v4().to_string());
        let request = UNNotificationRequest::requestWithIdentifier_content_trigger(
            &identifier,
            &content,
            None,
        );
        let (sender, receiver) = mpsc::sync_channel(1);
        let callback = RcBlock::new(move |error: *mut NSError| {
            let _ = sender.try_send(error.is_null());
        });
        UNUserNotificationCenter::currentNotificationCenter()
            .addNotificationRequest_withCompletionHandler(&request, Some(&callback));
        match receiver.recv_timeout(Duration::from_secs(5)) {
            Ok(true) => Ok(()),
            _ => Err("native_notification_delivery_failed".into()),
        }
    }
}

#[cfg(test)]
mod desktop_notification_contract {
    use super::*;

    fn payload(route: &str, owner: &str) -> NotificationPayload {
        NotificationPayload {
            title: "Finished".into(),
            body: Some("Task completed".into()),
            route: Some(route.into()),
            owner_user_id: Some(owner.into()),
        }
    }

    #[test]
    fn presentation_uses_only_options_supported_by_the_os() {
        assert_eq!(notification_presentation_options(true), 24);
        assert_eq!(notification_presentation_options(false), 4);
    }

    #[test]
    fn preserves_internal_run_target() {
        assert!(payload("/chat/session?run_id=run", "owner")
            .validate()
            .is_ok());
        let json = serde_json::to_value(payload("/chat/session?run_id=run", "owner")).unwrap();
        assert_eq!(json["ownerUserId"], "owner");
        assert_eq!(json["route"], "/chat/session?run_id=run");
    }

    #[test]
    fn rejects_external_notification_target() {
        assert!(payload("https://foreign.example", "owner")
            .validate()
            .is_err());
    }

    #[test]
    fn rejects_network_path_notification_target() {
        assert!(payload("//foreign.example", "owner").validate().is_err());
    }

    #[test]
    fn rejects_missing_notification_owner() {
        assert!(payload("/chat/session", "").validate().is_err());
    }

    #[test]
    fn rejects_path_traversal_and_controls() {
        for route in [
            "/chat/../settings",
            "/chat/session\\other",
            "/chat/session\nother",
        ] {
            assert!(payload(route, "owner").validate().is_err());
        }
    }
}
