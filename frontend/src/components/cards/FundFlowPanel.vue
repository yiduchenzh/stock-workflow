<template>
  <div class="fund-flow-panel">
    <!-- 北向资金 -->
    <div class="fund-flow-panel__item">
      <span class="fund-flow-panel__label">北向资金</span>
      <div class="fund-flow-panel__value-wrapper">
        <span
          class="fund-flow-panel__value"
          :class="flowClass(northBound?.net_amount)"
        >
          {{ northBound?.net_amount ?? '--' }}
        </span>
        <span class="fund-flow-panel__unit">亿</span>
      </div>
    </div>

    <!-- 主力超大单 -->
    <div class="fund-flow-panel__item">
      <span class="fund-flow-panel__label">主力超大单</span>
      <div class="fund-flow-panel__value-wrapper">
        <span
          class="fund-flow-panel__value"
          :class="flowClass(mainForce?.net_amount)"
        >
          {{ mainForce?.net_amount ?? '--' }}
        </span>
        <span class="fund-flow-panel__unit">亿</span>
      </div>
    </div>

    <!-- 环境 -->
    <div class="fund-flow-panel__item">
      <span class="fund-flow-panel__label">环境</span>
      <div class="fund-flow-panel__value-wrapper">
        <span class="fund-flow-panel__value">
          {{ diagnosis?.environment ?? '--' }}
        </span>
      </div>
    </div>

    <!-- 涨跌比 -->
    <div class="fund-flow-panel__item">
      <span class="fund-flow-panel__label">涨跌比</span>
      <div class="fund-flow-panel__value-wrapper">
        <span
          class="fund-flow-panel__value"
          :class="flowClass(diagnosis?.ratio)"
        >
          {{ diagnosis?.ratio ?? '--' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  northBound: { type: Object, default: () => ({}) },
  mainForce: { type: Object, default: () => ({}) },
  diagnosis: { type: Object, default: () => ({}) }
})

function flowClass(val) {
  if (val == null) return ''
  const n = parseFloat(val)
  if (isNaN(n)) return ''
  return n >= 0 ? 'positive' : 'negative'
}
</script>

<style scoped>
.fund-flow-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  background: #161B22;
  border: 1px solid #30363D;
  border-radius: 8px;
  padding: 16px;
}

.fund-flow-panel__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px;
  background: #0D1117;
  border-radius: 6px;
}

.fund-flow-panel__label {
  font-size: 12px;
  color: #8B949E;
}

.fund-flow-panel__value-wrapper {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.fund-flow-panel__value {
  font-size: 20px;
  font-weight: 700;
  color: #E6EDF3;
}

.fund-flow-panel__value.positive {
  color: #26A69A;
}

.fund-flow-panel__value.negative {
  color: #EF5350;
}

.fund-flow-panel__unit {
  font-size: 12px;
  color: #8B949E;
}
</style>
