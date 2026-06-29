<template>
  <main class="home">
    <section class="hero-card">
      <div class="hero-copy">
        <p class="eyebrow">Word Solver</p>
      </div>

      <div class="mode-switch" aria-label="Выбор режима">
        <button
          type="button"
          :class="{ active: activeMode === 'image' }"
          @click="setMode('image')"
        >
          По изображению
        </button>
        <button
          type="button"
          :class="{ active: activeMode === 'manual' }"
          @click="setMode('manual')"
        >
          Ручной ввод
        </button>
      </div>
    </section>

    <section class="workspace">
      <section v-if="activeMode === 'image'" class="card mode-panel">
        <div class="section-header">
          <h2>По изображению</h2>
        </div>

        <label class="file-picker">
          <input type="file" accept="image/*" @change="handleFileChange" />
          <span>Выбрать файл</span>
        </label>

        <p class="file-name">
          {{ selectedImage ? selectedImage.name : 'Файл не выбран' }}
        </p>

        <button class="primary-button" @click="uploadImage" :disabled="!selectedImage || loading">
          {{ loading ? 'Обработка...' : 'Найти слова' }}
        </button>
      </section>

      <section v-else class="card mode-panel">
        <div class="section-header">
          <h2>Ручной ввод</h2>
        </div>

        <div class="grid-size-controls">
          <label>
            <span>Строки</span>
            <select v-model.number="manualRows" @change="resizeManualGrid">
              <option v-for="size in sizeOptions" :key="`row-${size}`" :value="size">
                {{ size }}
              </option>
            </select>
          </label>

          <label>
            <span>Столбцы</span>
            <select v-model.number="manualCols" @change="resizeManualGrid">
              <option v-for="size in sizeOptions" :key="`col-${size}`" :value="size">
                {{ size }}
              </option>
            </select>
          </label>
        </div>

        <div class="grid-wrap">
          <div class="manual-grid" :style="manualGridStyle">
            <template v-for="(row, rowIndex) in manualGrid" :key="rowIndex">
              <input
                v-for="(_cell, colIndex) in row"
                :key="`${rowIndex}-${colIndex}`"
                :ref="(el) => setCellRef(el, rowIndex, colIndex)"
                v-model="manualGrid[rowIndex][colIndex]"
                type="text"
                maxlength="1"
                inputmode="text"
                autocomplete="off"
                :aria-label="`Строка ${rowIndex + 1}, столбец ${colIndex + 1}`"
                @input="normalizeManualCell(rowIndex, colIndex)"
                @keydown="handleManualCellKeydown($event, rowIndex, colIndex)"
              />
            </template>
          </div>
        </div>

        <button class="primary-button" @click="solveManualGrid" :disabled="loading">
          {{ loading ? 'Ищу слова...' : 'Найти слова' }}
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
          <li v-for="(word, index) in results" :key="`${word.name || word.word}-${index}`">
            <strong>{{ word.name || word.word }}</strong>
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
      activeMode: 'image',
      selectedImage: null,
      results: [],
      loading: false,
      errorMessage: '',
      hasSearched: false,
      manualRows: 5,
      manualCols: 5,
      manualGrid: Array.from({ length: 5 }, () => Array(5).fill('')),
      manualCellRefs: [],
    };
  },
  computed: {
    sizeOptions() {
      return Array.from({ length: 8 }, (_, index) => index + 2);
    },
    manualGridStyle() {
      return {
        gridTemplateColumns: `repeat(${this.manualCols}, var(--cell-size))`,
      };
    },
  },
  methods: {
    setMode(mode) {
      this.activeMode = mode;
      this.results = [];
      this.errorMessage = '';
      this.hasSearched = false;
    },
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
    resizeManualGrid() {
      const nextGrid = Array.from({ length: this.manualRows }, (_, rowIndex) =>
        Array.from({ length: this.manualCols }, (_unused, colIndex) =>
          this.manualGrid[rowIndex]?.[colIndex] || ''
        )
      );

      this.manualGrid = nextGrid;
      this.manualCellRefs = [];
      this.results = [];
      this.errorMessage = '';
      this.hasSearched = false;
    },
    setCellRef(el, rowIndex, colIndex) {
      if (!el) return;
      if (!this.manualCellRefs[rowIndex]) {
        this.manualCellRefs[rowIndex] = [];
      }
      this.manualCellRefs[rowIndex][colIndex] = el;
    },
    normalizeManualCell(rowIndex, colIndex) {
      const value = this.manualGrid[rowIndex][colIndex] || '';
      this.manualGrid[rowIndex][colIndex] = value.trim().toLowerCase().slice(0, 1);
      this.errorMessage = '';

      if (this.manualGrid[rowIndex][colIndex]) {
        this.focusNextCell(rowIndex, colIndex);
      }
    },
    handleManualCellKeydown(event, rowIndex, colIndex) {
      const moves = {
        ArrowLeft: [rowIndex, colIndex - 1],
        ArrowRight: [rowIndex, colIndex + 1],
        ArrowUp: [rowIndex - 1, colIndex],
        ArrowDown: [rowIndex + 1, colIndex],
      };

      if (moves[event.key]) {
        const [nextRow, nextCol] = moves[event.key];
        if (this.focusCell(nextRow, nextCol)) {
          event.preventDefault();
        }
        return;
      }

      if (event.key === 'Backspace' && !this.manualGrid[rowIndex][colIndex]) {
        const previousCell = this.getPreviousCell(rowIndex, colIndex);
        if (previousCell) {
          event.preventDefault();
          this.focusCell(previousCell.row, previousCell.col);
        }
      }
    },
    focusNextCell(rowIndex, colIndex) {
      const nextCol = colIndex + 1;
      if (nextCol < this.manualCols) {
        this.focusCell(rowIndex, nextCol);
        return;
      }

      const nextRow = rowIndex + 1;
      if (nextRow < this.manualRows) {
        this.focusCell(nextRow, 0);
      }
    },
    getPreviousCell(rowIndex, colIndex) {
      const previousCol = colIndex - 1;
      if (previousCol >= 0) {
        return { row: rowIndex, col: previousCol };
      }

      const previousRow = rowIndex - 1;
      if (previousRow >= 0) {
        return { row: previousRow, col: this.manualCols - 1 };
      }

      return null;
    },
    focusCell(rowIndex, colIndex) {
      if (
        rowIndex < 0 ||
        rowIndex >= this.manualRows ||
        colIndex < 0 ||
        colIndex >= this.manualCols
      ) {
        return false;
      }

      const cell = this.manualCellRefs[rowIndex]?.[colIndex];
      if (!cell) return false;

      cell.focus();
      cell.select();
      return true;
    },
    async solveManualGrid() {
      this.loading = true;
      this.errorMessage = '';
      this.hasSearched = false;
      this.results = [];

      try {
        const response = await fetch("/solve-grid", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ grid: this.manualGrid }),
        });

        if (!response.ok) {
          await this.setErrorFromResponse(response, "Не удалось найти слова");
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
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: 24px 18px 40px;
}

.hero-card,
.card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background:
    linear-gradient(135deg, rgba(88, 204, 2, 0.08), transparent 34%),
    var(--surface);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}

.hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 22px;
  margin-bottom: 16px;
}

.hero-copy,
.section-header {
  text-align: left;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h2,
p {
  margin-top: 0;
}

h2 {
  margin-bottom: 0;
  color: var(--text);
  font-size: 1.25rem;
}

.section-header p,
.file-name {
  color: var(--muted);
}

.mode-switch {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 6px;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-light);
}

.mode-switch button {
  min-width: 150px;
  padding: 12px 18px;
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--muted);
  background: transparent;
  font-weight: 800;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
}

.mode-switch button:hover {
  color: var(--text);
  border-color: rgba(88, 204, 2, 0.35);
}

.mode-switch button.active {
  color: #071006;
  background: var(--accent);
  box-shadow: 0 0 28px rgba(88, 204, 2, 0.28);
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
  gap: 16px;
  align-items: start;
}

.card {
  padding: 20px;
}

.section-header {
  margin-bottom: 16px;
}

.mode-panel {
  min-height: 0;
}

.file-picker {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 118px;
  margin-bottom: 12px;
  border: 1px dashed rgba(88, 204, 2, 0.45);
  border-radius: calc(var(--radius) - 6px);
  color: var(--text);
  background:
    radial-gradient(circle at 50% 0%, rgba(88, 204, 2, 0.14), transparent 38%),
    var(--surface-light);
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.file-picker:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
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
  padding: 12px 18px;
  border: 1px solid rgba(88, 204, 2, 0.65);
  border-radius: 12px;
  color: var(--accent);
  background: rgba(88, 204, 2, 0.08);
  font-weight: 800;
}

.file-name {
  min-height: 24px;
  margin-bottom: 18px;
  word-break: break-word;
}

.grid-size-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.grid-size-controls label {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  color: var(--muted);
  font-size: 0.92rem;
  font-weight: 700;
}

.grid-size-controls select {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  color: var(--text);
  background: var(--surface-light);
  font: inherit;
}

.grid-size-controls select:hover,
.grid-size-controls select:focus {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 3px rgba(88, 204, 2, 0.12);
}

.grid-wrap {
  max-width: 100%;
  margin-bottom: 20px;
  overflow-x: auto;
  padding: 4px 2px 10px;
}

.manual-grid {
  display: grid;
  width: max-content;
  max-width: 100%;
  justify-content: start;
  gap: 8px;
}

.manual-grid input {
  width: var(--cell-size);
  height: var(--cell-size);
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  color: var(--text);
  background: var(--surface-light);
  font-size: 1.4rem;
  font-weight: 900;
  text-align: center;
  text-transform: lowercase;
  caret-color: var(--accent);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.manual-grid input:hover {
  border-color: rgba(88, 204, 2, 0.55);
}

.manual-grid input:focus {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 3px rgba(88, 204, 2, 0.18), 0 0 18px rgba(88, 204, 2, 0.18);
  transform: translateY(-1px);
}

.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 48px;
  padding: 12px 18px;
  border: 1px solid transparent;
  border-radius: 14px;
  color: #071006;
  background: var(--accent);
  font-size: 1rem;
  font-weight: 900;
  cursor: pointer;
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
}

.primary-button:hover:not(:disabled) {
  background: var(--accent-hover);
  box-shadow: 0 12px 34px rgba(88, 204, 2, 0.24);
  transform: translateY(-1px);
}

.primary-button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

button:focus-visible,
.file-picker:focus-within {
  outline: none;
  box-shadow: 0 0 0 3px rgba(88, 204, 2, 0.2);
}

.status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  color: var(--text);
  background: var(--surface-light);
}

.loader {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(88, 204, 2, 0.25);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.notice,
.empty {
  padding: 14px;
  border: 1px solid rgba(88, 204, 2, 0.35);
  border-radius: 12px;
  color: var(--text);
  background: rgba(88, 204, 2, 0.08);
}

.empty {
  color: var(--muted);
}

.word-list {
  max-height: 560px;
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
  padding: 8px 0;
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
  color: var(--accent);
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
    --cell-size: 36px;
    padding: 12px 10px 28px;
  }

  .hero-card,
  .card {
    padding: 14px;
  }

  .hero-card {
    gap: 12px;
    margin-bottom: 12px;
  }

  .mode-switch {
    flex-direction: column;
    border-radius: 18px;
  }

  .mode-switch button {
    border-radius: 13px;
  }

  .grid-size-controls {
    flex-direction: column;
  }

  .manual-grid {
    gap: 6px;
  }

  .manual-grid input {
    border-radius: 10px;
    font-size: 1.05rem;
  }

  .score {
    width: auto;
  }
}
</style>
