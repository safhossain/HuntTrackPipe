<script setup lang="ts">
import docxLogo from '../img/docx_logo.png'
import jpgLogo from '../img/jpg_logo.png'
import pdfLogo from '../img/pdf_logo.png'
import pngLogo from '../img/png_logo.png'

const props = defineProps<{
  target: string
  disabled?: boolean
  busy?: boolean
  title?: string
}>()
defineEmits<{ click: [] }>()

const logos: Record<string, string> = {
  pdf: pdfLogo,
  docx: docxLogo,
  png: pngLogo,
  jpg: jpgLogo,
  jpeg: jpgLogo,
}

const logo = () => logos[props.target.toLowerCase()]
const label = () => props.target.toUpperCase()
</script>

<template>
  <button
    type="button"
    class="btn-secondary inline-flex items-center gap-1 px-2"
    :disabled="disabled || busy"
    :title="title ?? `Convert → ${label()}`"
    @click="$emit('click')"
  >
    <template v-if="busy">
      <span class="text-xs">…</span>
    </template>
    <template v-else>
      <span class="text-base font-semibold leading-none text-slate-600" aria-hidden="true">→</span>
      <img v-if="logo()" :src="logo()" :alt="label()" class="h-5 w-5 rounded-sm object-contain" />
      <span v-else class="font-mono text-[10px] font-semibold uppercase">{{ label() }}</span>
      <span class="sr-only">Convert to {{ label() }}</span>
    </template>
  </button>
</template>
