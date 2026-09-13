import { defineStore } from 'pinia'
import { ref, onMounted } from 'vue'

export const useSSEStore = defineStore('sse', () => {
  const connected = ref(false)
  let eventSource = null

  function connect() {
    if (eventSource) return
    eventSource = new EventSource('/api/sse/live')

    eventSource.onopen = () => { connected.value = true }

    eventSource.addEventListener('market', (e) => {
      try {
        const data = JSON.parse(e.data)
        const marketStore = useMarketStore()
        marketStore.update(data)
      } catch (err) { console.warn('[SSE] market parse error', err) }
    })

    eventSource.addEventListener('signal', (e) => {
      try {
        const data = JSON.parse(e.data)
        const signalsStore = useSignalsStore()
        signalsStore.addSignal(data)
      } catch (err) { console.warn('[SSE] signal parse error', err) }
    })

    eventSource.addEventListener('trade', (e) => {
      try {
        const data = JSON.parse(e.data)
        const portfolioStore = usePortfolioStore()
        portfolioStore.update(data)
      } catch (err) { console.warn('[SSE] trade parse error', err) }
    })

    eventSource.onerror = () => {
      connected.value = false
      setTimeout(() => { eventSource = null; connect() }, 3000)
    }
  }

  function disconnect() {
    if (eventSource) { eventSource.close(); eventSource = null }
    connected.value = false
  }

  return { connected, connect, disconnect }
})
