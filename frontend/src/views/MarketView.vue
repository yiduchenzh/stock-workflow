<template>
  <div class="market-view">
    <div class="market-main">
      <!-- 外围市场 -->
      <div class="section-card">
        <div class="section-header">🌐 外围市场</div>
        <div class="section-body">
          <div class="global-grid">
            <IndexCard v-for="idx in globalIndices" :key="'g'+idx.code"
              :name="idx.name" :price="idx.price" :changePct="idx.changePct"
              :changeAmt="idx.changeAmt" />
          </div>
        </div>
      </div>
      <!-- A股指数 -->
      <div class="section-card">
        <div class="section-header">📊 A股指数</div>
        <div class="section-body row-top">
          <MarketScore />
          <div class="index-grid">
            <IndexCard v-for="idx in indices" :key="idx.code"
              :name="idx.name" :price="idx.price" :changePct="idx.changePct"
              :changeAmt="idx.changeAmt" />
          </div>
        </div>
      </div>

      <!-- 板块轮动 + 板块资金净流入 + 市场环境柱状图 -->
      <div class="row-mid">
        <SectorBar :sectors="sectors" :sortable="true" class="panel-third" />
        <SectorFundFlow :sectors="sectorFundFlow" class="panel-third" />
        <EnvBarChart :data="envData" class="panel-third" />
      </div>

      <!-- 多周期共振 -->
      <MultiTFIndicator :signals="mtfSignals" class="row-bottom" />
    </div>

    <!-- 右侧屏: 今日计划 -->
    <div class="market-side">
      <TodayPlan :plan="{
        market_score: market.score,
        market_regime: market.regime,
        plans: market.plans,
        alerts: market.alerts,
        hasPlan: !!(market.plans && market.plans.length)
      }" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useMarketStore } from '../stores/market'
import MarketScore from '../components/gauge/MarketScore.vue'
import IndexCard from '../components/cards/IndexCard.vue'
import SectorBar from '../components/charts/SectorBar.vue'
import SectorFundFlow from '../components/charts/SectorFundFlow.vue'
import EnvBarChart from '../components/charts/EnvBarChart.vue'
import MultiTFIndicator from '../components/charts/MultiTFIndicator.vue'
import TodayPlan from '../components/cards/TodayPlan.vue'

const market = useMarketStore()
const sectors = ref([])
const sectorFundFlow = ref([])
const envData = ref({ distribution: [], up_count: 0, down_count: 0, total: 0 })
const mtfSignals = ref([])

const indices = ref([])
const globalIndices = ref([])

function parseIndices(raw) {
  const list = []
  const map = {
    '\u4e0a\u8bc1\u6307\u6570': '000001', '\u6df1\u8bc1\u6210\u6307': '399001',
    '\u521b\u4e1a\u677f\u6307': '399006', '\u79d1\u521b50': '000688',
  }
  for (const [name, val] of Object.entries(raw || {})) {
    const parts = val.split(' ')
    const price = parts[0] || '\u2014'
    const changePct = parts[1] || '0.00%'
    const isUp = !changePct.startsWith('-')
    list.push({ code: map[name] || '', name, price, changePct, changeAmt: changePct, isUp })
  }
  return list
}

async function fetchAll() {
  try {
    const [overviewRes, sectorsRes, sfRes, envRes, mtfRes] = await Promise.all([
      fetch('/api/market/overview'),
      fetch('/api/market/sectors'),
      fetch('/api/market/sector-fundflow'),
      fetch('/api/market/environment'),
      fetch('/api/market/mtf-signals'),
    ])
    const overview = await overviewRes.json()
    if (overview.indices) indices.value = parseIndices(overview.indices)
    if (overview.global_indices) globalIndices.value = parseIndices(overview.global_indices)
    market.update(overview)

    const s = await sectorsRes.json()
    if (s.sectors) sectors.value = s.sectors

    const sf = await sfRes.json()
    if (sf.sectors) sectorFundFlow.value = sf.sectors

    const env = await envRes.json()
    envData.value = env

    const m = await mtfRes.json()
    if (m.signals) mtfSignals.value = m.signals
  } catch (e) {
    console.warn('[MarketView] fetch error:', e)
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.market-view {
  display: flex;
  gap: var(--space-4);
  flex: 1;
  min-height: 0;
}
.market-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}
.market-side {
  width: 300px;
  flex-shrink: 0;
}
.section-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.section-header {
  padding: var(--space-2) var(--space-3);
  font-size: var(--fs-small);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
.section-body { padding: var(--space-3); }
.row-top {
  display: flex;
  gap: var(--space-4);
  align-items: stretch;
}
.index-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
}
.global-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
}
.row-mid {
  display: flex;
  gap: var(--space-4);
}
.panel-third {
  flex: 1;
  min-width: 0;
}
.row-bottom { flex-shrink: 0; }
</style>
