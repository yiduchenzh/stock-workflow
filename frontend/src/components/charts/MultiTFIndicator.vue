<template>
  <div class="multi-tf-indicator">
    <div class="mtf-section-header">🌐 多周期共振  <span class="mtf-subtitle">周线→日线→60分</span></div>
    <div v-for="signal in signals" :key="signal.code" class="multi-tf-indicator__row">
      <span class="multi-tf-indicator__icon" :class="resonanceClass(signal.resonance)">
        {{ resonanceIcon(signal.resonance) }}
      </span>
      <span class="multi-tf-indicator__name">{{ signal.name }}</span>
      <span class="multi-tf-indicator__resonance">{{ signal.resonance }}</span>
      <span class="multi-tf-indicator__score" :class="scoreClass(signal.score)">{{ signal.score }}</span>
      <span class="multi-tf-indicator__price">{{ signal.price }}</span>
    </div>
    <div v-if="!signals.length" class="mtf-empty">暂无共振信号</div>
  </div>
</template>

<script setup>
defineProps({
  signals: { type: Array, default: () => [] }
})

function resonanceClass(resonance) {
  if (!resonance) return ''
  if (resonance.includes('三级')) return 'resonance-3'
  if (resonance.includes('两级')) return 'resonance-2'
  return 'resonance-1'
}

function resonanceIcon(resonance) {
  if (!resonance) return '\u{1F7E1}'
  if (resonance.includes('三级')) return '\u{1F7E2}'
  if (resonance.includes('两级')) return '\u{1F535}'
  return '\u{1F7E1}'
}

function scoreClass(score) {
  const n = parseInt(score, 10)
  if (isNaN(n)) return ''
  if (n >= 70) return 'score-green'
  if (n >= 40) return 'score-yellow'
  return 'score-red'
}
</script>

<style scoped>
.multi-tf-indicator {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
}
.mtf-section-header {
  font-size: var(--fs-small);
  color: var(--text-secondary);
  font-weight: 600;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
  margin-bottom: var(--space-2);
}
.mtf-subtitle {
  font-weight: 400;
  font-size: 10px;
  color: var(--text-tertiary);
  margin-left: var(--space-2);
}
.multi-tf-indicator__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
}
.multi-tf-indicator__icon { font-size: 16px; flex-shrink: 0; }
.multi-tf-indicator__name { flex: 1; font-size: 13px; color: var(--text-primary); }
.multi-tf-indicator__resonance { font-size: 11px; color: var(--text-secondary); white-space: nowrap; }
.multi-tf-indicator__score { font-size: 13px; font-weight: 700; padding: 2px 8px; border-radius: 4px; min-width: 28px; text-align: center; }
.multi-tf-indicator__score.score-green { color: #26A69A; background: rgba(38, 166, 154, 0.15); }
.multi-tf-indicator__score.score-yellow { color: #F0C040; background: rgba(240, 192, 64, 0.15); }
.multi-tf-indicator__score.score-red { color: #EF5350; background: rgba(239, 83, 80, 0.15); }
.multi-tf-indicator__price { font-size: 12px; color: var(--text-tertiary); flex-shrink: 0; }
.mtf-empty { text-align: center; color: var(--text-tertiary); font-size: 13px; padding: 20px 0; }
</style>
