<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, type SessionListResponse } from '../api/client'
import DashboardMetrics from '../components/DashboardMetrics.vue'
import { useAppStore } from '../stores/app'
import { daysSince, errorText, fmtDate } from '../utils'

const app = useAppStore()
const data = ref<SessionListResponse | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await api.sessions()
  } catch (e) {
    app.toast(errorText(e), 'error')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const statusCls: Record<string, string> = {
  'Not Applied': 'bg-slate-100 text-slate-700',
  Applied: 'bg-blue-100 text-blue-800',
  'Recruiter-Screening': 'bg-indigo-100 text-indigo-800',
  'Technical Interview': 'bg-violet-100 text-violet-800',
  'Final Round': 'bg-fuchsia-100 text-fuchsia-800',
}
const outcomeCls: Record<string, string> = {
  Pending: 'bg-slate-100 text-slate-700',
  Withdrawn: 'bg-slate-200 text-slate-600',
  Rejected: 'bg-red-100 text-red-800',
  Offer: 'bg-emerald-100 text-emerald-800',
  Accepted: 'bg-emerald-600 text-white',
}

/** Outcome wins when it is terminal. Pending (or blank) falls through to status. */
function rowClass(row: { Application_Status?: unknown; Outcome?: unknown } | null | undefined): string {
  const outcome = row?.Outcome == null ? '' : String(row.Outcome)
  const status = row?.Application_Status == null ? '' : String(row.Application_Status)
  if (outcome === 'Withdrawn') return 'bg-slate-200 hover:bg-slate-300'
  if (outcome === 'Rejected') return 'bg-red-100 hover:bg-red-200'
  if (outcome === 'Offer' || outcome === 'Accepted') return 'bg-emerald-100 hover:bg-emerald-200'
  if (outcome === 'Pending' || outcome === '') {
    if (status === 'Not Applied') return 'bg-yellow-100 hover:bg-yellow-200'
    if (status === 'Recruiter-Screening') return 'bg-sky-100 hover:bg-sky-200'
    if (status === 'Technical Interview') return 'bg-orange-100 hover:bg-orange-200'
    if (status === 'Final Round') return 'bg-violet-100 hover:bg-violet-200'
  }
  return 'hover:bg-slate-50'
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold">Applications</h1>
      <div class="flex gap-2">
        <button class="btn-secondary" :disabled="loading" @click="load">Refresh</button>
        <RouterLink to="/new" class="btn-primary">New application</RouterLink>
      </div>
    </div>

    <div v-if="data?.tracker_error" class="rounded-md bg-red-50 p-3 text-sm text-red-800">
      Tracker could not be read: {{ data.tracker_error }}
    </div>

    <div class="card overflow-x-auto p-0">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-3 py-2">Organization</th>
            <th class="px-3 py-2">Position</th>
            <th class="px-3 py-2">Status</th>
            <th class="px-3 py-2">Outcome</th>
            <th class="px-3 py-2">Applied</th>
            <th class="px-3 py-2 text-right">Days</th>
            <th class="px-3 py-2">Folder</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!data || !data.sessions.length">
            <td colspan="7" class="px-3 py-6 text-center text-slate-500">{{ loading ? 'Loading…' : 'No applications yet.' }}</td>
          </tr>
          <tr v-for="s in data?.sessions ?? []" :key="s.folder" class="border-t border-slate-200" :class="rowClass(s.row)">
            <td class="px-3 py-2 font-medium">{{ s.row?.Organization ?? '—' }}</td>
            <td class="px-3 py-2">{{ s.row?.Position_Title ?? '—' }}</td>
            <td class="px-3 py-2">
              <span v-if="s.row?.Application_Status" class="chip" :class="statusCls[String(s.row.Application_Status)] ?? 'bg-slate-100'">{{ s.row.Application_Status }}</span>
              <span v-else-if="!s.row" class="chip bg-amber-100 text-amber-800" title="No row in the tracker for this folder">no row</span>
            </td>
            <td class="px-3 py-2">
              <span v-if="s.row?.Outcome" class="chip" :class="outcomeCls[String(s.row.Outcome)] ?? 'bg-slate-100'">{{ s.row.Outcome }}</span>
            </td>
            <td class="px-3 py-2 tabular-nums">{{ fmtDate(s.row?.Applied_Date) }}</td>
            <td class="px-3 py-2 text-right tabular-nums">{{ daysSince(s.row?.Applied_Date) ?? '' }}</td>
            <td class="px-3 py-2">
              <RouterLink :to="{ name: 'session', params: { folder: s.folder } }" class="font-mono text-xs text-indigo-600 hover:underline">{{ s.folder }}</RouterLink>
              <span v-if="s.pending_write" class="chip ml-1 bg-amber-100 text-amber-800" title="Excel write pending">pending</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="data?.unmanaged.length" class="text-xs text-slate-500">
      Folders without a session.json (unmanaged): <span class="font-mono">{{ data.unmanaged.join(', ') }}</span>
    </div>

    <DashboardMetrics v-if="data" :sessions="data.sessions" />
  </div>
</template>
