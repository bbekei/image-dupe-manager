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
  thumbnail_data?: string
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

// -- Migration --

export interface BreakingChange {
  version: number
  description: string
  reason_key: string
}

export interface MigrationStatus {
  needed: boolean
  from_version: number
  to_version: number
  breaking_changes: BreakingChange[]
  backup_path: string
  app_version: string
}

export interface MigrationConfirmResult {
  ok: boolean
  error?: string
  validation_errors?: string[]
}

// -- Backend API surface --

export interface ScanProgress {
  phase: string
  current: number
  total: number
  discovered: number
  duplicates: number
  message: string
}
