<!-- src/views/questionPractice/practice.vue -->
<template>
  <div>
    <div v-if="!isReady" class="loading-container">
      <el-loading-spinner />
    </div>
    <PracticeComponent v-show="isReady" :bank-id="Number(bankId)" :bank-name="bankName" :module-type="moduleType"
      @close="goBack" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getQuestionBank } from '@/api/questionBank/questionBank'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import PracticeComponent from '@/components/PracticeComponent/PracticeComponent.vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const bankId = ref<string | number | null>(null)
const bankName = ref('题库')
const moduleType = ref<string | null>(null)

const isReady = computed(() => bankId.value && moduleType.value)

const loadParams = () => {
  bankId.value = route.params.bankId as string
  moduleType.value = route.params.moduleType as string
  if (moduleType.value === 'wrong') moduleType.value = 'custom'
  if (route.query.bankName) {
    bankName.value = route.query.bankName as string
  } else {
    if (bankId.value) {
      getQuestionBank(bankId.value).then((res: any) => {
        if (res.code === 200 && res.data) {
          bankName.value = res.data.bankName || '题库'
        }
      }).catch(() => { })
    }
  }
}

const goBack = () => {
  cacheStore.setLastVisited('questionPractice', String(bankId.value))
  router.replace(`/front/questionPractice/${bankId.value}`)
}

watch(() => route.params.bankId, () => loadParams())
watch(() => route.params.moduleType, () => loadParams())

onMounted(() => {
  loadParams()
})
</script>

<style scoped>
.loading-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
</style>
