import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSignalsStore = defineStore('signals', () => {
  const signals = ref([])
  const filter = ref('all')
  const unreadCount = ref(0)

  const signalList = computed(() => signals.value)

  const filteredSignals = computed(() => {
    if (filter.value === 'all') return signals.value
    if (filter.value === 'bull') return signals.value.filter(s => s.score >= 60)
    if (filter.value === 'bear') return signals.value.filter(s => s.score < 40)
    if (filter.value === 'neutral') return signals.value.filter(s => s.score >= 40 && s.score < 60)
    if (filter.value === 'chan') return signals.value.filter(s => s.strategy?.startsWith('chan_'))
    if (filter.value === 'naked') return signals.value.filter(s => s.strategy?.startsWith('naked_'))
    return signals.value
  })

  function addSignal(signal) {
    signals.value.unshift(signal)
    unreadCount.value++
    if (signals.value.length > 200) signals.value = signals.value.slice(0, 200)
  }

  async function fetchSignals() {
    try {
      const r = await fetch('/api/signals/latest?limit=20')
      const d = await r.json()
      if (d.signals) signals.value = d.signals
    } catch (e) {
      console.warn('[signals] fetch error:', e)
    }
  }

  function markRead() { unreadCount.value = 0 }
  function setFilter(f) { filter.value = f }

  return { signals, filter, unreadCount, signalList, filteredSignals, addSignal, markRead, setFilter, fetchSignals }
})
