<script setup lang="ts">
// Floating right-side dock for Application_Status / Applied_Through / Found_From
// dropdown sync. Minimized = sync icon only; maximized = per-column diffs.
import { computed, ref } from 'vue'
import { api, type DropdownColumnDiff } from '../api/client'
import { useAppStore } from '../stores/app'
import { errorText } from '../utils'
import excelOk from '../img/excel-icon-green.png'

const EDITABLE = ['Application_Status', 'Applied_Through', 'Found_From'] as const
const app = useAppStore()
const syncing = ref(false)
const expanded = ref(false) // always start minimized

/** locked → grey (disabled); differs → yellow; in sync → blue (still clickable). */
const syncTone = computed<'locked' | 'differs' | 'ok'>(() => {
  if (app.trackerLocked || app.trackerStatus?.dropdown_sync.status === 'locked') return 'locked'
  if (app.suggestSync || app.trackerStatus?.dropdown_sync.status === 'mismatched') return 'differs'
  return 'ok'
})

const syncEnabled = computed(() => syncTone.value !== 'locked' && !syncing.value)

const statusLine = computed(() => {
  if (syncTone.value === 'locked') return 'Tracker open in Excel — sync unavailable'
  const s = app.trackerStatus?.dropdown_sync.status
  if (s === 'in_sync') return 'Dropdowns match Excel'
  if (s === 'mismatched') return 'HTP and Excel dropdowns differ'
  if (s === 'missing') return 'Tracker file missing'
  if (s === 'error') return app.trackerStatus?.dropdown_sync.detail || 'Could not read Excel dropdowns'
  return 'Checking dropdown sync…'
})

type ColDiffView = {
  column: string
  label: string
  excelMissing: boolean
  onlyHtp: string[]
  onlyExcel: string[]
  orderOnly: boolean
  htp: string[]
  excel: string[] | null
}

function labelFor(col: string) {
  return col.replace(/_/g, ' ')
}

function diffColumn(c: DropdownColumnDiff): ColDiffView {
  const htp = c.htp ?? []
  const excel = c.excel
  if (excel == null) {
    return {
      column: c.column,
      label: labelFor(c.column),
      excelMissing: true,
      onlyHtp: htp,
      onlyExcel: [],
      orderOnly: false,
      htp,
      excel,
    }
  }
  const hSet = new Set(htp)
  const eSet = new Set(excel)
  const onlyHtp = htp.filter((v) => !eSet.has(v))
  const onlyExcel = excel.filter((v) => !hSet.has(v))
  const orderOnly = onlyHtp.length === 0 && onlyExcel.length === 0 && htp.join('\0') !== excel.join('\0')
  return {
    column: c.column,
    label: labelFor(c.column),
    excelMissing: false,
    onlyHtp,
    onlyExcel,
    orderOnly,
    htp,
    excel,
  }
}

const columnDiffs = computed(() => {
  const cols = app.trackerStatus?.dropdown_sync.columns ?? []
  return cols
    .filter((c) => (EDITABLE as readonly string[]).includes(c.column) && c.changed)
    .map(diffColumn)
})

async function syncNow() {
  if (!syncEnabled.value) return
  const hadDiffs = syncTone.value === 'differs'
  syncing.value = true
  try {
    const st = await api.syncOptions()
    app.trackerStatus = st
    app.toast(hadDiffs ? 'Excel dropdowns synced from HTP.' : 'Already in sync with Excel.', 'success')
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
    await app.refreshTrackerStatus(true)
  } finally {
    syncing.value = false
  }
}

function joinList(values: string[]) {
  return values.length ? values.join(', ') : '—'
}
</script>

<template>
  <!-- Numeric widths only (not w-auto) so width+flex neighbor can ease smoothly.
       Chrome stays right-aligned so sync/min-max keep the same screen position. -->
  <aside
    v-if="app.apiReady"
    class="sticky top-4 z-20 flex shrink-0 flex-col overflow-hidden rounded-lg border transition-[width,background-color,border-color,box-shadow] duration-300 ease-in-out"
    :class="expanded
      ? 'w-72 border-slate-200 bg-white shadow-md'
      : 'w-[5.75rem] border-transparent bg-transparent shadow-none'"
    aria-label="Dropdown sync"
  >
    <!-- One colored chrome; two hit targets (sync | min/max). Minimized: chrome only (no white frame). -->
    <div
      class="ml-auto flex w-[5.75rem] overflow-hidden rounded-md transition-[margin] duration-300 ease-in-out"
      :class="[
        expanded ? 'm-1.5' : 'm-0',
        {
          'bg-slate-200 text-slate-400': syncTone === 'locked',
          'bg-amber-400 text-amber-950': syncTone === 'differs',
          'bg-sky-600 text-white': syncTone === 'ok',
          'opacity-70': syncing,
        },
      ]"
    >
      <button
        type="button"
        class="flex h-9 flex-1 items-center justify-center gap-1 px-1 transition"
        :class="{
          'cursor-not-allowed': !syncEnabled,
          'hover:bg-black/10': syncEnabled && syncTone === 'differs',
          'hover:bg-black/15': syncEnabled && syncTone === 'ok',
        }"
        :disabled="!syncEnabled"
        :title="statusLine"
        :aria-label="syncing ? 'Syncing' : 'Sync dropdowns to Excel'"
        @click="syncNow"
      >
        <svg
          class="h-4 w-4 shrink-0"
          :class="syncing ? 'animate-spin' : undefined"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M21 12a9 9 0 0 0-14.5-7.1L4 7" />
          <path d="M4 3v4h4" />
          <path d="M3 12a9 9 0 0 0 14.5 7.1L20 17" />
          <path d="M20 21v-4h-4" />
        </svg>
        <img :src="excelOk" alt="" class="h-4 w-4 shrink-0 object-contain" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="flex h-9 w-8 items-center justify-center transition hover:bg-black/10"
        :title="expanded ? 'Minimize' : 'Maximize'"
        :aria-expanded="expanded"
        :aria-label="expanded ? 'Minimize sync panel' : 'Maximize sync panel'"
        @click="expanded = !expanded"
      >
        <!-- minimize = title-bar dash; maximize = window with title bar -->
        <svg v-if="expanded" class="h-3.5 w-3.5" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
          <rect x="1" y="5.25" width="10" height="1.5" rx="0.2" />
        </svg>
        <svg v-else class="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true">
          <rect x="1.25" y="2" width="9.5" height="8" rx="0.6" />
          <path d="M1.25 4.25h9.5" />
        </svg>
      </button>
    </div>

    <div
      class="overflow-hidden transition-[max-height,opacity] duration-300 ease-in-out"
      :class="expanded ? 'max-h-[min(70vh,28rem)] opacity-100' : 'max-h-0 opacity-0'"
    >
      <div class="space-y-3 overflow-y-auto border-t border-slate-100 px-3 pb-3 pt-2 text-xs text-slate-700">
        <p class="font-medium text-slate-800">{{ statusLine }}</p>
        <p class="text-[11px] leading-4 text-slate-500">
          Compares Application Status, Applied Through, Found From only. Sync writes HTP → Excel.
        </p>

        <template v-if="columnDiffs.length">
          <div v-for="d in columnDiffs" :key="d.column" class="rounded-md border border-slate-100 bg-slate-50 p-2">
            <div class="mb-1 font-semibold text-slate-800">{{ d.label }}</div>
            <p v-if="d.excelMissing" class="text-amber-800">
              Excel has no list validation.
              <span class="block text-slate-600">HTP: {{ joinList(d.htp) }}</span>
            </p>
            <template v-else>
              <p v-if="d.onlyHtp.length" class="text-emerald-800">
                <span class="font-medium">Only in HTP:</span> {{ joinList(d.onlyHtp) }}
              </p>
              <p v-if="d.onlyExcel.length" class="text-amber-900">
                <span class="font-medium">Only in Excel:</span> {{ joinList(d.onlyExcel) }}
              </p>
              <p v-if="d.orderOnly" class="text-slate-600">
                Same values, different order.
                <span class="block">HTP: {{ joinList(d.htp) }}</span>
                <span class="block">Excel: {{ joinList(d.excel ?? []) }}</span>
              </p>
            </template>
          </div>
        </template>
        <p v-else-if="syncTone === 'ok'" class="text-slate-500">
          No differences for the three editable columns.
        </p>
      </div>
    </div>
  </aside>
</template>
