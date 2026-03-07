/**
 * TypeScript interfaces matching Python backend API contracts.
 * These types define the shape of data flowing between React ↔ Python via pywebview.
 */

// -- Sessions --

export interface Session {
  id: number
  name: string
  created_at: string
  status: 'in_progress' | 'paused' | 'complete' | 'stopped'
  folder_count: number
  file_count: number
}

export interface ScanSummary {
  session_id: number
  total_files: number
  total_groups: number
  total_duplicates: number
  recoverable_bytes: number
  similarity_group_count: number
}

// -- Files & Duplicate Groups --

export interface FileInfo {
  id: number
  session_id: number
  path: string
  size: number
  modified_at: string
  pixel_hash: string | null
  perceptual_hash: string | null
  thumbnail_path: string | null
  thumbnail_data?: string
  status: string
  width: number | null
  height: number | null
  action?: FileAction | null
}

export interface DuplicateGroup {
  pixel_hash: string
  hash_algorithm: string
  file_count: number
  files: FileInfo[]
}

export interface DuplicateGroupsPage {
  groups: DuplicateGroup[]
  total_count: number
}

export interface FilterCriteria {
  folder?: string
  date_from?: string
  date_to?: string
  min_size?: number
  max_size?: number
  extensions?: string[]
  min_copies?: number
}

// -- File Actions --

export type FileAction = 'keep' | 'delete' | 'ignore'
export type ActionScope = 'file' | 'folder'

export interface FileActionRecord {
  id: number
  file_id: number
  session_id: number
  action: FileAction
  scope: ActionScope
  decided_at: string
  executed_at: string | null
}

export interface PlanSummary {
  keep_count: number
  delete_count: number
  ignore_count: number
  total_size_bytes: number
  actions: PlanAction[]
}

export interface PlanAction {
  file_id: number
  path: string
  size: number
  action: FileAction
  pixel_hash: string
}

// -- Similarity --

export interface SimilarityGroupSummary {
  id: number
  session_id: number
  member_count: number
  status: string
  representative_path: string
}

export interface SimilarityGroupsPage {
  groups: SimilarityGroupSummary[]
  total_count: number
}

export interface SimilarityGroup {
  id: number
  member_count: number
  members: FileInfo[]
}

export interface KeeperRecommendation {
  file_id: number
  reason: string
}

// -- Soft Delete / Bin --

export interface BinItem {
  id: number
  session_id: number
  file_id: number
  original_path: string
  trash_path: string
  deleted_at: string
  expires_at: string
  recovered_at: string | null
}

// -- Family Sharing --

export interface RemotePeer {
  id: number
  username: string
  last_seen_at: string
}

export interface ShareRequest {
  id: number
  session_id: number
  file_id: number | null
  peer_username: string
  direction: 'incoming' | 'outgoing'
  type: string
  status: 'pending' | 'approved' | 'declined' | 'cancelled'
  message: string | null
  created_at: string
  responded_at: string | null
}

// -- Sync Config --

export interface SyncConfig {
  local_username: string
  gdrive_folder_id: string
  export_privacy: 'hash_only' | 'filename' | 'full_path'
  sync_enabled: boolean
  authenticated: boolean
}

// -- App Config --

export interface AppConfig {
  language: string
  theme: string
  max_scan_workers: number
  perf_logging: boolean
  scan_delay_ms: number
}

// -- Selection Presets --

export type SelectionPreset =
  | 'KEEP_LARGEST_FILE'
  | 'KEEP_NEWEST'
  | 'KEEP_OLDEST'
  | 'KEEP_SHORTEST_PATH'
  | 'KEEP_HIGHEST_RESOLUTION'

export type SortField = 'size' | 'resolution' | 'modified_at' | 'path_depth' | 'filename_length'

export interface SortCriterion {
  field: SortField
  ascending: boolean
}

export interface SelectionResult {
  keep_count: number
  delete_count: number
  active_preset: string
}

export interface SelectionProgressEvent {
  current: number
  total: number
}

export interface SelectionCompleteEvent {
  keep_count: number
  delete_count: number
  active_preset: string
}

// -- Events from Python backend --

export interface ScanProgressEvent {
  current: number
  total: number
  phase: string
}

export interface ScanStatusEvent {
  status: string
  message: string
}

export interface ExecProgressEvent {
  current: number
  total: number
  action: string
  file_path: string
}

export interface ExecCompleteEvent {
  success: number
  errors: number
  summary: string
}

// -- pywebview API surface --

export interface ScanProgress {
  phase: string
  current: number
  total: number
  discovered: number
  duplicates: number
  message: string
}

export interface PyWebViewAPI {
  // Scan & Session
  start_scan(folders: string[], session_name: string, enable_similarity: boolean): Promise<number>
  pause_scan(): Promise<void>
  resume_scan(session_id: number): Promise<void>
  stop_scan(): Promise<void>
  get_sessions(): Promise<Session[]>
  get_scan_summary(session_id: number): Promise<ScanSummary>
  get_scan_progress(): Promise<ScanProgress>

  // Duplicate Groups
  get_duplicate_groups(session_id: number, offset: number, limit: number, filters?: FilterCriteria): Promise<DuplicateGroupsPage>
  get_group_detail(session_id: number, pixel_hash: string): Promise<FileInfo[]>
  set_file_action(file_id: number, action: FileAction, scope: ActionScope): Promise<{ actions: Record<string, FileAction> }>
  keep_and_delete_others(keep_file_id: number, group_file_ids: number[]): Promise<{ actions: Record<string, FileAction> }>
  apply_folder_action(session_id: number, folder_path: string, action: FileAction): Promise<{ affected: number }>
  apply_selection_preset(session_id: number, preset: SelectionPreset, group_ids?: string[]): Promise<SelectionResult>
  apply_custom_selection(session_id: number, criteria: SortCriterion[]): Promise<SelectionResult>
  get_plan_summary(session_id: number): Promise<PlanSummary>
  execute_plan(session_id: number): Promise<void>
  clear_all_actions(session_id: number): Promise<void>

  // Similarity
  get_similarity_groups(session_id: number, offset: number, limit: number): Promise<SimilarityGroupsPage>
  get_similarity_group_detail(group_id: number): Promise<SimilarityGroup>
  apply_similarity_preset(session_id: number, preset: SelectionPreset, group_ids?: number[]): Promise<SelectionResult>
  apply_custom_similarity_selection(session_id: number, criteria: SortCriterion[]): Promise<SelectionResult>
  recommend_keeper(files: FileInfo[]): Promise<KeeperRecommendation>

  // Bin
  get_bin_items(session_id: number): Promise<BinItem[]>
  restore_from_bin(soft_delete_id: number): Promise<void>
  permanent_delete(soft_delete_ids: number[]): Promise<void>
  purge_expired(): Promise<number>

  // Sync Config
  get_sync_config(): Promise<SyncConfig>
  save_sync_config(username: string, folder_id: string, privacy: string): Promise<{ ok: boolean; error?: string }>
  authenticate_drive(): Promise<{ ok: boolean; error?: string }>
  remove_peer(username: string): Promise<void>

  // Family Sharing
  export_hashes(session_id: number): Promise<string>
  import_hashes(file_path: string): Promise<{ imported: number; username?: string; error?: string }>
  sync_drive(): Promise<{ status: string; errors: Record<string, string> }>
  get_remote_peers(): Promise<RemotePeer[]>
  get_requests(session_id: number): Promise<ShareRequest[]>
  respond_to_request(request_id: number, response: string): Promise<void>

  // Thumbnails & Config
  get_thumbnail_url(thumb_path: string): Promise<string>
  get_app_config(): Promise<AppConfig>
  set_app_config(key: string, value: string | number | boolean): Promise<void>

  // File dialogs
  select_folders(): Promise<string[]>
}

// Extend Window with pywebview
declare global {
  interface Window {
    pywebview?: {
      api: PyWebViewAPI
    }
  }
}
