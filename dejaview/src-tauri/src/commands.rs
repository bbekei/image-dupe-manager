use std::sync::Arc;
use serde_json::Value;
use tauri::command;
use tauri::State;
use crate::sidecar::SidecarState;

// ── Version & Migration ───────────────────────────────────────────────────────

#[command]
pub async fn get_app_version(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_app_version", serde_json::json!({})).await
}

#[command]
pub async fn get_migration_status(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_migration_status", serde_json::json!({})).await
}

#[command]
pub async fn confirm_migration(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("confirm_migration", serde_json::json!({})).await
}

// ── Scan & Session ────────────────────────────────────────────────────────────

#[command]
pub async fn start_scan(
    sidecar: State<'_, Arc<SidecarState>>,
    folders: Vec<String>,
    session_name: String,
    enable_similarity: bool,
) -> Result<Value, String> {
    sidecar.call("start_scan", serde_json::json!({
        "folders": folders,
        "session_name": session_name,
        "enable_similarity": enable_similarity,
    })).await
}

#[command]
pub async fn pause_scan(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("pause_scan", serde_json::json!({})).await
}

#[command]
pub async fn resume_scan(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("resume_scan", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn stop_scan(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("stop_scan", serde_json::json!({})).await
}

#[command]
pub async fn get_sessions(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_sessions", serde_json::json!({})).await
}

#[command]
pub async fn get_scan_summary(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("get_scan_summary", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn get_scan_progress(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_scan_progress", serde_json::json!({})).await
}

// ── Duplicate Groups ──────────────────────────────────────────────────────────

#[command]
pub async fn get_duplicate_groups(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    offset: i64,
    limit: i64,
) -> Result<Value, String> {
    sidecar.call("get_duplicate_groups", serde_json::json!({
        "session_id": session_id,
        "offset": offset,
        "limit": limit,
    })).await
}

#[command]
pub async fn get_group_detail(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    pixel_hash: String,
) -> Result<Value, String> {
    sidecar.call("get_group_detail", serde_json::json!({
        "session_id": session_id,
        "pixel_hash": pixel_hash,
    })).await
}

#[command]
pub async fn set_file_action(
    sidecar: State<'_, Arc<SidecarState>>,
    file_id: i64,
    action: String,
    scope: String,
) -> Result<Value, String> {
    sidecar.call("set_file_action", serde_json::json!({
        "file_id": file_id,
        "action": action,
        "scope": scope,
    })).await
}

#[command]
pub async fn keep_and_delete_others(
    sidecar: State<'_, Arc<SidecarState>>,
    keep_file_id: i64,
    group_file_ids: Vec<i64>,
) -> Result<Value, String> {
    sidecar.call("keep_and_delete_others", serde_json::json!({
        "keep_file_id": keep_file_id,
        "group_file_ids": group_file_ids,
    })).await
}

#[command]
pub async fn apply_folder_action(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    folder_path: String,
    action: String,
) -> Result<Value, String> {
    sidecar.call("apply_folder_action", serde_json::json!({
        "session_id": session_id,
        "folder_path": folder_path,
        "action": action,
    })).await
}

#[command]
pub async fn apply_selection_preset(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    preset: String,
) -> Result<Value, String> {
    sidecar.call("apply_selection_preset", serde_json::json!({
        "session_id": session_id,
        "preset": preset,
    })).await
}

#[command]
pub async fn apply_custom_selection(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    criteria: Value,
) -> Result<Value, String> {
    sidecar.call("apply_custom_selection", serde_json::json!({
        "session_id": session_id,
        "criteria": criteria,
    })).await
}

#[command]
pub async fn get_plan_summary(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("get_plan_summary", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn execute_plan(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("execute_plan", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn clear_all_actions(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("clear_all_actions", serde_json::json!({
        "session_id": session_id,
    })).await
}

// ── Similarity ────────────────────────────────────────────────────────────────

#[command]
pub async fn get_similarity_groups(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    offset: i64,
    limit: i64,
) -> Result<Value, String> {
    sidecar.call("get_similarity_groups", serde_json::json!({
        "session_id": session_id,
        "offset": offset,
        "limit": limit,
    })).await
}

#[command]
pub async fn get_similarity_group_detail(
    sidecar: State<'_, Arc<SidecarState>>,
    group_id: i64,
) -> Result<Value, String> {
    sidecar.call("get_similarity_group_detail", serde_json::json!({
        "group_id": group_id,
    })).await
}

#[command]
pub async fn apply_similarity_preset(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    preset: String,
) -> Result<Value, String> {
    sidecar.call("apply_similarity_preset", serde_json::json!({
        "session_id": session_id,
        "preset": preset,
    })).await
}

#[command]
pub async fn apply_custom_similarity_selection(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
    criteria: Value,
) -> Result<Value, String> {
    sidecar.call("apply_custom_similarity_selection", serde_json::json!({
        "session_id": session_id,
        "criteria": criteria,
    })).await
}

#[command]
pub async fn recommend_keeper(
    sidecar: State<'_, Arc<SidecarState>>,
    files: Value,
) -> Result<Value, String> {
    sidecar.call("recommend_keeper", serde_json::json!({
        "files": files,
    })).await
}

// ── Bin ───────────────────────────────────────────────────────────────────────

#[command]
pub async fn get_bin_items(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("get_bin_items", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn restore_from_bin(
    sidecar: State<'_, Arc<SidecarState>>,
    soft_delete_id: i64,
) -> Result<Value, String> {
    sidecar.call("restore_from_bin", serde_json::json!({
        "soft_delete_id": soft_delete_id,
    })).await
}

#[command]
pub async fn permanent_delete(
    sidecar: State<'_, Arc<SidecarState>>,
    soft_delete_ids: Vec<i64>,
) -> Result<Value, String> {
    sidecar.call("permanent_delete", serde_json::json!({
        "soft_delete_ids": soft_delete_ids,
    })).await
}

#[command]
pub async fn purge_expired(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("purge_expired", serde_json::json!({})).await
}

// ── Sync & Family Sharing ─────────────────────────────────────────────────────

#[command]
pub async fn get_sync_config(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_sync_config", serde_json::json!({})).await
}

#[command]
pub async fn save_sync_config(
    sidecar: State<'_, Arc<SidecarState>>,
    username: String,
    folder_id: String,
    privacy: String,
) -> Result<Value, String> {
    sidecar.call("save_sync_config", serde_json::json!({
        "username": username,
        "folder_id": folder_id,
        "privacy": privacy,
    })).await
}

#[command]
pub async fn authenticate_drive(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("authenticate_drive", serde_json::json!({})).await
}

#[command]
pub async fn remove_peer(
    sidecar: State<'_, Arc<SidecarState>>,
    username: String,
) -> Result<Value, String> {
    sidecar.call("remove_peer", serde_json::json!({
        "username": username,
    })).await
}

#[command]
pub async fn export_hashes(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("export_hashes", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn import_hashes(
    sidecar: State<'_, Arc<SidecarState>>,
    file_path: String,
) -> Result<Value, String> {
    sidecar.call("import_hashes", serde_json::json!({
        "file_path": file_path,
    })).await
}

#[command]
pub async fn sync_drive(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("sync_drive", serde_json::json!({})).await
}

#[command]
pub async fn get_remote_peers(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_remote_peers", serde_json::json!({})).await
}

#[command]
pub async fn get_requests(
    sidecar: State<'_, Arc<SidecarState>>,
    session_id: i64,
) -> Result<Value, String> {
    sidecar.call("get_requests", serde_json::json!({
        "session_id": session_id,
    })).await
}

#[command]
pub async fn respond_to_request(
    sidecar: State<'_, Arc<SidecarState>>,
    request_id: i64,
    response: String,
) -> Result<Value, String> {
    sidecar.call("respond_to_request", serde_json::json!({
        "request_id": request_id,
        "response": response,
    })).await
}

// ── App Config ────────────────────────────────────────────────────────────────

#[command]
pub async fn get_app_config(sidecar: State<'_, Arc<SidecarState>>) -> Result<Value, String> {
    sidecar.call("get_app_config", serde_json::json!({})).await
}

#[command]
pub async fn set_app_config(
    sidecar: State<'_, Arc<SidecarState>>,
    key: String,
    value: Value,
) -> Result<Value, String> {
    sidecar.call("set_app_config", serde_json::json!({
        "key": key,
        "value": value,
    })).await
}

// ── Thumbnails (local — no sidecar) ──────────────────────────────────────────

#[command]
pub async fn get_thumbnail_url(thumb_path: String) -> Result<String, String> {
    if thumb_path.is_empty() {
        return Ok(String::new());
    }
    // Tauri asset protocol: asset://localhost/<absolute-path>
    // On Linux the path starts with /, on Windows with C:\ etc.
    let url = format!("asset://localhost/{}", thumb_path.trim_start_matches('/'));
    Ok(url)
}

// ── File Dialogs ──────────────────────────────────────────────────────────────

#[command]
pub async fn select_folders(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    use tokio::sync::oneshot;
    let (tx, rx) = oneshot::channel();
    app.dialog()
        .file()
        .set_can_create_directories(true)
        .pick_folders(|result| {
            let _ = tx.send(result);
        });
    let result = rx.await.map_err(|_| "dialog channel closed".to_string())?;
    match result {
        Some(paths) => Ok(paths.iter().map(|p| p.to_string()).collect()),
        None => Ok(vec![]),
    }
}

/// Opens the folder picker and immediately starts a scan — avoids a second
/// IPC round-trip after the dialog closes (which is unreliable on some GTK
/// environments).  Returns null if the user cancelled, or the session ID.
#[command]
pub async fn select_and_start_scan(
    app: tauri::AppHandle,
    sidecar: State<'_, Arc<SidecarState>>,
    session_name: String,
    enable_similarity: bool,
) -> Result<Option<serde_json::Value>, String> {
    use tauri_plugin_dialog::DialogExt;
    use tokio::sync::oneshot;
    let (tx, rx) = oneshot::channel();
    app.dialog()
        .file()
        .set_can_create_directories(true)
        .pick_folders(|result| {
            let _ = tx.send(result);
        });
    let result = rx.await.map_err(|_| "dialog channel closed".to_string())?;
    let folders = match result {
        Some(paths) => paths.iter().map(|p| p.to_string()).collect::<Vec<_>>(),
        None => return Ok(None),
    };
    let session_id = sidecar.call("start_scan", serde_json::json!({
        "folders": folders,
        "session_name": session_name,
        "enable_similarity": enable_similarity,
    })).await?;
    Ok(Some(session_id))
}
