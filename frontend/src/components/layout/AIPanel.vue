<template>
  <aside :class="['ai-panel', { collapsed: isCollapsed }]">
    <div v-if="!isCollapsed" class="panel-content">
      <div class="panel-header">
        <h3 class="panel-title">🤖 交易员大厅</h3>
        <button class="collapse-btn" @click="toggleCollapse">▶</button>
      </div>

      <!-- 市场状态 -->
      <div class="market-ctx" v-if="marketScore">
        <span class="ctx-score" :class="scoreClass(marketScore)">{{ marketScore }}分</span>
        <span class="ctx-regime">{{ marketRegime }}</span>
      </div>

      <!-- 交易员列表(横向滚动) -->
      <div class="agent-strip">
        <button v-for="a in agents" :key="a.id"
          :class="['agent-btn', { active: activeAgent === a.id }]"
          :title="a.name + ' · ' + a.style"
          @click="selectAgent(a)">
          <span class="agent-icon">{{ a.icon }}</span>
          <span class="agent-name">{{ a.name }}</span>
        </button>
      </div>

      <!-- 当前交易员简介 -->
      <div class="agent-info" v-if="activeAgentData">
        <span class="ai-style">{{ activeAgentData.style }}</span>
        <p class="ai-desc">{{ activeAgentData.desc }}</p>
      </div>

      <!-- 对话区域 -->
      <div class="chat-area" ref="chatRef">
        <div v-for="(msg, i) in messages" :key="i" :class="['chat-msg', msg.role]">
          <div class="msg-header">{{ msg.role === 'assistant' ? activeAgentData?.icon + ' ' + activeAgentData?.name : '🙋 你' }}</div>
          <div class="msg-content">{{ msg.content }}</div>
        </div>
        <div v-if="loading" class="chat-msg assistant">
          <div class="msg-header">{{ activeAgentData?.icon }} {{ activeAgentData?.name }}</div>
          <div class="msg-content typing">思考中...</div>
        </div>
      </div>

      <div class="input-area">
        <input v-model="inputText" type="text" class="chat-input"
          :placeholder="'向' + (activeAgentData?.name || '交易员') + '提问...'"
          @keyup.enter="sendMessage" :disabled="loading" />
        <button class="send-btn" @click="sendMessage" :disabled="!inputText.trim() || loading">问</button>
      </div>
    </div>
    <div v-else class="collapsed-bar" @click="toggleCollapse">
      <span class="expand-arrow">◀</span>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'

const isCollapsed = ref(false)
const inputText = ref('')
const messages = ref([])
const loading = ref(false)
const agents = ref([])
const activeAgent = ref('david')
const activeAgentData = ref(null)
const marketScore = ref(null)
const marketRegime = ref('')
const chatRef = ref(null)

function scoreClass(s) { const n = parseInt(s); if (n >= 70) return 'sc-up'; if (n >= 40) return 'sc-mid'; return 'sc-dn' }

function scrollBottom() { nextTick(() => { if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight }) }

function selectAgent(a) {
  activeAgent.value = a.id
  activeAgentData.value = a
  messages.value.push({ role: 'assistant', content: `${a.name}（${a.style}）：${a.desc}。有什么想问我的？` })
  scrollBottom()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  inputText.value = ''
  messages.value.push({ role: 'user', content: text })
  loading.value = true
  scrollBottom()
  try {
    const r = await fetch('/api/agents/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: activeAgent.value, message: text })
    })
    const d = await r.json()
    messages.value.push({ role: 'assistant', content: d.reply })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '连接异常，请稍后重试。' })
  }
  loading.value = false
  scrollBottom()
}

function toggleCollapse() { isCollapsed.value = !isCollapsed.value }

onMounted(async () => {
  try {
    const [aR, oR] = await Promise.all([
      fetch('/api/agents'),
      fetch('/api/market/overview'),
    ])
    const aD = await aR.json()
    if (aD.agents) agents.value = aD.agents

    const oD = await oR.json()
    marketScore.value = oD.market_score
    marketRegime.value = oD.market_regime

    // Default agent
    if (agents.value.length) selectAgent(agents.value[9]) // david
  } catch (e) { console.warn(e) }
})
</script>

<style scoped>
.ai-panel { width: 300px; height: 100vh; background: #0D1117; border-left: 1px solid #21262D; display: flex; flex-direction: column; transition: width .25s; overflow: hidden; }
.ai-panel.collapsed { width: 20px; }
.panel-content { display: flex; flex-direction: column; height: 100%; }
.panel-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-bottom: 1px solid #21262D; }
.panel-title { margin: 0; font-size: 13px; font-weight: 600; color: #C9D1D9; }
.collapse-btn { background: transparent; border: 1px solid #30363D; color: #8B949E; font-size: 10px; padding: 2px 8px; border-radius: 4px; cursor: pointer; }
.market-ctx { display: flex; align-items: center; gap: 6px; padding: 4px 10px; background: #161B22; border-bottom: 1px solid #21262D; font-size: 10px; }
.ctx-score { font-weight: 700; padding: 1px 6px; border-radius: 3px; }
.ctx-score.sc-up { color: #26A69A; background: rgba(38,166,154,.15); }
.ctx-score.sc-mid { color: #F0C040; background: rgba(240,192,64,.15); }
.ctx-score.sc-dn { color: #EF5350; background: rgba(239,83,80,.15); }
.ctx-regime { color: #8B949E; }
.agent-strip { display: flex; gap: 2px; padding: 6px 8px; overflow-x: auto; border-bottom: 1px solid #21262D; }
.agent-strip::-webkit-scrollbar { height: 2px; }
.agent-strip::-webkit-scrollbar-thumb { background: #30363D; border-radius: 2px; }
.agent-btn { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 4px 6px; background: transparent; border: 1px solid transparent; border-radius: 6px; cursor: pointer; min-width: 40px; transition: all .15s; }
.agent-btn:hover { background: #161B22; }
.agent-btn.active { background: #1A202C; border-color: #58A6FF; }
.agent-icon { font-size: 18px; line-height: 1; }
.agent-name { font-size: 9px; color: #8B949E; white-space: nowrap; }
.agent-btn.active .agent-name { color: #58A6FF; }
.agent-info { display: flex; flex-direction: column; gap: 2px; padding: 6px 10px; border-bottom: 1px solid #21262D; }
.ai-style { font-size: 10px; color: #58A6FF; font-weight: 600; }
.ai-desc { font-size: 11px; color: #8B949E; line-height: 1.4; margin: 0; }
.chat-area { flex: 1; overflow-y: auto; padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; }
.chat-msg { max-width: 95%; }
.chat-msg.user { align-self: flex-end; }
.chat-msg.assistant { align-self: flex-start; }
.msg-header { font-size: 9px; color: #484F58; margin-bottom: 1px; }
.msg-content { padding: 6px 10px; border-radius: 6px; font-size: 12px; line-height: 1.5; word-break: break-word; }
.chat-msg.user .msg-content { background: #1F6FEB; color: #fff; }
.chat-msg.assistant .msg-content { background: #161B22; color: #C9D1D9; border: 1px solid #30363D; }
.typing { color: #8B949E; }
.input-area { display: flex; gap: 6px; padding: 6px 10px; border-top: 1px solid #21262D; }
.chat-input { flex: 1; padding: 6px 10px; background: #161B22; border: 1px solid #30363D; border-radius: 6px; color: #C9D1D9; font-size: 12px; outline: none; }
.chat-input:focus { border-color: #58A6FF; }
.chat-input::placeholder { color: #484F58; }
.send-btn { padding: 6px 14px; background: #1F6FEB; color: #fff; border: none; border-radius: 6px; font-size: 12px; cursor: pointer; }
.send-btn:disabled { opacity: .4; cursor: not-allowed; }
.collapsed-bar { width: 20px; height: 100vh; display: flex; align-items: center; justify-content: center; cursor: pointer; background: #0D1117; border-left: 1px solid #21262D; }
.collapsed-bar:hover { background: #161B22; }
.expand-arrow { font-size: 10px; color: #484F58; }
</style>
