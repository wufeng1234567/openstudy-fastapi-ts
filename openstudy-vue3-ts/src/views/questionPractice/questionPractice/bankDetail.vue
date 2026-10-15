<!-- src/views/questionPractice/bankDetail.vue -->
<template>
  <QuestionBankDetail v-if="bank" :bank="bank" @back="goBack" />
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontQuestionBankDetail' })
import { ref, watch, onMounted, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getQuestionBank } from '@/api/questionBank/questionBank'
import { getCurrentInstance } from 'vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import QuestionBankDetail from '@/components/QuestionBankDetail/QuestionBankDetail.vue'
import type { QuestionBank } from '@/types'

const route = useRoute()
const router = useRouter()
const { proxy } = getCurrentInstance() as any
const cacheStore = useFrontPageCacheStore()

const bank = ref<QuestionBank | null>(null)

const fetchBank = async () => {
  const bankId = route.params.bankId
  if (!bankId) {
    goBack()
    return
  }
  try {
    const res: any = await getQuestionBank(bankId as string)
    if (res.code === 200 && res.data) {
      bank.value = res.data
    } else {
      proxy.$modal.msgError('题库不存在')
      goBack()
    }
  } catch (e) {
    console.error('获取题库失败:', e)
    proxy.$modal.msgError('获取题库失败')
    goBack()
  }
}

const goBack = () => {
  const source = cacheStore.getCachedForm('bankDetailSource')
  cacheStore.clearCachedForm('bankDetailSource')
  cacheStore.setLastVisited('questionPractice', '')

  if (source === 'myLearning') {
    router.back()
  } else if (source === 'questionPractice') {
    router.replace('/front/questionPractice')
  } else {
    router.replace('/front/questionPractice')
  }
}

watch(() => route.params.bankId, (newId) => {
  if (newId) {
    fetchBank()
  }
})

onMounted(() => {
  if (route.query.from === 'myLearning') {
    cacheStore.setCachedForm('bankDetailSource', 'myLearning')
  } else if (route.query.from === 'questionPractice') {
    cacheStore.setCachedForm('bankDetailSource', 'questionPractice')
  }
  fetchBank()
})

onActivated(() => {
  if (route.query.from === 'myLearning') {
    cacheStore.setCachedForm('bankDetailSource', 'myLearning')
  } else if (route.query.from === 'questionPractice') {
    cacheStore.setCachedForm('bankDetailSource', 'questionPractice')
  }

  const bankId = route.params.bankId
  if (bankId && (!bank.value || bank.value.id !== Number(bankId))) {
    fetchBank()
  }
})
</script>
