<template>
  <nav class="navtabs">
    <router-link
      v-for="tab in tabs"
      :key="tab.path"
      :to="tab.path"
      class="nav-item"
      :class="{ active: $route.path === tab.path }"
    >
      <span class="nav-icon">{{ tab.icon }}</span>
      <span class="nav-label">{{ tab.label }}</span>
    </router-link>
  </nav>
</template>

<script setup>
const tabs = [
  { path: '/market',     label: '市场全景', icon: '📊' },
  { path: '/signals',    label: '量化信号', icon: '📡' },
  { path: '/portfolio',  label: '组合透视', icon: '💼' },
  { path: '/strategies', label: '策略工坊', icon: '⚙️' },
  { path: '/backtest',   label: '回测分析', icon: '📈' },
  { path: '/academy',    label: 'AI学院',   icon: '📚' },
  { path: '/training',   label: '盘感训练', icon: '🎮' },
]
</script>

<style scoped>
.navtabs {
  display: flex;
  gap: 2px;
  padding: var(--space-2) var(--space-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  overflow-x: auto;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  font-size: var(--fs-small);
  color: var(--text-secondary);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition: all 0.2s;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
}
.nav-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}
.nav-item.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
  background: rgba(88, 166, 255, 0.08);
}
.nav-icon { font-size: 14px; }
.nav-label { font-size: var(--fs-small); }
</style>
