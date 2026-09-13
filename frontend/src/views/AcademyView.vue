<template>
  <div class="academy-view">
    <h2 class="page-title">📚 AI学院</h2>
    <div class="categories-grid">
      <div v-for="cat in categories" :key="cat.name" class="category-card">
        <span class="cat-icon">{{ cat.icon }}</span>
        <span class="cat-name">{{ cat.name }}</span>
        <span class="cat-count">{{ cat.count }} 篇文章</span>
      </div>
    </div>
    <h3 class="section-title">🔥 热门问答</h3>
    <ul class="qa-list">
      <li v-for="(item, i) in qaList" :key="i" class="qa-item">
        <span class="qa-q">Q{{ i + 1 }}.</span>
        <span class="qa-text">{{ item }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
const categories = [
  { icon: '📊', name: 'K线基础',   count: 12 },
  { icon: '🌀', name: '缠论入门',   count: 8 },
  { icon: '📌', name: '裸K形态',    count: 10 },
  { icon: '🔁', name: '多周期共振', count: 6 },
  { icon: '💧', name: '资金流分析', count: 7 },
  { icon: '🛡️', name: '风险管理',   count: 9 },
]

const qaList = [
  '什么是缠论中的笔和段？如何正确划分？',
  'K线形态中的启明星和黄昏星如何识别？',
  '多周期共振的判断标准是什么？',
  '如何区分主力资金流入和流出的真伪？',
  '止损位设置有哪些常用方法？',
]
</script>

<style scoped>
.academy-view { padding: 24px; color: var(--text-primary); }
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 24px; }
.categories-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 32px; }
.category-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 10px; padding: 20px; display: flex; flex-direction: column; align-items: center; gap: 8px; cursor: pointer; transition: border-color 0.2s; }
.category-card:hover { border-color: var(--accent); }
.cat-icon { font-size: 32px; }
.cat-name { font-size: 15px; font-weight: 600; }
.cat-count { font-size: 12px; color: var(--text-secondary); }
.section-title { font-size: 17px; font-weight: 600; margin-bottom: 16px; }
.qa-list { list-style: none; padding: 0; margin: 0; }
.qa-item { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.qa-q { color: var(--accent); font-weight: 600; font-size: 13px; flex-shrink: 0; }
.qa-text { font-size: 13px; color: var(--text-primary); }
</style>
