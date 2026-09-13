import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const uid = ref('')
  const tier = ref('free')
  const isPaid = ref(false)

  function setUser(u) { uid.value = u.uid; tier.value = u.tier; isPaid.value = u.tier !== 'free' }

  return { uid, tier, isPaid, setUser }
})
