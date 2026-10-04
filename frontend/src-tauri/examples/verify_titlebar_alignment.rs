//! Native smoke test: `cargo run --example verify_titlebar_alignment` on macOS.
//! Uses real AppKit buttons and the production notification handlers, without a daemon.

#[cfg(target_os = "macos")]
#[path = "../src/titlebar.rs"]
mod titlebar;

#[cfg(target_os = "macos")]
fn main() {
    use objc2_app_kit::{
        NSWindow, NSWindowButton, NSWindowDidBecomeKeyNotification,
        NSWindowDidChangeBackingPropertiesNotification, NSWindowDidDeminiaturizeNotification,
        NSWindowDidExitFullScreenNotification, NSWindowDidResizeNotification,
    };
    use objc2_foundation::{NSNotificationCenter, NSPoint};
    use tauri::Manager;

    fn wait_for_fullscreen(window: &tauri::WebviewWindow, expected: bool) -> bool {
        for _ in 0..50 {
            if matches!(window.is_fullscreen(), Ok(value) if value == expected) {
                return true;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        false
    }

    fn assert_centers(window: &NSWindow) {
        let close = window
            .standardWindowButton(NSWindowButton::CloseButton)
            .expect("close");
        assert_eq!(close.frame().origin.x, 12.0);
        let mini = window
            .standardWindowButton(NSWindowButton::MiniaturizeButton)
            .expect("miniaturize");
        let zoom = window
            .standardWindowButton(NSWindowButton::ZoomButton)
            .expect("zoom");
        let first_gap = mini.frame().origin.x - close.frame().origin.x;
        let second_gap = zoom.frame().origin.x - mini.frame().origin.x;
        assert!(
            first_gap > close.frame().size.width,
            "native spacing is preserved"
        );
        assert_eq!(first_gap, second_gap);
        for kind in [
            NSWindowButton::CloseButton,
            NSWindowButton::MiniaturizeButton,
            NSWindowButton::ZoomButton,
        ] {
            let button = window.standardWindowButton(kind).expect("native control");
            let frame = button.frame();
            let point = NSPoint::new(frame.size.width / 2.0, frame.size.height / 2.0);
            // Convert from the button's own bounds to window coordinates, checking
            // the real view hierarchy rather than repeating our positioning formula.
            let center = button.convertPoint_toView(point, None);
            let from_top = window.frame().size.height - center.y;
            assert!(
                (from_top - 17.5).abs() < 0.01,
                "{kind:?}: center={from_top}"
            );
        }
    }

    let app = tauri::Builder::default()
        .setup(|app| {
            let window = app.get_webview_window("main").expect("main window");
            titlebar::install(&window)?;
            let native = unsafe { &*window.ns_window()?.cast::<NSWindow>() };
            assert_centers(native);
            println!("PASS: initial native centers match the 17.5px web toolbar center");
            let center = NSNotificationCenter::defaultCenter();
            for name in unsafe {
                [
                    NSWindowDidResizeNotification,
                    NSWindowDidExitFullScreenNotification,
                    NSWindowDidChangeBackingPropertiesNotification,
                    NSWindowDidDeminiaturizeNotification,
                    NSWindowDidBecomeKeyNotification,
                ]
            } {
                // Reproduce AppKit resetting button frames, then deliver the
                // actual native notification through NSNotificationCenter.
                for kind in [
                    NSWindowButton::CloseButton,
                    NSWindowButton::MiniaturizeButton,
                    NSWindowButton::ZoomButton,
                ] {
                    let button = native.standardWindowButton(kind).expect("native control");
                    let mut frame = button.frame();
                    frame.origin.y -= 7.0;
                    button.setFrameOrigin(frame.origin);
                }
                unsafe { center.postNotificationName_object(name, Some(native)) };
                assert_centers(native);
                println!("PASS: {name}");
            }
            titlebar::uninstall();
            let close = native
                .standardWindowButton(NSWindowButton::CloseButton)
                .expect("close");
            let mut frame = close.frame();
            frame.origin.y -= 7.0;
            close.setFrameOrigin(frame.origin);
            unsafe {
                center.postNotificationName_object(NSWindowDidResizeNotification, Some(native))
            };
            assert_eq!(close.frame().origin.y, frame.origin.y);
            println!("PASS: observers are removed on shutdown");
            titlebar::install(&window)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("build native titlebar check");
    app.run(|app, event| {
        if let tauri::RunEvent::Ready = event {
            let window = app.get_webview_window("main").expect("main");
            let app = app.clone();
            std::thread::spawn(move || {
                // Exercise real OS transitions too: manually posted notifications
                // cannot reveal ordering against AppKit/Tauri's own layout work.
                window
                    .set_size(tauri::LogicalSize::new(1040.0, 720.0))
                    .expect("resize");
                std::thread::sleep(std::time::Duration::from_secs(1));
                window.set_fullscreen(true).expect("enter fullscreen");
                std::thread::sleep(std::time::Duration::from_secs(1));
                if !wait_for_fullscreen(&window, true) {
                    eprintln!("FAIL: macOS did not enter fullscreen");
                    app.exit(1);
                    return;
                }
                window.set_fullscreen(false).expect("exit fullscreen");
                std::thread::sleep(std::time::Duration::from_secs(1));
                if !wait_for_fullscreen(&window, false) {
                    eprintln!("FAIL: macOS did not exit fullscreen");
                    app.exit(1);
                    return;
                }
                let main_window = window.clone();
                window
                    .run_on_main_thread(move || {
                        let native = unsafe {
                            &*main_window.ns_window().expect("native").cast::<NSWindow>()
                        };
                        assert_centers(native);
                        println!(
                            "PASS: real resize and fullscreen round-trip retain the toolbar center"
                        );
                        titlebar::uninstall();
                        app.exit(0);
                    })
                    .expect("verify on UI thread");
            });
        }
    });
}

#[cfg(not(target_os = "macos"))]
fn main() {
    println!("SKIP: native titlebar alignment requires macOS");
}
