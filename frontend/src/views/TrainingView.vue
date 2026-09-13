<template>
  <div class="training-view">
    <h2 class="page-title">🎮 盘感训练</h2>
    <div class="modes-grid">
      <div v-for="m in modes" :key="m.title" class="mode-card">
        <span class="mode-icon">{{ m.icon }}</span>
        <h3 class="mode-title">{{ m.title }}</h3>
        <p class="mode-desc">{{ m.desc }}</p>
        <button class="train-btn" @click="onStart">开始训练</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const modes = [
  { icon: '👁️', title: '盲K训练',   desc: '隐藏K线信息，仅凭裸K形态识别当前走势，训练你的盘感直觉。' },
  { icon: '📉', title: '识图挑战',   desc: '快速判断图表后续走势方向，提升对涨跌信号的敏感度。' },
  { icon: '🔍', title: '缠论判别',   desc: '识别缠论中的一买、二买、三买及对应卖点，巩固缠论实战能力。' },
]

function onStart() {
  alert('训练功能开发中，敬请期待！')
}
</script>

<style scoped>
.training-view { padding: 24px; color: var(--text-primary); }
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 24px; }
.modes-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.mode-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 28px 20px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 12px; transition: border-color 0.2s; }
.mode-card:hover { border-color: var(--accent); }
.mode-icon { font-size: 40px; }
.mode-title { font-size: 17px; font-weight: 600; margin: 0; }
.mode-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin: 0; }
.train-btn { margin-top: 8px; background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 10px 28px; font-size: 14px; font-weight: 500; cursor: pointer; transition: opacity 0.2s; }
.train-btn:hover { opacity: 0.85; }
.train-btn:active { opacity: 0.7; }
</style>
