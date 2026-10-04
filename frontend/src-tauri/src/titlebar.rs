//! macOS window controls share the WebView toolbar's vertical center.

const TITLEBAR_HEIGHT: f64 = 36.0;
const TITLEBAR_BOTTOM_BORDER: f64 = 1.0;

fn button_origin_y(button_height: f64) -> f64 {
    // AppKit coordinates grow upwards; flex centers inside the bottom border.
    (TITLEBAR_HEIGHT + TITLEBAR_BOTTOM_BORDER - button_height) / 2.0
}

#[cfg(target_os = "macos")]
mod macos {
    use super::*;
    use block2::RcBlock;
    use objc2::{rc::Retained, runtime::ProtocolObject, MainThreadMarker};
    use objc2_app_kit::{
        NSWindow, NSWindowButton, NSWindowDidBecomeKeyNotification,
        NSWindowDidChangeBackingPropertiesNotification, NSWindowDidDeminiaturizeNotification,
        NSWindowDidExitFullScreenNotification, NSWindowDidResizeNotification, NSWindowStyleMask,
    };
    use objc2_foundation::{NSNotificationCenter, NSObjectProtocol, NSOperationQueue};
    use std::cell::RefCell;

    struct Observer(Retained<ProtocolObject<dyn NSObjectProtocol>>);

    impl Drop for Observer {
        fn drop(&mut self) {
            // These tokens came from this notification center and stay on the UI thread.
            unsafe { NSNotificationCenter::defaultCenter().removeObserver((*self.0).as_ref()) };
        }
    }

    thread_local! {
        static OBSERVERS: RefCell<Vec<Observer>> = const { RefCell::new(Vec::new()) };
    }

    fn align(window: &tauri::WebviewWindow) -> tauri::Result<()> {
        if MainThreadMarker::new().is_none() {
            return Ok(());
        }
        // Tauri owns this NSWindow; the pointer is used only on the AppKit main thread.
        let native = unsafe { &*window.ns_window()?.cast::<NSWindow>() };
        if native.styleMask().contains(NSWindowStyleMask::FullScreen) {
            return Ok(()); // Fullscreen controls belong to the macOS auto-hiding titlebar.
        }
        let Some(close) = native.standardWindowButton(NSWindowButton::CloseButton) else {
            return Ok(());
        };
        // Standard AppKit buttons and their parent views are main-thread objects.
        let Some(container) = (unsafe { close.superview().and_then(|view| view.superview()) })
        else {
            return Ok(());
        };
        let horizontal_offset = 12.0 - close.frame().origin.x;
        let mut frame = container.frame();
        frame.size.height = TITLEBAR_HEIGHT;
        frame.origin.y = native.frame().size.height - TITLEBAR_HEIGHT;
        container.setFrame(frame);

        // Preserve macOS horizontal spacing and measure each button independently.
        for kind in [
            NSWindowButton::CloseButton,
            NSWindowButton::MiniaturizeButton,
            NSWindowButton::ZoomButton,
        ] {
            if let Some(button) = native.standardWindowButton(kind) {
                let mut frame = button.frame();
                frame.origin.x += horizontal_offset;
                frame.origin.y = button_origin_y(frame.size.height);
                button.setFrameOrigin(frame.origin);
            }
        }
        Ok(())
    }

    pub fn install(window: &tauri::WebviewWindow) -> tauri::Result<()> {
        if MainThreadMarker::new().is_none() {
            return Ok(());
        }
        align(window)?;
        let native = unsafe { &*window.ns_window()?.cast::<NSWindow>() };
        let center = NSNotificationCenter::defaultCenter();
        let queue = NSOperationQueue::mainQueue();
        // Observe instead of replacing Tauri's NSWindow delegate. In particular,
        // AppKit can reset button frames when returning from fullscreen.
        let names = unsafe {
            [
                NSWindowDidResizeNotification,
                NSWindowDidExitFullScreenNotification,
                NSWindowDidChangeBackingPropertiesNotification,
                NSWindowDidDeminiaturizeNotification,
                NSWindowDidBecomeKeyNotification,
            ]
        };
        OBSERVERS.with(|observers| {
            let mut observers = observers.borrow_mut();
            for name in names {
                let window = window.clone();
                let callback = RcBlock::new(move |_| {
                    if let Err(error) = align(&window) {
                        eprintln!("[lambchat-titlebar] alignment failed: {error}");
                    }
                });
                // Window notifications are scoped to this NSWindow; the Send
                // closure captures only Tauri's handle and runs on the main queue.
                let observer = unsafe {
                    center.addObserverForName_object_queue_usingBlock(
                        Some(name),
                        Some(native),
                        Some(&queue),
                        &callback,
                    )
                };
                observers.push(Observer(observer));
            }
        });
        Ok(())
    }

    pub fn uninstall() {
        OBSERVERS.with(|observers| observers.borrow_mut().clear());
    }
}

#[cfg(target_os = "macos")]
pub use macos::{install, uninstall};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_buttons_share_the_web_toolbar_center_at_different_sizes() {
        // A 36px border-box toolbar has 35px of flex content: center = 17.5.
        for (height, origin) in [(14.0, 11.5), (16.0, 10.5), (15.5, 10.75)] {
            assert_eq!(button_origin_y(height), origin);
            let center_from_top = TITLEBAR_HEIGHT - button_origin_y(height) - height / 2.0;
            assert_eq!(center_from_top, 17.5);
        }
    }
}
