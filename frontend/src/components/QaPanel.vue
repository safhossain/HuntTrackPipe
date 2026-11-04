<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, type Limit, type QAView, type Question } from '../api/client'
import { useAppStore } from '../stores/app'
import { errorText } from '../utils'

const props = defineProps<{ folder: string }>()
const emit = defineEmits<{ changed: [view: QAView] }>()
const app = useAppStore()

const view = ref<QAView | null>(null)
const busy = ref<string | null>(null)

// add form
const newText = ref('')
const onePerLine = ref(false)
const newLimitUnit = ref<'chars' | 'words' | ''>('')
const newLimitValue = ref<number | null>(null)

// per-question editing state
const editing = reactive<Record<string, { text: string; unit: 'chars' | 'words' | ''; value: number | null }>>({})
const drafts = reactive<Record<string, string>>({}) // answer textareas
const feedback = reactive<Record<string, string>>({})
const showFeedback = reactive<Record<string, boolean>>({})

const questions = computed(() => view.value?.qa.questions ?? [])
const pending = computed(() => questions.value.filter((q) => q.status === 'pending'))
const dirtyAnswers = computed(() => questions.value.filter((q) => (drafts[q.id] ?? q.answer ?? '') !== (q.answer ?? '')))

/** Merge server QA into local state. Only overwrite answer drafts listed in
 * ``overwriteDraftIds`` (or all on first load). Unsaved typing in other
 * question boxes is preserved across Save / Answer / Regenerate. */
function apply(v: QAView, overwriteDraftIds: string[] | 'all' = 'all') {
  const prevAnswers = Object.fromEntries((view.value?.qa.questions ?? []).map((q) => [q.id, q.answer ?? '']))
  view.value = v
  const keep = new Set(v.qa.questions.map((q) => q.id))
  for (const id of Object.keys(drafts)) {
    if (!keep.has(id)) delete drafts[id]
  }
  for (const q of v.qa.questions) {
    const server = q.answer ?? ''
    const prevServer = prevAnswers[q.id] ?? ''
    const force = overwriteDraftIds === 'all' || overwriteDraftIds.includes(q.id)
    const dirty = drafts[q.id] !== undefined && drafts[q.id] !== prevServer
    if (force || drafts[q.id] === undefined || !dirty) {
      drafts[q.id] = server
    }
  }
  emit('changed', v)
  for (const w of v.warnings) app.toast(w, 'info', 8000)
}

async function run(label: string, fn: () => Promise<QAView>, okMsg?: string, overwriteDraftIds: string[] | 'all' = []) {
  busy.value = label
  try {
    apply(await fn(), overwriteDraftIds)
    if (okMsg) app.toast(okMsg, 'success', 3000)
  } catch (e) {
    app.toast(errorText(e), 'error', 12000)
  } finally {
    busy.value = null
  }
}

onMounted(async () => {
  try {
    apply(await api.qa(props.folder), 'all')
  } catch (e) {
    app.toast(errorText(e), 'error')
  }
})

function limitFrom(unit: 'chars' | 'words' | '', value: number | null): Limit | null {
  return unit && value && value > 0 ? { unit, value } : null
}

async function add() {
  const lines = onePerLine.value ? newText.value.split(/\r?\n/) : [newText.value]
  const items = lines.map((t) => t.trim()).filter(Boolean).map((text) => ({ text, limit: limitFrom(newLimitUnit.value, newLimitValue.value) }))
  if (!items.length) return
  await run('add', () => api.addQuestions(props.folder, items), `Added ${items.length} question(s)`, [])
  newText.value = ''
}

function startEdit(q: Question) {
  editing[q.id] = { text: q.text, unit: q.limit?.unit ?? '', value: q.limit?.value ?? null }
}
async function saveEdit(q: Question) {
  const e = editing[q.id]
  if (!e) return
  const limit = limitFrom(e.unit, e.value)
  await run(`edit-${q.id}`, () => api.updateQuestion(props.folder, q.id, { text: e.text, limit, clear_limit: !limit }), undefined, [])
  delete editing[q.id]
}
const cancelEdit = (q: Question) => delete editing[q.id]

const saveAnswer = (q: Question) =>
  run(`answer-${q.id}`, () => api.updateQuestion(props.folder, q.id, { answer: drafts[q.id] ?? '' }), 'Answer saved', [q.id])
const remove = (q: Question) => {
  if (!confirm(`Delete this question?\n\n${q.text}`)) return
  return run(`del-${q.id}`, () => api.deleteQuestion(props.folder, q.id), undefined, [])
}
const answerPending = () => {
  const ids = pending.value.map((q) => q.id)
  return run('answer', () => api.answerQuestions(props.folder, null), `Answered ${ids.length} question(s)`, ids)
}
const answerOne = (q: Question) => run(`gen-${q.id}`, () => api.answerQuestions(props.folder, [q.id]), undefined, [q.id])
const regenerate = (q: Question) =>
  run(`gen-${q.id}`, () => api.regenerate(props.folder, q.id, (feedback[q.id] ?? '').trim() || null), 'Regenerated', [q.id]).then(() => {
    showFeedback[q.id] = false
  })

async function move(i: number, dir: -1 | 1) {
  const order = questions.value.map((q) => q.id)
  const j = i + dir
  if (j < 0 || j >= order.length) return
  ;[order[i], order[j]] = [order[j]!, order[i]!]
  await run('order', () => api.reorderQuestions(props.folder, order), undefined, [])
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    app.toast('Copied.', 'success', 1500)
  } catch {
    app.toast('Clipboard blocked; select the text and copy manually.', 'error')
  }
}

function measure(text: string, limit: Limit | null) {
  if (!limit) return `${text.length} chars · ${text.trim() ? text.trim().split(/\s+/).length : 0} words`
  const n = limit.unit === 'chars' ? text.length : text.trim() ? text.trim().split(/\s+/).length : 0
  return `${n} / ${limit.value} ${limit.unit}`
}
function over(text: string, limit: Limit | null) {
  if (!limit) return false
  const n = limit.unit === 'chars' ? text.length : text.trim() ? text.trim().split(/\s+/).length : 0
  return n > limit.value
}
const answersUrl = computed(() => (view.value?.answers_md ? api.downloadUrl(props.folder, view.value.answers_md, true) : null))
</script>

<template>
  <div v-if="view" class="space-y-4">
    <div v-if="!view.candidate_context_exists" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
      <p class="font-medium">Candidate context missing.</p>
      <p>Answers are written only from facts you provide. Create <span class="font-mono">{{ view.candidate_context_path }}</span> as plain text (background, education, work and projects with concrete results, skills and tools, what you are looking for and why). It is read fresh on every call, so you can refine it any time. You can still add questions now.</p>
    </div>

    <!-- add -->
    <div class="card space-y-2">
      <h3 class="font-semibold">Add question<span v-if="onePerLine">s</span></h3>
      <textarea v-model="newText" class="input min-h-20 font-normal" :rows="onePerLine ? 4 : 2" :placeholder="onePerLine ? 'One question per line…' : 'Paste the question from the application form…'" />
      <div class="flex flex-wrap items-center gap-3 text-sm">
        <label class="flex items-center gap-1"><input v-model="onePerLine" type="checkbox" /> one per line</label>
        <label class="flex items-center gap-1">
          limit
          <select v-model="newLimitUnit" class="input w-auto">
            <option value="">none</option>
            <option value="chars">characters</option>
            <option value="words">words</option>
          </select>
          <input v-model.number="newLimitValue" type="number" min="1" class="input w-24" :disabled="!newLimitUnit" placeholder="max" />
        </label>
        <button class="btn-primary ml-auto" :disabled="!!busy || !newText.trim()" @click="add">Add</button>
      </div>
    </div>

    <!-- toolbar -->
    <div class="flex flex-wrap items-center gap-2 text-sm">
      <button class="btn-primary" :disabled="!!busy || !pending.length || !view.candidate_context_exists" @click="answerPending" :title="view.candidate_context_exists ? 'One Claude call for every pending question' : 'Create the candidate context file first'">
        {{ busy === 'answer' ? 'Answering…' : `Answer pending (${pending.length})` }}
      </button>
      <a v-if="answersUrl" :href="answersUrl" target="_blank" class="btn-secondary">Open answers.md</a>
      <span class="ml-auto text-xs text-slate-500">
        <template v-if="view.organization || view.title">for {{ [view.organization, view.title].filter(Boolean).join(' · ') }} · </template>
        <template v-if="view.qa.usage.input_tokens">{{ view.qa.usage.input_tokens }} in / {{ view.qa.usage.output_tokens ?? 0 }} out tokens total</template>
        <template v-else>no model calls yet</template>
      </span>
    </div>

    <!-- list -->
    <p v-if="!questions.length" class="text-sm text-slate-500">No questions yet.</p>
    <div v-for="(q, i) in questions" :key="q.id" class="card space-y-2">
      <div class="flex items-start gap-2">
        <span class="mt-0.5 w-6 shrink-0 text-right text-xs text-slate-400">{{ i + 1 }}.</span>
        <div class="min-w-0 flex-1">
          <template v-if="editing[q.id]">
            <textarea v-model="editing[q.id]!.text" class="input" rows="2" />
            <div class="mt-1 flex flex-wrap items-center gap-2 text-xs">
              limit
              <select v-model="editing[q.id]!.unit" class="input w-auto">
                <option value="">none</option>
                <option value="chars">characters</option>
                <option value="words">words</option>
              </select>
              <input v-model.number="editing[q.id]!.value" type="number" min="1" class="input w-24" :disabled="!editing[q.id]!.unit" />
              <button class="btn-primary" :disabled="!!busy || !editing[q.id]!.text.trim()" @click="saveEdit(q)">Save</button>
              <button class="btn-secondary" @click="cancelEdit(q)">Cancel</button>
            </div>
          </template>
          <template v-else>
            <p class="text-sm font-medium">{{ q.text }}</p>
            <p class="text-xs text-slate-500">
              <span class="chip" :class="q.status === 'answered' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'">{{ q.status }}</span>
              <span v-if="q.limit" class="ml-1">max {{ q.limit.value }} {{ q.limit.unit }}</span>
              <span v-else class="ml-1">no limit</span>
              <span v-if="q.model" class="ml-1">· {{ q.model }}</span>
              <span v-if="q.answered_at" class="ml-1">· {{ q.answered_at.slice(0, 16).replace('T', ' ') }}</span>
            </p>
          </template>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <button class="btn-secondary px-2" :disabled="!!busy || i === 0" title="Move up" @click="move(i, -1)">▲</button>
          <button class="btn-secondary px-2" :disabled="!!busy || i === questions.length - 1" title="Move down" @click="move(i, 1)">▼</button>
          <button v-if="!editing[q.id]" class="btn-secondary" :disabled="!!busy" @click="startEdit(q)">Edit</button>
          <button class="btn-secondary px-2 text-red-600 hover:bg-red-50" :disabled="!!busy" title="Delete" @click="remove(q)">✕</button>
        </div>
      </div>

      <div v-if="q.note" class="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">{{ q.note }}</div>

      <textarea v-model="drafts[q.id]" class="input min-h-24 font-normal" :class="over(drafts[q.id] ?? '', q.limit) && 'border-red-400'" rows="4" :placeholder="q.status === 'pending' ? 'No answer yet. Click Answer, or type your own.' : ''" />
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span :class="over(drafts[q.id] ?? '', q.limit) ? 'font-medium text-red-600' : 'text-slate-500'">{{ measure(drafts[q.id] ?? '', q.limit) }}</span>
        <span class="ml-auto" />
        <button v-if="dirtyAnswers.some((d) => d.id === q.id)" class="btn-primary" :disabled="!!busy" @click="saveAnswer(q)">Save answer</button>
        <button class="btn-secondary" :disabled="!!busy || !(drafts[q.id] ?? '').trim()" @click="copy(drafts[q.id] ?? '')">Copy</button>
        <button v-if="q.status === 'pending'" class="btn-secondary" :disabled="!!busy || !view.candidate_context_exists" @click="answerOne(q)">{{ busy === `gen-${q.id}` ? 'Answering…' : 'Answer' }}</button>
        <template v-else>
          <button class="btn-secondary" :disabled="!!busy || !view.candidate_context_exists" @click="showFeedback[q.id] = !showFeedback[q.id]">Regenerate…</button>
        </template>
      </div>
      <div v-if="showFeedback[q.id]" class="flex gap-2">
        <input v-model="feedback[q.id]" class="input" placeholder="Optional feedback, e.g. 'mention the Kafka project, less formal'" @keydown.enter="regenerate(q)" />
        <button class="btn-primary" :disabled="!!busy" @click="regenerate(q)">{{ busy === `gen-${q.id}` ? 'Working…' : 'Go' }}</button>
      </div>
    </div>
  </div>
  <div v-else class="text-sm text-slate-500">Loading questions…</div>
</template>
