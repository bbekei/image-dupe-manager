mod commands;
mod sidecar;

use std::sync::Arc;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Register sidecar state before starting it
            let state = Arc::new(sidecar::SidecarState::new());
            app.manage(state.clone());

            // Start sidecar (spawns process + stdout reader)
            if let Err(e) = state.start(app.handle()) {
                log::error!("Failed to start sidecar: {e}");
                // Don't panic — the app can still run, commands will return errors
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_app_version,
            commands::get_migration_status,
            commands::confirm_migration,
            commands::start_scan,
            commands::pause_scan,
            commands::resume_scan,
            commands::stop_scan,
            commands::get_sessions,
            commands::get_scan_summary,
            commands::get_scan_progress,
            commands::get_duplicate_groups,
            commands::get_group_detail,
            commands::set_file_action,
            commands::keep_and_delete_others,
            commands::apply_folder_action,
            commands::apply_selection_preset,
            commands::apply_custom_selection,
            commands::get_plan_summary,
            commands::execute_plan,
            commands::clear_all_actions,
            commands::get_similarity_groups,
            commands::get_similarity_group_detail,
            commands::apply_similarity_preset,
            commands::apply_custom_similarity_selection,
            commands::recommend_keeper,
            commands::get_bin_items,
            commands::restore_from_bin,
            commands::permanent_delete,
            commands::purge_expired,
            commands::get_sync_config,
            commands::save_sync_config,
            commands::authenticate_drive,
            commands::remove_peer,
            commands::export_hashes,
            commands::import_hashes,
            commands::sync_drive,
            commands::get_remote_peers,
            commands::get_requests,
            commands::respond_to_request,
            commands::get_thumbnail_url,
            commands::get_app_config,
            commands::set_app_config,
            commands::select_folders,
            commands::select_and_start_scan,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
