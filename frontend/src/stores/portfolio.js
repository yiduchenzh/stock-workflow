import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePortfolioStore = defineStore('portfolio', () => {
  const totalAssets = ref(0)
  const cash = ref(0)
  const positions = ref([])
  const agents = ref([])
  const riskStatus = ref(null)

  function update(data) {
    totalAssets.value = data.total ?? totalAssets.value
    cash.value = data.cash ?? cash.value
    if (data.positions) positions.value = data.positions
    if (data.agents) agents.value = data.agents
    if (data.riskStatus) riskStatus.value = data.riskStatus
  }

  return { totalAssets, cash, positions, agents, riskStatus, update }
})
