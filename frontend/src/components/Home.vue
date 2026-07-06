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

.mode-switch button:hover {
  color: var(--text);
  border-color: rgba(75, 99, 130, 0.3);
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

.grid-size-controls {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}

.grid-size-controls label {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  color: var(--muted);
  font-size: 0.9rem;
  font-weight: 700;
}

.grid-size-controls select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  color: var(--text);
  background: var(--surface-light);
  font: inherit;
}

.grid-size-controls select:hover,
.grid-size-controls select:focus {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 3px rgba(75, 99, 130, 0.14);
}

.grid-wrap {
  max-width: 100%;
  margin-bottom: 14px;
  overflow-x: auto;
  padding: 2px 2px 8px;
}

.manual-grid {
  display: grid;
  width: max-content;
  max-width: 100%;
  justify-content: start;
  gap: 7px;
}

.manual-grid input {
  width: var(--cell-size);
  height: var(--cell-size);
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 9px;
  color: var(--text);
  background: var(--surface-light);
  font-size: 1.28rem;
  font-weight: 900;
  text-align: center;
  text-transform: lowercase;
  caret-color: var(--accent);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.manual-grid input:hover {
  border-color: rgba(75, 99, 130, 0.48);
}

.manual-grid input:focus {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 3px rgba(75, 99, 130, 0.18);
  transform: translateY(-1px);
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
    --cell-size: 36px;
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
