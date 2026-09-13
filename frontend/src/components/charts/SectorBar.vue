<template>
  <div class="sector-bar">
    <div class="sector-bar__header">
      <span class="sector-bar__title">板块涨幅</span>
      <button
        v-if="sortable"
        class="sector-bar__sort-btn"
        @click="toggleSort"
      >
        {{ sortLabel }}
      </button>
    </div>
    <div
      v-for="(sector, index) in sortedSectors"
      :key="sector.name"
      class="sector-bar__item"
    >
      <div class="sector-bar__label">
        <span v-if="index < 3" class="sector-bar__trophy">🏆</span>
        <span class="sector-bar__name">{{ sector.name }}</span>
      </div>
      <div class="sector-bar__track">
        <div
          class="sector-bar__fill"
          :class="{ up: pctNum(sector) > 0, down: pctNum(sector) < 0 }"
          :style="{ width: barWidth(pctNum(sector)) }"
        />
      </div>
      <span
        class="sector-bar__pct"
        :class="{ up: pctNum(sector) > 0, down: pctNum(sector) < 0 }"
      >
        {{ sector.change_pct }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  sectors: {
    type: Array,
    default: () => []
  },
  sortable: {
    type: Boolean,
    default: false
  }
})

const sortMode = ref('desc')

const sortLabel = computed(() => {
  if (sortMode.value === 'desc') return '降序'
  if (sortMode.value === 'asc') return '升序'
  return '默认'
})

function toggleSort() {
  if (sortMode.value === 'desc') {
    sortMode.value = 'asc'
  } else if (sortMode.value === 'asc') {
    sortMode.value = 'default'
  } else {
    sortMode.value = 'desc'
  }
}

function pctNum(sector) {
  return parseFloat(sector.change_pct) || 0
}

const sortedSectors = computed(() => {
  const list = [...props.sectors]
  if (sortMode.value === 'desc') {
    list.sort((a, b) => pctNum(b) - pctNum(a))
  } else if (sortMode.value === 'asc') {
    list.sort((a, b) => pctNum(a) - pctNum(b))
  }
  return list
})

function barWidth(pct) {
  const absVal = Math.abs(pct)
  const maxVal = Math.max(...props.sectors.map(s => Math.abs(pctNum(s))), 0.01)
  const ratio = Math.min(absVal / maxVal, 1)
  return `${ratio * 100}%`
}
</script>

<style scoped>
.sector-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #0D1117;
  border-radius: 8px;
  padding: 12px;
}

.sector-bar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.sector-bar__title {
  font-size: 13px;
  color: #8B949E;
}

.sector-bar__sort-btn {
  background: #21262D;
  border: 1px solid #30363D;
  border-radius: 4px;
  color: #C9D1D9;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.sector-bar__sort-btn:hover {
  background: #30363D;
}

.sector-bar__item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sector-bar__label {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 80px;
  flex-shrink: 0;
}

.sector-bar__trophy {
  font-size: 14px;
}

.sector-bar__name {
  font-size: 13px;
  color: #C9D1D9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sector-bar__track {
  flex: 1;
  height: 18px;
  background: #21262D;
  border-radius: 4px;
  overflow: hidden;
}

.sector-bar__fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.sector-bar__fill.up {
  background: #EF5350;
}

.sector-bar__fill.down {
  background: #26A69A;
}

.sector-bar__pct {
  font-size: 12px;
  font-weight: 600;
  min-width: 48px;
  text-align: right;
  flex-shrink: 0;
}

.sector-bar__pct.up {
  color: #EF5350;
}

.sector-bar__pct.down {
  color: #26A69A;
}
</style>
