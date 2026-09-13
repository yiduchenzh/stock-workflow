<template>
  <footer class="status-bar">
    <div class="ticker-scroll">
      <template v-for="(item, idx) in tickerItems" :key="idx">
        <span v-if="idx > 0" class="ticker-sep">|</span>
        <span class="ticker-item">
          <span class="ticker-name">{{ item.name }}</span>
          <span class="ticker-price">{{ item.price }}</span>
          <span :class="['ticker-change', item.change >= 0 ? 'up' : 'down']">
            ({{ item.change >= 0 ? '+' : '' }}{{ item.change }}%)
          </span>
        </span>
      </template>
      <span v-if="!tickerItems.length" class="ticker-empty">行情数据加载中...</span>
    </div>
  </footer>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const tickerItems = ref([])
let timer = null

const INDEX_MAP = {
  '上证指数': '上证',
  '深证成指': '深证',
  '创业板指': '创业板',
  '沪深300': '沪深300',
  '科创50': '科创50'
}

async function fetchMarketData() {
  try {
    const res = await fetch('http://127.0.0.1:7878/api/market/overview')
    if (!res.ok) return
    const data = await res.json()
    const indices = data.indices || data.result?.indices || {}
    const items = []
    for (const [fullName, val] of Object.entries(indices)) {
      const name = INDEX_MAP[fullName] || fullName
      const parts = String(val).split(' ')
      const price = parts[0] || '—'
      const changeStr = (parts[1] || '0.00%').replace('%', '')
      const change = parseFloat(changeStr) || 0
      items.push({ name, price, change })
    }
    if (items.length) tickerItems.value = items
  } catch (e) {
    // silent — keep last known data
  }
}

onMounted(() => {
  fetchMarketData()
  timer = setInterval(fetchMarketData, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.status-bar {
  height: 32px;
  background: var(--bg-primary, #0D1117);
  border-top: 1px solid var(--border, #30363D);
  display: flex;
  align-items: center;
  overflow: hidden;
}

.ticker-scroll {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.ticker-scroll::-webkit-scrollbar {
  display: none;
}

.ticker-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.ticker-name {
  color: var(--text-secondary, #8B949E);
  font-weight: 500;
}

.ticker-price {
  color: var(--text-primary, #F0F6FC);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.ticker-change {
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.ticker-change.up {
  color: var(--up, #EF5350);
}

.ticker-change.down {
  color: var(--down, #26A69A);
}

.ticker-sep {
  color: var(--border, #30363D);
  font-size: 10px;
  user-select: none;
}

.ticker-empty {
  color: var(--text-secondary, #8B949E);
  font-size: 12px;
}
</style>
