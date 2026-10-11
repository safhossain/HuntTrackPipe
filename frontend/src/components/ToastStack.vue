<script setup lang="ts">
import { useAppStore } from '../stores/app'
const app = useAppStore()
const cls: Record<string, string> = {
  info: 'bg-slate-800 text-white',
  success: 'bg-emerald-600 text-white',
  error: 'bg-red-600 text-white',
}
</script>

<template>
  <div class="pointer-events-none fixed right-4 bottom-4 z-50 flex w-96 flex-col gap-2">
    <div
      v-for="t in app.toasts"
      :key="t.id"
      class="pointer-events-auto rounded-md px-3 py-2 text-sm shadow-lg"
      :class="cls[t.kind]"
      @click="app.dismiss(t.id)"
    >
      {{ t.text }}
    </div>
  </div>
</template>
