fn main() {
    // Keep macOS 10.13 launch compatibility; the modern API is runtime guarded.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-link-arg=-Wl,-weak_framework,UserNotifications");
    }
    println!("cargo:rerun-if-env-changed=RELEASE_TAG");
    if let Ok(tag) = std::env::var("RELEASE_TAG") {
        println!(
            "cargo:rustc-env=LAMBCHAT_RELEASE_VERSION={}",
            tag.trim_start_matches('v')
        );
    }
    tauri_build::build();
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
        && std::env::var_os("CARGO_FEATURE_UPDATER_VERIFICATION").is_some()
    {
        // Tauri links Common-Controls v6 resources only to bins, not our verifier example.
        let resource =
            std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("resource.lib");
        println!("cargo:rustc-link-arg-examples={}", resource.display());
    }
}
