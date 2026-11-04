<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type FilesView, type InputFile } from '../api/client'
import { useAppStore } from '../stores/app'
import { UPLOAD_MODE_LABELS, errorText, extOf, fmtBytes } from '../utils'
import ConvertAllPdfButton from './ConvertAllPdfButton.vue'
import ConvertTargetButton from './ConvertTargetButton.vue'

const props = defineProps<{ folder: string }>()
const emit = defineEmits<{ changed: [view: FilesView] }>()
const app = useAppStore()

const view = ref<FilesView | null>(null)
const busy = ref<string | null>(null) // label of the running action
const dragOver = ref(false)
const dragIndex = ref<number | null>(null)
const overIndex = ref<number | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const brokenThumbs = ref<Set<string>>(new Set())

const inputs = computed(() => view.value?.files.inputs ?? [])
const typedIndices = computed(() => inputs.value.filter((i) => i.doc_type).map((i) => i.index))
const nonPdfCount = computed(() => inputs.value.filter((i) => extOf(i.file) !== 'pdf').length)
const combineHighlight = computed(() => view.value?.upload_mode === 'single_combined_file')
const finalsHighlight = computed(() => view.value?.upload_mode === 'separate_uploads' || view.value?.upload_mode === 'single_document')
const candidate = computed(() => (view.value?.candidate ?? 'Candidate').trim().replace(/\s+/g, '-'))
const combinedName = computed(() => (view.value ? `${candidate.value}_${view.value.x}.pdf` : ''))
const convertTargets = computed(() => view.value?.tools.targets ?? ['pdf', 'docx', 'png', 'jpg'])

function finalName(i: InputFile) {
  if (!view.value || !i.doc_type) return ''
  return `${candidate.value}_${i.doc_type}_${view.value.x}.${extOf(i.file)}`
}

function targetsFor(i: InputFile) {
  const e = extOf(i.file)
  return convertTargets.value.filter((t) => {
    if (t === e || (t === 'jpg' && e === 'jpeg')) return false
    if (t === 'docx') return e === 'pdf' && !!view.value?.tools.pdf2docx
    if (t === 'pdf') return true
    return true // png / jpg from anything that can be rendered
  })
}

function apply(v: FilesView) {
  view.value = v
  emit('changed', v)
}

async function run<T extends FilesView>(label: string, fn: () => Promise<T>, okMsg?: string) {
  busy.value = label
  try {
    apply(await fn())
    if (okMsg) app.toast(okMsg, 'success', 3000)
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    busy.value = null
  }
}

async function load() {
  try {
    apply(await api.files(props.folder))
  } catch (e) {
    app.toast(errorText(e), 'error')
  }
}
onMounted(load)

// ---- uploads ----
function pick() {
  fileInput.value?.click()
}
async function onPicked(ev: Event) {
  const el = ev.target as HTMLInputElement
  const files = Array.from(el.files ?? [])
  el.value = ''
  if (files.length) await addFiles(files)
}
async function onDrop(ev: DragEvent) {
  dragOver.value = false
  if (dragIndex.value !== null) return // internal reorder drag, not a file drop
  const files = Array.from(ev.dataTransfer?.files ?? [])
  if (files.length) await addFiles(files)
}
async function addFiles(files: File[]) {
  await run('upload', () => api.uploadFiles(props.folder, files), `Added ${files.length} file(s)`)
}

// ---- reorder (drag rows or arrows) ----
function onRowDragStart(i: number, ev: DragEvent) {
  dragIndex.value = i
  ev.dataTransfer?.setData('text/plain', String(i))
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move'
}
function onRowDragOver(i: number, ev: DragEvent) {
  if (dragIndex.value === null) return
  ev.preventDefault()
  overIndex.value = i
}
async function onRowDrop(i: number) {
  const from = dragIndex.value
  dragIndex.value = null
  overIndex.value = null
  if (from === null || from === i) return
  await move(from, i)
}
function onRowDragEnd() {
  dragIndex.value = null
  overIndex.value = null
}
async function move(from: number, to: number) {
  const order = inputs.value.map((x) => x.index)
  const [item] = order.splice(from, 1)
  order.splice(to, 0, item!)
  await run('reorder', () => api.reorderFiles(props.folder, order))
}

// ---- per-file actions ----
const setDocType = (i: InputFile, v: string) => run('doctype', () => api.setDocType(props.folder, i.index, v || null))
const remove = (i: InputFile) => {
  if (!confirm(`Delete ${i.file} from the folder?`)) return
  return run('delete', () => api.deleteInput(props.folder, i.index), `Deleted ${i.file}`)
}
const convertOne = (i: InputFile, target: string) => {
  if (!target) return
  const label = target === 'docx' ? 'DOCX (lossy)' : target.toUpperCase()
  return run(
    `convert-${i.index}-${target}`,
    () => api.convertInput(props.folder, i.index, target),
    `Converted ${i.file} → ${label}`,
  )
}
const makeFinal = (i: InputFile) => run(`final-${i.index}`, () => api.makeFinals(props.folder, [i.index]), `Made ${finalName(i)}`)
const makeAllFinals = () => run('finals', () => api.makeFinals(props.folder, null), `Made ${typedIndices.value.length} final file(s)`)
const combineAll = () => run('combine', () => api.combine(props.folder, null), `Combined into ${combinedName.value}`)
const convertAllPdf = () =>
  run(
    'convert-all-pdf',
    () => api.convertAllToPdf(props.folder),
    `Converted ${nonPdfCount.value} file(s) to PDF`,
  )
const deleteOutput = (name: string) => {
  if (!confirm(`Delete ${name}?`)) return
  return run('delete-output', () => api.deleteOutput(props.folder, name), `Deleted ${name}`)
}
const adopt = (name: string) => run('adopt', () => api.adoptFile(props.folder, name), `Adopted ${name}`)
const setMode = (mode: string) => run('mode', () => api.setUploadMode(props.folder, mode))

const thumb = (i: InputFile) => api.thumbUrl(props.folder, i.file, i.added_at)
const dl = (name: string, inline = false) => api.downloadUrl(props.folder, name, inline)
const fromLabel = (idx: number | null) => (idx === null ? 'source removed' : (inputs.value[idx]?.file ?? `#${idx}`))
</script>

<template>
  <div v-if="view" class="space-y-4">
    <!-- mode + hints -->
    <div class="card flex flex-wrap items-center gap-4 text-sm">
      <label class="flex items-center gap-2">
        <span class="label mb-0">Upload mode</span>
        <select class="input w-auto" :value="view.upload_mode" :disabled="!!busy" @change="setMode(($event.target as HTMLSelectElement).value)">
          <option v-for="m in app.meta?.upload_modes ?? Object.keys(UPLOAD_MODE_LABELS)" :key="m" :value="m">{{ UPLOAD_MODE_LABELS[m] ?? m }}</option>
        </select>
        <span class="text-xs text-slate-500">{{ view.upload_mode_source === 'jev' ? 'from Jev' : 'your override' }}</span>
      </label>
      <div v-if="view.required_docs.length" class="flex items-center gap-1 text-xs text-slate-600">
        Posting asks for:
        <span v-for="d in view.required_docs" :key="d" class="chip bg-sky-100 text-sky-800">{{ d }}</span>
      </div>
      <div class="ml-auto text-xs text-slate-500">
        <span v-if="!view.tools.soffice" class="text-amber-700">LibreOffice not found: Office → PDF disabled.</span>
        <span v-else>{{ '{X}' }} = <span class="font-mono">{{ view.x }}</span></span>
      </div>
    </div>

    <div v-if="view.missing.length" class="rounded-md bg-red-50 p-3 text-sm text-red-800">
      Missing on disk: <span class="font-mono">{{ view.missing.join(', ') }}</span>. They were moved or deleted outside the app.
    </div>

    <!-- drop zone -->
    <div
      class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-sm transition"
      :class="dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-white hover:bg-slate-50'"
      @click="pick"
      @dragover.prevent="dragOver = dragIndex === null"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
    >
      <span class="font-medium">Drop files here or click to browse</span>
      <span class="mt-1 text-xs text-slate-500">PDF, DOCX, PNG, JPG… Saved as <span class="font-mono">{count}_&lt;name&gt;.&lt;ext&gt;</span> in the application folder.</span>
      <input ref="fileInput" type="file" multiple class="hidden" @change="onPicked" />
    </div>

    <!-- inputs -->
    <div class="card space-y-2">
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="font-semibold">Inputs <span class="text-xs font-normal text-slate-500">({{ inputs.length }}) · drag to reorder; order = combine order</span></h3>
        <div class="flex flex-wrap items-center justify-end gap-2">
          <ConvertAllPdfButton
            :disabled="!!busy || !nonPdfCount"
            :busy="busy === 'convert-all-pdf'"
            :title="nonPdfCount ? `Convert ${nonPdfCount} non-PDF input(s) to PDF (results added as new inputs)` : 'No non-PDF inputs'"
            @click="convertAllPdf"
          />
          <button class="btn-secondary" :class="finalsHighlight && 'ring-2 ring-indigo-300'" :disabled="!!busy || !typedIndices.length" @click="makeAllFinals" :title="`Copy each typed input to ${candidate}_{DocType}_${view.x}.<ext>`">
            {{ busy === 'finals' ? 'Working…' : `Make finals (${typedIndices.length})` }}
          </button>
          <button class="btn-primary" :class="combineHighlight && 'ring-2 ring-indigo-300 ring-offset-1'" :disabled="!!busy || !inputs.length" @click="combineAll" :title="`Merge all inputs into ${combinedName}`">
            {{ busy === 'combine' ? 'Combining…' : 'Combine → PDF' }}
          </button>
        </div>
      </div>

      <p v-if="!inputs.length" class="text-sm text-slate-500">No files yet.</p>
      <ul v-else class="divide-y divide-slate-100">
        <li
          v-for="(i, pos) in inputs"
          :key="i.file + i.added_at"
          class="flex items-center gap-3 py-2"
          :class="[overIndex === pos && dragIndex !== pos ? 'bg-indigo-50' : '', dragIndex === pos ? 'opacity-50' : '']"
          draggable="true"
          @dragstart="onRowDragStart(pos, $event)"
          @dragover="onRowDragOver(pos, $event)"
          @drop.prevent="onRowDrop(pos)"
          @dragend="onRowDragEnd"
        >
          <span class="cursor-grab select-none text-slate-400" title="Drag to reorder">⋮⋮</span>
          <a :href="dl(i.file, true)" target="_blank" class="block h-20 w-16 shrink-0 overflow-hidden rounded border border-slate-200 bg-slate-50" :title="`Open ${i.file}`">
            <img v-if="!brokenThumbs.has(i.file)" :src="thumb(i)" :alt="i.file" class="h-full w-full object-cover object-top" loading="lazy" @error="brokenThumbs.add(i.file)" />
            <span v-else class="flex h-full items-center justify-center font-mono text-xs uppercase text-slate-500">{{ extOf(i.file) }}</span>
          </a>
          <div class="min-w-0 flex-1 space-y-1.5">
            <div class="min-w-0">
              <div class="truncate font-mono text-sm" :title="i.file">{{ i.file }}</div>
              <div class="truncate text-xs text-slate-500">
                {{ i.original }} · {{ fmtBytes(i.size) }}<span v-if="i.pages"> · {{ i.pages }} page{{ i.pages === 1 ? '' : 's' }}</span>
                <span v-if="i.doc_type" class="text-slate-400"> · final → <span class="font-mono">{{ finalName(i) }}</span></span>
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-1">
              <select class="input w-36" :value="i.doc_type ?? ''" :disabled="!!busy" @change="setDocType(i, ($event.target as HTMLSelectElement).value)">
                <option value="">— type —</option>
                <option v-for="d in app.meta?.doc_types ?? []" :key="d" :value="d">{{ d }}</option>
              </select>
              <ConvertTargetButton
                v-for="t in targetsFor(i)"
                :key="t"
                :target="t"
                :disabled="!!busy"
                :busy="busy === `convert-${i.index}-${t}`"
                :title="t === 'docx' ? 'Convert → DOCX (lossy); result added as a new input' : `Convert → ${t.toUpperCase()}; result added as a new input`"
                @click="convertOne(i, t)"
              />
              <span class="mx-1 h-5 border-l border-slate-200" />
              <button class="btn-secondary px-2" :disabled="!!busy || pos === 0" title="Move up" @click="move(pos, pos - 1)">▲</button>
              <button class="btn-secondary px-2" :disabled="!!busy || pos === inputs.length - 1" title="Move down" @click="move(pos, pos + 1)">▼</button>
              <button class="btn-secondary" :disabled="!!busy || !i.doc_type" :title="i.doc_type ? `Copy to ${finalName(i)}` : 'Pick a document type first'" @click="makeFinal(i)">
                {{ busy === `final-${i.index}` ? '…' : 'Make final' }}
              </button>
              <button class="btn-secondary px-2 text-red-600 hover:bg-red-50" :disabled="!!busy" title="Delete input" @click="remove(i)">✕</button>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!-- outputs -->
    <div class="grid gap-4 lg:grid-cols-2">
      <div class="card space-y-2">
        <h3 class="font-semibold">Final files <span class="text-xs font-normal text-slate-500">{{ candidate }}_{DocType}_{{ view.x }}</span></h3>
        <p v-if="!view.files.finals.length" class="text-sm text-slate-500">None yet. Set a document type on an input and click "Make final".</p>
        <ul v-else class="space-y-1 text-sm">
          <li v-for="f in view.files.finals" :key="f.file" class="flex items-center gap-2">
            <span class="chip bg-slate-100 text-slate-700">{{ f.doc_type }}</span>
            <a :href="dl(f.file, true)" target="_blank" class="min-w-0 flex-1 truncate font-mono text-indigo-700 hover:underline" :title="`from ${fromLabel(f.from)}`">{{ f.file }}</a>
            <a :href="dl(f.file)" class="btn-secondary px-2" title="Download">↓</a>
            <button class="btn-secondary px-2 text-red-600 hover:bg-red-50" :disabled="!!busy" @click="deleteOutput(f.file)">✕</button>
          </li>
        </ul>
      </div>
      <div class="card space-y-2">
        <h3 class="font-semibold">Combined PDF <span class="text-xs font-normal text-slate-500">{{ combinedName }}</span></h3>
        <p v-if="!view.files.combined" class="text-sm text-slate-500">None yet. "Combine → PDF" merges every input, in order, converting non-PDFs first.</p>
        <div v-else class="flex items-center gap-2 text-sm">
          <a :href="dl(view.files.combined.file, true)" target="_blank" class="min-w-0 flex-1 truncate font-mono text-indigo-700 hover:underline">{{ view.files.combined.file }}</a>
          <span class="text-xs text-slate-500">{{ view.files.combined.pages ?? '?' }} pages · {{ view.files.combined.from_indices.length }} inputs · {{ view.files.combined.at.slice(0, 16).replace('T', ' ') }}</span>
          <a :href="dl(view.files.combined.file)" class="btn-secondary px-2" title="Download">↓</a>
          <button class="btn-secondary px-2 text-red-600 hover:bg-red-50" :disabled="!!busy" @click="deleteOutput(view.files.combined.file)">✕</button>
        </div>
      </div>
    </div>

    <!-- untracked -->
    <div v-if="view.untracked.length" class="card space-y-2">
      <h3 class="font-semibold">Untracked files in the folder</h3>
      <ul class="space-y-1 text-sm">
        <li v-for="n in view.untracked" :key="n" class="flex items-center gap-2">
          <a :href="dl(n, true)" target="_blank" class="min-w-0 flex-1 truncate font-mono hover:underline">{{ n }}</a>
          <button class="btn-secondary" :disabled="!!busy" @click="adopt(n)">Adopt as input</button>
        </li>
      </ul>
    </div>
  </div>
  <div v-else class="text-sm text-slate-500">Loading files…</div>
</template>
