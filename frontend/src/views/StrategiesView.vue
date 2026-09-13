<template>
  <div class="strategies-view">
    <!-- 顶栏 -->
    <div class="editor-header">
      <h2 class="page-title">⚙️ 策略工坊 <span class="subtitle">Node Editor</span></h2>
      <div class="header-actions">
        <button class="tb-btn" @click="saveConfig">💾 保存策略</button>
        <button class="tb-btn" @click="loadConfig">📂 加载</button>
        <button class="tb-btn tb-reset" @click="resetCanvas">🔄 重置</button>
      </div>
    </div>

    <div class="editor-body">
      <!-- 左侧: 节点工具箱 -->
      <div class="node-toolbox">
        <div class="toolbox-title">🧩 节点</div>
        <div v-for="group in nodeGroups" :key="group.name" class="toolbox-group">
          <div class="group-label">{{ group.name }}</div>
          <button v-for="n in group.nodes" :key="n.type"
            class="toolbox-node" @click="addNode(n)">
            <span class="node-icon">{{ n.icon }}</span>
            <span class="node-label">{{ n.label }}</span>
          </button>
        </div>
      </div>

      <!-- 中间: 策略画布 -->
      <div class="strategy-canvas">
        <div v-if="nodes.length === 0" class="canvas-empty">
          <div class="empty-icon">🎯</div>
          <div>从左侧添加策略节点</div>
          <div class="empty-hint">条件 → 操作 → 风控</div>
        </div>
        <div v-else class="canvas-nodes">
          <div v-for="(node, i) in nodes" :key="node.id" class="node-wrapper">
            <!-- 连接线 -->
            <div v-if="i > 0" class="connector-line">
              <div class="connector-dot"></div>
              <div class="connector-arrow">▼</div>
            </div>
            <!-- 节点卡片 -->
            <div :class="['strategy-node', 'node-' + node.category]">
              <div class="node-header">
                <span class="node-title">{{ node.icon }} {{ node.label }}</span>
                <div class="node-actions">
                  <button class="node-up" @click="moveNode(i, -1)" :disabled="i===0">↑</button>
                  <button class="node-down" @click="moveNode(i, 1)" :disabled="i===nodes.length-1">↓</button>
                  <button class="node-del" @click="removeNode(i)">✕</button>
                </div>
              </div>
              <div class="node-body">
                <!-- 条件节点参数 -->
                <div v-if="node.type === 'price_ma'" class="node-params">
                  <label>周期 <input v-model.number="node.params.period" type="number" min="5" max="120" class="np-input" /></label>
                  <label>比较 <select v-model="node.params.operator" class="np-select">
                    <option value="above">价格 > MA</option><option value="below">价格 < MA</option>
                  </select></label>
                </div>
                <div v-if="node.type === 'rsi'" class="node-params">
                  <label>周期 <input v-model.number="node.params.period" type="number" min="6" max="30" class="np-input" /></label>
                  <label>阈值 <input v-model.number="node.params.threshold" type="number" min="0" max="100" class="np-input" /></label>
                  <label>方向 <select v-model="node.params.direction" class="np-select">
                    <option value="below">RSI < 阈值</option><option value="above">RSI > 阈值</option>
                  </select></label>
                </div>
                <div v-if="node.type === 'volume'" class="node-params">
                  <label>倍率 <input v-model.number="node.params.multiplier" type="number" min="1" max="10" step="0.1" class="np-input" /></label>
                </div>
                <!-- 操作节点参数 -->
                <div v-if="node.type === 'buy'" class="node-params">
                  <label>仓位% <input v-model.number="node.params.percent" type="number" min="1" max="100" class="np-input" /></label>
                </div>
                <div v-if="node.type === 'sell'" class="node-params">
                  <label>方式 <select v-model="node.params.method" class="np-select">
                    <option value="all">全部卖出</option><option value="percent">卖出百分比</option>
                  </select></label>
                  <label v-if="node.params.method==='percent'">比例% <input v-model.number="node.params.percent" type="number" min="1" max="100" class="np-input" /></label>
                </div>
                <div v-if="node.type === 'stop_loss'" class="node-params">
                  <label>止损% <input v-model.number="node.params.percent" type="number" min="1" max="20" step="0.5" class="np-input" /></label>
                </div>
                <div v-if="node.type === 'position'||node.type==='and'||node.type==='or'" class="node-params">
                  <div class="node-desc">{{ node.desc }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧: 策略预览/配置摘要 -->
      <div class="config-panel">
        <div class="cp-title">📋 策略摘要</div>
        <div class="cp-body">
          <div class="cp-section">
            <div class="cp-label">策略名称</div>
            <input v-model="strategyName" class="cp-input" placeholder="输入策略名称" />
          </div>
          <div class="cp-section">
            <div class="cp-label">节点数</div>
            <div class="cp-value">{{ nodes.length }}</div>
          </div>
          <div class="cp-section" v-if="nodes.length">
            <div class="cp-label">执行流程</div>
            <div class="cp-flow">
              <div v-for="(n,i) in nodes" :key="n.id" class="cp-step">
                <span class="step-idx">{{ i+1 }}</span>
                <span class="step-label">{{ n.icon }} {{ n.label }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const strategyName = ref('新策略')
const nodes = ref([])
let nodeCounter = 0

const nodeGroups = [
  { name: '条件', nodes: [
    { type:'price_ma', icon:'📏', label:'价格均线', category:'condition', desc:'价格与均线比较', params:{period:20,operator:'above'} },
    { type:'rsi', icon:'📊', label:'RSI指标', category:'condition', desc:'RSI超买超卖', params:{period:14,threshold:30,direction:'below'} },
    { type:'volume', icon:'📈', label:'成交量', category:'condition', desc:'成交量放大倍数', params:{multiplier:1.5} },
  ]},
  { name: '操作', nodes: [
    { type:'buy', icon:'🟢', label:'买入', category:'action', desc:'执行买入操作', params:{percent:20} },
    { type:'sell', icon:'🔴', label:'卖出', category:'action', desc:'执行卖出操作', params:{method:'all',percent:50} },
    { type:'stop_loss', icon:'🛑', label:'止损', category:'action', desc:'设置止损比例', params:{percent:5} },
    { type:'position', icon:'📐', label:'仓位管理', category:'action', desc:'调整目标仓位', params:{}} ,
  ]},
  { name: '逻辑', nodes: [
    { type:'and', icon:'🔗', label:'AND(与)', category:'logic', desc:'所有条件同时满足', params:{} },
    { type:'or', icon:'🔀', label:'OR(或)', category:'logic', desc:'任一条件满足', params:{} },
  ]},
]

function addNode(template) {
  nodes.value.push({
    id: 'node_' + (++nodeCounter),
    type: template.type,
    icon: template.icon,
    label: template.label,
    category: template.category,
    desc: template.desc,
    params: JSON.parse(JSON.stringify(template.params)),
  })
}

function removeNode(i) { nodes.value.splice(i, 1) }
function moveNode(i, dir) {
  const j = i + dir
  if (j < 0 || j >= nodes.value.length) return
  const tmp = nodes.value[i]
  nodes.value[i] = nodes.value[j]
  nodes.value[j] = tmp
}

function saveConfig() {
  const config = { name: strategyName.value, nodes: nodes.value.map(n => ({ type: n.type, label: n.label, params: n.params })) }
  localStorage.setItem('aurora_strategy', JSON.stringify(config))
  alert('策略已保存到本地')
}

function loadConfig() {
  try {
    const raw = localStorage.getItem('aurora_strategy')
    if (!raw) { alert('没有保存的策略'); return }
    const config = JSON.parse(raw)
    strategyName.value = config.name || '载入策略'
    nodes.value = config.nodes.map((n, i) => {
      const tpl = nodeGroups.flatMap(g => g.nodes).find(t => t.type === n.type)
      return { id: 'node_' + (++nodeCounter), type: n.type, icon: tpl?.icon || '📦', label: n.label, category: tpl?.category || 'condition', desc: tpl?.desc || '', params: n.params || {} }
    })
    alert('策略已载入')
  } catch { alert('载入失败') }
}

function resetCanvas() {
  if (nodes.value.length && !confirm('确认重置？')) return
  nodes.value = []
  nodeCounter = 0
  strategyName.value = '新策略'
}
</script>

<style scoped>
.strategies-view { display: flex; flex-direction: column; gap: var(--space-3); flex: 1; min-height: 0; }
.editor-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0; }
.subtitle { font-size: 11px; color: var(--text-tertiary); font-weight: 400; margin-left: var(--space-2); }
.header-actions { display: flex; gap: var(--space-2); }
.tb-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-primary); font-size: 12px; cursor: pointer; transition: all .15s; }
.tb-btn:hover { background: var(--bg-tertiary); }
.tb-reset { color: var(--down); border-color: rgba(38,166,154,.3); }
.editor-body { display: flex; gap: var(--space-3); flex: 1; min-height: 0; }

/* 左侧工具箱 */
.node-toolbox { width: 160px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-3); overflow-y: auto; }
.toolbox-title { font-size: 12px; font-weight: 700; color: var(--text-primary); margin-bottom: var(--space-3); }
.toolbox-group { margin-bottom: var(--space-3); }
.group-label { font-size: 10px; color: var(--text-tertiary); font-weight: 600; margin-bottom: var(--space-1); text-transform: uppercase; }
.toolbox-node { display: flex; align-items: center; gap: var(--space-2); width: 100%; padding: 6px 8px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: all .15s; margin-bottom: 2px; text-align: left; }
.toolbox-node:hover { background: var(--bg-tertiary); border-color: var(--border); color: var(--text-primary); }
.node-icon { font-size: 14px; }

/* 中间画布 */
.strategy-canvas { flex: 1; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-4); overflow-y: auto; display: flex; }
.canvas-empty { margin: auto; text-align: center; color: var(--text-tertiary); }
.empty-icon { font-size: 40px; margin-bottom: var(--space-2); }
.empty-hint { font-size: 11px; margin-top: var(--space-1); color: var(--text-tertiary); }
.canvas-nodes { display: flex; flex-direction: column; align-items: center; width: 100%; }
.node-wrapper { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 400px; }
.connector-line { display: flex; flex-direction: column; align-items: center; color: var(--text-tertiary); padding: 4px 0; }
.connector-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-tertiary); }
.connector-arrow { font-size: 8px; line-height: 1; }

/* 节点卡片 */
.strategy-node { width: 100%; border-radius: var(--radius-lg); border: 1px solid var(--border); overflow: hidden; background: var(--bg-primary); }
.node-condition { border-left: 3px solid #58A6FF; }
.node-action { border-left: 3px solid #3FB950; }
.node-logic { border-left: 3px solid #F0C040; }
.node-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: var(--bg-tertiary); }
.node-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.node-actions { display: flex; gap: 2px; }
.node-actions button { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); font-size: 10px; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.node-actions button:hover:not(:disabled) { background: var(--bg-secondary); }
.node-actions button:disabled { opacity: .3; cursor: not-allowed; }
.node-del { color: var(--down) !important; }
.node-body { padding: 10px 12px; }
.node-params { display: flex; flex-direction: column; gap: 6px; }
.node-params label { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); }
.np-input { width: 60px; padding: 3px 6px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: 12px; text-align: right; }
.np-select { padding: 3px 6px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: 11px; }
.node-desc { font-size: 11px; color: var(--text-secondary); font-style: italic; }

/* 右侧配置面板 */
.config-panel { width: 200px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-3); overflow-y: auto; }
.cp-title { font-size: 12px; font-weight: 700; color: var(--text-primary); margin-bottom: var(--space-3); }
.cp-body { display: flex; flex-direction: column; gap: var(--space-3); }
.cp-section { display: flex; flex-direction: column; gap: 4px; }
.cp-label { font-size: 10px; color: var(--text-tertiary); font-weight: 600; }
.cp-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.cp-input { padding: 6px 8px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: 12px; }
.cp-flow { display: flex; flex-direction: column; gap: 4px; }
.cp-step { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); }
.step-idx { width: 18px; height: 18px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 9px; font-weight: 700; color: var(--text-secondary); flex-shrink: 0; }
.step-label { font-size: 11px; }
</style>
