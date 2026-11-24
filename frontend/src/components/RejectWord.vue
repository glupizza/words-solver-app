<template>
  <div class="reject-word">
    <button v-if="!confirming" type="button" @click="confirming = true">Не принято игрой</button>
    <div v-else role="group" :aria-label="`Исключить слово ${word}?`">
      <p>Исключить слово «{{ word }}»?</p>
      <p>Это слово больше не будет появляться в результатах Грааля и обычного решателя.</p>
      <p>Его можно восстановить в списке исключённых слов.</p>
      <button type="button" :disabled="busy" @click="confirming = false">Отмена</button>
      <button type="button" :disabled="busy" @click="reject">{{ busy ? 'Сохранение…' : 'Исключить' }}</button>
      <p v-if="error" role="alert">{{ error }}</p>
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
.reject-word { padding: 12px; }
button { padding: 10px; margin: 4px; }
</style>
