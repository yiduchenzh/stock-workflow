import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMarketStore = defineStore('market', () => {
  const score = ref(50)
  const regime = ref('range')
  const indices = ref({})
  const sectors = ref([])
  const fundFlow = ref({})
  const diagnosis = ref({})
  const plans = ref([])

  function update(data) {
    score.value = data.market_score ?? score.value
    regime.value = data.market_regime ?? regime.value
    indices.value = data.indices ?? indices.value
    sectors.value = data.sectors ?? sectors.value
    plans.value = data.plans ?? plans.value
  }

  return { score, regime, indices, sectors, fundFlow, diagnosis, plans, update }
})
