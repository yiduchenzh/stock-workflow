<template>
  <div class="backtest-view">
    <h2 class="page-title">📈 回测分析</h2>
    <div class="table-wrapper">
      <table class="backtest-table">
        <thead>
          <tr>
            <th>策略名</th>
            <th>年化收益</th>
            <th>胜率</th>
            <th>盈亏比</th>
            <th>最大回撤</th>
            <th>夏普</th>
            <th>交易次数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data" :key="row.name">
            <td>{{ row.name }}</td>
            <td :class="row.annualReturn >= 0 ? 'up' : 'down'">{{ row.annualReturn }}%</td>
            <td>{{ row.winRate }}%</td>
            <td>{{ row.profitLossRatio }}</td>
            <td class="down">{{ row.maxDrawdown }}%</td>
            <td>{{ row.sharpe }}</td>
            <td>{{ row.trades }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
const data = [
  { name: '动量突破',   annualReturn: 32.5, winRate: 58.2, profitLossRatio: 2.1, maxDrawdown: 12.3, sharpe: 1.85, trades: 186 },
  { name: '均值回归',   annualReturn: 18.7, winRate: 62.8, profitLossRatio: 1.6, maxDrawdown: 8.9,  sharpe: 1.42, trades: 243 },
  { name: '缠论一买',   annualReturn: 45.2, winRate: 55.4, profitLossRatio: 2.8, maxDrawdown: 18.6, sharpe: 2.10, trades: 97 },
  { name: '裸K PinBar',  annualReturn: 22.1, winRate: 60.1, profitLossRatio: 1.9, maxDrawdown: 10.2, sharpe: 1.63, trades: 154 },
  { name: '多周期共振', annualReturn: 38.9, winRate: 65.3, profitLossRatio: 2.4, maxDrawdown: 14.1, sharpe: 2.25, trades: 112 },
  { name: '资金流向',   annualReturn: 15.3, winRate: 57.6, profitLossRatio: 1.5, maxDrawdown: 7.5,  sharpe: 1.18, trades: 201 },
  { name: '事件驱动',   annualReturn: 28.6, winRate: 51.2, profitLossRatio: 2.2, maxDrawdown: 16.8, sharpe: 1.55, trades: 138 },
  { name: 'CANSLIM',    annualReturn: 41.3, winRate: 59.7, profitLossRatio: 2.6, maxDrawdown: 15.4, sharpe: 2.02, trades: 76 },
  { name: '北向资金',   annualReturn: 20.8, winRate: 54.3, profitLossRatio: 1.8, maxDrawdown: 11.0, sharpe: 1.37, trades: 168 },
  { name: '趋势跟踪',   annualReturn: 35.4, winRate: 52.9, profitLossRatio: 3.1, maxDrawdown: 20.5, sharpe: 1.92, trades: 63 },
]
</script>

<style scoped>
.backtest-view { padding: 24px; color: var(--text-primary); }
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 24px; }
.table-wrapper { overflow-x: auto; }
.backtest-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.backtest-table th { background: var(--bg-tertiary); color: var(--text-secondary); padding: 12px 16px; text-align: left; font-weight: 500; border-bottom: 1px solid var(--border); white-space: nowrap; }
.backtest-table td { padding: 12px 16px; border-bottom: 1px solid var(--border); }
.backtest-table tbody tr:hover { background: var(--bg-tertiary); }
.up { color: var(--up); font-weight: 500; }
.down { color: var(--down); font-weight: 500; }
</style>
