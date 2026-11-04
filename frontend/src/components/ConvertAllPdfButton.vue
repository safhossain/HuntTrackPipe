<script setup lang="ts">
import pdfLogo from '../img/pdf_logo.png'

defineProps<{
  disabled?: boolean
  busy?: boolean
  title?: string
}>()
defineEmits<{ click: [] }>()
</script>

<template>
  <button
    type="button"
    class="btn-secondary inline-flex items-center gap-1.5 px-2.5"
    :disabled="disabled || busy"
    :title="title ?? 'Convert all files to PDF'"
    @click="$emit('click')"
  >
    <template v-if="busy">
      <span class="text-xs">Converting…</span>
    </template>
    <template v-else>
      <span class="text-base font-semibold leading-none text-slate-600" aria-hidden="true">→</span>
      <img :src="pdfLogo" alt="PDF" class="h-6 w-6 rounded-sm object-contain" />
      <span class="sr-only">Convert all to PDF</span>
    </template>
  </button>
</template>
