<script setup lang="ts">
import SyncDock from './SyncDock.vue'

defineProps<{ title?: string }>()
</script>

<template>
  <header class="flex flex-wrap items-start justify-between gap-2">
    <div class="min-w-0 flex-1 [overflow-wrap:anywhere]">
      <slot>
        <h1 class="text-xl font-semibold">{{ title }}</h1>
      </slot>
    </div>
    <div class="ml-auto flex max-w-full flex-wrap items-start justify-end gap-2">
      <slot name="actions" />
      <SyncDock />
    </div>
  </header>
</template>
