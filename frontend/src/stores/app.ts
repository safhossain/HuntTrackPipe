import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, waitForApi, type Meta, type SettingsView, type TrackerStatus } from '../api/client'

export type ToastKind = 'info' | 'success' | 'error'
export interface Toast { id: number; kind: ToastKind; text: string }

let toastSeq = 0
const STATUS_POLL_MS = 2000

export const useAppStore = defineStore('app', () => {
  const apiReady = ref(false)
  const apiError = ref<string | null>(null)
  const meta = ref<Meta | null>(null)
  const settings = ref<SettingsView | null>(null)
  const trackerStatus = ref<TrackerStatus | null>(null)
  const toasts = ref<Toast[]>([])
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let lastLocked: boolean | null = null
  let lastSuggestKey = ''

  const trackerLocked = computed(() => Boolean(trackerStatus.value?.locked))
  const suggestSync = computed(() => Boolean(trackerStatus.value?.suggest_sync))
  const modelProvider = computed(() => settings.value?.config.llm?.extract_provider ?? 'anthropic')
  const modelProviderLabel = computed(() => modelProvider.value === 'openai' ? 'OpenAI' : 'Claude')

  async function refreshTrackerStatus(force = false) {
    try {
      const st = await api.trackerStatus(force)
      const wasLocked = lastLocked
      trackerStatus.value = st
      lastLocked = st.locked
      // Toast once when Excel closes and dropdowns still differ.
      if (wasLocked === true && !st.locked && st.suggest_sync) {
        const key = `${st.dropdown_sync.checked_at}|${st.dropdown_sync.status}`
        if (key !== lastSuggestKey) {
          lastSuggestKey = key
          toast('Tracker closed. Dropdown lists differ from Excel — use Sync on the right when ready.', 'info', 10000)
        }
      }
    } catch {
      /* keep last known status */
    }
  }

  function startStatusPoll() {
    stopStatusPoll()
    void refreshTrackerStatus(true)
    pollTimer = setInterval(() => void refreshTrackerStatus(false), STATUS_POLL_MS)
  }

  function stopStatusPoll() {
    if (pollTimer != null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function bootstrap() {
    try {
      await waitForApi()
      apiReady.value = true
      ;[meta.value, settings.value] = await Promise.all([api.meta(), api.settings()])
      if (settings.value?.tracker_status) trackerStatus.value = settings.value.tracker_status
      startStatusPoll()
    } catch (e) {
      apiError.value = e instanceof Error ? e.message : String(e)
    }
  }

  function toast(text: string, kind: ToastKind = 'info', ms = 5000) {
    const id = ++toastSeq
    toasts.value.push({ id, kind, text })
    setTimeout(() => dismiss(id), ms)
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return {
    apiReady,
    apiError,
    meta,
    settings,
    trackerStatus,
    trackerLocked,
    suggestSync,
    modelProvider,
    modelProviderLabel,
    toasts,
    bootstrap,
    refreshTrackerStatus,
    toast,
    dismiss,
  }
})
