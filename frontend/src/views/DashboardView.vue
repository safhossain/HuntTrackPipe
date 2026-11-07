<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, type SessionListResponse } from '../api/client'
import DashboardMetrics from '../components/DashboardMetrics.vue'
import SyncDock from '../components/SyncDock.vue'
import { rowColorStyle } from '../applicationColors'
import { useAppStore } from '../stores/app'
import { daysSince, errorText, fmtDate, outcomeLabel } from '../utils'

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
  'Early interest': 'bg-[#E8EEF6] text-[#52647A]',
  Withdrawn: 'bg-slate-700 text-slate-50',
  Rejected: 'bg-red-100 text-red-800',
  Offer: 'bg-emerald-100 text-emerald-800',
  Accepted: 'bg-emerald-600 text-white',
}

</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <h1 class="text-xl font-semibold">Applications</h1>
      <div class="ml-auto flex max-w-full items-start gap-2">
        <button
          type="button"
          class="btn-secondary toolbar-control w-8 px-0"
          :disabled="loading"
          title="Reload application list from Excel"
          aria-label="Refresh application list"
          @click="load"
        >
          <svg
            class="h-4 w-4"
            :class="loading ? 'animate-spin' : undefined"
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
        </button>
        <RouterLink to="/new" class="btn-primary toolbar-control">New application</RouterLink>
        <SyncDock dashboard />
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
            <th class="px-3 py-2 text-center align-middle">Status</th>
            <th class="px-3 py-2 text-center align-middle">Outcome</th>
            <th class="px-3 py-2 text-center align-middle">Applied</th>
            <th class="px-3 py-2 text-center align-middle">Days</th>
            <th class="px-3 py-2">Folder</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!data || !data.sessions.length">
            <td colspan="7" class="px-3 py-6 text-center text-slate-500">{{ loading ? 'Loading…' : 'No applications yet.' }}</td>
          </tr>
          <tr v-for="s in data?.sessions ?? []" :key="s.folder" class="application-row border-t border-slate-200" :style="rowColorStyle(s.row)">
            <td class="px-3 py-2 font-medium">{{ s.row?.Organization ?? '—' }}</td>
            <td class="px-3 py-2">{{ s.row?.Position_Title ?? '—' }}</td>
            <td class="px-3 py-2 text-center align-middle">
              <span v-if="s.row?.Application_Status" class="chip justify-center text-center" :class="statusCls[String(s.row.Application_Status)] ?? 'bg-slate-100'">{{ s.row.Application_Status }}</span>
              <span v-else-if="!s.row" class="chip justify-center text-center bg-amber-100 text-amber-800" title="No row in the tracker for this folder">no row</span>
            </td>
            <td class="px-3 py-2 text-center align-middle">
              <span v-if="s.row?.Outcome" class="chip justify-center text-center" :class="outcomeCls[outcomeLabel(s.row.Outcome)] ?? 'bg-slate-100'">{{ outcomeLabel(s.row.Outcome) }}</span>
            </td>
            <td class="px-3 py-2 text-center align-middle tabular-nums">{{ fmtDate(s.row?.Applied_Date) }}</td>
            <td class="px-3 py-2 text-center align-middle tabular-nums">{{ daysSince(s.row?.Applied_Date) ?? '' }}</td>
            <td class="px-3 py-2">
              <RouterLink :to="{ name: 'session', params: { folder: s.folder } }" class="application-row-link font-mono text-xs hover:underline">{{ s.folder }}</RouterLink>
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

<style scoped>
.application-row {
  background-color: var(--application-row-bg);
  color: var(--application-row-text);
}
.application-row:hover {
  background-color: var(--application-row-hover);
}
.application-row-link {
  color: var(--application-row-link);
}
</style>
