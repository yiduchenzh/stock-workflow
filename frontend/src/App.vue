<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <div class="app">
        <div class="app-body">
          <!-- 左侧Dock导航 -->
          <SideNav :activeRoute="$route.path" @navigate="navigate" />

          <!-- 中间主内容区 -->
          <div class="app-center">
            <!-- 顶栏 -->
            <TopBar />
            <!-- 路由内容 -->
            <div class="main-content">
              <router-view />
            </div>
          </div>

          <!-- 右侧AI面板 -->
          <AIPanel ref="aiPanel" />
        </div>
        <!-- 底部行情滚动条 -->
        <StatusBar />
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { darkTheme, zhCN, dateZhCN } from 'naive-ui'
import TopBar from './components/layout/TopBar.vue'
import SideNav from './components/layout/SideNav.vue'
import AIPanel from './components/layout/AIPanel.vue'
import StatusBar from './components/layout/StatusBar.vue'
import { useSSEStore } from './stores/sse'

const router = useRouter()
const sse = useSSEStore()
const aiPanel = ref(null)

function navigate(route) {
  router.push(route)
}

onMounted(() => {
  sse.connect()
})

onUnmounted(() => {
  sse.disconnect()
})
</script>

<style>
@import './styles/variables.css';

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }

.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-deepest);
  overflow: hidden;
}
.app-body {
  display: flex;
  flex: 1;
  min-height: 0;
  height: calc(100vh - 32px);
}
.app-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.main-content {
  flex: 1;
  display: flex;
  padding: var(--space-3);
  overflow: auto;
  min-height: 0;
}
</style>
