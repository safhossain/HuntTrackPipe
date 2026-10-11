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
