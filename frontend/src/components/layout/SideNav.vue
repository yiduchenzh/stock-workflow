<template>
  <nav class="side-nav">
    <div class="nav-items">
      <button
        v-for="item in navItems"
        :key="item.route"
        :class="['nav-btn', { active: activeRoute.includes(item.route) }]"
        :title="item.label"
        @click="$emit('navigate', item.route)"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-tooltip">{{ item.label }}</span>
      </button>
    </div>
    <div class="nav-footer">
      <button
        v-for="item in footerItems"
        :key="item.route"
        :class="['nav-btn', { active: activeRoute.includes(item.route) }]"
        :title="item.label"
        @click="$emit('navigate', item.route)"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-tooltip">{{ item.label }}</span>
      </button>
    </div>
  </nav>
</template>

<script setup>
defineProps({
  activeRoute: {
    type: String,
    default: ''
  }
})

defineEmits(['navigate'])

const navItems = [
  { icon: '📊', label: '市场', route: 'market' },
  { icon: '📡', label: '信号', route: 'signals' },
  { icon: '💼', label: '组合', route: 'portfolio' },
  { icon: '⚙️', label: '策略', route: 'strategies' },
  { icon: '📈', label: '回测', route: 'backtest' },
  { icon: '📚', label: '学院', route: 'academy' },
  { icon: '🎮', label: '训练', route: 'training' }
]

const footerItems = [
  { icon: '📰', label: '资讯', route: 'news' },
  { icon: '⚙️', label: '设置', route: 'settings' }
]
</script>

<style scoped>
.side-nav {
  width: 60px;
  min-height: 100%;
  background: var(--bg-primary, #0D1117);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-right: 1px solid var(--border, #30363D);
  user-select: none;
}

.nav-items {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 0;
}

.nav-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid var(--border, #30363D);
}

.nav-btn {
  position: relative;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary, #8B949E);
  font-size: 20px;
  transition: all 0.2s ease;
  margin: 2px 0;
}

.nav-btn:hover {
  background: var(--bg-secondary, #161B22);
  color: var(--text-primary, #F0F6FC);
}

.nav-btn.active {
  background: var(--bg-tertiary, #1A202C);
  color: var(--accent, #58A6FF);
  border-left: 3px solid var(--accent, #58A6FF);
  border-radius: 0 8px 8px 0;
  margin-left: -3px;
  width: 47px;
}

.nav-icon {
  line-height: 1;
}

.nav-tooltip {
  display: none;
  position: absolute;
  left: 56px;
  top: 50%;
  transform: translateY(-50%);
  background: var(--bg-tertiary, #1A202C);
  color: var(--text-primary, #F0F6FC);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  white-space: nowrap;
  z-index: 100;
  border: 1px solid var(--border, #30363D);
  pointer-events: none;
}

.nav-btn:hover .nav-tooltip {
  display: block;
}
</style>
