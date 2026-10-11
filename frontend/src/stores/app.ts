import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, waitForApi, type Meta, type SettingsView } from '../api/client'

export type ToastKind = 'info' | 'success' | 'error'
export interface Toast { id: number; kind: ToastKind; text: string }

let toastSeq = 0

export const useAppStore = defineStore('app', () => {
  const apiReady = ref(false)
  const apiError = ref<string | null>(null)
  const meta = ref<Meta | null>(null)
  const settings = ref<SettingsView | null>(null)
  const toasts = ref<Toast[]>([])

  async function bootstrap() {
    try {
      await waitForApi()
      apiReady.value = true
      ;[meta.value, settings.value] = await Promise.all([api.meta(), api.settings()])
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

  return { apiReady, apiError, meta, settings, toasts, bootstrap, toast, dismiss }
})
