<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, downloadResponse } from '../api/client'
import { useAppStore } from '../stores/app'
import { errorText, extOf, fmtBytes } from '../utils'
import ConvertAllPdfButton from '../components/ConvertAllPdfButton.vue'
import PageHeader from '../components/PageHeader.vue'

const app = useAppStore()
const tools = ref<{ soffice: string | null; pdf2docx: boolean; targets: string[] } | null>(null)
const files = ref<File[]>([])
const target = ref('pdf')
const busy = ref<string | null>(null)
const dragOver = ref(false)
const input = ref<HTMLInputElement | null>(null)
const history = ref<{ from: string; to: string }[]>([])

onMounted(async () => {
  try {
    tools.value = await api.tools()
  } catch (e) {
    app.toast(errorText(e), 'error')
  }
})

const single = computed(() => (files.value.length === 1 ? files.value[0]! : null))
const ext = computed(() => (single.value ? extOf(single.value.name) : ''))
const targets = computed(() => {
  const all = tools.value?.targets ?? ['pdf', 'docx', 'png', 'jpg']
  if (!single.value) return all
  return all.filter((t) => {
    if (t === ext.value) return false
    if (t === 'docx') return ext.value === 'pdf' && !!tools.value?.pdf2docx
    return true
  })
})
const nonPdfCount = computed(() => files.value.filter((f) => extOf(f.name) !== 'pdf').length)
const totalBytes = computed(() => files.value.reduce((n, f) => n + f.size, 0))

function setFiles(list: File[]) {
  files.value = list
  if (single.value && !targets.value.includes(target.value)) {
    target.value = targets.value[0] ?? 'pdf'
  }
}
function onPicked(ev: Event) {
  const el = ev.target as HTMLInputElement
  setFiles(Array.from(el.files ?? []))
  el.value = ''
}
function onDrop(ev: DragEvent) {
  dragOver.value = false
  setFiles(Array.from(ev.dataTransfer?.files ?? []))
}
function clear() {
  setFiles([])
}

async function convertOne() {
  if (!single.value) return
  busy.value = 'one'
  try {
    const res = await api.convertFile(single.value, target.value)
    const name = await downloadResponse(res, `${single.value.name}.${target.value}`)
    history.value.unshift({ from: single.value.name, to: name })
    app.toast(`Downloaded ${name}`, 'success', 4000)
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    busy.value = null
  }
}

async function convertAllPdf() {
  if (!files.value.length) return
  busy.value = 'all-pdf'
  try {
    const res = await api.convertAllFilesToPdf(files.value)
    const fallback = files.value.length === 1 ? `${extOf(files.value[0]!.name) === 'pdf' ? files.value[0]!.name : files.value[0]!.name.replace(/\.[^.]+$/, '') + '.pdf'}` : 'converted_pdfs.zip'
    const name = await downloadResponse(res, fallback)
    history.value.unshift({
      from: files.value.length === 1 ? files.value[0]!.name : `${files.value.length} files`,
      to: name,
    })
    app.toast(`Downloaded ${name}`, 'success', 4000)
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <PageHeader title="Convert a file" />
    <div class="mx-auto max-w-2xl space-y-4">
      <p class="text-sm text-slate-500">Standalone converter; nothing is stored. Drop one file for any target, or several and use → PDF. Office → PDF uses LibreOffice, PDF → DOCX uses pdf2docx (lossy), PDF → PNG/JPG gives one image per page (zipped when more than one).</p>

      <div v-if="tools && !tools.soffice" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900">LibreOffice (soffice) not found: Office documents → PDF is unavailable. Install it or set <span class="font-mono">files.soffice_path</span> in <span class="font-mono">htp.config.json</span>.</div>

      <div
        class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-sm transition"
        :class="dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-white hover:bg-slate-50'"
        @click="input?.click()"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >
        <template v-if="files.length === 1">
          <span class="font-mono">{{ files[0]!.name }}</span>
          <span class="mt-1 text-xs text-slate-500">{{ fmtBytes(files[0]!.size) }} · click or drop to replace</span>
        </template>
        <template v-else-if="files.length > 1">
          <span class="font-medium">{{ files.length }} files selected</span>
          <span class="mt-1 text-xs text-slate-500">{{ fmtBytes(totalBytes) }} · click or drop to replace</span>
          <ul class="mt-3 max-h-28 w-full max-w-md space-y-0.5 overflow-y-auto text-left font-mono text-xs text-slate-600">
            <li v-for="(f, i) in files" :key="i" class="truncate">{{ f.name }}</li>
          </ul>
        </template>
        <template v-else>
          <span class="font-medium">Drop file(s) here or click to browse</span>
          <span class="mt-1 text-xs text-slate-500">PDF, DOCX, DOC, ODT, PPTX, XLSX, PNG, JPG, …</span>
        </template>
        <input ref="input" type="file" multiple class="hidden" @change="onPicked" />
      </div>

      <div class="card flex flex-wrap items-end gap-3">
        <label class="block">
          <span class="label">Convert to</span>
          <select v-model="target" class="input w-40" :disabled="!single || !!busy">
            <option v-for="t in targets" :key="t" :value="t">{{ t.toUpperCase() }}{{ t === 'docx' ? ' (lossy)' : '' }}</option>
          </select>
        </label>
        <button class="btn-primary" :disabled="!single || !!busy || !targets.length" @click="convertOne">
          {{ busy === 'one' ? 'Converting…' : 'Convert & download' }}
        </button>
        <ConvertAllPdfButton
          :disabled="!files.length || !!busy"
          :busy="busy === 'all-pdf'"
          :title="files.length ? `Convert ${files.length} file(s) to PDF and download` : 'Select file(s) first'"
          @click="convertAllPdf"
        />
        <button v-if="files.length" type="button" class="btn-secondary" :disabled="!!busy" @click="clear">Clear</button>
        <span v-if="single && !targets.length" class="text-xs text-amber-700">No conversion available for .{{ ext }} files.</span>
        <span v-else-if="files.length > 1" class="text-xs text-slate-500">Multi-file: use → PDF (zip when more than one). Already-PDF files are kept as-is.</span>
        <span v-else-if="files.length === 1 && nonPdfCount === 0" class="text-xs text-slate-500">Already a PDF — → PDF downloads a copy.</span>
      </div>

      <div v-if="history.length" class="card">
        <h3 class="mb-2 text-sm font-semibold">This session</h3>
        <ul class="space-y-1 text-xs text-slate-600">
          <li v-for="(h, i) in history" :key="i" class="font-mono">{{ h.from }} → {{ h.to }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>
