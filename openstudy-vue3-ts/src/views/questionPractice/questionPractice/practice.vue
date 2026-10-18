<!-- src/views/questionPractice/practice.vue -->
<template>
  <div>
    <!--
      题库加载占位
      ------------------------------------------------------------------
      ⚠️ 原来写的是 `<el-loading-spinner />` —— 但 Element Plus **并不导出这个组件**
         （它的 loading 是内置 `h('svg', ...)` 直接渲染原生 SVG，没有独立组件名）。
         结果是组件解析失败、控制台刷 `Failed to resolve component: el-loading-spinner`，
         而且页面上只剩一个空白容器、**看不到转圈动画**（进题库先白屏一下）。
      改用官方 `v-loading` 指令：遮罩 + 转圈都由 Element Plus 自己渲染。
    -->
    <div v-if="!isReady" v-loading="true" class="loading-container" element-loading-text="正在加载题库…"></div>
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
