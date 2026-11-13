import { computed } from 'vue'
import useUserStore from '@/store/modules/user'

/**
 * QuestionBuilder.vue 的上下文派生值。
 *
 * 从 SFC 抽出的纯状态辅助：当前登录用户 id（唯一可信来源）与当前题库 id
 * （跟随父组件传入的 props.bankId 动态变化）。不含 watch、生命周期或 API 调用。
 * 返回的名字以原名解构回 `<script setup>`，调用点与模板绑定不变。
 */
export function useQuestionBuilderContext(props: any) {
  const userStore = useUserStore()
  const userId = computed(() => userStore.id)
  const currentBankId = computed(() => props.bankId)
  return { userId, currentBankId }
}
