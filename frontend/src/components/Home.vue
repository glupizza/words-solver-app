<template>
  <main class="home">
    <section class="hero-card">
      <div class="hero-copy">
        <p class="eyebrow">Word Solver</p>
      </div>

      <div class="mode-switch" aria-label="Выбор режима">
        <button
          type="button"
          class="active"
        >
          По изображению
        </button>
        <button
          type="button"
          disabled
        >
          Грааль (не работает)
        </button>
      </div>
    </section>

    <section class="workspace">
      <section class="card mode-panel">
        <div class="section-header">
          <h2>По изображению</h2>
        </div>

        <label class="file-picker">
          <input type="file" accept="image/*" @change="handleFileChange" />
          <span>Выбрать файл</span>
        </label>

        <button class="primary-button" @click="uploadImage" :disabled="!selectedImage || loading">
          {{ loading ? 'Обработка...' : 'Найти слова' }}
        </button>
      </section>

      <aside class="card results-card">
        <div class="section-header">
          <h2>Найденные слова</h2>
        </div>

        <div v-if="loading" class="status">
          <span class="loader" aria-hidden="true"></span>
          Идёт обработка...
        </div>

        <div v-if="errorMessage" class="notice">
          {{ errorMessage }}
        </div>

        <div v-if="!loading && hasSearched && results.length === 0 && !errorMessage" class="empty">
          Слова не найдены
        </div>

        <ul v-if="results.length > 0" class="word-list">
          <li v-for="(word, index) in results" :key="`${word.name}-${index}`">
            <strong>{{ word.name }}</strong>
            <span class="score">{{ word.score }} очк.</span>
          </li>
        </ul>
      </aside>
    </section>
  </main>
</template>

<script>
export default {
  name: 'Home',
  data() {
    return {
      selectedImage: null,
      results: [],
      loading: false,
      errorMessage: '',
      hasSearched: false,
    };
  },
  methods: {
    handleFileChange(event) {
      this.selectedImage = event.target.files[0] || null;
      this.errorMessage = '';
      this.hasSearched = false;
    },
    async uploadImage() {
      if (!this.selectedImage) return;

      this.loading = true;
      this.errorMessage = '';
      this.hasSearched = false;
      this.results = [];
      const formData = new FormData();
      formData.append("image", this.selectedImage);

      try {
        const response = await fetch("/upload", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          await this.setErrorFromResponse(response, "Error uploading image");
          return;
        }

        const data = await response.json();
        this.results = Array.isArray(data.words) ? data.words : [];
        this.hasSearched = true;
      } catch (error) {
        console.error("Network error:", error);
        this.errorMessage = "Network error";
      } finally {
        this.loading = false;
      }
    },
    async setErrorFromResponse(response, fallbackMessage) {
      try {
        const data = await response.json();
        this.errorMessage = data.error || fallbackMessage;
      } catch (_error) {
        this.errorMessage = fallbackMessage;
      }
    },
  },
};
</script>

<style scoped>
.home {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: 16px 16px 28px;
}

.hero-card,
.card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: 0 14px 36px rgba(36, 52, 71, 0.12);
}

.hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  margin-bottom: 12px;
}

.hero-copy,
.section-header {
  text-align: left;
}

.eyebrow {
  margin: 0;
  color: var(--accent);
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h2,
p {
  margin-top: 0;
}

h2 {
  margin-bottom: 0;
  color: var(--text);
  font-size: 1.08rem;
}

.mode-switch {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-light);
}

.mode-switch button {
  min-width: 136px;
  min-height: 34px;
  padding: 7px 14px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: var(--muted);
  background: transparent;
  font-size: 0.94rem;
  font-weight: 750;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
}

.mode-switch button:hover:not(:disabled) {
  color: var(--text);
  border-color: rgba(75, 99, 130, 0.3);
}

.mode-switch button:disabled {
  opacity: 1;
  color: var(--muted);
  cursor: not-allowed;
}

.mode-switch button.active {
  color: #ffffff;
  background: var(--accent);
  box-shadow: 0 6px 18px rgba(75, 99, 130, 0.2);
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(340px, 1.05fr);
  gap: 12px;
  align-items: start;
}

.card {
  padding: 14px;
}

.section-header {
  margin-bottom: 12px;
}

.mode-panel {
  min-height: 0;
}

.file-picker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: auto;
  min-height: 38px;
  margin-bottom: 10px;
  border: 1px dashed rgba(75, 99, 130, 0.35);
  border-radius: 10px;
  color: var(--accent);
  background: var(--surface-light);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.file-picker:hover {
  border-color: var(--accent);
  background: #eef3f6;
}

.file-picker input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.file-picker span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 13px;
  border: 0;
  border-radius: 9px;
  color: var(--accent);
  background: transparent;
  font-size: 0.92rem;
  font-weight: 800;
}

.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 40px;
  padding: 9px 16px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: #ffffff;
  background: var(--accent);
  font-size: 0.96rem;
  font-weight: 900;
  cursor: pointer;
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
}

.primary-button:hover:not(:disabled) {
  background: var(--accent-hover);
  box-shadow: 0 10px 24px rgba(75, 99, 130, 0.22);
  transform: translateY(-1px);
}

.primary-button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

button:focus-visible,
.file-picker:focus-within {
  outline: none;
  box-shadow: 0 0 0 3px rgba(75, 99, 130, 0.18);
}

.status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  background: var(--surface-light);
}

.loader {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(75, 99, 130, 0.22);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.notice,
.empty {
  padding: 12px;
  border: 1px solid rgba(166, 136, 104, 0.32);
  border-radius: 10px;
  color: var(--text);
  background: rgba(166, 136, 104, 0.08);
}

.empty {
  color: var(--muted);
}

.word-list {
  max-height: min(62vh, 620px);
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.word-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
}

.word-list li:last-child {
  border-bottom: 0;
}

.word-list strong {
  color: var(--text);
  font-size: 1rem;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score {
  color: var(--color-warm);
  font-size: 0.95rem;
  font-weight: 800;
  white-space: nowrap;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 920px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .hero-card {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
  }

  .mode-switch {
    width: 100%;
  }

  .mode-switch button {
    flex: 1;
    min-width: 0;
  }
}

@media (max-width: 560px) {
  .home {
    padding: 10px 10px 24px;
  }

  .hero-card,
  .card {
    padding: 12px;
  }

  .hero-card {
    margin-bottom: 10px;
  }

  .mode-switch {
    border-radius: 12px;
  }

  .mode-switch button {
    min-width: 0;
    padding-right: 8px;
    padding-left: 8px;
    border-radius: 9px;
  }

  .score {
    width: auto;
  }
}
</style>
