<template>
  <div class="reject-word">
    <button v-if="!confirming" class="reject-trigger" type="button" @click="confirming = true">Не принято игрой</button>
    <div v-else class="reject-confirm" role="group" :aria-label="`Исключить слово ${word}?`">
      <p class="confirm-title">Исключить слово «{{ word }}»?</p>
      <p>Это слово больше не будет появляться в результатах Грааля и обычного решателя.</p>
      <p>Его можно восстановить в списке исключённых слов.</p>
      <div class="confirm-actions"><button class="confirm-cancel" type="button" :disabled="busy" @click="confirming = false">Отмена</button>
      <button class="confirm-submit" type="button" :disabled="busy" @click="reject">{{ busy ? 'Сохранение…' : 'Исключить' }}</button></div>
      <p v-if="error" class="confirm-error" role="alert">{{ error }}</p>
    </div>
  </div>
</template>
<script>
import { adminRequest } from '../adminApi.js';
export default {
  props: { word: { type: String, required: true } },
  emits: ['rejected'],
  data() { return { confirming: false, busy: false, error: '' }; },
  methods: { async reject() { if (this.busy) return; this.busy = true; this.error = ''; try { const result = await adminRequest('rejected', { word: this.word }); this.$emit('rejected', this.word, result.created); } catch (error) { this.error = error.message; } finally { this.busy = false; } } },
};
</script>
<style scoped>
.reject-word { padding: 10px 0 2px; }
.reject-word button { min-height: 44px; padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px; font-weight: 700; cursor: pointer; }
.reject-word button:focus-visible { outline: 3px solid var(--color-warm); outline-offset: 2px; }
.reject-word button:disabled { cursor: not-allowed; opacity: .55; }
.reject-trigger, .confirm-cancel { background: var(--surface); color: var(--accent-hover); }
.reject-trigger:hover, .confirm-cancel:hover { background: var(--surface-light); border-color: var(--accent); }
.reject-confirm { padding: 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-light); }
.reject-confirm p { margin: 0 0 10px; color: var(--muted); font-size: .9rem; }
.reject-confirm .confirm-title { color: var(--text); font-size: 1rem; font-weight: 800; overflow-wrap: anywhere; }
.confirm-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.confirm-submit { border-color: var(--accent) !important; background: var(--accent); color: #fff; }
.confirm-submit:hover { background: var(--accent-hover); }
.reject-confirm .confirm-error { margin: 12px 0 0; color: #774b43; }
@media (max-width: 380px) { .confirm-actions button { flex: 1 1 auto; } }
</style>
