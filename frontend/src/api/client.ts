// Typed fetch wrapper for the HuntTrackPipe API (proxied at /api).

export class ApiError extends Error {
  status: number
  type?: string
  constructor(status: number, detail: string, type?: string) {
    super(detail)
    this.status = status
    this.type = type
  }
  get isLocked() {
    return this.status === 423
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    let type: string | undefined
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
      type = body.type
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail, type)
  }
  return (await res.json()) as T
}

export async function waitForApi(maxMs = 90_000): Promise<void> {
  const start = Date.now()
  let delay = 300
  while (Date.now() - start < maxMs) {
    try {
      await request<{ ok: boolean }>('/health')
      return
    } catch {
      await new Promise((r) => setTimeout(r, delay))
      delay = Math.min(delay * 1.5, 3000)
    }
  }
  throw new Error('API did not come up in time')
}

// ---- types (mirror backend/api/models.py + sessions/models.py) ----
export type RowValue = string | number | null
export type Row = Record<string, RowValue>

export interface Meta {
  extracted_columns: string[]
  manual_columns: string[]
  engine_columns: string[]
  date_columns: string[]
  options: Record<string, string[]>
  doc_types: string[]
}

export interface SettingsView {
  config: Record<string, unknown>
  paths: Record<string, string>
  keys: Record<string, boolean>
  tracker_exists: boolean
  candidate_context_exists: boolean
}

export interface NoulAnswer { type: 'noul'; noul: number }
export interface ChoiceAnswer { type: 'choice'; choice: string; confidence?: number; probabilities?: Record<string, number> }
export type JevAnswer = NoulAnswer | ChoiceAnswer | { type: string; [k: string]: unknown }

export interface JevDerived {
  schema_fields: string[]
  direct_values: Record<string, string>
  low_confidence_choices: string[]
  upload_mode: string
  upload_mode_confidence: number | null
  required_docs: string[]
  is_job_posting: number | null
  warnings: string[]
}

export interface JevRecord {
  model: string
  at: string
  answers: Record<string, JevAnswer>
  usage: Record<string, unknown>
  derived: JevDerived
}

export interface LLMRecord {
  model: string
  at: string
  schema: Record<string, unknown>
  output: Record<string, unknown>
  usage: Record<string, unknown>
}

export interface ExtractResponse {
  jev: JevRecord | null
  llm: LLMRecord | null
  derived: JevDerived
  values: Row
  warnings: string[]
}

export interface WriteReport {
  row: number
  created: boolean
  written: Row
  skipped: Record<string, [RowValue, RowValue]>
}

export interface Session {
  schema_version: number
  session_id: string
  created_at: string
  folder: string
  posting: { text: string; url: string | null }
  jev: JevRecord | null
  llm: LLMRecord | null
  review: { values: Row; written_at: string | null; pending_write: { values: Row; force_columns: string[] } | null }
  upload_mode: string
  upload_mode_source: string
  files: unknown
  qa: { questions: unknown[] }
}

export interface SessionSummary {
  folder: string
  created_at: string
  upload_mode: string
  pending_write: boolean
  row: Row | null
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  unmanaged: string[]
  tracker_error: string | null
}

export interface SessionDetail {
  session: Session
  row: Row | null
  row_error: string | null
}

export const api = {
  meta: () => request<Meta>('/meta'),
  settings: () => request<SettingsView>('/settings'),
  extract: (posting_text: string, use_jev: boolean, use_llm: boolean) =>
    request<ExtractResponse>('/extract', { method: 'POST', body: JSON.stringify({ posting_text, use_jev, use_llm }) }),
  sessions: () => request<SessionListResponse>('/sessions'),
  session: (folder: string) => request<SessionDetail>(`/sessions/${encodeURIComponent(folder)}`),
  createSession: (body: { posting_text: string; posting_url: string | null; extraction: ExtractResponse; manual: Row }) =>
    request<{ session: Session; report: WriteReport }>('/sessions', { method: 'POST', body: JSON.stringify(body) }),
  writeRow: (folder: string, values: Row, force_columns: string[]) =>
    request<{ report: WriteReport; row: Row | null }>(`/sessions/${encodeURIComponent(folder)}/row`, {
      method: 'PUT',
      body: JSON.stringify({ values, force_columns }),
    }),
  retryRow: (folder: string) =>
    request<{ report: WriteReport; row: Row | null }>(`/sessions/${encodeURIComponent(folder)}/row/retry`, { method: 'POST' }),
}
