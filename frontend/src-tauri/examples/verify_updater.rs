//! Release gate: use the real native updater verifier without creating a WebView.
use std::{error::Error, fs, path::Path};
use tauri::test::{mock_builder, mock_context, noop_assets, MockRuntime};
use tauri_plugin_updater::{Update, UpdaterExt};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn prepare_update(
    public_key: &str,
    signature: &str,
    announced: &str,
    installed: &str,
    executable: &Path,
    install: bool,
) -> Result<(tauri::App<MockRuntime>, Option<Update>)> {
    let mut context = mock_context(noop_assets());
    context.package_info_mut().version = installed.parse()?;
    let mut config: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json"))?;
    config["plugins"]["updater"]["pubkey"] = public_key.into();
    // A release gate must reject legacy signatures lacking a version too.
    config["plugins"]["updater"]["requireSignedVersion"] = true.into();
    context
        .config_mut()
        .plugins
        .0
        .insert("updater".into(), config["plugins"]["updater"].clone());
    let app = mock_builder()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .build(context)?;
    let builder = app
        .updater_builder()
        .executable_path(executable)
        .restart_after_install(false);
    #[cfg(windows)]
    let builder = if install {
        builder.installer_arg(format!(
            "/D={}",
            executable.parent().ok_or("No install directory")?.display()
        ))
    } else {
        builder
    };
    #[cfg(not(windows))]
    let _ = install;
    let update = builder.build()?.restore_update(serde_json::json!({
        "version": announced,
        "url": "https://example.invalid/updater-verification",
        "signature": signature.trim(),
    }))?;
    Ok((app, update))
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if !(3..=5).contains(&args.len()) {
        return Err(
            "Usage: verify_updater ARTIFACT SIGNATURE VERSION [INSTALLED_VERSION] [INSTALL_EXE]"
                .into(),
        );
    }
    let config: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json"))?;
    let key = config["plugins"]["updater"]["pubkey"]
        .as_str()
        .ok_or("Missing updater public key")?;
    let fallback = std::env::temp_dir().join("updater-verification.app/Contents/MacOS/verify");
    let executable = args.get(4).map(Path::new).unwrap_or(&fallback);
    let installed = args.get(3).map(String::as_str).unwrap_or("0.1.0");
    let (_app, update) = prepare_update(
        key,
        &fs::read_to_string(&args[1])?,
        &args[2],
        installed,
        executable,
        args.len() == 5,
    )?;
    let update = update.ok_or("Native updater did not select this version")?;
    let bytes = fs::read(&args[0])?;
    update.verify(&bytes)?;
    println!(
        "PASS: native updater verified signature and signed version {}",
        args[2]
    );
    if args.len() == 5 {
        update.install(bytes)?;
        println!(
            "PASS: native updater installed into {}",
            executable.display()
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    const KEY: &str = include_str!("fixtures/updater/public.key");
    const PAYLOAD: &[u8] = include_bytes!("fixtures/updater/payload.txt");
    const CORE: &str = include_str!("fixtures/updater/core.sig");
    const DEV2: &str = include_str!("fixtures/updater/dev2.sig");

    fn verify(signature: &str, announced: &str, installed: &str, payload: &[u8]) -> Result<()> {
        let exe = std::env::temp_dir().join("updater-test.app/Contents/MacOS/test");
        let (_app, update) =
            prepare_update(KEY.trim(), signature, announced, installed, &exe, false)?;
        update.ok_or("No update")?.verify(payload)?;
        Ok(())
    }

    #[test]
    fn rejects_core_signature_for_dev_announcement() {
        let error = verify(CORE, "2.15.3-dev.2", "2.15.2", PAYLOAD).unwrap_err();
        assert!(error.to_string().contains("signed for version 2.15.3 but"));
    }

    #[test]
    fn accepts_full_dev_signature_from_stable_and_previous_dev() {
        for installed in ["2.15.2", "2.15.3-dev.1"] {
            verify(DEV2, "2.15.3-dev.2", installed, PAYLOAD).unwrap();
        }
    }

    #[test]
    fn rejects_different_dev_number_and_tampered_payload() {
        assert!(verify(DEV2, "2.15.3-dev.3", "2.15.3-dev.1", PAYLOAD).is_err());
        assert!(verify(DEV2, "2.15.3-dev.2", "2.15.3-dev.1", b"tampered").is_err());
    }

    #[test]
    fn rejects_signature_without_version_metadata() {
        assert!(verify(
            include_str!("fixtures/updater/unversioned.sig"),
            "2.15.3-dev.2",
            "2.15.2",
            PAYLOAD
        )
        .is_err());
    }

    #[test]
    fn accepts_stable_after_dev_and_does_not_repeat_or_downgrade() {
        verify(CORE, "2.15.3", "2.15.3-dev.2", PAYLOAD).unwrap();
        for announced in ["2.15.3-dev.1", "2.15.3-dev.2"] {
            let exe = std::env::temp_dir().join("updater-test.app/Contents/MacOS/test");
            let (_app, update) =
                prepare_update(KEY.trim(), DEV2, announced, "2.15.3-dev.2", &exe, false).unwrap();
            assert!(update.is_none());
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn native_install_preserves_old_app_on_bad_signature_and_replaces_valid_app() {
        let root =
            std::env::temp_dir().join(format!("lambchat-updater-test-{}", uuid::Uuid::new_v4()));
        let app_dir = root.join("LambChat.app");
        let executable = app_dir.join("Contents/MacOS/fixture");
        fs::create_dir_all(executable.parent().unwrap()).unwrap();
        fs::write(&executable, "old application").unwrap();
        fs::write(root.join("user-data"), "keep-me").unwrap();
        let archive = include_bytes!("fixtures/updater/app.tar.gz");
        let (_app, update) = prepare_update(
            KEY.trim(),
            include_str!("fixtures/updater/app.tar.gz.sig"),
            "2.15.3-dev.2",
            "2.15.3-dev.1",
            &executable,
            true,
        )
        .unwrap();
        let update = update.unwrap();
        let rejected = update.install(b"tampered").is_err();
        let old_preserved = fs::read_to_string(&executable).unwrap() == "old application";
        let installed = update.install(archive);
        let replaced = fs::read_to_string(&executable).unwrap() == "updated application fixture\n";
        let data_preserved = fs::read_to_string(root.join("user-data")).unwrap() == "keep-me";
        fs::remove_dir_all(root).unwrap();
        assert!(rejected && old_preserved);
        installed.unwrap();
        assert!(replaced && data_preserved);
    }
}
