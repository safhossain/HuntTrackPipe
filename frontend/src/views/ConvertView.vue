<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, downloadResponse } from '../api/client'
import { useAppStore } from '../stores/app'
import { errorText, extOf, fmtBytes } from '../utils'

const app = useAppStore()
const tools = ref<{ soffice: string | null; pdf2docx: boolean; targets: string[] } | null>(null)
const file = ref<File | null>(null)
const target = ref('pdf')
const busy = ref(false)
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

const ext = computed(() => (file.value ? extOf(file.value.name) : ''))
const targets = computed(() => {
  const all = tools.value?.targets ?? ['pdf', 'docx', 'png', 'jpg']
  if (!file.value) return all
  return all.filter((t) => {
    if (t === ext.value) return false
    if (t === 'docx') return ext.value === 'pdf' && !!tools.value?.pdf2docx
    return true
  })
})

function setFile(f: File | null) {
  file.value = f
  if (!targets.value.includes(target.value)) target.value = targets.value[0] ?? 'pdf'
}
function onPicked(ev: Event) {
  const el = ev.target as HTMLInputElement
  setFile(el.files?.[0] ?? null)
  el.value = ''
}
function onDrop(ev: DragEvent) {
  dragOver.value = false
  setFile(ev.dataTransfer?.files?.[0] ?? null)
}

async function convert() {
  if (!file.value) return
  busy.value = true
  try {
    const res = await api.convertFile(file.value, target.value)
    const name = await downloadResponse(res, `${file.value.name}.${target.value}`)
    history.value.unshift({ from: file.value.name, to: name })
    app.toast(`Downloaded ${name}`, 'success', 4000)
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-4">
    <div>
      <h1 class="text-xl font-semibold">Convert a file</h1>
      <p class="text-sm text-slate-500">Standalone converter; nothing is stored. Office → PDF uses LibreOffice, PDF → DOCX uses pdf2docx (lossy), PDF → PNG/JPG gives one image per page (zipped when more than one).</p>
    </div>

    <div v-if="tools && !tools.soffice" class="rounded-md bg-amber-50 p-3 text-sm text-amber-900">LibreOffice (soffice) not found: Office documents → PDF is unavailable. Install it or set <span class="font-mono">files.soffice_path</span> in <span class="font-mono">htp.config.json</span>.</div>

    <div
      class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-sm transition"
      :class="dragOver ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-white hover:bg-slate-50'"
      @click="input?.click()"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
    >
      <template v-if="file">
        <span class="font-mono">{{ file.name }}</span>
        <span class="mt-1 text-xs text-slate-500">{{ fmtBytes(file.size) }} · click or drop to replace</span>
      </template>
      <template v-else>
        <span class="font-medium">Drop a file here or click to browse</span>
        <span class="mt-1 text-xs text-slate-500">PDF, DOCX, DOC, ODT, PPTX, XLSX, PNG, JPG, …</span>
      </template>
      <input ref="input" type="file" class="hidden" @change="onPicked" />
    </div>

    <div class="card flex flex-wrap items-end gap-3">
      <label class="block">
        <span class="label">Convert to</span>
        <select v-model="target" class="input w-40" :disabled="!file || busy">
          <option v-for="t in targets" :key="t" :value="t">{{ t.toUpperCase() }}{{ t === 'docx' ? ' (lossy)' : '' }}</option>
        </select>
      </label>
      <button class="btn-primary" :disabled="!file || busy || !targets.length" @click="convert">{{ busy ? 'Converting…' : 'Convert & download' }}</button>
      <span v-if="file && !targets.length" class="text-xs text-amber-700">No conversion available for .{{ ext }} files.</span>
    </div>

    <div v-if="history.length" class="card">
      <h3 class="mb-2 text-sm font-semibold">This session</h3>
      <ul class="space-y-1 text-xs text-slate-600">
        <li v-for="(h, i) in history" :key="i" class="font-mono">{{ h.from }} → {{ h.to }}</li>
      </ul>
    </div>
  </div>
</template>
