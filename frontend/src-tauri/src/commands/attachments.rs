//! Only native picker/drop receipts authorize reading an original for cloud upload.
use serde::{Deserialize, Serialize};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

#[derive(Clone, Serialize, Deserialize)]
pub struct DesktopFile {
    token: String,
    path: PathBuf,
    name: String,
    size: u64,
    modified: String,
}
fn receipt_path(root: &Path, token: &str) -> Result<PathBuf, String> {
    if token.len() != 32
        || !token
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err("Invalid file reference".into());
    }
    Ok(root.join(format!("{token}.json")))
}
fn file_info(path: &Path, token: String) -> Result<DesktopFile, String> {
    let canonical = path
        .canonicalize()
        .map_err(|_| "Original file unavailable")?;
    // Refuse a symlink substitution after selection; the receipt stores the canonical original.
    if canonical != path {
        return Err("Original file path changed".into());
    }
    let metadata = std::fs::metadata(&canonical).map_err(|_| "Original file unavailable")?;
    if !metadata.is_file() {
        return Err("Select a file, not a folder".into());
    }
    let modified = metadata
        .modified()
        .map_err(|_| "File timestamp unavailable")?
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| "Invalid timestamp")?
        .as_nanos()
        .to_string();
    let name = canonical
        .file_name()
        .ok_or("Missing filename")?
        .to_string_lossy()
        .into_owned();
    Ok(DesktopFile {
        token,
        path: canonical,
        name,
        size: metadata.len(),
        modified,
    })
}
fn read_chunk(
    info: &DesktopFile,
    offset: u64,
    length: usize,
    size: u64,
    modified: &str,
) -> Result<Vec<u8>, String> {
    if length == 0
        || length > 1024 * 1024
        || offset
            .checked_add(length as u64)
            .is_none_or(|end| end > size)
    {
        return Err("Invalid read range".into());
    }
    let current = file_info(&info.path, info.token.clone())?;
    if current.size != size || current.modified != modified {
        return Err("Original file changed during upload".into());
    }
    let mut file = std::fs::File::open(&current.path).map_err(|_| "Original file unavailable")?;
    file.seek(SeekFrom::Start(offset))
        .map_err(|e| e.to_string())?;
    let mut bytes = vec![0; length];
    file.read_exact(&mut bytes)
        .map_err(|_| "Original file changed during upload")?;
    let after = file_info(&info.path, info.token.clone())?;
    if after.size != size || after.modified != modified {
        return Err("Original file changed during upload".into());
    }
    Ok(bytes)
}
fn root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("file-references"))
}
pub(crate) fn register(app: &AppHandle, path: &Path) -> Result<DesktopFile, String> {
    let path = path
        .canonicalize()
        .map_err(|_| "Original file unavailable")?;
    let info = file_info(&path, uuid::Uuid::new_v4().simple().to_string())?;
    let root = root(app)?;
    std::fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700))
            .map_err(|e| e.to_string())?;
    }
    std::fs::write(
        receipt_path(&root, &info.token)?,
        serde_json::to_vec(&info).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Ok(info)
}
fn load(app: &AppHandle, token: &str) -> Result<DesktopFile, String> {
    let bytes = std::fs::read(receipt_path(&root(app)?, token)?)
        .map_err(|_| "File reference unavailable on this device")?;
    let info: DesktopFile = serde_json::from_slice(&bytes).map_err(|_| "Invalid file reference")?;
    if info.token != token {
        return Err("Invalid file reference".into());
    }
    file_info(&info.path, token.to_owned())
}
#[tauri::command]
pub async fn desktop_pick_files(app: AppHandle, title: String) -> Result<Vec<DesktopFile>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(files) = app.dialog().file().set_title(title).blocking_pick_files() else {
            return Ok(vec![]);
        };
        files
            .into_iter()
            .map(|file| register(&app, &file.into_path().map_err(|e| e.to_string())?))
            .collect()
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
pub async fn desktop_file_info(app: AppHandle, token: String) -> Result<DesktopFile, String> {
    tauri::async_runtime::spawn_blocking(move || load(&app, &token))
        .await
        .map_err(|e| e.to_string())?
}
#[tauri::command]
pub async fn desktop_read_file_chunk(
    app: AppHandle,
    token: String,
    offset: u64,
    length: usize,
    size: u64,
    modified: String,
) -> Result<Vec<u8>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        read_chunk(&load(&app, &token)?, offset, length, size, &modified)
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
pub async fn desktop_reveal_file(app: AppHandle, token: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.opener()
            .reveal_item_in_dir(load(&app, &token)?.path)
            .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}
/// HTML5 file drops are intercepted by the native webview on Windows.
pub fn handle_drop(window: &tauri::Window, event: &tauri::WindowEvent) {
    if window.label() != "main" {
        return;
    }
    if let tauri::WindowEvent::DragDrop(tauri::DragDropEvent::Drop { paths, position }) = event {
        let app = window.app_handle().clone();
        let paths = paths.clone();
        let position = *position;
        let batch = uuid::Uuid::new_v4().simple().to_string();
        let _ = app.emit_to("main", "desktop-files-dropped", serde_json::json!({"batchId": batch, "pending": true, "files": [], "position": position}));
        tauri::async_runtime::spawn_blocking(move || {
            let result: Result<Vec<_>, _> = paths.iter().map(|path| register(&app, path)).collect();
            let payload = match result {
                Ok(files) => {
                    serde_json::json!({"batchId": batch, "files": files, "position": position})
                }
                Err(error) => {
                    serde_json::json!({"batchId": batch, "files": [], "error": error, "position": position})
                }
            };
            let _ = app.emit_to("main", "desktop-files-dropped", payload);
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn receipt_ids_cannot_select_other_files() {
        assert!(receipt_path(std::path::Path::new("/tmp/receipts"), &"a".repeat(32)).is_ok());
        for value in ["../secret", "", "/etc/passwd", "aaaaaaaa-aaaa"] {
            assert!(receipt_path(std::path::Path::new("/tmp/receipts"), value).is_err());
        }
    }
    #[test]
    fn reads_are_bounded_and_reject_changed_originals() {
        let path = std::env::temp_dir().join(format!("file-ref-{}", uuid::Uuid::new_v4()));
        std::fs::write(&path, b"abc").unwrap();
        let path = path.canonicalize().unwrap();
        let info = file_info(&path, "a".repeat(32)).unwrap();
        assert_eq!(
            read_chunk(&info, 1, 2, info.size, &info.modified).unwrap(),
            b"bc"
        );
        assert!(read_chunk(&info, 0, 1024 * 1024 + 1, info.size, &info.modified).is_err());
        std::fs::write(&path, b"changed").unwrap();
        assert!(read_chunk(&info, 0, 3, info.size, &info.modified).is_err());
        std::fs::remove_file(&path).unwrap();
        assert!(file_info(&path, info.token).is_err());
    }
}
