<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, type Row, type RowValue, type SessionDetail } from '../api/client'
import FieldInput from '../components/FieldInput.vue'
import JevPanel from '../components/JevPanel.vue'
import { useAppStore } from '../stores/app'
import { errorText, fmtDate } from '../utils'

const props = defineProps<{ folder: string }>()
const app = useAppStore()

const detail = ref<SessionDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const tab = ref<'overview' | 'files' | 'questions' | 'log'>('overview')
const showPosting = ref(false)

const form = reactive<Row>({})
const original = reactive<Row>({})

const columns = computed(() => [...(app.meta?.extracted_columns ?? []), ...(app.meta?.manual_columns ?? [])])
const dirty = computed(() => columns.value.filter((c) => (form[c] ?? null) !== (original[c] ?? null)))
const folderPath = computed(() => {
  const base = app.settings?.paths.applications_dir ?? ''
  return base ? `${base}\\${props.folder}` : props.folder
})

function hydrate(d: SessionDetail) {
  detail.value = d
  const src: Row = d.row ?? d.session.review.values
  for (const c of columns.value) {
    const v = src[c] ?? null
    original[c] = v === null ? null : app.meta?.date_columns.includes(c) ? fmtDate(v) : v
    form[c] = original[c]
  }
}

async function load() {
  loading.value = true
  try {
    hydrate(await api.session(props.folder))
  } catch (e) {
    app.toast(errorText(e), 'error')
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.folder, load)

async function save() {
  if (!dirty.value.length) return
  saving.value = true
  try {
    const values: Row = {}
    for (const c of dirty.value) values[c] = form[c] ?? null
    const { report, row } = await api.writeRow(props.folder, values, dirty.value)
    app.toast(`Saved ${Object.keys(report.written).length} cell(s) to row ${report.row}`, 'success')
    if (detail.value) hydrate({ ...detail.value, row, session: { ...detail.value.session, review: { ...detail.value.session.review, pending_write: null } } })
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
    await load()
  } finally {
    saving.value = false
  }
}

async function retry() {
  saving.value = true
  try {
    const { report } = await api.retryRow(props.folder)
    app.toast(`Pending write flushed: ${Object.keys(report.written).join(', ') || 'nothing to write'}`, 'success')
    const skipped = Object.keys(report.skipped)
    if (skipped.length) app.toast(`Not overwritten: ${skipped.join(', ')}`, 'info', 8000)
    await load()
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    saving.value = false
  }
}

function setField(c: string, v: RowValue) {
  form[c] = v
}

async function copyPath() {
  try {
    await navigator.clipboard.writeText(folderPath.value)
    app.toast('Folder path copied.', 'success', 2000)
  } catch {
    app.toast(folderPath.value, 'info', 8000)
  }
}

const pretty = (o: unknown) => JSON.stringify(o, null, 2)
</script>

<template>
  <div v-if="detail" class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h1 class="font-mono text-lg font-semibold">{{ folder }}</h1>
        <p class="text-xs text-slate-500">
          created {{ fmtDate(detail.session.created_at) }} · upload mode <span class="font-mono">{{ detail.session.upload_mode }}</span>
          <span v-if="detail.session.review.written_at"> · last Excel write {{ detail.session.review.written_at.slice(0, 16).replace('T', ' ') }}</span>
        </p>
      </div>
      <button class="btn-secondary" @click="copyPath" title="Copy folder path">Copy path</button>
    </div>

    <div v-if="detail.session.review.pending_write" class="flex items-center justify-between rounded-md bg-amber-50 p-3 text-sm text-amber-900">
      <span>Excel write pending for: <span class="font-mono">{{ Object.keys(detail.session.review.pending_write.values).join(', ') }}</span>. Close Excel, then retry.</span>
      <button class="btn-primary" :disabled="saving" @click="retry">Retry</button>
    </div>
    <div v-if="detail.row_error" class="rounded-md bg-red-50 p-3 text-sm text-red-800">Tracker could not be read: {{ detail.row_error }}</div>
    <div v-else-if="!detail.row" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900">No row in the tracker for this folder yet. Saving will create one.</div>

    <nav class="flex gap-1 border-b border-slate-200 text-sm">
      <button v-for="t in (['overview', 'files', 'questions', 'log'] as const)" :key="t" class="-mb-px border-b-2 px-3 py-2 capitalize" :class="tab === t ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'" @click="tab = t">{{ t }}</button>
    </nav>

    <section v-if="tab === 'overview'" class="space-y-4">
      <div class="card space-y-3">
        <div class="flex items-baseline justify-between">
          <h3 class="font-semibold">Tracker row <span class="text-xs font-normal text-slate-500">(values read from Excel; your edits overwrite)</span></h3>
          <button class="btn-primary" :disabled="saving || !dirty.length" @click="save">{{ saving ? 'Saving…' : `Save ${dirty.length ? `(${dirty.length})` : ''}` }}</button>
        </div>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <FieldInput v-for="c in columns" :key="c" :column="c" :model-value="form[c] ?? null" :hint="dirty.includes(c) ? '• edited' : undefined" @update:model-value="(v) => setField(c, v)" />
        </div>
      </div>

      <div class="card">
        <button class="text-sm font-semibold" @click="showPosting = !showPosting">{{ showPosting ? '▾' : '▸' }} Posting text<span v-if="detail.session.posting.url" class="ml-2 text-xs font-normal text-slate-500">{{ detail.session.posting.url }}</span></button>
        <pre v-if="showPosting" class="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{{ detail.session.posting.text }}</pre>
      </div>
    </section>

    <section v-else-if="tab === 'files'" class="card text-sm text-slate-500">
      Files (rename, convert, combine) arrive in step 3. Jev flagged upload mode <span class="font-mono">{{ detail.session.upload_mode }}</span><span v-if="detail.session.jev?.derived.required_docs.length">; documents: {{ detail.session.jev.derived.required_docs.join(', ') }}</span>.
    </section>

    <section v-else-if="tab === 'questions'" class="card text-sm text-slate-500">Application questions arrive in step 4.</section>

    <section v-else class="grid gap-4 lg:grid-cols-2">
      <JevPanel v-if="detail.session.jev" :jev="detail.session.jev" :derived="detail.session.jev.derived" :warnings="detail.session.jev.derived.warnings" />
      <div class="card space-y-2">
        <h3 class="font-semibold">LLM <span v-if="detail.session.llm" class="text-xs font-normal text-slate-500">{{ detail.session.llm.model }} · {{ pretty(detail.session.llm.usage) }}</span></h3>
        <pre v-if="detail.session.llm" class="max-h-80 overflow-auto rounded bg-slate-50 p-3 text-xs">{{ pretty(detail.session.llm.output) }}</pre>
        <p v-else class="text-sm text-slate-500">No LLM call recorded.</p>
      </div>
      <div class="card lg:col-span-2">
        <h3 class="mb-2 font-semibold">Raw Jev answers</h3>
        <pre class="max-h-80 overflow-auto rounded bg-slate-50 p-3 text-xs">{{ pretty(detail.session.jev?.answers ?? null) }}</pre>
      </div>
    </section>
  </div>
  <div v-else class="text-sm text-slate-500">{{ loading ? 'Loading…' : 'Session not found.' }}</div>
</template>
