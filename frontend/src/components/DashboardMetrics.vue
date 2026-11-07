<script setup lang="ts">
import { computed } from 'vue'
import type { SessionSummary } from '../api/client'
import { outcomeColorBuckets } from '../applicationColors'

const props = defineProps<{ sessions: SessionSummary[] }>()

const PALETTE = ['#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#64748b', '#ec4899', '#14b8a6']

const STATUS_COLOR: Record<string, string> = {
  'Not Applied': '#94a3b8',
  Applied: '#3b82f6',
  'Recruiter-Screening': '#6366f1',
  'Technical Interview': '#8b5cf6',
  'Final Round': '#d946ef',
}

interface Bucket { key?: string; label: string; n: number; color: string }
interface Slice extends Bucket { d: string; full: boolean }

function cell(s: SessionSummary, col: string): string {
  const v = s.row?.[col]
  return v === null || v === undefined || String(v).trim() === '' ? 'Not set' : String(v).trim()
}

/** Split multi-location free text for metrics only. Keeps "Toronto, ON" intact (no bare commas). */
function splitLocations(raw: string): string[] {
  const text = raw.trim()
  if (!text || text === 'Not set') return ['Not set']
  const parts = text
    .split(/\s*(?:;|\||\/|\s+and\s+|\s+or\s+|\s+&\s+)\s*/i)
    .map((p) => p.trim())
    .filter(Boolean)
  // De-dupe within one cell so "Toronto; Toronto" counts once for that application.
  return [...new Set(parts.length ? parts : [text])]
}

/** Subrole_Categories is stored as "A, B, C". */
function splitCategories(raw: string): string[] {
  const text = raw.trim()
  if (!text || text === 'Not set') return ['Not set']
  const parts = text.split(',').map((p) => p.trim()).filter(Boolean)
  return [...new Set(parts.length ? parts : [text])]
}

function appliedIso(s: SessionSummary): string | null {
  const v = s.row?.Applied_Date
  if (v === null || v === undefined || String(v).trim() === '') return null
  const iso = String(v).slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso : null
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

/** Like tally, but each application can contribute multiple labels (location lists). */
function tallyMulti(pick: (s: SessionSummary) => string[], colors?: Record<string, string>): Bucket[] {
  const map = new Map<string, number>()
  for (const s of props.sessions) {
    for (const key of pick(s)) {
      map.set(key, (map.get(key) ?? 0) + 1)
    }
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
const byOutcome = computed(() => outcomeColorBuckets(props.sessions.map((s) => s.row)))
const byStatus = computed(() => tally((s) => cell(s, 'Application_Status'), STATUS_COLOR))
const byWorkMode = computed(() => tally((s) => cell(s, 'Work_Mode')))
const byCountry = computed(() => tallyMulti((s) => splitLocations(cell(s, 'Location_Country'))))
const byCity = computed(() => tallyMulti((s) => splitLocations(cell(s, 'Location_City'))))
const byRoleCategory = computed(() => tally((s) => cell(s, 'Role_Category')))
const bySubrole = computed(() => tallyMulti((s) => splitCategories(cell(s, 'Subrole_Categories'))))
const byEmploymentType = computed(() => tally((s) => cell(s, 'Employment_Type')))
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

/** Sent = has Applied_Date. Avg = sent / inclusive calendar span of first→last Applied_Date. */
const sentStats = computed(() => {
  const byDate = new Map<string, number>()
  const byOrg = new Map<string, number>()
  const dates: string[] = []
  for (const s of props.sessions) {
    const d = appliedIso(s)
    if (!d) continue
    dates.push(d)
    byDate.set(d, (byDate.get(d) ?? 0) + 1)
    const org = cell(s, 'Organization')
    if (org !== 'Not set') byOrg.set(org, (byOrg.get(org) ?? 0) + 1)
  }
  if (!dates.length) return null
  dates.sort()
  const first = dates[0]!
  const last = dates[dates.length - 1]!
  const spanDays = Math.round((Date.parse(last + 'T00:00:00') - Date.parse(first + 'T00:00:00')) / 86_400_000) + 1
  let peakDate = first
  let peakN = 0
  for (const [d, n] of byDate) {
    if (n > peakN || (n === peakN && d < peakDate)) {
      peakDate = d
      peakN = n
    }
  }
  const topOrgs = [...byOrg.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([label, n]) => ({ label, n }))
  return {
    sent: dates.length,
    avgPerDay: dates.length / Math.max(1, spanDays),
    spanDays,
    peakDate,
    peakN,
    topOrgs,
  }
})

const outcomeSlices = computed(() => slices(byOutcome.value))
const workSlices = computed(() => slices(byWorkMode.value))
const countrySlices = computed(() => slices(byCountry.value))
const citySlices = computed(() => slices(byCity.value))
const roleCategorySlices = computed(() => slices(byRoleCategory.value))
const subroleSlices = computed(() => slices(bySubrole.value))
const employmentSlices = computed(() => slices(byEmploymentType.value))
const countryCount = computed(() => byCountry.value.filter((b) => b.label !== 'Not set').length)
const cityCount = computed(() => byCity.value.filter((b) => b.label !== 'Not set').length)
const roleCategoryCount = computed(() => byRoleCategory.value.filter((b) => b.label !== 'Not set').length)
const subroleCount = computed(() => bySubrole.value.filter((b) => b.label !== 'Not set').length)
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
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Outcomes grouped by dashboard row color">
            <template v-for="s in outcomeSlices" :key="s.key">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" stroke="var(--color-slate-300)" stroke-width="0.5">
                <title>{{ s.label }}: {{ s.n }}</title>
              </circle>
              <path v-else :d="s.d" :fill="s.color" stroke="var(--color-slate-300)" stroke-width="0.5">
                <title>{{ s.label }}: {{ s.n }}</title>
              </path>
            </template>
          </svg>
          <ul class="min-w-0 space-y-1 text-xs">
            <li v-for="s in byOutcome" :key="s.key" class="flex items-start gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-inset ring-slate-300" :style="{ background: s.color }" />
              <span class="min-w-0 break-words" :title="s.label">{{ s.label }}</span>
              <span class="shrink-0 tabular-nums text-slate-500">{{ s.n }}</span>
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

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Location country</h3>
        <p class="mb-2 text-[11px] text-slate-400">
          {{ countryCount }} countr{{ countryCount === 1 ? 'y' : 'ies' }} identified
        </p>
        <p v-if="!byCountry.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Location country pie chart">
            <template v-for="s in countrySlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="max-h-36 min-w-0 space-y-1 overflow-y-auto text-xs">
            <li v-for="s in byCountry" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate" :title="s.label">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Location city</h3>
        <p class="mb-2 text-[11px] text-slate-400">
          {{ cityCount }} cit{{ cityCount === 1 ? 'y' : 'ies' }} identified
        </p>
        <p v-if="!byCity.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Location city pie chart">
            <template v-for="s in citySlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="max-h-36 min-w-0 space-y-1 overflow-y-auto text-xs">
            <li v-for="s in byCity" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate" :title="s.label">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Role category</h3>
        <p class="mb-2 text-[11px] text-slate-400">
          {{ roleCategoryCount }} categor{{ roleCategoryCount === 1 ? 'y' : 'ies' }} identified
        </p>
        <p v-if="!byRoleCategory.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Role category pie chart">
            <template v-for="s in roleCategorySlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="max-h-36 min-w-0 space-y-1 overflow-y-auto text-xs">
            <li v-for="s in byRoleCategory" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate" :title="s.label">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Subrole categories</h3>
        <p class="mb-2 text-[11px] text-slate-400">
          {{ subroleCount }} categor{{ subroleCount === 1 ? 'y' : 'ies' }} identified
        </p>
        <p v-if="!bySubrole.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Subrole categories pie chart">
            <template v-for="s in subroleSlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="max-h-36 min-w-0 space-y-1 overflow-y-auto text-xs">
            <li v-for="s in bySubrole" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate" :title="s.label">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
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

      <div class="card">
        <h3 class="mb-2 text-sm font-semibold">Employment type</h3>
        <p v-if="!byEmploymentType.length" class="text-sm text-slate-500">No applications yet.</p>
        <div v-else class="flex items-center gap-4">
          <svg viewBox="0 0 100 100" class="h-28 w-28 shrink-0" role="img" aria-label="Employment type pie chart">
            <template v-for="s in employmentSlices" :key="s.label">
              <circle v-if="s.full" cx="50" cy="50" r="42" :fill="s.color" />
              <path v-else :d="s.d" :fill="s.color" />
            </template>
          </svg>
          <ul class="max-h-36 min-w-0 space-y-1 overflow-y-auto text-xs">
            <li v-for="s in byEmploymentType" :key="s.label" class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: s.color }" />
              <span class="truncate" :title="s.label">{{ s.label }}</span>
              <span class="tabular-nums text-slate-500">{{ s.n }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="card sm:col-span-2">
        <h3 class="mb-2 text-sm font-semibold">Status</h3>
        <div v-if="sentStats" class="mb-3 grid gap-2 sm:grid-cols-3 text-xs">
          <div class="rounded-md bg-slate-50 px-2.5 py-2">
            <p class="text-[11px] uppercase tracking-wide text-slate-500">Avg applications / day</p>
            <p class="mt-0.5 text-lg font-semibold tabular-nums text-indigo-700">{{ sentStats.avgPerDay.toFixed(2) }}</p>
            <p class="text-[11px] text-slate-400">{{ sentStats.sent }} with Applied_Date · {{ sentStats.spanDays }} day span</p>
          </div>
          <div class="rounded-md bg-slate-50 px-2.5 py-2">
            <p class="text-[11px] uppercase tracking-wide text-slate-500">Busiest apply day</p>
            <p class="mt-0.5 text-lg font-semibold tabular-nums text-indigo-700">{{ sentStats.peakDate }}</p>
            <p class="text-[11px] text-slate-400">{{ sentStats.peakN }} application{{ sentStats.peakN === 1 ? '' : 's' }}</p>
          </div>
          <div class="rounded-md bg-slate-50 px-2.5 py-2">
            <p class="text-[11px] uppercase tracking-wide text-slate-500">Top organizations</p>
            <ul v-if="sentStats.topOrgs.length" class="mt-1 space-y-0.5">
              <li v-for="o in sentStats.topOrgs" :key="o.label" class="flex items-baseline justify-between gap-2">
                <span class="min-w-0 truncate font-medium" :title="o.label">{{ o.label }}</span>
                <span class="shrink-0 tabular-nums text-slate-500">{{ o.n }}</span>
              </li>
            </ul>
            <p v-else class="mt-1 text-slate-400">None yet</p>
          </div>
        </div>
        <p v-else class="mb-3 text-xs text-slate-400">No Applied_Date values yet — apply-day stats appear once you set them.</p>
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
