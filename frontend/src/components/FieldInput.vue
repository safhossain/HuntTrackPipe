<script setup lang="ts">
// One tracker column -> the right input (select for dropdown columns, date for Applied_Date, text otherwise).
import { computed } from 'vue'
import type { RowValue } from '../api/client'
import { useAppStore } from '../stores/app'

const props = defineProps<{ column: string; modelValue: RowValue; hint?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: RowValue] }>()
const app = useAppStore()

const options = computed(() => app.meta?.options[props.column] ?? null)
const isDate = computed(() => props.column === 'Applied_Date')
const str = computed(() => (props.modelValue === null || props.modelValue === undefined ? '' : String(props.modelValue)))
const postingHref = computed(() => {
  if (props.column !== 'Posting_URL') return ''
  const raw = str.value.trim()
  if (!raw) return ''
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`
  try {
    const url = new URL(withScheme)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return ''
    if (!url.hostname.includes('.')) return ''
    return url.href
  } catch {
    return ''
  }
})

function onInput(ev: Event) {
  const v = (ev.target as HTMLInputElement | HTMLSelectElement).value
  emit('update:modelValue', v === '' ? null : v)
}
</script>

<template>
  <label class="block">
    <span class="label">
      {{ column.replace(/_/g, ' ') }}
      <a
        v-if="postingHref"
        :href="postingHref"
        target="_blank"
        rel="noopener noreferrer"
        class="ml-1.5 inline-block rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0 text-[10px] font-semibold normal-case leading-4 tracking-normal text-indigo-700 hover:bg-indigo-100"
        @click.stop
      >Open</a>
      <span v-if="hint" class="ml-1 normal-case text-slate-400">{{ hint }}</span>
    </span>
    <select v-if="options" class="input" :value="str" @change="onInput">
      <option value="">—</option>
      <option v-for="o in options" :key="o" :value="o">{{ o }}</option>
    </select>
    <input v-else-if="isDate" type="date" class="input" :value="str.slice(0, 10)" @input="onInput" />
    <input v-else type="text" class="input" :value="str" :placeholder="column === 'Deadline' ? 'YYYY-MM-DD or phrase' : ''" @input="onInput" />
  </label>
</template>
