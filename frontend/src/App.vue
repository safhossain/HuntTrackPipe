<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useAppStore } from './stores/app'
import ToastStack from './components/ToastStack.vue'

const app = useAppStore()
onMounted(() => app.bootstrap())
</script>

<template>
  <div class="min-h-screen">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <RouterLink to="/" class="text-lg font-semibold tracking-tight">HuntTrackPipe</RouterLink>
        <nav class="flex gap-4 text-sm">
          <RouterLink to="/" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium" exact-active-class="text-indigo-600 font-medium">Dashboard</RouterLink>
          <RouterLink to="/new" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">New application</RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-3 text-xs text-slate-500">
          <template v-if="app.settings">
            <span :class="app.settings.keys.TYPESAFE_API_KEY ? 'text-emerald-600' : 'text-red-600'">Jev key {{ app.settings.keys.TYPESAFE_API_KEY ? 'ok' : 'missing' }}</span>
            <span :class="app.settings.keys.ANTHROPIC_API_KEY ? 'text-emerald-600' : 'text-red-600'">Claude key {{ app.settings.keys.ANTHROPIC_API_KEY ? 'ok' : 'missing' }}</span>
            <span :class="app.settings.tracker_exists ? 'text-emerald-600' : 'text-red-600'">tracker {{ app.settings.tracker_exists ? 'found' : 'missing' }}</span>
          </template>
          <span v-else-if="app.apiError" class="text-red-600">API unreachable: {{ app.apiError }}</span>
          <span v-else>Connecting to API…</span>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-4 py-6">
      <div v-if="!app.apiReady && !app.apiError" class="text-sm text-slate-500">Waiting for the API on :8010…</div>
      <RouterView v-else />
    </main>

    <ToastStack />
  </div>
</template>
