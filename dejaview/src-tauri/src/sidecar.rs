//! sidecar.rs — JSON-RPC 2.0 client for the DejaView Python sidecar process.
//!
//! Spawns `dejaview-sidecar` via tauri-plugin-shell, writes requests to stdin,
//! reads responses and notifications from stdout.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use serde_json::Value;
use tauri::{AppHandle, Emitter};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tokio::sync::oneshot;

/// Shared state managed by Tauri (registered via `app.manage()`).
pub struct SidecarState {
    child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
    pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>>,
    next_id: AtomicU64,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            pending: Arc::new(Mutex::new(HashMap::new())),
            next_id: AtomicU64::new(1),
        }
    }

    /// Spawn the sidecar and start the stdout reader loop.
    pub fn start(&self, app: &AppHandle) -> Result<(), String> {
        let (mut rx, child) = app
            .shell()
            .sidecar("dejaview-sidecar")
            .map_err(|e| format!("sidecar command error: {e}"))?
            .spawn()
            .map_err(|e| format!("sidecar spawn error: {e}"))?;

        *self.child.lock().unwrap() = Some(child);

        let pending = self.pending.clone();
        let app_handle = app.clone();

        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(bytes) => {
                        let line = String::from_utf8_lossy(&bytes);
                        let line = line.trim();
                        if line.is_empty() {
                            continue;
                        }
                        match serde_json::from_str::<Value>(line) {
                            Ok(json) => Self::handle_message(json, &pending, &app_handle),
                            Err(e) => log::warn!("sidecar: invalid JSON on stdout: {e}: {line}"),
                        }
                    }
                    CommandEvent::Stderr(bytes) => {
                        let line = String::from_utf8_lossy(&bytes);
                        log::debug!("sidecar stderr: {}", line.trim());
                    }
                    CommandEvent::Terminated(status) => {
                        log::warn!("sidecar terminated: {:?}", status);
                        break;
                    }
                    _ => {}
                }
            }
        });

        Ok(())
    }

    fn handle_message(
        json: Value,
        pending: &Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>>,
        app: &AppHandle,
    ) {
        // Notification: no "id" field, method == "event"
        if json.get("id").is_none() {
            if json.get("method").and_then(|v| v.as_str()) == Some("event") {
                if let Some(params) = json.get("params") {
                    if let (Some(name), Some(detail)) = (
                        params.get("name").and_then(|v| v.as_str()),
                        params.get("detail"),
                    ) {
                        if let Err(e) = app.emit(name, detail) {
                            log::warn!("sidecar: emit error for {name}: {e}");
                        }
                    }
                }
            }
            return;
        }

        // Response: has "id"
        if let Some(id) = json.get("id").and_then(|v| v.as_u64()) {
            if let Some(sender) = pending.lock().unwrap().remove(&id) {
                let _ = sender.send(json);
            }
        }
    }

    /// Send a JSON-RPC request and await the response result value.
    pub async fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        let (tx, rx) = oneshot::channel::<Value>();
        self.pending.lock().unwrap().insert(id, tx);

        let mut line = serde_json::to_string(&request).map_err(|e| e.to_string())?;
        line.push('\n');

        log::info!("sidecar -> {} (id={})", method, id);
        {
            let mut child_guard = self.child.lock().unwrap();
            let child = child_guard
                .as_mut()
                .ok_or_else(|| "Sidecar not running".to_string())?;
            child
                .write(line.as_bytes())
                .map_err(|e| format!("sidecar write error: {e}"))?;
        }
        log::info!("sidecar wrote {} bytes for {}", line.len(), method);

        let resp = rx.await.map_err(|_| "Sidecar response channel closed".to_string())?;
        log::info!("sidecar <- {} (id={})", method, id);

        if let Some(err) = resp.get("error") {
            let msg = err
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown sidecar error");
            Err(msg.to_string())
        } else {
            Ok(resp.get("result").cloned().unwrap_or(Value::Null))
        }
    }
}
