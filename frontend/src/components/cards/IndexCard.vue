<template>
  <div
    class="index-card"
    :class="{ 'is-up': isUp, 'is-down': isDown }"
  >
    <div class="index-card__left">
      <span class="index-card__name">{{ name }}</span>
    </div>
    <div class="index-card__right">
      <span class="index-card__price">{{ price }}</span>
      <span class="index-card__change" :class="{ 'up': isUp, 'down': isDown }">
        {{ isUp ? '↑' : isDown ? '↓' : '' }} {{ changePct }}
      </span>
    </div>
    <!-- 迷你走势线占位 -->
    <svg class="index-card__mini-chart" width="60" height="24" viewBox="0 0 60 24">
      <polyline
        :stroke="isUp ? '#EF5350' : isDown ? '#26A69A' : '#888'"
        fill="none"
        stroke-width="1.5"
        points="0,18 10,14 20,16 30,8 40,12 50,4 60,6"
      />
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, default: '' },
  price: { type: String, default: '--' },
  changePct: { type: String, default: '0.00%' }
})

const isUp = computed(() => {
  const v = parseFloat(props.changePct)
  return v > 0
})

const isDown = computed(() => {
  const v = parseFloat(props.changePct)
  return v < 0
})
</script>

<style scoped>
.index-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #161B22;
  border: 1px solid #30363D;
  border-radius: 8px;
  padding: 12px 16px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  cursor: default;
  position: relative;
  overflow: hidden;
}

.index-card:hover {
  transform: scale(1.02);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.index-card__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.index-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #C9D1D9;
}

.index-card__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.index-card__price {
  font-size: 14px;
  font-weight: 500;
  color: #E6EDF3;
}

.index-card__change {
  font-size: 13px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}

.index-card__change.up {
  color: #EF5350;
  background: rgba(239, 83, 80, 0.12);
}

.index-card__change.down {
  color: #26A69A;
  background: rgba(38, 166, 154, 0.12);
}

.index-card__mini-chart {
  position: absolute;
  right: 16px;
  bottom: 4px;
  opacity: 0.5;
}
</style>
