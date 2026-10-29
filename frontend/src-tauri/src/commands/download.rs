//! Downloads can write only to a destination chosen in the native save dialog.
use std::io::Write;
use std::path::Path;
use tauri_plugin_dialog::DialogExt;

fn suggested_name(name: &str) -> String {
    let name = name.rsplit(['/', '\\']).next().unwrap_or("");
    let name: String = name.chars().filter(|c| !c.is_control()).collect();
    if name.is_empty() || name == "." || name == ".." {
        "download".into()
    } else {
        name
    }
}

fn write_download(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path.parent().ok_or("Invalid download destination")?;
    let temp = parent.join(format!(".lambchat-download-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| {
        let mut options = std::fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(&temp)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        // Same-directory rename replaces only after the complete file is durable.
        std::fs::rename(&temp, path)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    result.map_err(|e: std::io::Error| e.to_string())
}

#[tauri::command]
pub async fn desktop_save_file(
    app: tauri::AppHandle,
    request: tauri::ipc::Request<'_>,
) -> Result<bool, String> {
    let name: String = serde_json::from_str(
        request
            .headers()
            .get("x-file-name")
            .and_then(|value| value.to_str().ok())
            .ok_or("Missing download filename")?,
    )
    .map_err(|_| "Invalid download filename")?;
    let bytes = match request.body() {
        tauri::ipc::InvokeBody::Raw(bytes) => bytes.clone(),
        _ => return Err("Download requires binary bytes".into()),
    };
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .set_file_name(suggested_name(&name))
            .blocking_save_file()
        else {
            return Ok(false);
        };
        let path = file.into_path().map_err(|e| e.to_string())?;
        write_download(&path, &bytes)?;
        Ok(true)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn suggested_filename_never_sets_a_destination_path() {
        assert_eq!(suggested_name("../../报告.docx"), "报告.docx");
        assert_eq!(suggested_name("C:\\private\\report.docx"), "report.docx");
        assert_eq!(suggested_name(".."), "download");
        assert_eq!(suggested_name("\0"), "download");
    }

    #[test]
    fn saves_exact_binary_bytes_and_atomically_replaces_existing_file() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        std::fs::create_dir(&root).unwrap();
        let path = root.join("报告.docx");
        std::fs::write(&path, b"original").unwrap();
        write_download(&path, &[80, 75, 0, 255]).unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), [80, 75, 0, 255]);
        assert_eq!(std::fs::read_dir(&root).unwrap().count(), 1);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn failed_replacement_keeps_existing_destination_and_cleans_temporary_file() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let path = root.join("existing");
        std::fs::create_dir_all(&path).unwrap();
        std::fs::write(path.join("original"), b"keep").unwrap();
        assert!(write_download(&path, b"new").is_err());
        assert_eq!(std::fs::read(path.join("original")).unwrap(), b"keep");
        assert_eq!(std::fs::read_dir(&root).unwrap().count(), 1);
        std::fs::remove_dir_all(root).unwrap();
    }
}
