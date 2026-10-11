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

async function raw(path: string, init?: RequestInit, json = true): Promise<Response> {
  const res = await fetch(`/api${path}`, {
    ...(json ? { headers: { 'Content-Type': 'application/json' } } : {}),
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
  return res
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await raw(path, init)).json()) as T
}

/** multipart POST; FormData sets its own Content-Type boundary. */
async function upload<T>(path: string, form: FormData): Promise<T> {
  return (await (await raw(path, { method: 'POST', body: form }, false)).json()) as T
}

/** Trigger a browser download of a binary response. */
export async function downloadResponse(res: Response, fallbackName: string): Promise<string> {
  const cd = res.headers.get('Content-Disposition') ?? ''
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd)
  const name = m ? decodeURIComponent(m[1] ?? m[2] ?? fallbackName) : fallbackName
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
  return name
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
  upload_modes: string[]
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

export interface InputFile {
  index: number
  file: string
  doc_type: string | null
  original: string
  size: number | null
  pages: number | null
  added_at: string
}

export interface FinalFile {
  file: string
  doc_type: string
  from: number | null
  at: string
}

export interface CombinedFile {
  file: string
  from_indices: number[]
  pages: number | null
  at: string
}

export interface Files {
  inputs: InputFile[]
  finals: FinalFile[]
  combined: CombinedFile | null
}

export interface FilesView {
  files: Files
  upload_mode: string
  upload_mode_source: string
  required_docs: string[]
  untracked: string[]
  missing: string[]
  x: string
  candidate: string
  tools: { soffice: string | null; pdf2docx: boolean; targets: string[] }
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
  files: Files
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

  // ---- files ----
  files: (folder: string) => request<FilesView>(filesPath(folder)),
  uploadFiles: (folder: string, files: File[]) => {
    const form = new FormData()
    for (const f of files) form.append('files', f, f.name)
    return upload<FilesView>(filesPath(folder), form)
  },
  adoptFile: (folder: string, name: string) =>
    request<FilesView>(`${filesPath(folder)}/adopt`, { method: 'POST', body: JSON.stringify({ name }) }),
  reorderFiles: (folder: string, order: number[]) =>
    request<FilesView>(`${filesPath(folder)}/order`, { method: 'PUT', body: JSON.stringify({ order }) }),
  setUploadMode: (folder: string, upload_mode: string) =>
    request<FilesView>(`${filesPath(folder)}/upload-mode`, { method: 'PUT', body: JSON.stringify({ upload_mode }) }),
  setDocType: (folder: string, index: number, doc_type: string | null) =>
    request<FilesView>(`${filesPath(folder)}/${index}`, { method: 'PUT', body: JSON.stringify({ doc_type }) }),
  deleteInput: (folder: string, index: number) => request<FilesView>(`${filesPath(folder)}/${index}`, { method: 'DELETE' }),
  convertInput: (folder: string, index: number, target: string) =>
    request<FilesView>(`${filesPath(folder)}/${index}/convert`, { method: 'POST', body: JSON.stringify({ target }) }),
  makeFinals: (folder: string, indices: number[] | null) =>
    request<FilesView>(`${filesPath(folder)}/final`, { method: 'POST', body: JSON.stringify({ indices }) }),
  combine: (folder: string, indices: number[] | null) =>
    request<FilesView>(`${filesPath(folder)}/combine`, { method: 'POST', body: JSON.stringify({ indices }) }),
  deleteOutput: (folder: string, name: string) =>
    request<FilesView>(`${filesPath(folder)}/output/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  // Absolute URLs for <img src> / <a href> (not routed through request()).
  thumbUrl: (folder: string, name: string, stamp?: string | number) =>
    `/api${filesPath(folder)}/thumb/${encodeURIComponent(name)}${stamp !== undefined ? `?v=${encodeURIComponent(String(stamp))}` : ''}`,
  downloadUrl: (folder: string, name: string, inline = false) =>
    `/api${filesPath(folder)}/download/${encodeURIComponent(name)}${inline ? '?inline=true' : ''}`,

  // ---- standalone converter ----
  tools: () => request<{ soffice: string | null; pdf2docx: boolean; targets: string[] }>('/files/tools'),
  convertFile: async (file: File, target: string) => {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('target', target)
    return raw('/files/convert', { method: 'POST', body: form }, false)
  },
}

function filesPath(folder: string) {
  return `/sessions/${encodeURIComponent(folder)}/files`
}
