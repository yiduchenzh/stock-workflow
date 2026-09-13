<template>
  <div class="gauge-card">
    <div class="gauge-visual">
      <svg viewBox="0 0 120 70" class="gauge-svg">
        <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="var(--border)" stroke-width="8" stroke-linecap="round"/>
        <path :d="arcPath" fill="none" :stroke="arcColor" stroke-width="8" stroke-linecap="round"
              style="transition: stroke-dashoffset 1s ease-out, stroke 0.5s"/>
        <text x="60" y="42" text-anchor="middle" :fill="arcColor"
              style="font-size:22px;font-weight:700;transition:fill 0.5s">{{ score }}</text>
      </svg>
    </div>
    <div class="gauge-info">
      <span class="gauge-label">市场评分</span>
      <span class="gauge-tag" :style="{ background: tagBg, color: tagColor }">{{ tagText }}</span>
    </div>
    <div class="gauge-bar">
      <div class="gauge-bar-bg">
        <div class="gauge-bar-fill" :style="{ width: score + '%', background: arcColor }" />
      </div>
      <div class="gauge-bar-labels">
        <span>弱</span>
        <span>强</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useMarketStore } from '../../stores/market'

const market = useMarketStore()
const score = computed(() => market.score)

const arcColor = computed(() => {
  if (score.value >= 70) return 'var(--score-high)'
  if (score.value >= 40) return 'var(--score-mid)'
  return 'var(--score-low)'
})

const tagText = computed(() => {
  if (score.value >= 70) return '偏强'
  if (score.value >= 40) return '中性'
  return '偏弱'
})

const tagBg = computed(() => {
  if (score.value >= 70) return 'rgba(63,185,80,0.15)'
  if (score.value >= 40) return 'rgba(210,153,34,0.15)'
  return 'rgba(248,81,73,0.15)'
})

const tagColor = computed(() => arcColor.value)

const arcPath = computed(() => {
  const r = 50, cx = 60, cy = 60
  const pct = Math.min(score.value / 100, 1)
  const angle = -180 + pct * 180
  const rad = angle * Math.PI / 180
  const x = cx + r * Math.cos(rad - Math.PI)
  const y = cy + r * Math.sin(rad - Math.PI)
  const large = pct > 0.5 ? 1 : 0
  return `M10 60 A${r} ${r} 0 ${large} 1 ${x.toFixed(1)} ${y.toFixed(1)}`
})
</script>

<style scoped>
.gauge-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  min-width: 200px;
}
.gauge-visual { width: 120px; height: 70px; }
.gauge-svg { width: 100%; height: 100%; }
.gauge-info { display: flex; align-items: center; gap: var(--space-2); }
.gauge-label { font-size: var(--fs-small); color: var(--text-secondary); }
.gauge-tag {
  font-size: var(--fs-small);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}
.gauge-bar { width: 100%; }
.gauge-bar-bg {
  height: 5px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}
.gauge-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 1s ease-out;
}
.gauge-bar-labels {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
</style>
