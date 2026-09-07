<template>
  <div class="path-map" aria-label="Путь слова на поле 5 на 5">
    <svg class="path-lines" viewBox="0 0 250 250" aria-hidden="true">
      <polyline v-if="points" :points="points" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    <div class="path-grid">
      <div
        v-for="cell in cells"
        :key="cell.position"
        class="path-cell"
        :class="{ used: cell.used, suffix: cell.suffix, start: cell.start }"
      >
        <template v-if="cell.used">
          <span class="path-letter">{{ cell.letter }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'GrailPathMap',
  props: {
    word: {
      type: String,
      required: true,
    },
    path: {
      type: Array,
      required: true,
    },
    suffix: {
      type: String,
      default: '',
    },
  },
  computed: {
    wordCharacters() {
      const word = typeof this.word === 'string' ? this.word : '';
      return Array.from(word);
    },
    suffixStartIndex() {
      const word = typeof this.word === 'string' ? this.word : '';
      const suffix = typeof this.suffix === 'string' ? this.suffix : '';
      const wordCharacters = Array.from(word);
      const suffixCharacters = Array.from(suffix);
      if (
        !Array.isArray(this.path)
        || !word
        || !suffix
        || !suffixCharacters.length
        || this.path.length !== wordCharacters.length
        || !word.endsWith(suffix)
      ) {
        return null;
      }
      return wordCharacters.length - suffixCharacters.length;
    },
    usedCells() {
      const path = Array.isArray(this.path) ? this.path : [];
      return path.reduce((cells, position, index) => {
        if (Number.isInteger(position) && position >= 0 && position < 25) {
          cells[position] = {
            letter: this.wordCharacters[index] || '',
            suffix: this.suffixStartIndex !== null && index >= this.suffixStartIndex,
            start: index === 0,
          };
        }
        return cells;
      }, {});
    },
    cells() {
      return Array.from({ length: 25 }, (_cell, position) => ({
        position,
        used: Boolean(this.usedCells[position]),
        ...this.usedCells[position],
      }));
    },
    points() {
      const path = Array.isArray(this.path) ? this.path : [];
      return path
        .filter((position) => Number.isInteger(position) && position >= 0 && position < 25)
        .map((position) => `${(position % 5) * 50 + 25},${Math.floor(position / 5) * 50 + 25}`)
        .join(' ');
    },
  },
};
</script>

<style scoped>
.path-map {
  position: relative;
  width: min(100%, 250px);
  margin: 10px 0 2px;
  color: var(--accent);
}

.path-lines,
.path-grid {
  width: 100%;
  aspect-ratio: 1;
}

.path-lines {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.path-grid {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 3px;
}

.path-cell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--surface-light);
}

.path-cell.used {
  border-color: var(--accent);
  color: #ffffff;
  background: var(--accent);
  box-shadow: 0 2px 8px rgba(75, 99, 130, 0.22);
}

.path-cell.used.suffix {
  border-color: var(--color-warm);
  background: var(--color-warm);
}

.path-cell.used.start {
  border-color: var(--color-secondary);
  color: var(--text);
  background: var(--color-secondary);
  box-shadow: 0 2px 8px rgba(75, 99, 130, 0.22);
}

.path-cell.used.start.suffix {
  border-color: var(--color-warm);
  color: #ffffff;
  background: var(--accent-hover);
  box-shadow: inset 0 0 0 3px var(--color-warm), 0 2px 8px rgba(75, 99, 130, 0.22);
}

.path-letter {
  font-size: clamp(1rem, 5vw, 1.3rem);
  font-weight: 900;
}
</style>
