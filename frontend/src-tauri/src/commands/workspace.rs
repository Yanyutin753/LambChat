use serde::Serialize;
use std::path::PathBuf;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelectedWorkspace {
    id: String,
    machine_id: String,
    path: String,
}

/// 解析会话工作区为本地基目录（reveal 用）。
///
/// 绑定目录可以是用户自选的任意文件夹（不在 open_local_path 的
/// ~/.lambchat 白名单内），因此校验依据是**绑定文件本身**：前端传来的
/// `workspace_selection`（agent_options 里的原样 JSON）必须与本机
/// `.selected/<id>.json` 里落盘的真实路径逐字一致，且机器匹配本机——
/// 伪造任意目录在比对处即被拒。未绑定/坏绑定时回落 `data_root/{session_id}`
/// （服务端 fs 端点同一解析规则）。
fn resolve_workspace_base(
    home: &std::path::Path,
    config: &serde_json::Value,
    session_id: &str,
    workspace_selection: &Option<String>,
) -> Result<PathBuf, String> {
    let root = config["data_root"]
        .as_str()
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join("workspaces"));

    if let Some(raw) = workspace_selection {
        if let Ok(sel) = serde_json::from_str::<serde_json::Value>(raw) {
            let id = sel["id"].as_str().unwrap_or("");
            let machine = sel["machineId"].as_str().unwrap_or("");
            let claimed_path = sel["path"].as_str().unwrap_or("");
            let local_machine = config["machine_id"].as_str().unwrap_or("");
            let id_ok = id.len() == 39
                && id.starts_with("local-")
                && id["local-".len()..]
                    .chars()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase());
            if id_ok && !machine.is_empty() && machine == local_machine {
                let binding = root.join(".selected").join(format!("{id}.json"));
                if let Ok(bytes) = std::fs::read(&binding) {
                    if let Ok(persisted) = serde_json::from_slice::<String>(&bytes) {
                        if persisted == claimed_path && !claimed_path.is_empty() {
                            return Ok(PathBuf::from(claimed_path));
                        }
                    }
                }
            }
        }
    }

    // 默认工作区：data_root/{session_id}（与服务端 cwd 解析同形态；形态门
    // + canonicalize 前缀校验双防线，防 session_id 注入路径段）
    let id_ok = !session_id.is_empty()
        && session_id.len() <= 128
        && session_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-');
    if !id_ok {
        return Err("invalid session id".into());
    }
    Ok(root.join(session_id))
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

/// 在系统文件管理器中显示工作区文件（Finder / 资源管理器）。
///
/// `rel_path` 是工作区内相对路径；目标不存在时回退显示基目录（与 VS Code
/// 的直觉一致）。逃逸防线：词法归一拒绝 `..` + canonicalize 后必须仍在
/// 基目录之下（符号链接指向外部即拒，与 resolve_openable_path 同款手法）。
#[tauri::command]
pub async fn reveal_workspace_path(
    app: tauri::AppHandle,
    session_id: String,
    rel_path: String,
    workspace_selection: Option<String>,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let home = crate::daemon::sandbox_home()?;
        let config: serde_json::Value = serde_json::from_slice(
            &std::fs::read(home.join("sandbox.json")).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let base = resolve_workspace_base(&home, &config, &session_id, &workspace_selection)?;

        let rel = rel_path.trim().trim_start_matches("./");
        if rel.split('/').any(|seg| seg == "..") {
            return Err("relative path must not traverse upward".into());
        }
        let base_canon = std::fs::canonicalize(&base).unwrap_or_else(|_| base.clone());
        let target = if rel.is_empty() {
            base.clone()
        } else {
            base.join(rel)
        };
        let target_canon = match std::fs::canonicalize(&target) {
            // 文件/目录存在：canonicalize 成功，做前缀校验后 reveal 它
            Ok(c) => {
                if !c.starts_with(&base_canon) {
                    return Err("resolved path escapes the workspace".into());
                }
                c
            }
            // 不存在（沙箱快照 vs 本地已删）：回退 reveal 基目录
            Err(_) => base_canon,
        };

        app.opener()
            .reveal_item_in_dir(&target_canon)
            .map_err(|e| format!("failed to reveal {}: {e}", target_canon.display()))
    })
    .await
    .map_err(|e| e.to_string())?
}
