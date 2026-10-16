import { ApiError } from './api/client'

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.isLocked) return `Excel has the tracker open. Close it and retry. (${e.message})`
    return e.message
  }
  return e instanceof Error ? e.message : String(e)
}

export function daysSince(iso: string | number | null | undefined): number | null {
  if (!iso || typeof iso !== 'string') return null
  const d = new Date(iso.slice(0, 10) + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((today.getTime() - d.getTime()) / 86_400_000)
}

export function todayIso(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function fmtDate(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return ''
  return typeof v === 'string' ? v.slice(0, 10) : String(v)
}

export function pct(p: number | null | undefined): string {
  return p === null || p === undefined ? '-' : `${Math.round(p * 100)}%`
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

/** Trim a pasted posting: drop leading tabs, collapse blank gaps, join wrapped lines, keep paragraph breaks. */
export function cleanPostingText(raw: string): string {
  const lines = raw
    .replace(/\u00a0/g, ' ')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map((line) => line.replace(/^\t+/, '').trim())
  const collapsed = lines.join('\n').replace(/\n{3,}/g, '\n\n').trim()
  // A single line break is a wrap; a blank line is a paragraph.
  const unwrapped = collapsed.replace(/([^\n])\n(?!\n)/g, '$1 ')
  return unwrapped
    .split('\n')
    .map((line) => line.replace(/[^\S\n]+/g, ' ').trim())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export const UPLOAD_MODE_LABELS: Record<string, string> = {
  single_document: 'Single document',
  separate_uploads: 'Separate uploads',
  single_combined_file: 'One combined file',
  not_stated: 'Not stated',
}
