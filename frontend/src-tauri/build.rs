fn main() {
    // Keep macOS 10.13 launch compatibility; the modern API is runtime guarded.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-link-arg=-Wl,-weak_framework,UserNotifications");
    }
    tauri_build::build()
}
