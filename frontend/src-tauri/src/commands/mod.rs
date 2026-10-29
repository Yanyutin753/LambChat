pub mod preview;
pub mod workspace;

pub mod notification;

#[cfg(target_os = "macos")]
mod notification_macos_api;
#[cfg(any(target_os = "windows", test))]
pub mod windows_notification;

pub mod attachments;
