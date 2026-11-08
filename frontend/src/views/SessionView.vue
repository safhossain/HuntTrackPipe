<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type DiffEntry, type FilesView, type QAView, type ReextractResponse, type Row, type RowValue, type SessionDetail } from '../api/client'
import FieldInput from '../components/FieldInput.vue'
import FilesPanel from '../components/FilesPanel.vue'
import JevPanel from '../components/JevPanel.vue'
import QaPanel from '../components/QaPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import { useAppStore } from '../stores/app'
import { cleanPostingText, errorText, fmtDate, todayIso } from '../utils'

const props = defineProps<{ folder: string }>()
const app = useAppStore()
const router = useRouter()

const detail = ref<SessionDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const tab = ref<'overview' | 'files' | 'questions' | 'notes' | 'log'>('overview')
const showPosting = ref(false)
const cleanedPosting = computed(() => cleanPostingText(detail.value?.session.posting.text ?? ''))
const postingDraft = ref<string | null>(null)
const postingEditor = ref<HTMLTextAreaElement | null>(null)
const postingSaving = ref(false)
const offerReextract = ref(false)
const canSavePosting = computed(() => Boolean(postingDraft.value?.trim()) && postingDraft.value !== detail.value?.session.posting.text)
const notesDraft = ref('')
let notesTimer: ReturnType<typeof setTimeout> | null = null
let notesSeq = 0

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
  notesDraft.value = d.session.notes ?? ''
  const src: Row = d.row ?? d.session.review.values
  for (const c of columns.value) {
    const v = src[c] ?? null
    original[c] = v === null ? null : app.meta?.date_columns.includes(c) ? fmtDate(v) : v
    form[c] = original[c]
  }
}

function onNotesInput(ev: Event) {
  notesDraft.value = (ev.target as HTMLTextAreaElement).value
  if (notesTimer) clearTimeout(notesTimer)
  notesTimer = setTimeout(() => {
    void saveNotes()
  }, 500)
}

async function saveNotes() {
  if (!detail.value) return
  const text = notesDraft.value
  if (text === (detail.value.session.notes ?? '')) return
  const seq = ++notesSeq
  try {
    const r = await api.setSessionNotes(props.folder, text)
    if (seq !== notesSeq) return
    detail.value.session.notes = r.notes
  } catch (e) {
    if (seq === notesSeq) app.toast(errorText(e), 'error')
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
watch(() => props.folder, () => {
  postingDraft.value = null
  offerReextract.value = false
  reResult.value = null
  void load()
})

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

const compensationEstimated = computed(() => detail.value?.session.review.compensation_estimated ?? false)

async function setCompensationEstimated(v: boolean) {
  if (!detail.value) return
  const prev = detail.value.session.review.compensation_estimated
  detail.value.session.review.compensation_estimated = v
  try {
    const r = await api.setSessionFlags(props.folder, { compensation_estimated: v })
    detail.value.session.review.compensation_estimated = r.compensation_estimated
  } catch (e) {
    detail.value.session.review.compensation_estimated = prev
    app.toast(errorText(e), 'error')
  }
}

// ---- duplicate ----
/** Fields shown in the Duplicate panel; Requisition_ID first so a new req lands in the folder name. */
const DUPLICATE_FIELDS = [
  'Requisition_ID',
  'Organization',
  'Position_Title',
  'Posting_URL',
  'Applied_Date',
  'Application_Status',
  'Outcome',
  'Applied_Through',
  'Found_From',
] as const
const showDuplicate = ref(false)
const duplicating = ref(false)
const dupForm = reactive<Row>({})

function openDuplicate() {
  for (const c of DUPLICATE_FIELDS) {
    if (c === 'Applied_Date') dupForm[c] = todayIso()
    else if (c === 'Application_Status') dupForm[c] = 'Not Applied'
    else if (c === 'Outcome') dupForm[c] = 'Pending'
    else dupForm[c] = form[c] ?? null
  }
  showDuplicate.value = true
}

function setDupField(c: string, v: RowValue) {
  dupForm[c] = v
}

async function confirmDuplicate() {
  duplicating.value = true
  try {
    const values: Row = {}
    for (const c of DUPLICATE_FIELDS) values[c] = dupForm[c] ?? null
    const { session, report } = await api.duplicateSession(props.folder, values)
    app.toast(`Duplicated as ${session.folder} (row ${report.row})`, 'success')
    showDuplicate.value = false
    router.push({ name: 'session', params: { folder: session.folder } })
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    duplicating.value = false
  }
}

// ---- re-extract ----
const reextracting = ref(false)
const reUseJev = ref(true)
const reUseLlm = ref(true)
const reextractPanel = ref<HTMLElement | null>(null)
const reResult = ref<ReextractResponse | null>(null)
const reSelected = reactive<Record<string, boolean>>({})
const reChanged = computed(() => reResult.value?.diff.filter((d) => d.changed) ?? [])
const reChosen = computed(() => reChanged.value.filter((d) => reSelected[d.column]))

async function reextract() {
  const folder = props.folder
  if (detail.value?.session.folder !== folder || postingDraft.value !== null) return
  reextracting.value = true
  reResult.value = null
  try {
    const r = await api.reextract(folder, reUseJev.value, reUseLlm.value)
    if (folder !== props.folder) return
    offerReextract.value = false
    reResult.value = r
    for (const k of Object.keys(reSelected)) delete reSelected[k]
    for (const d of r.diff) if (d.changed) reSelected[d.column] = true
    if (detail.value) {
      if (r.extraction.jev) detail.value.session.jev = r.extraction.jev
      if (r.extraction.llm) detail.value.session.llm = r.extraction.llm
    }
    for (const w of r.extraction.warnings) app.toast(w, 'info', 8000)
    if (!reChanged.value.length) app.toast('Re-extraction matches the tracker row; nothing to apply.', 'success')
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    reextracting.value = false
  }
}

async function applyReextract() {
  if (!reChosen.value.length) return
  saving.value = true
  try {
    const values: Row = {}
    for (const d of reChosen.value) values[d.column] = d.proposed
    const { report } = await api.writeRow(props.folder, values, Object.keys(values))
    app.toast(`Applied ${Object.keys(report.written).length} column(s) to row ${report.row}`, 'success')
    reResult.value = null
    await load()
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
    await load()
  } finally {
    saving.value = false
  }
}

const cell = (v: DiffEntry['current']) => (v === null || v === undefined || v === '' ? '—' : String(v))

async function editPosting() {
  if (detail.value?.session.folder !== props.folder) return
  postingDraft.value = detail.value.session.posting.text
  showPosting.value = true
  await nextTick()
  postingEditor.value?.focus()
}

async function savePosting() {
  const folder = props.folder
  const text = postingDraft.value
  if (text === null || !canSavePosting.value || postingSaving.value || detail.value?.session.folder !== folder) return
  postingSaving.value = true
  try {
    const posting = await api.setSessionPosting(folder, text)
    if (props.folder !== folder || detail.value?.session.folder !== folder) return
    detail.value.session.posting = posting
    postingDraft.value = null
    reResult.value = null
    offerReextract.value = true
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    postingSaving.value = false
  }
}

function reextractUpdatedPosting() {
  reextractPanel.value?.scrollIntoView({ block: 'nearest' })
  void reextract()
}

async function copyPosting() {
  try {
    await navigator.clipboard.writeText(cleanedPosting.value)
    app.toast('Posting text copied.', 'success', 2000)
  } catch {
    app.toast('Could not copy the posting text.', 'error')
  }
}

async function copyPath() {
  try {
    await navigator.clipboard.writeText(folderPath.value)
    app.toast('Folder path copied.', 'success', 2000)
  } catch {
    app.toast(folderPath.value, 'info', 8000)
  }
}

function onFilesChanged(v: FilesView) {
  if (!detail.value) return
  detail.value.session.files = v.files
  detail.value.session.upload_mode = v.upload_mode
  detail.value.session.upload_mode_source = v.upload_mode_source
}

function onQaChanged(v: QAView) {
  if (detail.value) detail.value.session.qa = v.qa
}

const tabLabel = (t: string) => {
  if (!detail.value) return t
  if (t === 'files') return `files (${detail.value.session.files.inputs.length})`
  if (t === 'questions') {
    const qs = detail.value.session.qa.questions
    const pending = qs.filter((q) => q.status === 'pending').length
    return `questions (${qs.length}${pending ? `, ${pending} pending` : ''})`
  }
  return t
}

const pretty = (o: unknown) => JSON.stringify(o, null, 2)
</script>

<template>
  <div v-if="detail" class="space-y-4">
    <PageHeader>
      <template #default>
        <h1 class="font-mono text-lg font-semibold">{{ folder }}</h1>
        <p class="text-xs text-slate-500">
          created {{ fmtDate(detail.session.created_at) }} · upload mode <span class="font-mono">{{ detail.session.upload_mode }}</span>
          <span v-if="detail.session.review.written_at"> · last Excel write {{ detail.session.review.written_at.slice(0, 16).replace('T', ' ') }}</span>
        </p>
      </template>
      <template #actions>
        <button class="btn-secondary toolbar-control" :disabled="duplicating || app.trackerLocked" :title="app.trackerLocked ? 'Close Excel first' : undefined" @click="openDuplicate">Duplicate…</button>
        <button class="btn-secondary toolbar-control" @click="copyPath" title="Copy folder path">Copy path</button>
      </template>
    </PageHeader>

    <div v-if="showDuplicate" class="card space-y-3 border-indigo-200">
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="font-semibold">Duplicate application <span class="text-xs font-normal text-slate-500">(new folder dated today; edit identifying fields before create — folder name is fixed after)</span></h3>
        <button type="button" class="text-sm text-slate-500 hover:text-slate-800" :disabled="duplicating" @click="showDuplicate = false">Cancel</button>
      </div>
      <p class="text-sm text-slate-600">Copies posting + Jev/LLM into a new session. Files and questions start empty. Change Requisition_ID (and anything else) here for a same-role / different-req listing.</p>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <FieldInput v-for="c in DUPLICATE_FIELDS" :key="c" :column="c" :model-value="dupForm[c] ?? null" @update:model-value="(v) => setDupField(c, v)" />
      </div>
      <div class="flex justify-end">
        <button class="btn-primary" :disabled="duplicating || app.trackerLocked" @click="confirmDuplicate">{{ duplicating ? 'Creating…' : 'Create duplicate' }}</button>
      </div>
    </div>

    <div v-if="detail.session.review.pending_write" class="flex items-center justify-between rounded-md bg-amber-50 p-3 text-sm text-amber-900">
      <span>Excel write pending for: <span class="font-mono">{{ Object.keys(detail.session.review.pending_write.values).join(', ') }}</span>. Close Excel, then retry.</span>
      <button class="btn-primary" :disabled="saving || postingSaving || app.trackerLocked" :title="app.trackerLocked ? 'Close Excel first' : undefined" @click="retry">Retry</button>
    </div>
    <div v-if="detail.row_error" class="rounded-md bg-red-50 p-3 text-sm text-red-800">Tracker could not be read: {{ detail.row_error }}</div>
    <div v-else-if="!detail.row" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900">No row in the tracker for this folder yet. Saving will create one.</div>

    <nav class="flex gap-1 border-b border-slate-200 text-sm">
      <button v-for="t in (['overview', 'files', 'questions', 'notes', 'log'] as const)" :key="t" class="-mb-px border-b-2 px-3 py-2 capitalize" :class="tab === t ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'" @click="tab = t">{{ tabLabel(t) }}</button>
    </nav>

    <section v-if="tab === 'overview'" class="space-y-4">
      <div class="card space-y-3">
        <div class="flex items-baseline justify-between">
          <h3 class="font-semibold">Tracker row <span class="text-xs font-normal text-slate-500">(values read from Excel; your edits overwrite)</span></h3>
          <button class="btn-primary" :disabled="saving || postingSaving || !dirty.length || app.trackerLocked" :title="app.trackerLocked ? 'Close Excel first' : undefined" @click="save">{{ saving ? 'Saving…' : `Save ${dirty.length ? `(${dirty.length})` : ''}` }}</button>
        </div>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <FieldInput
            v-for="c in columns"
            :key="c"
            :column="c"
            :model-value="form[c] ?? null"
            :hint="dirty.includes(c) ? '• edited' : undefined"
            :estimated="c === 'Compensation' ? compensationEstimated : undefined"
            @update:model-value="(v) => setField(c, v)"
            @update:estimated="setCompensationEstimated"
          />
        </div>
      </div>

      <div ref="reextractPanel" class="card space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="font-semibold">Re-extract <span class="text-xs font-normal text-slate-500">(run the selected services on the stored posting, then review differences)</span></h3>
          <div class="flex items-center gap-3 text-sm">
            <label class="flex items-center gap-1"><input v-model="reUseJev" type="checkbox" /> Jev</label>
            <label class="flex items-center gap-1"><input v-model="reUseLlm" type="checkbox" /> {{ app.modelProviderLabel }}</label>
            <button class="btn-secondary" :disabled="reextracting || saving || postingDraft !== null" @click="reextract">{{ reextracting ? 'Extracting…' : 'Re-extract' }}</button>
          </div>
        </div>
        <template v-if="reResult">
          <p v-if="!reChanged.length" class="text-sm text-slate-500">No differences against the tracker row.</p>
          <template v-else>
            <table class="w-full text-sm">
              <thead class="text-left text-xs uppercase text-slate-500">
                <tr><th class="w-8 py-1"></th><th class="py-1">Column</th><th class="py-1">Tracker</th><th class="py-1">Proposed</th></tr>
              </thead>
              <tbody>
                <tr v-for="d in reChanged" :key="d.column" class="border-t border-slate-100">
                  <td class="py-1"><input v-model="reSelected[d.column]" type="checkbox" /></td>
                  <td class="py-1 font-mono text-xs">{{ d.column }}</td>
                  <td class="py-1 text-slate-500">{{ cell(d.current) }}</td>
                  <td class="py-1" :class="reSelected[d.column] ? 'font-medium text-emerald-700' : ''">{{ cell(d.proposed) }}</td>
                </tr>
              </tbody>
            </table>
            <div class="flex items-center justify-end gap-3">
              <span class="text-xs text-slate-500">Selected columns overwrite the tracker cell.</span>
              <button class="btn-primary" :disabled="saving || postingDraft !== null || !reChosen.length || app.trackerLocked" :title="app.trackerLocked ? 'Close Excel first' : undefined" @click="applyReextract">Apply {{ reChosen.length ? `(${reChosen.length})` : '' }}</button>
            </div>
          </template>
        </template>
      </div>

      <div class="card space-y-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <button type="button" class="text-sm font-semibold" :aria-expanded="showPosting" :disabled="postingDraft !== null" @click="showPosting = !showPosting">{{ showPosting ? '▾' : '▸' }} Posting text<span v-if="detail.session.posting.url" class="ml-2 text-xs font-normal text-slate-500">{{ detail.session.posting.url }}</span></button>
          <div v-if="postingDraft === null" class="flex gap-2">
            <button type="button" class="btn-secondary" :disabled="reextracting || postingSaving" @click="editPosting">Edit posting</button>
            <button type="button" class="btn-secondary" @click="copyPosting">Copy all</button>
          </div>
        </div>
        <form v-if="postingDraft !== null" class="space-y-2" @submit.prevent="savePosting">
          <label class="block">
            <span class="label">Edit posting text</span>
            <textarea ref="postingEditor" v-model="postingDraft" rows="12" class="input resize-y font-mono text-xs" :readonly="postingSaving" required />
          </label>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn-secondary" :disabled="postingSaving" @click="postingDraft = null">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="!canSavePosting || postingSaving || saving">{{ postingSaving ? 'Saving…' : 'Save posting' }}</button>
          </div>
        </form>
        <template v-else>
          <div v-if="offerReextract" class="flex flex-wrap items-center justify-between gap-2 rounded-md bg-indigo-50 p-3 text-sm text-indigo-900">
            <p role="status">Posting saved. Re-extract to review possible updates to the tracker fields.</p>
            <div class="flex gap-2">
              <button type="button" class="btn-primary" :disabled="reextracting || saving" @click="reextractUpdatedPosting">Re-extract now</button>
              <button type="button" class="btn-secondary" @click="offerReextract = false">Dismiss</button>
            </div>
          </div>
          <pre v-if="showPosting" class="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{{ cleanedPosting }}</pre>
        </template>
      </div>
    </section>

    <section v-else-if="tab === 'files'">
      <FilesPanel :folder="folder" @changed="onFilesChanged" />
    </section>

    <section v-else-if="tab === 'questions'">
      <QaPanel :folder="folder" @changed="onQaChanged" />
    </section>

    <section v-else-if="tab === 'notes'">
      <textarea
        class="input min-h-[28rem] w-full resize-y font-normal"
        :value="notesDraft"
        placeholder=""
        @input="onNotesInput"
        @blur="saveNotes"
      />
    </section>

    <section v-else-if="tab === 'log'" class="grid gap-4 lg:grid-cols-2">
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
  <div v-else class="space-y-4">
    <PageHeader title="Application" />
    <p class="text-sm text-slate-500">{{ loading ? 'Loading…' : 'Session not found.' }}</p>
  </div>
</template>
