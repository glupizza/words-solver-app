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
        :class="{ used: cell.used }"
      >
        <template v-if="cell.used">
          <span class="path-order">{{ cell.order }}</span>
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
  },
  computed: {
    usedCells() {
      return this.path.reduce((cells, position, index) => {
        if (Number.isInteger(position) && position >= 0 && position < 25) {
          cells[position] = {
            letter: Array.from(this.word)[index] || '',
            order: index + 1,
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
      return this.path
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

.path-letter {
  font-size: clamp(0.78rem, 4vw, 1rem);
  font-weight: 900;
}

.path-order {
  position: absolute;
  top: 2px;
  left: 4px;
  font-size: 0.58rem;
  font-weight: 800;
}
</style>
