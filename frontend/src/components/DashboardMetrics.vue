<script setup lang="ts">
import { computed } from 'vue'
import type { SessionSummary } from '../api/client'

const props = defineProps<{ sessions: SessionSummary[] }>()

const PALETTE = ['#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#64748b', '#ec4899', '#14b8a6']

const OUTCOME_COLOR: Record<string, string> = {
  Pending: '#94a3b8',
  Withdrawn: '#64748b',
  Rejected: '#ef4444',
  Offer: '#10b981',
  Accepted: '#047857',
}
const STATUS_COLOR: Record<string, string> = {
  'Not Applied': '#94a3b8',
  Applied: '#3b82f6',
  'Recruiter-Screening': '#6366f1',
  'Technical Interview': '#8b5cf6',
  'Final Round': '#d946ef',
}

interface Bucket { label: string; n: number; color: string }
interface Slice extends Bucket { d: string; full: boolean }

function cell(s: SessionSummary, col: string): string {
  const v = s.row?.[col]
  return v === null || v === undefined || String(v).trim() === '' ? 'Not set' : String(v).trim()
}

function tally(pick: (s: SessionSummary) => string, colors?: Record<string, string>): Bucket[] {
  const map = new Map<string, number>()
  for (const s of props.sessions) {
    const key = pick(s)
    map.set(key, (map.get(key) ?? 0) + 1)
  }
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([label, n], i) => ({ label, n, color: colors?.[label] ?? PALETTE[i % PALETTE.length] }))
}

function arc(cx: number, cy: number, r: number, start: number, end: number): string {
  const pt = (a: number) => {
    const rad = ((a - 90) * Math.PI) / 180
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)]
  }
  const [x1, y1] = pt(start)
  const [x2, y2] = pt(end)
  const large = end - start > 180 ? 1 : 0
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`
}

function slices(items: Bucket[]): Slice[] {
  const sum = items.reduce((n, i) => n + i.n, 0)
  if (!sum) return []
  let angle = 0
  return items.filter((i) => i.n > 0).map((it) => {
    const sweep = (it.n / sum) * 360
    const full = sweep >= 359.99
    const d = full ? '' : arc(50, 50, 42, angle, angle + sweep)
    angle += sweep
    return { ...it, d, full }
  })
}

function barWidth(items: Bucket[], n: number): string {
  const max = Math.max(1, ...items.map((i) => i.n))
  return `${Math.round((n / max) * 100)}%`
}

const total = computed(() => props.sessions.length)
const byOutcome = computed(() => tally((s) => cell(s, 'Outcome'), OUTCOME_COLOR))
const byStatus = computed(() => tally((s) => cell(s, 'Application_Status'), STATUS_COLOR))
const byWorkMode = computed(() => tally((s) => cell(s, 'Work_Mode')))
const byChannel = computed(() => tally((s) => cell(s, 'Applied_Through')))
const byMonth = computed(() => {
  const map = new Map<string, number>()
  for (const s of props.sessions) {
    const key = (s.created_at || '').slice(0, 7) || 'Unknown'
    map.set(key, (map.get(key) ?? 0) + 1)
  }
  return [...map.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([label, n], i) => ({ label, n, color: PALETTE[i % PALETTE.length] }))
})

const outcomeSlices = computed(() => slices(byOutcome.value))
const workSlices = computed(() => slices(byWorkMode.value))
</script>

<template>
  <section class="space-y-3">
    <h2 class="text-lg font-semibold">Metrics</h2>
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div class="card flex flex-col justify-center">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-500">Total applications</p>
        <p class="mt-1 text-4xl font-semibold tabular-nums text-indigo-700">{{ total }}</p>
        <p class="mt-1 text-xs text-slate-500">Managed sessions</p>
      </div>

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Outcome</h3>
        <p v-if="!byOutcome.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Outcome pie chart">
            <template v-for="s in outcomeSlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="min-w-0 space-y-1 text-xs">
            <li v-for="s in byOutcome" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Work mode</h3>
        <p v-if="!byWorkMode.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Work mode pie chart">
            <template v-for="s in workSlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="min-w-0 space-y-1 text-xs">
            <li v-for="s in byWorkMode" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card sm:col-span-2">
        <h3 class="mb-2 text-sm font-semibold">Status</h3>
        <p v-if="!byStatus.length" class="text-sm text-slate-500">No applications yet.</p>
        <ul v-else class="space-y-1.5">
          <li v-for="s in byStatus" :key="s.label" class="flex items-center gap-2 text-xs">
            <span class="w-40 shrink-0 truncate" :title="s.label">{{ s.label }}</span>
            <span class="h-3 flex-1 overflow-hidden rounded bg-slate-100">
              <span class="block h-3 rounded" :style="{ width: barWidth(byStatus, s.n), background: s.color }" />
            </span>
            <span class="w-6 text-right tabular-nums text-slate-500">{{ s.n }}</span>
          </li>
        </ul>
      </div>

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Applied through</h3>
        <p v-if="!byChannel.length" class="text-sm text-slate-500">No applications yet.</p>
        <ul v-else class="space-y-1.5">
          <li v-for="s in byChannel" :key="s.label" class="flex items-center gap-2 text-xs">
            <span class="w-24 shrink-0 truncate" :title="s.label">{{ s.label }}</span>
            <span class="h-3 flex-1 overflow-hidden rounded bg-slate-100">
              <span class="block h-3 rounded" :style="{ width: barWidth(byChannel, s.n), background: s.color }" />
            </span>
            <span class="w-6 text-right tabular-nums text-slate-500">{{ s.n }}</span>
          </li>
        </ul>
      </div>

      <div class="card lg:col-span-3">
        <h3 class="mb-2 text-sm font-semibold">Created by month</h3>
        <p v-if="!byMonth.length" class="text-sm text-slate-500">No applications yet.</p>
        <ul v-else class="space-y-1.5">
          <li v-for="s in byMonth" :key="s.label" class="flex items-center gap-2 text-xs">
            <span class="w-24 shrink-0 truncate">{{ s.label }}</span>
            <span class="h-3 flex-1 overflow-hidden rounded bg-slate-100">
              <span class="block h-3 rounded" :style="{ width: barWidth(byMonth, s.n), background: s.color }" />
            </span>
            <span class="w-6 text-right tabular-nums text-slate-500">{{ s.n }}</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
