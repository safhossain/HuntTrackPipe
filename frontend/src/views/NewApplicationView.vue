<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ApiError, api, type DuplicateHit, type ExtractResponse, type Row, type RowValue } from '../api/client'
import FieldInput from '../components/FieldInput.vue'
import JevPanel from '../components/JevPanel.vue'
import { useAppStore } from '../stores/app'
import { cleanPostingText, errorText, todayIso } from '../utils'

const app = useAppStore()
const router = useRouter()

const posting = ref('')
const url = ref('')
const useJev = ref(true)
const useLlm = ref(true)
const extracting = ref(false)
const creating = ref(false)

const result = ref<ExtractResponse | null>(null)
const duplicates = ref<DuplicateHit[]>([])
const values = reactive<Row>({})
const manual = reactive<Row>({
  Applied_Date: todayIso(),
  Application_Status: 'Not Applied',
  Outcome: 'Pending',
})
const compensationEstimated = ref(false)

const extractedCols = computed(() => app.meta?.extracted_columns ?? [])
const manualCols = computed(() => app.meta?.manual_columns ?? [])
const cleanedPosting = computed(() => cleanPostingText(posting.value))

async function copyPosting() {
  try {
    await navigator.clipboard.writeText(cleanedPosting.value)
    app.toast('Posting text copied.', 'success', 2000)
  } catch {
    app.toast('Could not copy the posting text.', 'error')
  }
}

function setRow(target: Row, col: string, v: RowValue) {
  target[col] = v
}

function setCompensationEstimated(v: boolean) {
  compensationEstimated.value = v
}

async function runExtract() {
  if (!posting.value.trim()) return app.toast('Paste a posting first.', 'error')
  extracting.value = true
  result.value = null
  try {
    const r = await api.extract(posting.value, useJev.value, useLlm.value)
    result.value = r
    duplicates.value = r.duplicates ?? []
    for (const c of extractedCols.value) values[c] = r.values[c] ?? null
    if (url.value && !manual.Posting_URL) manual.Posting_URL = url.value
    for (const w of r.warnings) app.toast(w, 'info', 8000)
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    extracting.value = false
  }
}

async function create(allowDuplicate = false) {
  if (!result.value) return
  if (!allowDuplicate && duplicates.value.length) {
    const list = duplicates.value.map((d) => `${d.folder} (${d.reason})`).join('\n')
    if (!confirm(`This posting looks like an existing application:\n\n${list}\n\nCreate a second application anyway?`)) return
    allowDuplicate = true
  }
  creating.value = true
  try {
    const { session, report } = await api.createSession({
      posting_text: posting.value,
      posting_url: url.value.trim() || null,
      extraction: { ...result.value, values: { ...values } },
      manual: { ...manual },
      allow_duplicate: allowDuplicate,
      compensation_estimated: compensationEstimated.value,
    })
    app.toast(`Created ${session.folder} (row ${report.row})`, 'success')
    const skipped = Object.keys(report.skipped)
    if (skipped.length) app.toast(`Not overwritten (cell already had a value): ${skipped.join(', ')}`, 'info', 8000)
    router.push({ name: 'session', params: { folder: session.folder } })
  } catch (e) {
    if (e instanceof ApiError && e.isDuplicate) {
      // Server-side check caught something the extract step did not (e.g. a session created meanwhile).
      duplicates.value = e.duplicates
      creating.value = false
      return create(false)
    }
    app.toast(errorText(e), 'error', 10000)
  } finally {
    creating.value = false
  }
}

const hintFor = (col: string) => {
  if (!result.value) return undefined
  if (col in result.value.derived.direct_values) return '(Jev)'
  const llmField = col.toLowerCase()
  if (result.value.llm && llmField in result.value.llm.output) return '(LLM)'
  return '(not in posting)'
}
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">New application</h1>

    <div class="card space-y-3">
      <label class="block">
        <span class="label">Job posting text</span>
        <textarea v-model="posting" rows="10" class="input font-mono text-xs" placeholder="Paste the full posting here…" />
      </label>
      <div class="flex flex-wrap items-end gap-3">
        <label class="block grow">
          <span class="label">Posting URL (optional)</span>
          <input v-model="url" type="url" class="input" placeholder="https://…" />
        </label>
        <label class="flex items-center gap-1 text-sm"><input v-model="useJev" type="checkbox" /> Jev</label>
        <label class="flex items-center gap-1 text-sm"><input v-model="useLlm" type="checkbox" /> LLM</label>
        <button class="btn-primary" :disabled="extracting || !posting.trim()" @click="runExtract">
          {{ extracting ? 'Extracting…' : 'Run extraction' }}
        </button>
      </div>
      <p class="text-xs text-slate-500">{{ posting.length.toLocaleString() }} chars · ~{{ Math.round(posting.length / 3.5).toLocaleString() }} tokens</p>
    </div>

    <div v-if="result && duplicates.length" class="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <p class="font-medium">Possible duplicate</p>
      <ul class="mt-1 list-disc pl-5">
        <li v-for="d in duplicates" :key="d.folder">
          <RouterLink :to="{ name: 'session', params: { folder: d.folder } }" class="underline">{{ d.folder }}</RouterLink>
          <span class="text-amber-700"> · {{ d.reason }}</span>
        </li>
      </ul>
      <p class="mt-1 text-xs text-amber-700">You will be asked to confirm before a second application is created.</p>
    </div>

    <div v-if="result" class="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <JevPanel :jev="result.jev" :derived="result.derived" :warnings="result.warnings" />

      <div class="space-y-4">
        <div class="card space-y-3">
          <div class="flex items-baseline justify-between">
            <h3 class="font-semibold">Extracted fields <span class="text-xs font-normal text-slate-500">(edit before creating)</span></h3>
            <span v-if="result.llm" class="text-xs text-slate-500">{{ result.llm.model }} · {{ (result.llm.usage as any)?.input_tokens }} in / {{ (result.llm.usage as any)?.output_tokens }} out</span>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <FieldInput
              v-for="c in extractedCols"
              :key="c"
              :column="c"
              :model-value="values[c] ?? null"
              :hint="hintFor(c)"
              :estimated="c === 'Compensation' ? compensationEstimated : undefined"
              @update:model-value="(v) => setRow(values, c, v)"
              @update:estimated="setCompensationEstimated"
            />
          </div>
        </div>

        <div class="card space-y-3">
          <h3 class="font-semibold">Manual fields</h3>
          <div class="grid gap-3 sm:grid-cols-2">
            <FieldInput v-for="c in manualCols" :key="c" :column="c" :model-value="manual[c] ?? null" @update:model-value="(v) => setRow(manual, c, v)" />
          </div>
        </div>

        <div class="flex items-center justify-end gap-3">
          <span class="text-xs text-slate-500">{{ app.trackerLocked ? 'Tracker is open in Excel — close it to create.' : 'Creates the folder, posting.txt, session.json and the tracker row.' }}</span>
          <button class="btn-primary" :disabled="creating || app.trackerLocked" :title="app.trackerLocked ? 'Close Excel first' : undefined" @click="create()">{{ creating ? 'Creating…' : 'Create application' }}</button>
        </div>
      </div>
    </div>

    <div v-if="result" class="card space-y-2">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-sm font-semibold">Posting text <span class="text-xs font-normal text-slate-500">trimmed; wrapped lines joined, paragraph breaks kept</span></h3>
        <button type="button" class="btn-secondary" @click="copyPosting">Copy all</button>
      </div>
      <pre class="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{{ cleanedPosting }}</pre>
    </div>
  </div>
</template>
