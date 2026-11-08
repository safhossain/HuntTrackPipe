<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useAppStore } from './stores/app'
import ToastStack from './components/ToastStack.vue'

import huntTrackPipeLogo from './img/hunttrackpipe-logo.png'
import excelOk from './img/excel-icon-green.png'
import excelBad from './img/excel-icon-red.png'
import jevOk from './img/jev_logo-transparent_green.png'
import jevBad from './img/jev_logo-transparent_red.png'
import claudeOk from './img/claude_orange.png'
import claudeMissing from './img/claude_black.png'
import claudeInactive from './img/claude_grey.png'
import claudeLowCredit from './img/claude_red.png'
import openaiOk from './img/chatgpt_green.png'
import openaiMissing from './img/chatgpt_black.png'
import openaiInactive from './img/chatgpt_grey.png'
import openaiLowCredit from './img/chatgpt_red.png'

const app = useAppStore()
onMounted(() => app.bootstrap())

const navbar = ref<HTMLElement | null>(null)
const pinned = ref(true)
const unpinning = ref(false)
const hiddenUntilTop = ref(false)
const navbarHeight = ref(0)
const scrollY = ref(0)
const floating = computed(() => pinned.value || unpinning.value)
let resizeObserver: ResizeObserver | undefined
let exitAnimation: Animation | undefined
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const trackScroll = () => {
  scrollY.value = window.scrollY
  if (scrollY.value === 0) hiddenUntilTop.value = false
}

onMounted(() => {
  trackScroll()
  window.addEventListener('scroll', trackScroll, { passive: true })
  resizeObserver = new ResizeObserver(() => {
    navbarHeight.value = navbar.value?.offsetHeight ?? 0
  })
  if (navbar.value) resizeObserver.observe(navbar.value)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', trackScroll)
  resizeObserver?.disconnect()
  exitAnimation?.cancel()
})

async function togglePin() {
  if (unpinning.value) return
  if (!pinned.value) {
    navbarHeight.value = navbar.value?.offsetHeight ?? 0
    pinned.value = true
    return
  }
  // Keep the fixed header and its layout space until the exit finishes.
  unpinning.value = window.scrollY > 0
  pinned.value = false
  if (!unpinning.value) return
  exitAnimation = navbar.value?.animate(
    [{ transform: 'translateY(0)' }, { transform: 'translateY(-100%)' }],
    { duration: reducedMotion() ? 0 : 260, easing: 'ease-in', fill: 'forwards' },
  )
  try { await exitAnimation?.finished } catch { /* Cancelled on unmount. */ }
  hiddenUntilTop.value = window.scrollY > 0
  unpinning.value = false
  exitAnimation?.cancel()
  exitAnimation = undefined
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: reducedMotion() ? 'instant' : 'smooth' })
}

const trackerIcon = computed(() => (app.settings?.tracker_exists ? excelOk : excelBad))
const trackerTitle = computed(() => {
  if (app.trackerLocked) return 'Tracker open in Excel — close it before writing'
  if (app.settings?.tracker_exists) return 'Tracker workbook found'
  return 'Tracker workbook missing'
})

const jevIcon = computed(() => (app.settings?.keys.TYPESAFE_API_KEY ? jevOk : jevBad))
const jevTitle = computed(() =>
  app.settings?.keys.TYPESAFE_API_KEY ? 'Jev API key set' : 'Jev API key missing',
)

const claudeStatus = computed(() => {
  if (!app.settings?.keys.ANTHROPIC_API_KEY) {
    return { icon: claudeMissing, title: 'Claude API key missing' }
  }
  if (app.modelProvider !== 'anthropic') {
    return { icon: claudeInactive, title: 'Claude is inactive' }
  }
  if (app.trackerStatus?.claude_credit_low) {
    return { icon: claudeLowCredit, title: 'Claude API credit balance is too low' }
  }
  return { icon: claudeOk, title: 'Claude API key set' }
})

const openaiStatus = computed(() => {
  if (!app.settings?.keys.OPENAI_API_KEY) {
    return { icon: openaiMissing, title: 'OpenAI API key missing' }
  }
  if (app.modelProvider !== 'openai') {
    return { icon: openaiInactive, title: 'OpenAI is inactive' }
  }
  if (app.trackerStatus?.openai_credit_low) {
    return { icon: openaiLowCredit, title: 'OpenAI API credit balance is too low' }
  }
  return { icon: openaiOk, title: 'OpenAI API key set' }
})
</script>

<template>
  <div class="min-h-screen" :style="{ '--navbar-offset': floating ? `${navbarHeight}px` : '0px' }">
    <div :style="floating ? { height: `${navbarHeight}px` } : undefined">
    <header ref="navbar" class="relative border-b border-slate-200 bg-white" :class="[floating ? 'navbar-floating shadow-sm' : undefined, hiddenUntilTop && !floating ? 'invisible' : undefined]">
      <div class="page-shell flex items-center gap-3 py-1.5 sm:gap-6">
        <RouterLink to="/" class="shrink-0">
          <img :src="huntTrackPipeLogo" alt="HuntTrackPipe" width="2172" height="724" class="h-auto w-28 sm:w-32" />
        </RouterLink>
        <nav class="flex min-w-0 gap-4 overflow-x-auto whitespace-nowrap text-sm">
          <RouterLink to="/" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium" exact-active-class="text-indigo-600 font-medium">Dashboard</RouterLink>
          <RouterLink to="/new" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">New application</RouterLink>
          <RouterLink to="/convert" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">Convert</RouterLink>
          <RouterLink to="/settings" class="hover:text-indigo-600" active-class="text-indigo-600 font-medium">Settings</RouterLink>
        </nav>
        <div class="ml-auto flex shrink-0 items-center gap-2.5">

          <template v-if="app.settings">
            <img
              :src="trackerIcon"
              :alt="trackerTitle"
              :title="trackerTitle"
              class="h-5 w-5 object-contain"
              :class="app.trackerLocked ? 'opacity-60' : undefined"
            />
            <img :src="jevIcon" :alt="jevTitle" :title="jevTitle" class="h-5 w-5 object-contain" />
            <img :src="claudeStatus.icon" :alt="claudeStatus.title" :title="claudeStatus.title" class="h-5 w-5 object-contain" />
            <img :src="openaiStatus.icon" :alt="openaiStatus.title" :title="openaiStatus.title" class="h-5 w-5 object-contain" />
          </template>
          <span v-else-if="app.apiError" class="text-xs text-red-600">API unreachable</span>
          <span v-else class="text-xs text-slate-500">Connecting…</span>
          <button
            type="button"
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600"
            :class="pinned ? 'bg-indigo-50 text-indigo-600' : 'text-slate-500'"
            :title="pinned ? 'Unpin navbar' : 'Pin navbar'"
            :aria-label="pinned ? 'Unpin navbar' : 'Pin navbar'"
            :aria-pressed="pinned"
            :disabled="unpinning"
            @click="togglePin"
          >
            <svg class="h-5 w-5 transition-transform" :class="pinned ? '' : '-rotate-45'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M9 3h6l-1 7 4 4v2H6v-2l4-4-1-7Z" />
              <path d="M12 16v6" />
            </svg>
          </button>
        </div>
      </div>
      <div
        v-if="app.trackerLocked"
        class="border-t border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900"
      >
        Tracker workbook is open in Excel. Close it before creating applications, saving rows, or syncing dropdowns.
      </div>
    </header>
    </div>

    <main class="page-shell min-w-0 py-6">
        <div v-if="!app.apiReady && !app.apiError" class="text-sm text-slate-500">Waiting for the API on :8010…</div>
        <RouterView v-else />
    </main>

    <button v-show="scrollY > 0" type="button" class="fixed bottom-4 left-4 z-30 flex h-10 w-10 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-600 shadow-md hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600" title="Scroll to top" aria-label="Scroll to top" @click="scrollToTop">
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="m6 10 6-6 6 6M12 4v16" />
      </svg>
    </button>
    <ToastStack />
  </div>
</template>

<style scoped>
.navbar-floating {
  position: fixed;
  inset: 0 0 auto;
  z-index: 40;
}
</style>
