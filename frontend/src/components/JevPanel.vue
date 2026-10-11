<script setup lang="ts">
import { computed } from 'vue'
import type { JevDerived, JevRecord } from '../api/client'
import { pct } from '../utils'

const props = defineProps<{ jev: JevRecord | null; derived: JevDerived; warnings: string[] }>()

const nouls = computed(() =>
  Object.entries(props.jev?.answers ?? {})
    .filter(([, a]) => a.type === 'noul')
    .map(([k, a]) => ({ key: k, p: (a as { noul: number }).noul })),
)
const choices = computed(() =>
  Object.entries(props.jev?.answers ?? {})
    .filter(([, a]) => a.type === 'choice')
    .map(([k, a]) => ({ key: k, choice: (a as { choice: string }).choice, conf: (a as { confidence?: number }).confidence ?? null })),
)
function bar(p: number) {
  return p >= 0.7 ? 'bg-emerald-500' : p >= 0.35 ? 'bg-amber-400' : 'bg-slate-300'
}
</script>

<template>
  <div class="card space-y-4">
    <div class="flex items-baseline justify-between">
      <h3 class="font-semibold">Jev</h3>
      <span v-if="jev" class="text-xs text-slate-500">{{ jev.model }} · {{ (jev.usage as any)?.input_tokens ?? '?' }} in tokens</span>
      <span v-else class="text-xs text-slate-500">skipped</span>
    </div>

    <div v-if="warnings.length" class="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
      <div v-for="w in warnings" :key="w">⚠ {{ w }}</div>
    </div>

    <div v-if="nouls.length" class="space-y-1">
      <div v-for="n in nouls" :key="n.key" class="flex items-center gap-2 text-xs">
        <span class="w-44 truncate font-mono text-slate-600">{{ n.key }}</span>
        <div class="h-2 flex-1 rounded bg-slate-100"><div class="h-2 rounded" :class="bar(n.p)" :style="{ width: `${Math.round(n.p * 100)}%` }" /></div>
        <span class="w-10 text-right tabular-nums">{{ pct(n.p) }}</span>
      </div>
    </div>

    <div v-if="choices.length" class="flex flex-wrap gap-2">
      <span v-for="c in choices" :key="c.key" class="chip bg-slate-100 text-slate-700">
        <span class="font-mono text-slate-500">{{ c.key }}:</span>&nbsp;{{ c.choice }}
        <span class="ml-1 text-slate-400">{{ pct(c.conf) }}</span>
      </span>
    </div>

    <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      <dt class="text-slate-500">LLM asked for</dt>
      <dd class="font-mono">{{ [...derived.schema_fields, ...derived.low_confidence_choices].join(', ') || '(nothing)' }}</dd>
      <dt class="text-slate-500">Written directly</dt>
      <dd class="font-mono">{{ Object.entries(derived.direct_values).map(([k, v]) => `${k}=${v}`).join(', ') || '(none)' }}</dd>
      <dt class="text-slate-500">Upload mode</dt>
      <dd>{{ derived.upload_mode }} <span class="text-slate-400">{{ pct(derived.upload_mode_confidence) }}</span></dd>
      <dt class="text-slate-500">Docs flagged</dt>
      <dd>{{ derived.required_docs.join(', ') || '(none)' }}</dd>
    </dl>
  </div>
</template>
