<template>
  <div class="today-plan">
    <!-- 标题 -->
    <div class="today-plan__header">
      <span class="today-plan__title">今日计划</span>
      <span
        v-if="plan.market_score != null"
        class="today-plan__score"
        :class="scoreClass(plan.market_score)"
      >
        {{ plan.market_score }}分
      </span>
    </div>

    <!-- 市场判断 -->
    <div v-if="plan.market_regime" class="today-plan__regime">
      {{ plan.market_regime }}
    </div>

    <!-- 建议 -->
    <div v-if="plan.plans && plan.plans.length" class="today-plan__section">
      <div class="today-plan__section-title">📋 操作建议</div>
      <ul class="today-plan__list">
        <li v-for="(item, i) in plan.plans" :key="i">{{ item }}</li>
      </ul>
    </div>

    <!-- 候选标的 -->
    <div v-if="plan.candidates && plan.candidates.length" class="today-plan__section">
      <div class="today-plan__section-title">🎯 候选标的</div>
      <ul class="today-plan__list">
        <li v-for="(item, i) in plan.candidates" :key="i">{{ item }}</li>
      </ul>
    </div>

    <!-- 今日提醒 -->
    <div v-if="plan.alerts && plan.alerts.length" class="today-plan__section">
      <div class="today-plan__section-title">⚠️ 今日提醒</div>
      <ul class="today-plan__list today-plan__list--alerts">
        <li v-for="(alert, i) in plan.alerts" :key="i">{{ alert }}</li>
      </ul>
    </div>

    <!-- 无计划 -->
    <div v-if="plan.hasPlan === false" class="today-plan__empty">
      今日暂无操作计划
    </div>
  </div>
</template>

<script setup>
defineProps({
  plan: {
    type: Object,
    default: () => ({
      market_score: null,
      market_regime: '',
      plans: [],
      candidates: [],
      alerts: [],
      hasPlan: true
    })
  }
})

function scoreClass(score) {
  const n = parseInt(score, 10)
  if (isNaN(n)) return ''
  if (n >= 70) return 'score-green'
  if (n >= 40) return 'score-yellow'
  return 'score-red'
}
</script>

<style scoped>
.today-plan {
  background: #161B22;
  border: 1px solid #30363D;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.today-plan__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.today-plan__title {
  font-size: 15px;
  font-weight: 700;
  color: #E6EDF3;
}

.today-plan__score {
  font-size: 14px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 4px;
}

.today-plan__score.score-green {
  color: #26A69A;
  background: rgba(38, 166, 154, 0.15);
}

.today-plan__score.score-yellow {
  color: #F0C040;
  background: rgba(240, 192, 64, 0.15);
}

.today-plan__score.score-red {
  color: #EF5350;
  background: rgba(239, 83, 80, 0.15);
}

.today-plan__regime {
  font-size: 13px;
  color: #8B949E;
  padding: 6px 10px;
  background: #0D1117;
  border-radius: 4px;
}

.today-plan__section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.today-plan__section-title {
  font-size: 13px;
  font-weight: 600;
  color: #C9D1D9;
}

.today-plan__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.today-plan__list li {
  font-size: 13px;
  color: #C9D1D9;
  padding: 4px 8px;
  background: #0D1117;
  border-radius: 4px;
}

.today-plan__list--alerts li {
  color: #F0C040;
  background: rgba(240, 192, 64, 0.08);
}

.today-plan__empty {
  font-size: 13px;
  color: #8B949E;
  text-align: center;
  padding: 20px 0;
}
</style>
