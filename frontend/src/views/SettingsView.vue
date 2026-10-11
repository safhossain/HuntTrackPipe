<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, type SettingsView } from '../api/client'
import { useAppStore } from '../stores/app'
import { errorText } from '../utils'

const app = useAppStore()

interface Form {
  candidate_name: string
  applications_dir: string
  tracker_path: string
  candidate_context_path: string
  backups_keep: number
  jev: { model: string; noul_include_threshold: number; choice_direct_confidence: number; doc_noul_threshold: number; job_posting_warn_below: number; timeout_s: number; max_attempts: number }
  llm: { extract_model: string; qa_model: string; effort: string; max_tokens: number; token_warn: number }
  files: { image_dpi: number; soffice_path: string }
}

const form = reactive<Form>({
  candidate_name: '',
  applications_dir: '',
  tracker_path: '',
  candidate_context_path: '',
  backups_keep: 10,
  jev: { model: '', noul_include_threshold: 0.35, choice_direct_confidence: 0.7, doc_noul_threshold: 0.5, job_posting_warn_below: 0.5, timeout_s: 30, max_attempts: 3 },
  llm: { extract_model: '', qa_model: '', effort: 'low', max_tokens: 2048, token_warn: 80000 },
  files: { image_dpi: 150, soffice_path: '' },
})
const snapshot = ref('')
const saving = ref(false)
const logs = ref<string[]>([])
const logPath = ref('')
const logLines = ref(200)
const logsLoading = ref(false)

function fill(s: SettingsView) {
  const c = s.config as Record<string, any>
  form.candidate_name = c.candidate_name ?? ''
  form.applications_dir = c.applications_dir ?? ''
  form.tracker_path = c.tracker_path ?? ''
  form.candidate_context_path = c.candidate_context_path ?? ''
  form.backups_keep = c.backups_keep ?? 10
  Object.assign(form.jev, c.jev ?? {})
  Object.assign(form.llm, c.llm ?? {})
  form.files.image_dpi = c.files?.image_dpi ?? 150
  form.files.soffice_path = c.files?.soffice_path ?? ''
  snapshot.value = JSON.stringify(form)
}

const dirty = computed(() => JSON.stringify(form) !== snapshot.value)

async function save() {
  saving.value = true
  try {
    const patch = {
      candidate_name: form.candidate_name.trim(),
      applications_dir: form.applications_dir.trim(),
      tracker_path: form.tracker_path.trim(),
      candidate_context_path: form.candidate_context_path.trim(),
      backups_keep: Number(form.backups_keep),
      jev: { ...form.jev },
      llm: { ...form.llm },
      files: { image_dpi: Number(form.files.image_dpi), soffice_path: form.files.soffice_path.trim() || null },
    }
    const s = await api.updateSettings(patch)
    app.settings = s
    fill(s)
    app.toast('Settings saved to htp.config.json.', 'success')
  } catch (e) {
    app.toast(errorText(e), 'error', 10000)
  } finally {
    saving.value = false
  }
}

function reset() {
  if (app.settings) fill(app.settings)
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const r = await api.logs(logLines.value)
    logs.value = r.lines
    logPath.value = r.path
  } catch (e) {
    app.toast(errorText(e), 'error')
  } finally {
    logsLoading.value = false
  }
}

onMounted(async () => {
  if (app.settings) fill(app.settings)
  else {
    try {
      app.settings = await api.settings()
      fill(app.settings)
    } catch (e) {
      app.toast(errorText(e), 'error')
    }
  }
  await loadLogs()
})

const lineClass = (ln: string) => (/ ERROR +/.test(ln) ? 'text-red-700' : / WARNING +/.test(ln) ? 'text-amber-700' : '')
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-baseline justify-between">
      <h1 class="text-xl font-semibold">Settings</h1>
      <span v-if="app.settings" class="font-mono text-xs text-slate-500">{{ app.settings.paths.config_path }}</span>
    </div>

    <div v-if="app.settings" class="card space-y-2 text-sm">
      <h3 class="font-semibold">Status</h3>
      <div class="grid gap-x-6 gap-y-1 sm:grid-cols-2">
        <div><span :class="app.settings.keys.TYPESAFE_API_KEY ? 'text-emerald-600' : 'text-red-600'">●</span> <span class="font-mono">TYPESAFE_API_KEY</span> {{ app.settings.keys.TYPESAFE_API_KEY ? 'set' : 'missing' }}</div>
        <div><span :class="app.settings.keys.ANTHROPIC_API_KEY ? 'text-emerald-600' : 'text-red-600'">●</span> <span class="font-mono">ANTHROPIC_API_KEY</span> {{ app.settings.keys.ANTHROPIC_API_KEY ? 'set' : 'missing' }}</div>
        <div><span :class="app.settings.tracker_exists ? 'text-emerald-600' : 'text-red-600'">●</span> tracker <span class="font-mono text-xs">{{ app.settings.paths.tracker_path }}</span></div>
        <div><span :class="app.settings.candidate_context_exists ? 'text-emerald-600' : 'text-amber-600'">●</span> candidate context <span class="font-mono text-xs">{{ app.settings.paths.candidate_context_path }}</span></div>
      </div>
      <p class="text-xs text-slate-500">API keys live in <span class="font-mono">.env</span> next to <span class="font-mono">htp.config.json</span>; restart the API after changing them.</p>
    </div>

    <form class="card space-y-4" @submit.prevent="save">
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="block"><span class="label">Candidate name (file names)</span><input v-model="form.candidate_name" class="input" required /></label>
        <label class="block"><span class="label">Backups to keep</span><input v-model.number="form.backups_keep" type="number" min="0" class="input" /></label>
        <label class="block sm:col-span-2"><span class="label">Applications dir</span><input v-model="form.applications_dir" class="input font-mono text-xs" required /></label>
        <label class="block sm:col-span-2"><span class="label">Tracker workbook</span><input v-model="form.tracker_path" class="input font-mono text-xs" required /></label>
        <label class="block sm:col-span-2"><span class="label">Candidate context file</span><input v-model="form.candidate_context_path" class="input font-mono text-xs" required /></label>
      </div>
      <p class="text-xs text-slate-500">Relative paths are resolved against the repo root. Changing the applications dir does not move existing folders.</p>

      <h3 class="font-semibold">Jev</h3>
      <div class="grid gap-3 sm:grid-cols-3">
        <label class="block"><span class="label">Model</span><input v-model="form.jev.model" class="input" /></label>
        <label class="block"><span class="label">Include field at noul ≥</span><input v-model.number="form.jev.noul_include_threshold" type="number" step="0.05" min="0" max="1" class="input" /></label>
        <label class="block"><span class="label">Direct choice at confidence ≥</span><input v-model.number="form.jev.choice_direct_confidence" type="number" step="0.05" min="0" max="1" class="input" /></label>
        <label class="block"><span class="label">Required doc at noul ≥</span><input v-model.number="form.jev.doc_noul_threshold" type="number" step="0.05" min="0" max="1" class="input" /></label>
        <label class="block"><span class="label">Warn "not a posting" below</span><input v-model.number="form.jev.job_posting_warn_below" type="number" step="0.05" min="0" max="1" class="input" /></label>
        <label class="block"><span class="label">Timeout (s) / attempts</span>
          <div class="flex gap-2"><input v-model.number="form.jev.timeout_s" type="number" min="1" class="input" /><input v-model.number="form.jev.max_attempts" type="number" min="1" class="input w-20" /></div>
        </label>
      </div>

      <h3 class="font-semibold">Claude</h3>
      <div class="grid gap-3 sm:grid-cols-3">
        <label class="block"><span class="label">Extraction model</span><input v-model="form.llm.extract_model" class="input" /></label>
        <label class="block"><span class="label">Q&amp;A model</span><input v-model="form.llm.qa_model" class="input" /></label>
        <label class="block"><span class="label">Effort</span>
          <select v-model="form.llm.effort" class="input"><option>low</option><option>medium</option><option>high</option></select>
        </label>
        <label class="block"><span class="label">Max output tokens</span><input v-model.number="form.llm.max_tokens" type="number" min="256" class="input" /></label>
        <label class="block"><span class="label">Warn above input tokens</span><input v-model.number="form.llm.token_warn" type="number" min="1000" class="input" /></label>
      </div>

      <h3 class="font-semibold">Files</h3>
      <div class="grid gap-3 sm:grid-cols-3">
        <label class="block"><span class="label">Image DPI</span><input v-model.number="form.files.image_dpi" type="number" min="50" max="600" class="input" /></label>
        <label class="block sm:col-span-2"><span class="label">LibreOffice soffice path (blank = auto-detect)</span><input v-model="form.files.soffice_path" class="input font-mono text-xs" /></label>
      </div>

      <div class="flex items-center justify-end gap-3">
        <button type="button" class="btn-secondary" :disabled="!dirty || saving" @click="reset">Reset</button>
        <button type="submit" class="btn-primary" :disabled="!dirty || saving">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>
    </form>

    <div class="card space-y-2">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="font-semibold">Log <span class="font-mono text-xs font-normal text-slate-500">{{ logPath }}</span></h3>
        <div class="flex items-center gap-2 text-sm">
          <select v-model.number="logLines" class="input w-24"><option :value="100">100</option><option :value="200">200</option><option :value="500">500</option><option :value="2000">2000</option></select>
          <button class="btn-secondary" :disabled="logsLoading" @click="loadLogs">{{ logsLoading ? 'Loading…' : 'Refresh' }}</button>
        </div>
      </div>
      <pre v-if="logs.length" class="max-h-[32rem] overflow-auto rounded bg-slate-50 p-3 text-xs leading-5"><div v-for="(ln, i) in logs" :key="i" :class="lineClass(ln)">{{ ln }}</div></pre>
      <p v-else class="text-sm text-slate-500">No log entries yet.</p>
    </div>
  </div>
</template>
