<script setup lang="ts">
// One tracker column -> the right input (select for dropdown columns, date for Applied_Date, text otherwise).
// Editable option columns (Application_Status, Applied_Through, Found_From) can grow via "Add…".
// Compensation shows a compact "Estimated." toggle (session-only; not an Excel column).
import { computed, ref } from 'vue'
import { api, ApiError, type RowValue } from '../api/client'
import { useAppStore } from '../stores/app'
import { outcomeLabel, postingUrlHref } from '../utils'

const props = defineProps<{
  column: string
  modelValue: RowValue
  hint?: string
  /** Compensation only: optional Estimated? flag (session.json, not Excel). */
  estimated?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: RowValue]
  'update:estimated': [value: boolean]
}>()
const app = useAppStore()

const ADD = '__htp_add__'
const options = computed(() => app.meta?.options[props.column] ?? null)
const editable = computed(() => Boolean(app.meta?.editable_option_columns?.includes(props.column)))
const isDate = computed(() => props.column === 'Applied_Date')
const isCompensation = computed(() => props.column === 'Compensation')
const str = computed(() => (props.modelValue === null || props.modelValue === undefined ? '' : String(props.modelValue)))
const adding = ref(false)
const selectEl = ref<HTMLSelectElement | null>(null)

const postingHref = computed(() => props.column === 'Posting_URL' ? postingUrlHref(props.modelValue) : '')

async function copyPostingLink() {
  const link = postingHref.value
  if (!link) return
  try {
    await navigator.clipboard.writeText(link)
    app.toast('Link copied.', 'success', 2000)
  } catch {
    app.toast('Could not copy the link.', 'error')
  }
}

function onInput(ev: Event) {
  const v = (ev.target as HTMLInputElement | HTMLSelectElement).value
  emit('update:modelValue', v === '' ? null : v)
}

function toggleEstimated() {
  emit('update:estimated', !props.estimated)
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
  <label class="block min-w-0">
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
      <button
        v-if="postingHref"
        type="button"
        class="ml-1 inline-block rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0 text-[10px] font-semibold normal-case leading-4 tracking-normal text-indigo-700 hover:bg-indigo-100"
        @click.stop="copyPostingLink"
      >Copy link</button>
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
      <option v-if="editable" :value="ADD">Add…</option>
      <option v-for="o in options" :key="o" :value="o">{{ column === 'Outcome' ? outcomeLabel(o) : o }}</option>
    </select>
    <input v-else-if="isDate" type="date" class="input" :value="str.slice(0, 10)" @input="onInput" />
    <div v-else-if="isCompensation" class="flex min-w-0 items-end gap-1.5">
      <input
        type="text"
        class="input min-w-0 flex-1"
        :value="str"
        placeholder="e.g. CAD 80,000 / year"
        @input="onInput"
      />
      <div class="flex shrink-0 flex-col items-center gap-0.5 pb-0.5">
        <span class="text-[10px] leading-none text-slate-500">Estimated.</span>
        <button
          type="button"
          role="checkbox"
          :aria-checked="estimated ? 'true' : 'false'"
          class="flex h-8 w-8 items-center justify-center rounded border text-sm font-semibold leading-none transition"
          :class="estimated
            ? 'border-amber-400 bg-amber-50 text-amber-800'
            : 'border-slate-300 bg-white text-slate-400 hover:border-slate-400'"
          title="Mark compensation as estimated (saved in session, not Excel)"
          @click.prevent="toggleEstimated"
        >{{ estimated ? '✓' : '' }}</button>
      </div>
    </div>
    <input v-else type="text" class="input" :value="str" :placeholder="column === 'Deadline' ? 'YYYY-MM-DD or phrase' : ''" @input="onInput" />
  </label>
</template>
