import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/market' },
  {
    path: '/market',
    name: 'Market',
    component: () => import('../views/MarketView.vue'),
    meta: { title: '市场全景', icon: 'chart' }
  },
  {
    path: '/signals',
    name: 'Signals',
    component: () => import('../views/SignalsView.vue'),
    meta: { title: '量化信号', icon: 'flash' }
  },
  {
    path: '/portfolio',
    name: 'Portfolio',
    component: () => import('../views/PortfolioView.vue'),
    meta: { title: '组合透视', icon: 'wallet' }
  },
  {
    path: '/strategies',
    name: 'Strategies',
    component: () => import('../views/StrategiesView.vue'),
    meta: { title: '策略工坊', icon: 'settings' }
  },
  {
    path: '/backtest',
    name: 'Backtest',
    component: () => import('../views/BacktestView.vue'),
    meta: { title: '回测分析', icon: 'trending' }
  },
  {
    path: '/academy',
    name: 'Academy',
    component: () => import('../views/AcademyView.vue'),
    meta: { title: 'AI学院', icon: 'book' }
  },
  {
    path: '/training',
    name: 'Training',
    component: () => import('../views/TrainingView.vue'),
    meta: { title: '盘感训练', icon: 'game' }
  },
  {
    path: '/news',
    name: 'News',
    component: () => import('../views/NewsView.vue'),
    meta: { title: '市场资讯', icon: 'newspaper' }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { title: '系统设置', icon: 'cog' }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
