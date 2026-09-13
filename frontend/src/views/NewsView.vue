<template>
  <div class="news-view">
    <div class="page-header">📰 市场资讯</div>
    <div v-if="loading" class="loading-text">加载中...</div>
    <div v-else-if="!items.length" class="empty-text">暂无资讯</div>
    <div v-else class="news-list">
      <div v-for="(item, idx) in items" :key="idx" class="news-card">
        <div class="news-type">{{ item.type === 'alert' ? '⚠️ 提醒' : '📋 计划' }}</div>
        <div class="news-time">{{ item.time || '' }}</div>
        <div class="news-content">{{ item.content || item.message || '' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const items = ref([])
const loading = ref(true)

async function fetchNews() {
  loading.value = true
  try {
    const res = await fetch('http://127.0.0.1:7878/api/engine_state')
    if (!res.ok) {
      items.value = []
      return
    }
    const data = await res.json()
    const result = []
    const alerts = data.alerts || data.result?.alerts || []
    const plans = data.plans || data.result?.plans || []
    for (const a of alerts) {
      result.push({ type: 'alert', time: a.time || '', content: a.content || a.message || JSON.stringify(a) })
    }
    for (const p of plans) {
      result.push({ type: 'plan', time: p.time || '', content: p.content || p.message || JSON.stringify(p) })
    }
    items.value = result
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchNews)
</script>

<style scoped>
.news-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 16px);
  padding: var(--space-4, 16px);
  min-height: 0;
}

.page-header {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #F0F6FC);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border, #30363D);
}

.loading-text {
  color: var(--text-secondary, #8B949E);
  font-size: 14px;
  text-align: center;
  padding: 40px 0;
}

.empty-text {
  color: var(--text-secondary, #8B949E);
  font-size: 14px;
  text-align: center;
  padding: 60px 0;
}

.news-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.news-card {
  background: var(--bg-secondary, #161B22);
  border: 1px solid var(--border, #30363D);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.2s;
}

.news-card:hover {
  border-color: var(--accent, #58A6FF);
}

.news-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent, #58A6FF);
}

.news-time {
  font-size: 11px;
  color: var(--text-secondary, #8B949E);
}

.news-content {
  font-size: 14px;
  color: var(--text-primary, #F0F6FC);
  line-height: 1.5;
}
</style>
