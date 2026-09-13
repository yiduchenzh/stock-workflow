<template>
  <header class="topbar">
    <div class="topbar-brand">
      <span class="logo">Aurora</span>
      <span class="logo-sub">AI 量化投资</span>
    </div>
    <div class="topbar-right">
      <span class="status-dot" :class="sse.connected ? 'online' : 'offline'" />
      <span class="status-text">{{ sse.connected ? '已连接' : '连接中...' }}</span>
    </div>
  </header>
</template>

<script setup>
import { useSSEStore } from '../../stores/sse'
const sse = useSSEStore()
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  height: 48px;
  flex-shrink: 0;
}
.logo {
  font-size: var(--fs-large);
  font-weight: 700;
  background: var(--brand-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.logo-sub {
  font-size: var(--fs-small);
  color: var(--text-secondary);
  margin-left: var(--space-2);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
}
.status-dot.online { background: var(--score-high); }
.status-dot.offline { background: var(--score-low); }
.status-text { font-size: var(--fs-small); color: var(--text-secondary); }
</style>
