<template>
  <main class="home">
    <section class="hero-card">
      <div class="hero-copy">
        <p class="eyebrow">Word Solver</p>
      </div>

      <div class="mode-switch" aria-label="Выбор режима">
        <button
          type="button"
          :class="{ active: mode === 'normal' }"
          @click="mode = 'normal'"
        >
          Обычный
        </button>
        <button
          type="button"
          :class="{ active: mode === 'grail' }"
          @click="mode = 'grail'"
        >
          Грааль
        </button>
      </div>
    </section>

    <section v-if="mode === 'normal'" class="workspace">
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

    <section v-else class="workspace">
      <section class="card mode-panel">
        <div class="section-header">
          <h2>Грааль</h2>
        </div>

        <label class="file-picker grail-picker">
          <input
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/webp"
              multiple
              :disabled="grailLoading"
              @change="handleGrailFilesChange"
          />
          <span>Выбрать 5 изображений</span>
        </label>
        <p class="selection-count">{{ grailFiles.length }} из 5</p>

        <div v-if="grailSelectionMessage" class="notice selection-notice">
          {{ grailSelectionMessage }}
        </div>

        <div v-if="grailFiles.length" class="thumbnail-list" aria-label="Выбранные изображения">
          <div v-for="(item, index) in grailFiles" :key="item.preview" class="thumbnail">
            <img :src="item.preview" :alt="`Выбранное изображение ${index + 1}`" />
            <button
              type="button"
              class="remove-thumbnail"
              :aria-label="`Удалить изображение ${index + 1}`"
              :disabled="grailLoading"
              @click="removeGrailFile(index)"
            >
              ×
            </button>
          </div>
        </div>

        <button class="primary-button" :disabled="grailFiles.length !== 5 || grailLoading" @click="uploadGrailImages">
          {{ grailLoading ? 'Распознаём 5 полей и ищем слова…' : 'Найти слова' }}
        </button>
      </section>

      <aside class="card results-card">
        <div class="section-header">
          <h2>Результаты Грааля</h2>
        </div>

        <div v-if="grailLoading" class="status">
          <span class="loader" aria-hidden="true"></span>
          Распознаём 5 полей и ищем слова…
        </div>

        <div v-if="grailErrorMessage" class="notice">
          {{ grailErrorMessage }}
        </div>

        <template v-if="!grailLoading && grailHasSearched && !grailErrorMessage">
            <div class="result-tabs" role="tablist" aria-label="Результаты Грааля">
              <button
                type="button"
                role="tab"
                :aria-selected="grailTab === 'series'"
                :class="{ active: grailTab === 'series' }"
                @click="grailTab = 'series'"
              >
                Серии
              </button>

              <button
                type="button"
                role="tab"
                :aria-selected="grailTab === 'best'"
                :class="{ active: grailTab === 'best' }"
                @click="grailTab = 'best'"
              >
                Лучшие
              </button>
            </div>

          <div v-if="grailTab === 'best'">
            <div v-if="grailWords.length === 0" class="empty">Слова не найдены</div>
            <div v-else class="grail-word-list">
              <article v-for="(word, index) in grailWords" :key="`best-${word.name}-${index}`" class="grail-word-card">
                <button type="button" class="grail-word-button" :aria-expanded="expandedBestWord === index" @click="toggleBestWord(index)">
                  <strong>{{ word.name }}</strong><span class="score">{{ word.score }}</span>
                </button>
                <GrailPathMap v-if="expandedBestWord === index" :word="word.name" :path="word.path" />
              </article>
            </div>
          </div>

          <div v-else>
            <div v-if="grailSeries.length === 0" class="empty">Серии не найдены</div>
            <div v-else class="series-list">
              <article v-for="(series, seriesIndex) in grailSeries" :key="`${series.suffix}-${series.role}-${seriesIndex}`" class="series-card">
                <button
                  type="button"
                  class="series-header"
                  :aria-expanded="expandedSeries === seriesIndex"
                  @click="toggleSeries(seriesIndex, $event)"
                >
                  <strong>{{ series.suffix }}<small v-if="series.role"> · {{ series.role === 'main' ? 'Основная' : 'Выгодная' }}</small></strong>
                  <span>{{ series.words.length }} слов</span>
                  <span>{{ series.top5_sum }} очков</span>
                </button>
                <div v-if="expandedSeries === seriesIndex" class="series-words">
                  <section v-for="(bundle, bundleIndex) in seriesBundles(series)" :key="`${bundle.label}-${bundleIndex}`" class="series-bundle">
                    <h3>{{ bundle.label }} · {{ bundle.words.length }}</h3>
                  <article v-for="(word, wordIndex) in bundle.words" :key="`${word.name}-${wordIndex}`" class="grail-word-card compact-word-card">
                    <button type="button" class="grail-word-button" :aria-expanded="expandedSeriesWord === `${seriesIndex}-${bundleIndex}-${wordIndex}`" @click="toggleSeriesWord(seriesIndex, `${bundleIndex}-${wordIndex}`)">
                      <strong>{{ word.name }}</strong><span class="score">{{ word.score }}</span>
                    </button>
                    <GrailPathMap v-if="expandedSeriesWord === `${seriesIndex}-${bundleIndex}-${wordIndex}`" :word="word.name" :path="word.path" :suffix="series.suffix" />
                  </article>
                  </section>
                </div>
              </article>
            </div>
          </div>
        </template>
      </aside>
    </section>
  </main>
</template>

<script>
import GrailPathMap from './GrailPathMap.vue';

export default {
  name: 'Home',
  components: { GrailPathMap },
  data() {
    return {
      mode: 'normal',
      selectedImage: null,
      results: [],
      loading: false,
      errorMessage: '',
      hasSearched: false,
      grailFiles: [],
      grailSelectionMessage: '',
      grailWords: [],
      grailSeries: [],
      grailLoading: false,
      grailErrorMessage: '',
      grailHasSearched: false,
      grailTab: 'series',
      expandedBestWord: null,
      expandedSeries: null,
      expandedSeriesWord: null,
    };
  },
  methods: {
    handleFileChange(event) {
      this.selectedImage = event.target.files[0] || null;
      this.errorMessage = '';
      this.hasSearched = false;
    },
    handleGrailFilesChange(event) {
      const files = Array.from(event.target.files || []);

      this.clearGrailPreviews();

      this.grailFiles = files.slice(0, 5).map((file) => ({
        file,
        preview: URL.createObjectURL(file),
      }));

      this.grailSelectionMessage =
        files.length > 5
          ? 'Можно выбрать не более 5 изображений. Оставлены первые 5.'
          : '';

      this.grailErrorMessage = '';
      this.grailHasSearched = false;
      this.grailWords = [];
      this.grailSeries = [];
      this.expandedBestWord = null;
      this.expandedSeries = null;
      this.expandedSeriesWord = null;

      event.target.value = '';
    },
    removeGrailFile(index) {
      const [removed] = this.grailFiles.splice(index, 1);
      if (removed) URL.revokeObjectURL(removed.preview);
      this.grailSelectionMessage = '';
      this.grailErrorMessage = '';
      this.grailHasSearched = false;
      this.grailWords = [];
      this.grailSeries = [];
      this.expandedBestWord = null;
      this.expandedSeries = null;
      this.expandedSeriesWord = null;
    },
    clearGrailPreviews() {
      this.grailFiles.forEach((item) => URL.revokeObjectURL(item.preview));
    },
    toggleBestWord(index) {
      this.expandedBestWord = this.expandedBestWord === index ? null : index;
    },
    toggleSeries(index, event) {
      const header = event.currentTarget;
      const beforeTop = header.getBoundingClientRect().top;
      this.expandedSeries = this.expandedSeries === index ? null : index;
      this.expandedSeriesWord = null;
      this.$nextTick(() => {
        window.scrollBy(0, header.getBoundingClientRect().top - beforeTop);
      });
    },
    seriesBundles(series) {
      const suffix = Array.from(series.suffix || '');
      const bundles = new Map();
      (series.words || []).forEach((word) => {
        const chars = Array.from(word.name || '');
        const prefixLength = chars.length - suffix.length;
        const link = prefixLength > 0 ? chars[prefixLength - 1] : '';
        const position = prefixLength > 0 && Array.isArray(word.path) ? word.path[prefixLength - 1] : -1;
        const key = `${link}|${position}`;
        if (!bundles.has(key)) bundles.set(key, { label: link ? `${link}${series.suffix}` : series.suffix, words: [] });
        bundles.get(key).words.push(word);
      });
      return Array.from(bundles.values());
    },
    toggleSeriesWord(seriesIndex, wordIndex) {
      const key = `${seriesIndex}-${wordIndex}`;
      this.expandedSeriesWord = this.expandedSeriesWord === key ? null : key;
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
    async uploadGrailImages() {
      if (this.grailFiles.length !== 5 || this.grailLoading) return;

      this.grailLoading = true;
      this.grailErrorMessage = '';
      this.grailHasSearched = false;
      this.grailWords = [];
      this.grailSeries = [];
      this.expandedBestWord = null;
      this.expandedSeries = null;
      this.expandedSeriesWord = null;
      const formData = new FormData();
      this.grailFiles.forEach((item) => formData.append('images', item.file));

      try {
        const response = await fetch('/upload-grail', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          await this.setGrailErrorFromResponse(response, 'Не удалось обработать изображения');
          return;
        }

        const data = await response.json();
        this.grailWords = Array.isArray(data.words) ? data.words : [];
        this.grailSeries = Array.isArray(data.series) ? data.series : [];
        this.grailHasSearched = true;
        this.grailTab = 'series';
      } catch (error) {
        console.error('Grail network error:', error);
        this.grailErrorMessage = 'Ошибка сети';
      } finally {
        this.grailLoading = false;
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
    async setGrailErrorFromResponse(response, fallbackMessage) {
      try {
        const data = await response.json();
        this.grailErrorMessage = data.error || fallbackMessage;
      } catch (_error) {
        this.grailErrorMessage = fallbackMessage;
      }
    },
  },
  beforeUnmount() {
    this.clearGrailPreviews();
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

.grail-picker {
  width: 100%;
  min-height: 46px;
}

.selection-count {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 0.92rem;
  font-weight: 800;
}

.selection-notice {
  margin-bottom: 10px;
}

.thumbnail-list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 0 0 12px;
}

.thumbnail {
  position: relative;
  min-width: 0;
  aspect-ratio: 1;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-light);
}

.thumbnail img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.remove-thumbnail {
  position: absolute;
  top: 3px;
  right: 3px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 50%;
  color: var(--text);
  background: var(--surface);
  font-size: 1.35rem;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
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

.result-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  margin-bottom: 12px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-light);
}

.result-tabs button {
  min-height: 38px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: var(--muted);
  background: transparent;
  font-size: 0.94rem;
  font-weight: 800;
  cursor: pointer;
}

.result-tabs button.active {
  color: #ffffff;
  background: var(--accent);
  box-shadow: 0 6px 18px rgba(75, 99, 130, 0.2);
}

.grail-word-list,
.series-list {
  display: grid;
  gap: 8px;
}

.grail-word-card,
.series-card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-light);
}

.grail-word-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 46px;
  gap: 12px;
  padding: 10px;
  border-radius: 10px;
  color: var(--text);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.grail-word-button strong {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 1rem;
  font-weight: 800;
}

.grail-word-card :deep(.path-map) {
  margin-right: 10px;
  margin-left: 10px;
  padding-bottom: 10px;
}

.series-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  width: 100%;
  gap: 3px 10px;
  padding: 10px;
  border: 0;
  border-radius: 10px;
  color: var(--muted);
  background: transparent;
  font-size: 0.84rem;
  text-align: left;
  cursor: pointer;
}

.series-header strong {
  min-width: 0;
  grid-row: span 2;
  align-self: center;
  color: var(--text);
  overflow-wrap: anywhere;
  font-size: 1rem;
}

.series-header small {
  color: var(--color-warm);
  font-size: 0.78rem;
  font-weight: 800;
}

.series-words {
  display: grid;
  gap: 6px;
  padding: 0 10px 10px;
}

.series-bundle + .series-bundle {
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.series-bundle h3 {
  margin: 0 0 5px;
  color: var(--muted);
  font-size: 0.8rem;
  font-weight: 800;
}

.compact-word-card {
  background: var(--surface);
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

  .thumbnail-list {
    gap: 6px;
  }

  .remove-thumbnail {
    width: 30px;
    height: 30px;
  }
}
</style>
