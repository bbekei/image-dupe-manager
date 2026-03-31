/**
 * helpers/flow-parser.ts — YAML flow definition parser.
 *
 * Phase 4: Reads YAML flow files and returns typed step arrays.
 *
 * Guardrail: Flow YAML is not code. If a scenario needs conditional logic,
 * it belongs in a proper spec file, not YAML.
 */

import fs from 'fs'
import path from 'path'

// ── Types ───────────────────────────────────────────────────────────────────

export type FlowMode = 'smoke' | 'long-running'

export interface ScanStep {
  action: 'scan'
  folders: string[]
  session_name: string
  enable_similarity?: boolean
  expect?: {
    min_duplicates?: number
    min_files_scanned?: number
    completes_without_hang?: boolean
  }
}

export interface ApplyPresetStep {
  action: 'apply_preset'
  preset: string
}

export interface ExecuteStep {
  action: 'execute'
  expect?: {
    bin_items_min?: number
  }
}

export interface ViewDuplicatesStep {
  action: 'view_duplicates'
}

export interface ViewSimilarityStep {
  action: 'view_similarity'
}

export interface RestoreAllStep {
  action: 'restore_all'
}

export interface VerifySettingsStep {
  action: 'verify_settings'
  expect: Record<string, unknown>
}

export type FlowStep = ScanStep | ApplyPresetStep | ExecuteStep | ViewDuplicatesStep | ViewSimilarityStep | RestoreAllStep | VerifySettingsStep

export interface FlowDefinition {
  name: string
  mode: FlowMode
  timeout: number
  steps: FlowStep[]
  filePath: string
}

// ── Simple YAML parser (avoids adding js-yaml dependency) ───────────────────

function parseSimpleYaml(content: string): Record<string, unknown> {
  // Minimal YAML parser for flow definitions.
  // Supports: scalars, lists, nested objects (2-level indentation).
  // Does NOT support: anchors, aliases, multi-line strings, flow syntax.
  const result: Record<string, unknown> = {}
  const lines = content.split('\n')
  let currentKey = ''
  let currentList: unknown[] | null = null
  let currentObj: Record<string, unknown> | null = null
  let inSteps = false
  let currentStep: Record<string, unknown> | null = null
  let currentExpect: Record<string, unknown> | null = null
  const steps: Record<string, unknown>[] = []

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, '')

    // Skip comments and blank lines
    if (line.trim().startsWith('#') || line.trim() === '') continue

    const indent = line.length - line.trimStart().length
    const trimmed = line.trim()

    if (indent === 0 && trimmed.includes(':')) {
      // Top-level key
      const colonIdx = trimmed.indexOf(':')
      const key = trimmed.slice(0, colonIdx).trim()
      const value = trimmed.slice(colonIdx + 1).trim()

      if (key === 'steps') {
        inSteps = true
        currentKey = key
        continue
      }

      inSteps = false
      currentKey = key

      if (value.startsWith('"') && value.endsWith('"')) {
        result[key] = value.slice(1, -1)
      } else if (value === 'true') {
        result[key] = true
      } else if (value === 'false') {
        result[key] = false
      } else if (value !== '' && !isNaN(Number(value))) {
        result[key] = Number(value)
      } else if (value !== '') {
        result[key] = value
      }
    } else if (inSteps && indent === 2 && trimmed.startsWith('- action:')) {
      // New step
      if (currentStep) {
        if (currentExpect) {
          currentStep.expect = currentExpect
          currentExpect = null
        }
        steps.push(currentStep)
      }
      const action = trimmed.replace('- action:', '').trim()
      currentStep = { action }
    } else if (inSteps && currentStep && indent === 4) {
      if (trimmed.startsWith('- ')) {
        // List item within a step field
        const listVal = trimmed.slice(2).trim().replace(/^"(.*)"$/, '$1')
        const lastKey = Object.keys(currentStep).pop()!
        if (!Array.isArray(currentStep[lastKey])) {
          currentStep[lastKey] = []
        }
        ;(currentStep[lastKey] as unknown[]).push(listVal)
      } else if (trimmed.includes(':')) {
        const colonIdx = trimmed.indexOf(':')
        const key = trimmed.slice(0, colonIdx).trim()
        const value = trimmed.slice(colonIdx + 1).trim()

        if (key === 'expect') {
          currentExpect = {}
        } else if (key === 'folders') {
          currentStep[key] = []
        } else {
          currentStep[key] = parseValue(value)
        }
      }
    } else if (inSteps && currentExpect && indent === 6) {
      if (trimmed.includes(':')) {
        const colonIdx = trimmed.indexOf(':')
        const key = trimmed.slice(0, colonIdx).trim()
        const value = trimmed.slice(colonIdx + 1).trim()
        currentExpect[key] = parseValue(value)
      }
    } else if (inSteps && currentStep && indent === 6 && trimmed.startsWith('- ')) {
      // Nested list (e.g., folders)
      const listVal = trimmed.slice(2).trim().replace(/^"(.*)"$/, '$1')
      const lastArrayKey = Object.keys(currentStep).filter(
        k => Array.isArray(currentStep![k])
      ).pop()
      if (lastArrayKey) {
        ;(currentStep[lastArrayKey] as unknown[]).push(listVal)
      }
    }
  }

  // Push last step
  if (currentStep) {
    if (currentExpect) {
      currentStep.expect = currentExpect
    }
    steps.push(currentStep)
  }

  if (steps.length > 0) {
    result.steps = steps
  }

  return result
}

function parseValue(value: string): unknown {
  if (value.startsWith('"') && value.endsWith('"')) return value.slice(1, -1)
  if (value === 'true') return true
  if (value === 'false') return false
  if (value !== '' && !isNaN(Number(value))) return Number(value)
  return value
}

// ── Public API ──────────────────────────────────────────────────────────────

export function parseFlowFile(filePath: string): FlowDefinition {
  const content = fs.readFileSync(filePath, 'utf-8')
  const raw = parseSimpleYaml(content)

  if (!raw.name || typeof raw.name !== 'string') {
    throw new Error(`Flow ${filePath}: missing or invalid 'name'`)
  }
  if (!raw.mode || (raw.mode !== 'smoke' && raw.mode !== 'long-running')) {
    throw new Error(`Flow ${filePath}: mode must be 'smoke' or 'long-running'`)
  }
  if (!raw.steps || !Array.isArray(raw.steps) || raw.steps.length === 0) {
    throw new Error(`Flow ${filePath}: must have at least one step`)
  }

  return {
    name: raw.name as string,
    mode: raw.mode as FlowMode,
    timeout: (raw.timeout as number) ?? 120000,
    steps: raw.steps as FlowStep[],
    filePath,
  }
}

export function loadFlows(flowsDir: string, filter?: { mode?: FlowMode; file?: string }): FlowDefinition[] {
  if (filter?.file) {
    const filePath = path.resolve(flowsDir, filter.file)
    return [parseFlowFile(filePath)]
  }

  if (!fs.existsSync(flowsDir)) return []

  const files = fs.readdirSync(flowsDir).filter(f => f.endsWith('.yaml') || f.endsWith('.yml'))
  const flows = files.map(f => parseFlowFile(path.join(flowsDir, f)))

  if (filter?.mode) {
    return flows.filter(f => f.mode === filter.mode)
  }

  return flows
}
