<template>
  <div class="portfolio-view">
    <!-- 统计卡片行 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">总资产</div>
        <div class="stat-value">{{ formatMoney(stats.total_assets) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">可用资金</div>
        <div class="stat-value">{{ formatMoney(stats.cash) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">持仓市值</div>
        <div class="stat-value up">{{ formatMoney(stats.market_value) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">总盈亏</div>
        <div :class="['stat-value', stats.total_pnl >= 0 ? 'up' : 'dn']">{{ formatMoney(stats.total_pnl) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">日盈亏</div>
        <div :class="['stat-value', stats.daily_pnl >= 0 ? 'up' : 'dn']">{{ stats.daily_pnl >= 0 ? '+' : '' }}{{ stats.daily_pnl.toFixed(2) }}%</div>
      </div>
    </div>

    <!-- 风险指标行 -->
    <div class="section-card">
      <div class="section-header">📊 风险指标 <span class="subtitle">VaR · Sharpe · 最大回撤</span></div>
      <div class="risk-grid">
        <div class="risk-item"><span class="risk-label">VaR (95%)</span><span class="risk-value">{{ risk.var95 }}%</span></div>
        <div class="risk-item"><span class="risk-label">VaR (99%)</span><span class="risk-value">{{ risk.var99 }}%</span></div>
        <div class="risk-item"><span class="risk-label">夏普比率</span><span :class="['risk-value', risk.sharpe >= 1 ? 'up' : 'dn']">{{ risk.sharpe.toFixed(2) }}</span></div>
        <div class="risk-item"><span class="risk-label">最大回撤</span><span class="risk-value dn">-{{ risk.max_drawdown }}%</span></div>
        <div class="risk-item"><span class="risk-label">Beta</span><span class="risk-value">{{ risk.beta.toFixed(2) }}</span></div>
        <div class="risk-item"><span class="risk-label">仓位比例</span><span class="risk-value">{{ risk.position_ratio }}%</span></div>
      </div>
    </div>

    <!-- 持仓表格 -->
    <div class="section-card">
      <div class="section-header">📋 持仓明细</div>
      <table class="position-table">
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th>持仓(股)</th><th>均价</th><th>现价</th><th>市值</th><th>盈亏</th><th>盈亏率</th><th>占比</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in positions" :key="p.code">
            <td class="mono">{{ p.code }}</td>
            <td>{{ p.name }}</td>
            <td class="mono">{{ p.shares }}</td>
            <td class="mono">{{ p.avg_cost.toFixed(2) }}</td>
            <td class="mono">{{ p.price.toFixed(2) }}</td>
            <td class="mono">{{ formatMoney(p.market_value) }}</td>
            <td :class="['mono', p.pnl >= 0 ? 'up' : 'dn']">{{ p.pnl >= 0 ? '+' : '' }}{{ formatMoney(p.pnl) }}</td>
            <td :class="['mono', p.pnl_pct >= 0 ? 'up' : 'dn']">{{ p.pnl_pct >= 0 ? '+' : '' }}{{ p.pnl_pct.toFixed(2) }}%</td>
            <td class="mono">{{ p.ratio.toFixed(1) }}%</td>
          </tr>
          <tr v-if="!positions.length"><td colspan="9" class="empty-cell">暂无持仓</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 交易记录 -->
    <div class="section-card">
      <div class="section-header">📜 交易记录</div>
      <table class="trade-table">
        <thead><tr><th>时间</th><th>方向</th><th>代码</th><th>名称</th><th>价格</th><th>数量</th><th>金额</th></tr></thead>
        <tbody>
          <tr v-for="t in trades" :key="t.time">
            <td class="mono small">{{ t.time }}</td>
            <td><span :class="['tag', t.action === 'buy' ? 'tag-buy' : 'tag-sell']">{{ t.action === 'buy' ? '买入' : '卖出' }}</span></td>
            <td class="mono">{{ t.code }}</td><td>{{ t.name }}</td>
            <td class="mono">{{ t.price.toFixed(2) }}</td>
            <td class="mono">{{ t.shares }}</td>
            <td class="mono">{{ formatMoney(t.amount) }}</td>
          </tr>
          <tr v-if="!trades.length"><td colspan="7" class="empty-cell">暂无交易记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { usePortfolioStore } from '../stores/portfolio'

const store = usePortfolioStore()
const positions = ref([])
const trades = ref([])
const stats = ref({ total_assets: 1000000, cash: 989972, market_value: 0, total_pnl: 0, daily_pnl: 0 })
const risk = ref({ var95: 2.3, var99: 5.1, sharpe: 0.85, max_drawdown: 8.5, beta: 0.92, position_ratio: 0 })

function formatMoney(val) {
  if (val >= 100000000) return (val / 100000000).toFixed(2) + '亿'
  if (val >= 10000) return (val / 10000).toFixed(2) + '万'
  return val.toFixed(2)
}

async function fetchAll() {
  try {
    const [ovR, simR, tradesR] = await Promise.all([
      fetch('/api/market/overview'),
      fetch('/api/positions'),
      fetch('/api/trades'),
    ])
    const ov = await ovR.json()
    if (ov.positions && ov.positions.length) {
      positions.value = ov.positions.map(p => ({
        code: p.code || p.stock_code || '',
        name: p.name || '',
        shares: p.shares || 0,
        avg_cost: p.avg_cost || p.cost_price || 0,
        price: p.price || p.current_price || 0,
        market_value: (p.shares || 0) * (p.price || p.current_price || 0),
        pnl: ((p.price || 0) - (p.avg_cost || 0)) * (p.shares || 0),
        pnl_pct: ((p.price || 0) - (p.avg_cost || 0)) / (p.avg_cost || 1) * 100,
        ratio: ((p.shares || 0) * (p.price || 0)) / (stats.value.total_assets || 1) * 100,
      }))
    }
  } catch (e) {
    console.warn('[Portfolio] fetch error:', e)
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.portfolio-view { display: flex; flex-direction: column; gap: var(--space-4); flex: 1; }
.stats-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: var(--space-3); }
.stat-card {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: var(--space-3);
}
.stat-label { font-size: var(--fs-small); color: var(--text-secondary); }
.stat-value { font-size: 18px; font-weight: 700; margin-top: var(--space-1); }
.section-card {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: var(--radius-lg); overflow: hidden;
}
.section-header {
  padding: var(--space-2) var(--space-3);
  font-size: var(--fs-small); color: var(--text-secondary);
  border-bottom: 1px solid var(--border); font-weight: 600;
}
.subtitle { font-weight: 400; font-size: 10px; color: var(--text-tertiary); margin-left: var(--space-2); }
.risk-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: var(--space-3); padding: var(--space-3); }
.risk-item { display: flex; flex-direction: column; gap: 4px; }
.risk-label { font-size: var(--fs-small); color: var(--text-secondary); }
.risk-value { font-size: 16px; font-weight: 700; }
.up { color: var(--up); }
.dn { color: var(--down); }
.position-table, .trade-table { width: 100%; border-collapse: collapse; }
.position-table th, .trade-table th {
  padding: var(--space-2) var(--space-3); text-align: left;
  font-size: var(--fs-small); color: var(--text-secondary);
  border-bottom: 1px solid var(--border); font-weight: 600;
}
.position-table td, .trade-table td {
  padding: var(--space-2) var(--space-3); font-size: 13px; color: var(--text-primary);
  border-bottom: 1px solid var(--border);
}
.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }
.small { font-size: 11px; color: var(--text-tertiary); }
.empty-cell { text-align: center; padding: 32px !important; color: var(--text-tertiary); }
.tag {
  display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 11px; font-weight: 600;
}
.tag-buy { color: var(--up); background: rgba(239, 83, 80, 0.12); }
.tag-sell { color: var(--down); background: rgba(38, 166, 154, 0.12); }
</style>
