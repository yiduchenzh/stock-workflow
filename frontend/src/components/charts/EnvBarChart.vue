<template>
  <div class="env-bar-chart">
    <div class="env-bar-chart__title">📊 涨跌幅分布</div>
    <div class="env-bar-chart__body">
      <!-- Y轴刻度 -->
      <div class="env-bar-chart__yaxis">
        <span>{{ maxCount }}</span>
        <span>{{ Math.round(maxCount/2) }}</span>
        <span>0</span>
      </div>
      <!-- 柱子区域 -->
      <div class="env-bar-chart__bars" ref="barsRef">
        <div v-for="item in data.distribution" :key="item.range" class="env-bar-chart__col">
          <span class="env-bar-chart__count">{{ item.count }}</span>
          <div class="env-bar-chart__track">
            <div class="env-bar-chart__fill" :class="upClass(item.range)" :style="{ height: colHeight(item.count) }" />
          </div>
          <span class="env-bar-chart__range">{{ item.range }}</span>
        </div>
      </div>
    </div>
    <div class="env-bar-chart__footer">
      <span class="env-bar-chart__footer-item up">上涨 {{ data.up_count }}家</span>
      <span class="env-bar-chart__footer-item down">下跌 {{ data.down_count }}家</span>
      <span class="env-bar-chart__footer-item total">总计 {{ data.total }}家</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: {
    type: Object,
    default: () => ({ distribution: [], up_count: 0, down_count: 0, total: 0 })
  }
})

const maxCount = computed(() => Math.max(...props.data.distribution.map(d => d.count || 0), 1))

function upClass(range) {
  if (!range) return 'down'
  const r = String(range).trim()
  if (r.startsWith('>') || r.startsWith('+') || r === '0~1%' || r === '0~1') return 'up'
  return 'down'
}

function colHeight(count) {
  const ratio = Math.min((count || 0) / maxCount.value, 1)
  return Math.max(ratio * 100, 2) + '%'
}
</script>

<style scoped>
.env-bar-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #161B22;
  border: 1px solid #30363D;
  border-radius: 8px;
  padding: 10px;
  height: 100%;
}
.env-bar-chart__title {
  font-size: 12px;
  color: #8B949E;
  font-weight: 600;
  padding-bottom: 4px;
  border-bottom: 1px solid #21262D;
}
.env-bar-chart__body {
  display: flex;
  gap: 4px;
  flex: 1;
  min-height: 0;
}
.env-bar-chart__yaxis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 9px;
  color: #484F58;
  padding-right: 4px;
  min-width: 24px;
  text-align: right;
}
.env-bar-chart__bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  flex: 1;
  height: 140px;
}
.env-bar-chart__col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  flex: 1;
}
.env-bar-chart__count {
  font-size: 11px;
  font-weight: 700;
  color: #F0F6FC;
  line-height: 1;
}
.env-bar-chart__track {
  width: 100%;
  flex: 1;
  background: #1C2128;
  border-radius: 3px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
  min-height: 4px;
  max-height: 100px;
  width: 24px;
}
.env-bar-chart__fill {
  width: 100%;
  border-radius: 3px;
  transition: height 0.5s ease;
  min-height: 2px;
}
.env-bar-chart__fill.up { background: #EF5350; }
.env-bar-chart__fill.down { background: #26A69A; }
.env-bar-chart__range {
  font-size: 9px;
  color: #484F58;
  white-space: nowrap;
}
.env-bar-chart__footer {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding-top: 6px;
  border-top: 1px solid #21262D;
}
.env-bar-chart__footer-item { font-size: 11px; color: #8B949E; }
.env-bar-chart__footer-item.up { color: #EF5350; }
.env-bar-chart__footer-item.down { color: #26A69A; }
.env-bar-chart__footer-item.total { color: #C9D1D9; }
</style>
