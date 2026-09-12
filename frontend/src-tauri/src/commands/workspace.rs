use serde::Serialize;
use std::path::PathBuf;
use tauri_plugin_dialog::DialogExt;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelectedWorkspace {
    id: String,
    machine_id: String,
    path: String,
}

// The path is obtained from the native picker, never supplied by the server.
#[tauri::command]
pub async fn sandbox_pick_workspace(
    app: tauri::AppHandle,
    title: String,
) -> Result<Option<SelectedWorkspace>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = crate::daemon::sandbox_home()?;
        let config: serde_json::Value = serde_json::from_slice(
            &std::fs::read(home.join("sandbox.json")).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let machine_id = config["machine_id"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("Local machine is not paired")?
            .to_owned();
        let Some(folder) = app.dialog().file().set_title(title).blocking_pick_folder() else {
            return Ok(None);
        };
        let path = folder
            .into_path()
            .map_err(|e| e.to_string())?
            .canonicalize()
            .map_err(|e| e.to_string())?;
        if !path.is_dir() {
            return Err("Selected path is not a directory".into());
        }
        let root = config["data_root"]
            .as_str()
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("workspaces"));
        let bindings = root.join(".selected");
        std::fs::create_dir_all(&bindings).map_err(|e| e.to_string())?;
        let id = format!("local-{}", uuid::Uuid::new_v4().simple());
        let path = path.to_string_lossy().into_owned();
        std::fs::write(
            bindings.join(format!("{id}.json")),
            serde_json::to_vec(&path).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        Ok(Some(SelectedWorkspace {
            id,
            machine_id,
            path,
        }))
    })
    .await
    .map_err(|e| e.to_string())?
}
