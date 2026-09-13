<template>
  <div class="settings-view">
    <div class="page-header">⚙️ 系统设置</div>

    <div class="settings-grid">
      <!-- 数据源状态 -->
      <div class="setting-card">
        <div class="card-title">📡 数据源状态</div>
        <div class="card-body">
          <div class="status-row">
            <span class="label">WZ</span>
            <span :class="['badge', health.wz ? 'badge-ok' : 'badge-err']">
              {{ health.wz ? '正常' : '异常' }}
            </span>
          </div>
          <div class="status-row">
            <span class="label">Tencent</span>
            <span :class="['badge', health.tencent ? 'badge-ok' : 'badge-err']">
              {{ health.tencent ? '正常' : '异常' }}
            </span>
          </div>
          <div class="status-row">
            <span class="label">Sina</span>
            <span :class="['badge', health.sina ? 'badge-ok' : 'badge-err']">
              {{ health.sina ? '正常' : '异常' }}
            </span>
          </div>
        </div>
      </div>

      <!-- 引擎运行状态 -->
      <div class="setting-card">
        <div class="card-title">🚀 引擎运行状态</div>
        <div class="card-body">
          <div class="status-row">
            <span class="label">服务状态</span>
            <span :class="['badge', engineOnline ? 'badge-ok' : 'badge-err']">
              {{ engineOnline ? '运行中' : '离线' }}
            </span>
          </div>
          <div v-if="engineOnline" class="status-row">
            <span class="label">运行时间</span>
            <span class="value">{{ uptime }}</span>
          </div>
          <div v-if="engineOnline" class="status-row">
            <span class="label">版本</span>
            <span class="value">{{ version }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const health = ref({ wz: false, tencent: false, sina: false })
const engineOnline = ref(false)
const uptime = ref('—')
const version = ref('—')

async function fetchHealth() {
  try {
    const res = await fetch('http://127.0.0.1:7878/api/health')
    if (!res.ok) return
    const data = await res.json()
    engineOnline.value = true
    uptime.value = data.uptime || data.result?.uptime || '—'
    version.value = data.version || data.result?.version || '—'

    const sources = data.data_sources || data.sources || data.result?.data_sources || {}
    health.value.wz = sources.wz === true || sources.wz === 'ok' || sources.wz === '正常'
    health.value.tencent = sources.tencent === true || sources.tencent === 'ok' || sources.tencent === '正常'
    health.value.sina = sources.sina === true || sources.sina === 'ok' || sources.sina === '正常'
  } catch (e) {
    engineOnline.value = false
  }
}

onMounted(fetchHealth)
</script>

<style scoped>
.settings-view {
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

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.setting-card {
  background: var(--bg-secondary, #161B22);
  border: 1px solid var(--border, #30363D);
  border-radius: 8px;
  overflow: hidden;
}

.card-title {
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #F0F6FC);
  border-bottom: 1px solid var(--border, #30363D);
}

.card-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.label {
  font-size: 13px;
  color: var(--text-secondary, #8B949E);
}

.value {
  font-size: 13px;
  color: var(--text-primary, #F0F6FC);
  font-variant-numeric: tabular-nums;
}

.badge {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 10px;
}

.badge-ok {
  color: var(--down, #26A69A);
  background: rgba(38, 166, 154, 0.12);
}

.badge-err {
  color: var(--up, #EF5350);
  background: rgba(239, 83, 80, 0.12);
}
</style>
