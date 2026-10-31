<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useAppStore } from './stores/app'
import SyncDock from './components/SyncDock.vue'
import ToastStack from './components/ToastStack.vue'

import excelOk from './img/excel-icon-green.png'
import excelBad from './img/excel-icon-red.png'
import jevOk from './img/jev_logo-transparent_green.png'
import jevBad from './img/jev_logo-transparent_red.png'
import claudeOk from './img/claude_orange.png'
import claudeBad from './img/claude_grey.png'

const app = useAppStore()
onMounted(() => app.bootstrap())

const trackerIcon = computed(() => (app.settings?.tracker_exists ? excelOk : excelBad))
const trackerTitle = computed(() => {
  if (app.trackerLocked) return 'Tracker open in Excel — close it before writing'
  if (app.settings?.tracker_exists) return 'Tracker workbook found'
  return 'Tracker workbook missing'
})

const jevIcon = computed(() => (app.settings?.keys.TYPESAFE_API_KEY ? jevOk : jevBad))
const jevTitle = computed(() =>
  app.settings?.keys.TYPESAFE_API_KEY ? 'Jev API key set' : 'Jev API key missing',
)

const claudeIcon = computed(() => (app.settings?.keys.ANTHROPIC_API_KEY ? claudeOk : claudeBad))
const claudeTitle = computed(() =>
  app.settings?.keys.ANTHROPIC_API_KEY ? 'Claude API key set' : 'Claude API key missing',
)
</script>

<template>
  <div class="min-h-screen">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <RouterLink to="/" class="text-lg font-semibold tracking-tight">HuntTrackPipe</RouterLink>
        <nav class="flex gap-4 whitespace-nowrap text-sm">
          <RouterLink to="/" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium" exact-active-class="text-indigo-600 font-medium">Dashboard</RouterLink>
          <RouterLink to="/new" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">New application</RouterLink>
          <RouterLink to="/convert" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">Convert</RouterLink>
          <RouterLink to="/settings" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">Settings</RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-2.5">
          <template v-if="app.settings">
            <img
              :src="trackerIcon"
              :alt="trackerTitle"
              :title="trackerTitle"
              class="h-5 w-5 object-contain"
              :class="app.trackerLocked ? 'opacity-60' : undefined"
            />
            <img :src="jevIcon" :alt="jevTitle" :title="jevTitle" class="h-5 w-5 object-contain" />
            <img :src="claudeIcon" :alt="claudeTitle" :title="claudeTitle" class="h-5 w-5 object-contain" />
          </template>
          <span v-else-if="app.apiError" class="text-xs text-red-600">API unreachable</span>
          <span v-else class="text-xs text-slate-500">Connecting…</span>
        </div>
      </div>
      <div
        v-if="app.trackerLocked"
        class="border-t border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900"
      >
        Tracker workbook is open in Excel. Close it before creating applications, saving rows, or syncing dropdowns.
      </div>
    </header>

    <!-- Content + sync column share one row: small gap, no overlay, no empty canyon. -->
    <div class="mx-auto flex max-w-7xl items-start gap-4 px-4 py-6">
      <main class="min-w-0 flex-1">
        <div v-if="!app.apiReady && !app.apiError" class="text-sm text-slate-500">Waiting for the API on :8010…</div>
        <RouterView v-else />
      </main>
      <SyncDock />
    </div>

    <ToastStack />
  </div>
</template>
