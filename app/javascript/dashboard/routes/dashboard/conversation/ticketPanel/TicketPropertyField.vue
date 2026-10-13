<script setup>
// Linha de propriedade do painel do ticket: rótulo + controle, no padrão
// de formulário compacto (rótulo 12px semibold acima do campo).
defineProps({
  label: { type: String, required: true },
  hint: { type: String, default: '' },
});
</script>

<template>
  <div class="flex flex-col min-w-0 gap-1">
    <div class="flex items-center justify-between gap-2 min-h-5">
      <span class="text-xs font-semibold text-n-slate-11">
        {{ label }}
      </span>
      <slot name="action" />
    </div>
    <slot />
    <span v-if="hint" class="-mt-1 text-xs text-n-slate-10">{{ hint }}</span>
  </div>
</template>
