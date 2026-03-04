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
}

export interface DuplicateGroup {
  pixel_hash: string
  hash_algorithm: string
  file_count: number
  files: FileInfo[]
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

export interface SimilarityGroup {
  id: number
  session_id: number
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

export interface PyWebViewAPI {
  // Scan & Session
  start_scan(folders: string[], session_name: string, enable_similarity: boolean): Promise<number>
  pause_scan(): Promise<void>
  resume_scan(session_id: number): Promise<void>
  stop_scan(): Promise<void>
  get_sessions(): Promise<Session[]>
  get_scan_summary(session_id: number): Promise<ScanSummary>

  // Duplicate Groups
  get_duplicate_groups(session_id: number, offset: number, limit: number, filters?: FilterCriteria): Promise<DuplicateGroup[]>
  get_group_detail(session_id: number, pixel_hash: string): Promise<FileInfo[]>
  set_file_action(file_id: number, action: FileAction, scope: ActionScope): Promise<void>
  apply_selection_preset(session_id: number, preset: SelectionPreset, group_ids?: string[]): Promise<{ keep_count: number; delete_count: number }>
  get_plan_summary(session_id: number): Promise<PlanSummary>
  execute_plan(session_id: number): Promise<void>
  clear_all_actions(session_id: number): Promise<void>

  // Similarity
  get_similarity_groups(session_id: number, threshold?: number): Promise<SimilarityGroup[]>
  apply_similarity_preset(session_id: number, preset: SelectionPreset, group_ids?: number[]): Promise<{ keep_count: number; delete_count: number }>
  recommend_keeper(files: FileInfo[]): Promise<KeeperRecommendation>

  // Bin
  get_bin_items(session_id: number): Promise<BinItem[]>
  restore_from_bin(soft_delete_id: number): Promise<void>
  permanent_delete(soft_delete_ids: number[]): Promise<void>
  purge_expired(): Promise<number>

  // Family Sharing
  export_hashes(session_id: number): Promise<string>
  import_hashes(file_path: string): Promise<{ imported: number; treasures: number }>
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
