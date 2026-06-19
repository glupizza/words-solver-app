<template>
  <div class="home">
    <h1>Photo Word Finder</h1>

    <div class="mode-switch">
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

    <section v-if="activeMode === 'image'" class="mode-panel">
      <input type="file" accept="image/*" @change="handleFileChange" />
      <button @click="uploadImage" :disabled="!selectedImage || loading">
        Upload Image
      </button>
    </section>

    <section v-else class="mode-panel">
      <div class="grid-size-controls">
        <label>
          Строки
          <select v-model.number="manualRows" @change="resizeManualGrid">
            <option v-for="size in sizeOptions" :key="`row-${size}`" :value="size">
              {{ size }}
            </option>
          </select>
        </label>

        <label>
          Столбцы
          <select v-model.number="manualCols" @change="resizeManualGrid">
            <option v-for="size in sizeOptions" :key="`col-${size}`" :value="size">
              {{ size }}
            </option>
          </select>
        </label>
      </div>

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
            @input="normalizeManualCell(rowIndex, colIndex)"
            @keydown="handleManualCellKeydown($event, rowIndex, colIndex)"
          />
        </template>
      </div>

      <button @click="solveManualGrid" :disabled="loading">
        Найти слова
      </button>
    </section>

    <div v-if="loading" class="status">Loading...</div>
    <div v-if="errorMessage" class="error">{{ errorMessage }}</div>

    <div v-if="results.length > 0" class="results">
      <h2>Found Words:</h2>
      <ul>
        <li v-for="(word, index) in results" :key="index">
          {{ word.name || word.word }} - {{ word.score }} points
          <span v-if="word.path" class="path">
            {{ formatPath(word.path) }}
          </span>
        </li>
      </ul>
    </div>
  </div>
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
        gridTemplateColumns: `repeat(${this.manualCols}, 42px)`,
      };
    },
  },
  methods: {
    setMode(mode) {
      this.activeMode = mode;
      this.results = [];
      this.errorMessage = '';
    },
    handleFileChange(event) {
      this.selectedImage = event.target.files[0] || null;
      this.errorMessage = '';
    },
    async uploadImage() {
      if (!this.selectedImage) return;

      this.loading = true;
      this.errorMessage = '';
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
    formatPath(path) {
      return path.map(([row, col]) => `(${row + 1},${col + 1})`).join(' ');
    },
  },
};
</script>

<style scoped>
.home {
  text-align: center;
  margin-top: 50px;
}

.mode-switch {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin: 20px 0;
}

.mode-switch button {
  background-color: #e8f3ee;
  color: #244236;
}

.mode-switch button.active {
  background-color: #42b983;
  color: white;
}

.mode-panel {
  margin: 20px auto;
}

.grid-size-controls {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-bottom: 18px;
}

.grid-size-controls label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.grid-size-controls select {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 5px;
}

.manual-grid {
  display: grid;
  justify-content: center;
  gap: 6px;
  margin: 0 auto 18px;
}

.manual-grid input {
  width: 42px;
  height: 42px;
  padding: 0;
  border: 1px solid #b9c4bf;
  border-radius: 6px;
  font-size: 22px;
  text-align: center;
  text-transform: lowercase;
}

.status {
  margin-top: 16px;
}

.error {
  max-width: 560px;
  margin: 16px auto 0;
  padding: 10px 12px;
  border: 1px solid #d85d5d;
  border-radius: 6px;
  color: #9b1c1c;
  background-color: #fff1f1;
}

.results {
  margin-top: 24px;
}

ul {
  list-style-type: none;
  padding: 0;
}

li {
  margin: 10px 0;
  display: block;
}

.path {
  display: block;
  margin-top: 4px;
  color: #667;
  font-size: 0.9em;
}

button {
  padding: 10px 20px;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
}

button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

input[type="file"] {
  display: block;
  margin: 20px auto;
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 5px;
}

@media (max-width: 560px) {
  .manual-grid {
    gap: 4px;
  }

  .manual-grid input {
    width: 32px;
    height: 32px;
    font-size: 18px;
  }
}
</style>
