<template>
  <div class="sector-fund-flow">
    <div class="sector-fund-flow__header">
      <span class="sector-fund-flow__title">板块资金净流入</span>
      <button
        class="sector-fund-flow__sort-btn"
        @click="toggleSort"
      >
        {{ sortLabel }}
      </button>
    </div>
    <div
      v-for="sector in sortedSectors"
      :key="sector.name"
      class="sector-fund-flow__item"
    >
      <span class="sector-fund-flow__name">{{ sector.name }}</span>
      <div class="sector-fund-flow__track">
        <div
          class="sector-fund-flow__bar"
          :class="flowClass(sector.net_flow_yi)"
          :style="{ width: barWidth(sector.net_flow_yi) }"
        />
      </div>
      <span
        class="sector-fund-flow__amount"
        :class="flowClass(sector.net_flow_yi)"
      >
        {{ sector.net_flow_yi }}亿
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

function flowVal(sector) {
  return parseFloat(sector.net_flow_yi) || 0
}

function flowClass(val) {
  const n = parseFloat(val) || 0
  return n >= 0 ? 'inflow' : 'outflow'
}

const sortedSectors = computed(() => {
  const list = [...props.sectors]
  if (sortMode.value === 'desc') {
    list.sort((a, b) => flowVal(b) - flowVal(a))
  } else if (sortMode.value === 'asc') {
    list.sort((a, b) => flowVal(a) - flowVal(b))
  }
  return list
})

function barWidth(val) {
  const absVal = Math.abs(parseFloat(val) || 0)
  const maxVal = Math.max(...props.sectors.map(s => Math.abs(parseFloat(s.net_flow_yi) || 0)), 0.01)
  const ratio = Math.min(absVal / maxVal, 1)
  return `${ratio * 100}%`
}
</script>

<style scoped>
.sector-fund-flow {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #0D1117;
  border-radius: 8px;
  padding: 12px;
}

.sector-fund-flow__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.sector-fund-flow__title {
  font-size: 13px;
  color: #8B949E;
}

.sector-fund-flow__sort-btn {
  background: #21262D;
  border: 1px solid #30363D;
  border-radius: 4px;
  color: #C9D1D9;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.sector-fund-flow__sort-btn:hover {
  background: #30363D;
}

.sector-fund-flow__item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sector-fund-flow__name {
  font-size: 13px;
  color: #C9D1D9;
  min-width: 80px;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sector-fund-flow__track {
  flex: 1;
  height: 18px;
  background: #21262D;
  border-radius: 4px;
  overflow: hidden;
}

.sector-fund-flow__bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.sector-fund-flow__bar.inflow {
  background: #EF5350;
}

.sector-fund-flow__bar.outflow {
  background: #26A69A;
}

.sector-fund-flow__amount {
  font-size: 12px;
  font-weight: 600;
  min-width: 60px;
  text-align: right;
  flex-shrink: 0;
}

.sector-fund-flow__amount.inflow {
  color: #EF5350;
}

.sector-fund-flow__amount.outflow {
  color: #26A69A;
}
</style>
