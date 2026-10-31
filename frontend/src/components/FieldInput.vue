<script setup lang="ts">
// One tracker column -> the right input (select for dropdown columns, date for Applied_Date, text otherwise).
// Editable option columns (Application_Status, Applied_Through, Found_From) can grow via "Add…".
import { computed, ref } from 'vue'
import { api, ApiError, type RowValue } from '../api/client'
import { useAppStore } from '../stores/app'

const props = defineProps<{ column: string; modelValue: RowValue; hint?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: RowValue] }>()
const app = useAppStore()

const ADD = '__htp_add__'
const options = computed(() => app.meta?.options[props.column] ?? null)
const editable = computed(() => Boolean(app.meta?.editable_option_columns?.includes(props.column)))
const isDate = computed(() => props.column === 'Applied_Date')
const str = computed(() => (props.modelValue === null || props.modelValue === undefined ? '' : String(props.modelValue)))
const adding = ref(false)
const selectEl = ref<HTMLSelectElement | null>(null)

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

async function onSelectChange(ev: Event) {
  const el = ev.target as HTMLSelectElement
  const v = el.value
  if (v !== ADD) {
    emit('update:modelValue', v === '' ? null : v)
    return
  }
  // Restore previous selection while we prompt.
  el.value = str.value
  const label = props.column.replace(/_/g, ' ')
  const raw = window.prompt(`New ${label} value:`)
  if (raw == null) return
  const name = raw.trim()
  if (!name) return
  adding.value = true
  try {
    const res = await api.addOption(props.column, name)
    if (app.meta) app.meta = { ...app.meta, options: { ...app.meta.options, ...res.options } }
    emit('update:modelValue', res.value)
    if (!res.excel_synced) {
      app.toast(res.excel_error || 'Option saved; close Excel so dropdowns can sync on the next write.', 'info')
    } else {
      app.toast(`Added ${res.value} to ${label}`, 'success')
    }
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
    app.toast(msg, 'error')
  } finally {
    adding.value = false
  }
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
    <select
      v-if="options"
      ref="selectEl"
      class="input"
      :value="str"
      :disabled="adding"
      @change="onSelectChange"
    >
      <option value="">—</option>
      <option v-for="o in options" :key="o" :value="o">{{ o }}</option>
      <option v-if="editable" :value="ADD">Add…</option>
    </select>
    <input v-else-if="isDate" type="date" class="input" :value="str.slice(0, 10)" @input="onInput" />
    <input v-else type="text" class="input" :value="str" :placeholder="column === 'Deadline' ? 'YYYY-MM-DD or phrase' : ''" @input="onInput" />
  </label>
</template>
