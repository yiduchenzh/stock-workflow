<template>
  <div class="signals-view">
    <div class="filter-bar">
      <button v-for="f in filters" :key="f.key"
        :class="['filter-btn', { active: activeFilter === f.key }]"
        @click="activeFilter = f.key">{{ f.label }}</button>
      <span class="signal-count">共 {{ filteredSignals.length }} 条</span>
    </div>

    <div class="signal-list">
      <div v-for="sig in filteredSignals" :key="sig.code + sig.strategy"
        :class="['signal-card', sig.strength?.icon === 'fire' ? 'strong' : sig.strength?.icon === 'warning' ? 'mid' : 'weak']"
        @click="selected = selected?.code === sig.code && selected?.strategy === sig.strategy ? null : sig">
        <div class="card-header">
          <div class="card-tags">
            <span :class="['tag-strategy', sig.safe_strategy ? 's'+hashStr(sig.safe_strategy) : '']">{{ sig.safe_strategy }}</span>
            <span :class="['tag-strength', sig.strength?.icon]">{{ sig.strength?.label }}</span>
          </div>
          <div class="card-score" :class="scoreClass(sig.score)">{{ sig.score }}分</div>
        </div>
        <div class="card-body">
          <span class="stock-name">{{ sig.name }}</span>
          <span class="stock-code">{{ sig.code }}</span>
          <span class="stock-price">{{ sig.price }}</span>
          <span class="stock-action">{{ sig.safe_action }}</span>
          <button class="research-btn" @click.stop="openResearch(sig)">深度研究</button>
        </div>
        <div class="card-compliance">{{ sig.safe_action }} · {{ sig.safe_strategy }} · {{ sig.strength?.label }}</div>
        <div v-if="selected?.code === sig.code && selected?.strategy === sig.strategy" class="card-detail">
          <div v-for="(v, k) in sig.commentary_6d" :key="k" class="detail-item">
            <span class="detail-label">{{ detailLabels[k] || k }}</span>
            <span class="detail-text">{{ v }}</span>
          </div>
        </div>
      </div>
      <div v-if="!filteredSignals.length" class="empty">暂无信号</div>
    </div>

    <!-- 深度研究弹窗 -->
    <div v-if="showResearch" class="research-overlay" @click.self="showResearch=false">
      <div class="research-modal">
        <div class="modal-header">
          <span class="modal-title">📊 {{ researchData?.name || '' }} 深度研究</span>
          <button class="modal-close" @click="showResearch=false">✕</button>
        </div>
        <div class="modal-body" v-if="researchData">
          <!-- 实时行情 -->
          <div class="r-section r-quote">
            <span>现价 <b>{{ researchData.price }}</b></span>
            <span>开 {{ researchData.open }}</span>
            <span>高 {{ researchData.high }}</span>
            <span>低 {{ researchData.low }}</span>
          </div>
          <!-- 技术指标 -->
          <div class="r-section" v-if="researchData.technicals">
            <div class="r-title">📈 技术指标</div>
            <div class="r-grid">
              <div class="r-item"><span class="r-lbl">MA5</span><span class="r-val">{{ researchData.technicals.ma5 }}</span></div>
              <div class="r-item"><span class="r-lbl">MA20</span><span class="r-val" :class="researchData.technicals.above_ma20 ? 'up' : 'dn'">{{ researchData.technicals.ma20 }}</span></div>
              <div class="r-item"><span class="r-lbl">MA60</span><span class="r-val">{{ researchData.technicals.ma60 }}</span></div>
              <div class="r-item"><span class="r-lbl">20日涨跌</span><span class="r-val" :class="researchData.technicals.change_20d >= 0 ? 'up' : 'dn'">{{ researchData.technicals.change_20d }}%</span></div>
            </div>
          </div>
          <!-- 估值 -->
          <div class="r-section">
            <div class="r-title">💰 DCF估值</div>
            <div class="r-grid">
              <div class="r-item"><span class="r-lbl">PE(TTM)</span><span class="r-val">{{ researchData.valuation.pe_ttm }}</span></div>
              <div class="r-item"><span class="r-lbl">PB</span><span class="r-val">{{ researchData.valuation.pb }}</span></div>
              <div class="r-item"><span class="r-lbl">DCF高估</span><span class="r-val up">{{ researchData.valuation.dcf_value_high }}</span></div>
              <div class="r-item"><span class="r-lbl">DCF低估</span><span class="r-val dn">{{ researchData.valuation.dcf_value_low }}</span></div>
              <div class="r-item"><span class="r-lbl">行业均值PE</span><span class="r-val">{{ researchData.valuation.sector_avg_pe }}</span></div>
            </div>
          </div>
          <!-- 风险 -->
          <div class="r-section">
            <div class="r-title">⚠️ 风险评估</div>
            <div class="r-grid">
              <div class="r-item"><span class="r-lbl">VaR(95%)</span><span class="r-val dn">{{ researchData.risk.var_95 }}</span></div>
              <div class="r-item"><span class="r-lbl">波动率</span><span class="r-val">{{ researchData.risk.volatility_20d }}%</span></div>
              <div class="r-item"><span class="r-lbl">风险评分</span><span class="r-val" :class="scoreClass(researchData.risk.score)">{{ researchData.risk.score }}</span></div>
            </div>
          </div>
        </div>
        <div v-else class="modal-body" style="text-align:center;padding:40px">加载中...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSignalsStore } from '../stores/signals'

const store = useSignalsStore()
const activeFilter = ref('all')
const selected = ref(null)
const showResearch = ref(false)
const researchData = ref(null)

const filters = [
  { key: 'all', label: '全部' }, { key: 'strong', label: '较强' },
  { key: 'mid', label: '一般' }, { key: 'chan', label: '缠论' }, { key: 'naked', label: '裸K' },
]

const detailLabels = { '1_selection':'选股逻辑','2_trigger':'触发条件','3_strategy':'策略适配','4_risk':'风控位','5_holding':'关注周期','6_history':'历史表现' }

function hashStr(s) { let h = 0; for (let c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h) % 5 }
function scoreClass(s) { const n = parseInt(s); if (n >= 70) return 'sc-up'; if (n >= 40) return 'sc-mid'; return 'sc-dn' }

const filteredSignals = computed(() => {
  let list = store.signalList
  if (activeFilter.value === 'all') return list
  if (activeFilter.value === 'strong') return list.filter(s => s.strength?.icon === 'fire')
  if (activeFilter.value === 'mid') return list.filter(s => s.strength?.icon === 'warning')
  if (activeFilter.value === 'chan') return list.filter(s => (s.safe_strategy || '').includes('缠') || s.strategy?.startsWith('chan'))
  if (activeFilter.value === 'naked') return list.filter(s => (s.safe_strategy || '').includes('裸') || s.strategy?.startsWith('naked'))
  return list
})

async function openResearch(sig) {
  showResearch.value = true
  researchData.value = null
  try {
    const r = await fetch(`/api/research/${sig.code}`)
    researchData.value = await r.json()
  } catch (e) {
    researchData.value = { name: sig.name, price: sig.price }
  }
}

onMounted(() => store.fetchSignals())
</script>

<style scoped>
.signals-view { display: flex; flex-direction: column; gap: var(--space-3); flex: 1; position: relative; }
.filter-bar { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) 0; }
.filter-btn { padding: 4px 14px; border-radius: 20px; border: 1px solid var(--border); background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: all .2s; }
.filter-btn.active { background: #1F6FEB; color: #fff; border-color: #1F6FEB; }
.filter-btn:hover:not(.active) { border-color: var(--text-secondary); }
.signal-count { margin-left: auto; font-size: 11px; color: var(--text-tertiary); }
.signal-list { display: flex; flex-direction: column; gap: var(--space-3); flex: 1; overflow-y: auto; }
.signal-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-3); cursor: pointer; transition: all .2s; border-left: 4px solid; }
.signal-card.strong { border-left-color: var(--up); } .signal-card.mid { border-left-color: #F0C040; } .signal-card.weak { border-left-color: var(--text-tertiary); }
.signal-card:hover { background: var(--bg-tertiary); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2); }
.card-tags { display: flex; gap: var(--space-1); flex-wrap: wrap; }
.tag-strategy { padding: 1px 8px; border-radius: 3px; font-size: 10px; font-weight: 600; background: rgba(88,166,255,.12); color: #58A6FF; }
.tag-strategy.s0 { background: rgba(239,83,80,.12); color: #EF5350; }
.tag-strategy.s1 { background: rgba(38,166,154,.12); color: #26A69A; }
.tag-strategy.s2 { background: rgba(240,192,64,.12); color: #F0C040; }
.tag-strength { padding: 1px 8px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.tag-strength.fire { background: rgba(239,83,80,.12); color: #EF5350; }
.tag-strength.warning { background: rgba(240,192,64,.12); color: #F0C040; }
.card-score { font-size: 18px; font-weight: 700; } .sc-up { color: var(--up); } .sc-mid { color: #F0C040; } .sc-dn { color: var(--down); }
.card-body { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
.stock-name { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.stock-code { font-size: 11px; color: var(--text-tertiary); font-family: monospace; }
.stock-price { font-size: 13px; color: var(--text-secondary); }
.stock-action { font-size: 11px; padding: 2px 8px; border-radius: 3px; background: var(--bg-primary); color: var(--text-secondary); }
.research-btn { margin-left: auto; padding: 3px 10px; font-size: 11px; background: transparent; border: 1px solid #58A6FF; color: #58A6FF; border-radius: 4px; cursor: pointer; transition: all .2s; }
.research-btn:hover { background: #58A6FF; color: #fff; }
.card-compliance { font-size: 10px; color: var(--text-tertiary); padding-top: var(--space-1); border-top: 1px solid var(--border); }
.card-detail { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: var(--space-2); }
.detail-item { display: flex; flex-direction: column; gap: 2px; }
.detail-label { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
.detail-text { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.empty { text-align: center; padding: 60px 0; color: var(--text-tertiary); font-size: 14px; }

/* 研究弹窗 */
.research-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.research-modal { background: #161B22; border: 1px solid #30363D; border-radius: 12px; width: 520px; max-height: 80vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid #30363D; }
.modal-title { font-size: 15px; font-weight: 700; color: #F0F6FC; }
.modal-close { background: transparent; border: none; color: #8B949E; font-size: 18px; cursor: pointer; }
.modal-body { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.r-section { display: flex; flex-direction: column; gap: 8px; }
.r-title { font-size: 12px; font-weight: 600; color: #8B949E; }
.r-quote { display: flex; gap: 16px; font-size: 13px; color: #C9D1D9; }
.r-quote b { font-size: 18px; color: #F0F6FC; }
.r-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.r-item { display: flex; flex-direction: column; gap: 2px; background: #0D1117; padding: 8px 10px; border-radius: 6px; }
.r-lbl { font-size: 10px; color: #484F58; }
.r-val { font-size: 14px; font-weight: 700; color: #C9D1D9; }
.r-val.up { color: var(--up); } .r-val.dn { color: var(--down); }
</style>
