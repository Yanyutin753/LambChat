use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;

#[derive(serde::Serialize)]
struct ClientSandboxExecuteResult {
    output: String,
    exit_code: i32,
    truncated: bool,
}

#[derive(serde::Serialize)]
struct ClientSandboxReadResult {
    content: String,
    truncated: bool,
}

#[derive(serde::Serialize)]
struct ClientSandboxWriteResult {
    message: String,
}

#[derive(serde::Serialize)]
struct ClientSandboxEntry {
    path: String,
    is_dir: bool,
    size: Option<u64>,
    modified_at: Option<String>,
}

#[derive(serde::Serialize)]
struct ClientSandboxListResult {
    entries: Vec<ClientSandboxEntry>,
}

fn normalize_workspace_root(workspace_root: &str) -> Result<PathBuf, String> {
    let expanded = if workspace_root == "~" || workspace_root.starts_with("~/") {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .map_err(|_| "failed to resolve home directory".to_string())?;
        if workspace_root == "~" {
            home
        } else {
            format!("{home}/{}", &workspace_root[2..])
        }
    } else {
        workspace_root.to_string()
    };
    let root = PathBuf::from(expanded);
    if !root.exists() {
        fs::create_dir_all(&root).map_err(|e| format!("failed to create workspace: {e}"))?;
    }
    root.canonicalize()
        .map_err(|e| format!("invalid workspace root: {e}"))
}

fn map_virtual_workspace_path(root: &Path, requested_path: &str) -> Option<PathBuf> {
    const VIRTUAL_ROOTS: [&str; 6] = [
        "/home/user/LambChatWorkspace",
        "/home/user/lambchatworkspace",
        "~/LambChatWorkspace",
        "~/lambchatworkspace",
        "/workspace",
        "/home/user",
    ];

    if requested_path == "~" {
        return Some(root.to_path_buf());
    }

    for virtual_root in VIRTUAL_ROOTS {
        if requested_path == virtual_root {
            return Some(root.to_path_buf());
        }
        if let Some(relative) = requested_path.strip_prefix(&format!("{virtual_root}/")) {
            return Some(root.join(relative));
        }
    }

    None
}

fn shell_quote_path(path: &Path) -> String {
    let raw = path.to_string_lossy();
    format!("'{}'", raw.replace('\'', "'\\''"))
}

fn rewrite_virtual_paths_in_command(root: &Path, command: &str) -> String {
    let mut rewritten = command.to_string();
    let root_text = root.to_string_lossy();
    let replacements = [
        "/home/user/LambChatWorkspace",
        "/home/user/lambchatworkspace",
        "~/LambChatWorkspace",
        "~/lambchatworkspace",
        "/workspace",
        "/home/user",
    ];

    for virtual_root in replacements {
        rewritten = rewritten.replace(virtual_root, &root_text);
    }

    // Keep the exact root shell-safe when it contains spaces.
    if root_text.contains(' ') {
        rewritten = rewritten.replace(&root_text.to_string(), &shell_quote_path(root));
    }

    rewritten
}

fn rewrite_local_paths_in_output(root: &Path, output: &str) -> String {
    let root_text = root.to_string_lossy();
    output.replace(root_text.as_ref(), "/workspace")
}

fn resolve_under_workspace(workspace_root: &str, requested_path: &str) -> Result<PathBuf, String> {
    let root = normalize_workspace_root(workspace_root)?;
    let candidate = if requested_path.is_empty() || requested_path == "/" {
        root.clone()
    } else {
        let path = Path::new(requested_path);
        if let Some(mapped) = map_virtual_workspace_path(&root, requested_path) {
            mapped
        } else if path.is_absolute() {
            path.to_path_buf()
        } else {
            root.join(path)
        }
    };

    if candidate.exists() {
        let canonical = candidate
            .canonicalize()
            .map_err(|e| format!("invalid path: {e}"))?;
        if canonical.starts_with(&root) {
            Ok(canonical)
        } else {
            Err("path escapes workspace root".to_string())
        }
    } else {
        let parent = candidate
            .parent()
            .ok_or_else(|| "path has no parent".to_string())?;
        let canonical_parent = parent
            .canonicalize()
            .map_err(|e| format!("invalid parent path: {e}"))?;
        if canonical_parent.starts_with(&root) {
            Ok(candidate)
        } else {
            Err("path escapes workspace root".to_string())
        }
    }
}

fn truncate_string(mut value: String, max_bytes: usize) -> (String, bool) {
    if value.len() <= max_bytes {
        return (value, false);
    }
    while !value.is_char_boundary(max_bytes) {
        value.truncate(max_bytes - 1);
    }
    value.truncate(max_bytes);
    (value, true)
}

#[tauri::command]
fn client_sandbox_execute(
    workspace_root: String,
    command: String,
    cwd: Option<String>,
    timeout_seconds: Option<u64>,
) -> Result<ClientSandboxExecuteResult, String> {
    let root = normalize_workspace_root(&workspace_root)?;
    let workspace_root_path = root.clone();
    let working_dir = match cwd {
        Some(value) => resolve_under_workspace(&workspace_root, &value)?,
        None => root,
    };
    let command = rewrite_virtual_paths_in_command(&workspace_root_path, &command);
    let timeout = Duration::from_secs(timeout_seconds.unwrap_or(60).max(1));

    #[cfg(target_os = "windows")]
    let mut child = Command::new("cmd")
        .args(["/C", &command])
        .current_dir(&working_dir)
        .env("USERPROFILE", &workspace_root_path)
        .env("HOME", &workspace_root_path)
        .env("LAMBCHAT_WORKSPACE", &workspace_root_path)
        .env("WORKSPACE", &workspace_root_path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to spawn command: {e}"))?;

#[cfg(not(target_os = "windows"))]
    let mut child = Command::new("sh")
        .args(["-lc", &command])
        .current_dir(&working_dir)
        .env("HOME", &workspace_root_path)
        .env("LAMBCHAT_WORKSPACE", &workspace_root_path)
        .env("WORKSPACE", &workspace_root_path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to spawn command: {e}"))?;

    let start = Instant::now();
    let mut timed_out = false;
    loop {
        if child
            .try_wait()
            .map_err(|e| format!("failed to poll command: {e}"))?
            .is_some()
        {
            break;
        }
        if start.elapsed() >= timeout {
            timed_out = true;
            let _ = child.kill();
            break;
        }
        thread::sleep(Duration::from_millis(25));
    }

    let output = child
        .wait_with_output()
        .map_err(|e| format!("failed to collect command output: {e}"))?;
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    if !output.stderr.is_empty() {
        if !text.is_empty() {
            text.push('\n');
        }
        text.push_str(&String::from_utf8_lossy(&output.stderr));
    }
    if timed_out {
        if !text.is_empty() {
            text.push('\n');
        }
        text.push_str(&format!("Command timed out after {} seconds", timeout.as_secs()));
    }
    let text = rewrite_local_paths_in_output(&workspace_root_path, &text);
    let (output_text, truncated) = truncate_string(text, 256 * 1024);

    Ok(ClientSandboxExecuteResult {
        output: output_text,
        exit_code: if timed_out {
            -1
        } else {
            output.status.code().unwrap_or(-1)
        },
        truncated,
    })
}

#[tauri::command]
fn client_sandbox_read_file(
    workspace_root: String,
    path: String,
    limit: Option<usize>,
) -> Result<ClientSandboxReadResult, String> {
    let target = resolve_under_workspace(&workspace_root, &path)?;
    let mut file = fs::File::open(target).map_err(|e| format!("failed to open file: {e}"))?;
    let max_bytes = limit.unwrap_or(2 * 1024 * 1024).min(2 * 1024 * 1024);
    let mut buffer = Vec::new();
    file.by_ref()
        .take(max_bytes as u64 + 1)
        .read_to_end(&mut buffer)
        .map_err(|e| format!("failed to read file: {e}"))?;
    let truncated = buffer.len() > max_bytes;
    if truncated {
        buffer.truncate(max_bytes);
    }
    Ok(ClientSandboxReadResult {
        content: String::from_utf8_lossy(&buffer).to_string(),
        truncated,
    })
}

#[tauri::command]
fn client_sandbox_write_file(
    workspace_root: String,
    path: String,
    content: String,
) -> Result<ClientSandboxWriteResult, String> {
    let target = resolve_under_workspace(&workspace_root, &path)?;
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("failed to create parent dir: {e}"))?;
    }
    fs::write(&target, content).map_err(|e| format!("failed to write file: {e}"))?;
    Ok(ClientSandboxWriteResult {
        message: format!("Wrote {}", rewrite_local_paths_in_output(&normalize_workspace_root(&workspace_root)?, &target.display().to_string())),
    })
}

#[tauri::command]
fn client_sandbox_list(
    workspace_root: String,
    path: Option<String>,
) -> Result<ClientSandboxListResult, String> {
    let target = resolve_under_workspace(&workspace_root, path.as_deref().unwrap_or("/"))?;
    let mut entries = Vec::new();
    for entry in fs::read_dir(target).map_err(|e| format!("failed to list dir: {e}"))? {
        let entry = entry.map_err(|e| format!("failed to read dir entry: {e}"))?;
        let path = entry.path();
        let metadata = entry.metadata().ok();
        let modified_at = metadata
            .as_ref()
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs().to_string());
        let root = normalize_workspace_root(&workspace_root)?;
        entries.push(ClientSandboxEntry {
            path: rewrite_local_paths_in_output(&root, &path.display().to_string()),
            is_dir: path.is_dir(),
            size: metadata.as_ref().map(|m| m.len()),
            modified_at,
        });
    }
    Ok(ClientSandboxListResult { entries })
}

/// On version upgrade, clean webview data so the user starts fresh.
fn clean_on_version_upgrade(app_handle: &tauri::AppHandle) {
    let app_dir = app_handle
        .path()
        .app_data_dir()
        .expect("failed to resolve app data dir");
    let version_file = app_dir.join(".installed-version");
    let current_version = env!("CARGO_PKG_VERSION");

    let should_clean = if version_file.exists() {
        match fs::read_to_string(&version_file) {
            Ok(prev) if prev.trim() != current_version => true,
            Ok(_) => false,
            Err(_) => true,
        }
    } else {
        true
    };

    if should_clean {
        let _ = fs::create_dir_all(&app_dir);
        if let Ok(entries) = fs::read_dir(&app_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                // Remove everything except the version file itself
                if path.file_name().map_or(false, |n| {
                    n != ".installed-version"
                }) {
                    let _ = fs::remove_dir_all(&path);
                }
            }
        }
    }

    // Always write current version
    let _ = fs::write(&version_file, current_version);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolves_virtual_workspace_cwd_to_local_workspace_root() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let resolved = resolve_under_workspace(
            root.to_str().unwrap(),
            "/home/user/LambChatWorkspace",
        )
        .unwrap();

        assert_eq!(resolved, root.canonicalize().unwrap());
    }

    #[test]
    fn resolves_virtual_workspace_child_under_local_workspace_root() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let resolved = resolve_under_workspace(
            root.to_str().unwrap(),
            "/home/user/LambChatWorkspace/files",
        )
        .unwrap();

        assert_eq!(resolved, root.join("files"));
    }

    #[test]
    fn resolves_tilde_workspace_cwd_to_local_workspace_root() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let resolved = resolve_under_workspace(root.to_str().unwrap(), "~/LambChatWorkspace")
            .unwrap();

        assert_eq!(resolved, root.canonicalize().unwrap());
    }

    #[test]
    fn rewrites_virtual_paths_inside_shell_commands() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let command = "cd /home/user/lambchatworkspace/files 2>/dev/null || cd ~/lambchatworkspace/files";
        let rewritten = rewrite_virtual_paths_in_command(&root, command);

        assert!(!rewritten.contains("/home/user/lambchatworkspace"));
        assert!(!rewritten.contains("~/lambchatworkspace"));
        assert!(rewritten.contains(&format!("{}/files", root.display())));
    }

    #[test]
    fn rewrites_home_user_inside_shell_commands() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let command = "python /home/user/hello.py";
        let rewritten = rewrite_virtual_paths_in_command(&root, command);

        assert!(!rewritten.contains("/home/user/hello.py"));
        assert!(rewritten.contains(&format!("{}/hello.py", root.display())));
    }

    #[test]
    fn rewrites_local_workspace_paths_in_output() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let output = format!("{}/hello.py\n", root.display());
        let rewritten = rewrite_local_paths_in_output(&root, &output);

        assert_eq!(rewritten, "/workspace/hello.py\n");
    }

    #[test]
    #[cfg(not(target_os = "windows"))]
    fn executes_command_with_virtual_workspace_path() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(root.join("files")).unwrap();

        let result = client_sandbox_execute(
            root.to_string_lossy().to_string(),
            "cd /home/user/lambchatworkspace/files 2>/dev/null || cd ~/lambchatworkspace/files; pwd".to_string(),
            Some("/home/user/LambChatWorkspace".to_string()),
            Some(5),
        )
        .unwrap();

        assert_eq!(result.exit_code, 0);
        assert!(result.output.contains("/workspace/files"));
    }

    #[test]
    #[cfg(not(target_os = "windows"))]
    fn executes_command_with_home_environment_mapped_to_workspace() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let result = client_sandbox_execute(
            root.to_string_lossy().to_string(),
            "echo $HOME && ls $HOME".to_string(),
            Some("/home/user/LambChatWorkspace".to_string()),
            Some(5),
        )
        .unwrap();

        assert_eq!(result.exit_code, 0);
        assert!(result.output.contains("/workspace"));
        assert!(!result.output.contains("invalid parent path"));
    }

    #[test]
    #[cfg(not(target_os = "windows"))]
    fn executes_pwd_with_tilde_workspace_cwd() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("workspace");
        fs::create_dir_all(&root).unwrap();

        let result = client_sandbox_execute(
            root.to_string_lossy().to_string(),
            "pwd 2>&1 || echo \"pwd failed\"".to_string(),
            Some("~/LambChatWorkspace".to_string()),
            Some(5),
        )
        .unwrap();

        assert_eq!(result.exit_code, 0);
        assert!(result.output.contains("/workspace"));
        assert!(!result.output.contains("invalid parent path"));
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            client_sandbox_execute,
            client_sandbox_read_file,
            client_sandbox_write_file,
            client_sandbox_list
        ])
        .setup(|app| {
            clean_on_version_upgrade(app.handle());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running LambChat desktop app");
}
