<template>
  <div class="create-studio">
    <!--
      题库信息
      ==========================================================================
      标题行已整块去掉（用户 2026-10-19）：
      「把第一行的『题库信息 · 名称、科目与封面，决定它出现在别人面前的第一眼』
       移动到『题库搭建』后面」。

      所以现在顶栏是：
        题库搭建 · 题库信息 · 名称、科目与封面，决定它出现在别人面前的第一眼
      （见 `layout/front.vue` 的 `SECOND_LEVEL_BY_ROUTE` / `SECOND_LEVEL_HINT`）

      内容区不再有「题库信息 + 副标题 + 下拉框」那一行 —— 垂直少 32px，
      下面直接从表单开始。

      「载入已有题库」原来挂在标题行右侧，标题行没了之后它如果单独占一行，
      就成了「一个下拉框独占一行」的孤岛（正是用户嫌它占地方的地方）。
      现在下移到**「题库名称」标签的右侧**：那里本来就是一行只有标签的空白带，
      下拉框放进去不增加任何行高，语义上也对得上（"载入一个已有题库" 与
      "给题库起名" 是同一件事的两个方向：新建 or 接着改）。
    -->
    <section class="os-block">
      <el-form ref="basicFormRef" :model="basicForm" :rules="basicRules" label-position="top" class="basic-form">
        <el-row :gutter="20">
          <el-col :span="12">
            <!-- 名称标签行：右侧空位放「载入已有题库」 -->
            <el-form-item prop="bankName" class="name-item">
              <template #label>
                <!--
                  `el-form-item__label-inner` 这一层是必须的：
                  Element Plus 给 label 加的必填星号 `*` 是 `::before`，
                  它作用在 label 的**直接内容前**。如果这里直接放 flex 容器，
                  星号会被挤到容器外面、单独占一行（实测首版就是这样）。
                  把文字包一层 span，星号就能正常贴在「题库名称」前面。
                -->
                <span class="label-tool-row">
                  <span class="label-tool-row__text">题库名称</span>
                  <el-select v-model="selectedBankId" placeholder="载入已有题库" clearable filterable size="small"
                    class="bank-selector" @change="onBankChange">
                    <el-option v-for="bank in myBanks" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
                  </el-select>
                </span>
              </template>
              <el-input v-model="basicForm.bankName" placeholder="给你的题库起个名字" size="large" maxlength="50"
                show-word-limit />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="科目分类" prop="subject">
              <el-select v-model="basicForm.subject" placeholder="选择或输入科目" size="large" filterable allow-create
                style="width: 100%">
                <el-option label="Java" value="Java" />
                <el-option label="Python" value="Python" />
                <el-option label="前端开发" value="前端开发" />
                <el-option label="数据库" value="数据库" />
                <el-option label="算法" value="算法" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="题库封面">
              <ImageUpload v-model="basicForm.coverImage" :limit="1" :file-size="5" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="题库描述">
              <el-input v-model="basicForm.description" type="textarea" :rows="4" placeholder="简单介绍一下这个题库（选填）"
                maxlength="200" show-word-limit />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </section>

    <!-- 题目搭建 -->
    <section class="os-block">
      <header class="os-block__head">
        <div class="os-block__title">
          <h2>
            题目搭建
            <span class="os-block__sub">手动逐题录入；要 AI 批量出题，直接在左侧「智能对话」里说就行</span>
          </h2>
        </div>
      </header>
      <!--
        「AI 搭建」tab 已下线（用户 2026-10-18：「直接把题库搭建页面的 AI 搭建隐藏掉，不需要了」）。
        原因：它与「智能对话」里的出题能力重复，且两套 UI 风格不一致。
        现在只保留「手动搭建」，因此**整个 el-tabs 也一并去掉**（只剩一个 tab 的
        标签栏是纯噪音）。
        ⚠️ 没有删除组件文件与路由参数，若要恢复：
            解开下面的 `<el-tabs>` 块、并让 `buildMode` 能取到 'ai' 即可。
      -->
      <QuestionBuilder ref="builderRef" :bank-id="selectedBankId || bankId"
        :loading="questionsLoading" @reset="resetQuestions" />
    </section>

    <!-- 发布设置 -->
    <section class="os-block">
      <header class="os-block__head">
        <div class="os-block__title">
          <h2>
            发布设置
            <span class="os-block__sub">决定它是自己练，还是放进学习分享</span>
          </h2>
        </div>
      </header>
      <!--
        发布设置改成**两列并排**（2026-10-18）：
        原来可见性、其他设置上下堆叠，右侧整片空着（实测块高 315px、右半页全空），
        在宽屏上非常突兀。现在可见性占左（内容宽）、其他设置占右（窄），
        两列同为 200px 上下，视觉上齐平。
      -->
      <el-form label-position="top" class="publish-form">
        <div class="publish-grid">
          <el-form-item label="题库可见性" class="pg-main">
            <el-radio-group v-model="publishForm.visibility" class="visibility-group">
              <el-radio value="public" class="visibility-item">
                <span class="vi-title">公开</span>
                <span class="vi-desc">所有用户可见，可收藏练习</span>
              </el-radio>
              <el-radio value="private" class="visibility-item">
                <span class="vi-title">私有</span>
                <span class="vi-desc">仅自己可见和管理</span>
              </el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="其他设置" class="pg-side">
            <el-checkbox v-model="publishForm.allowFork">允许其他人复制（Fork）</el-checkbox>
          </el-form-item>
        </div>
      </el-form>
    </section>

    <!-- 底部操作栏（贴底，按钮居中） -->
    <div class="step-footer">
      <div class="sf-inner">
        <el-button type="primary" size="large" :loading="saving" @click="handleSave">
          {{ isEditMode ? '保存修改' : '发布题库' }}
        </el-button>
        <span class="sf-hint">
          {{ isEditMode ? '修改会立即对已收藏该题库的用户生效' : '发布后可在「题库练习」里看到，也可放进学习分享' }}
        </span>
      </div>
    </div>

    <!-- 滚动按钮 -->
    <ScrollButton :bottom="20" :right="20" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontStudioCreate' })
import ImageUpload from '@/components/ImageUpload/index.vue'
import { ref, reactive, computed, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import QuestionBuilder from '../components/QuestionBuilder.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'
import {
  getQuestionBank,
  listMyQuestionBank,
  updateQuestionBank,
  createQuestionBankWithReturn
} from '@/api/questionBank/questionBank'
import { listQuestionMainAll, addQuestionMain, updateQuestionMain, delQuestionMain } from '@/api/questionMain/questionMain'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const isEditMode = computed(() => !!route.query.bankId)
const bankId = computed(() => route.query.bankId ? parseInt(route.query.bankId) : null)
const autoOpenAi = computed(() => route.query.autoOpenAi === 'true')
const newBank = computed(() => route.query.newBank === 'true')

const saving = ref(false)
const basicFormRef = ref(null)
const builderRef = ref(null)
const questionsLoading = ref(false)
const myBanks = ref([])
const selectedBankId = ref(null)

/*
 * 「AI 搭建」tab 已下线（用户 2026-10-18）。
 *
 * 连带影响（都在这里说明白，避免以后有人把 isAiMode 加回来时踩坑）：
 *   · 原来 `buildMode` 有 'manual' / 'ai' 两态，'ai' 时会**隐藏**「发布设置」与
 *     底部发布按钮（因为那时题库由模型创建，不走这套表单）；
 *   · 现在只剩手动搭建，`isAiMode` 恒为 false —— 所以直接删掉它，
 *     模板里那两个 `v-if="!isAiMode"` 也一并去掉（否则读者会以为是活逻辑）。
 *   · 历史上的第三个 tab「Agent 搭建」早已迁到 `/front/agent/chat`。
 */

const basicForm = reactive({
  bankName: '',
  subject: '',
  coverImage: '',
  description: ''
})

const basicRules = {
  bankName: [
    { required: true, message: '请输入题库名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  subject: [{ required: true, message: '请选择或输入科目', trigger: 'change' }]
}

const publishForm = reactive({
  visibility: 'public',
  allowFork: true
})

// ========== 加载用户题库列表 ==========
const loadMyBanks = async () => {
  try {
    const res = await listMyQuestionBank()
    if (res.code === 200 && res.data) {
      myBanks.value = res.data || []
    }
  } catch (error) {
    console.error('加载我的题库失败:', error)
  }
}

// 选中题库变化处理
const onBankChange = async (bankId) => {
  if (!bankId) return
  selectedBankId.value = bankId
  cacheStore.clearCachedForm('studioCreateForm')
  Object.assign(basicForm, {
    bankName: '',
    subject: '',
    coverImage: '',
    description: ''
  })
  if (builderRef.value) builderRef.value.questions = []
  await loadEditData()
}

// ========== Pinia 缓存：恢复表单数据 ==========
onMounted(async () => {
  await loadMyBanks()

  const cachedForm = cacheStore.getCachedForm('studioCreateForm')
  if (cachedForm) {
    Object.assign(basicForm, cachedForm.basicForm || {})
    Object.assign(publishForm, cachedForm.publishForm || {})
  }

  if (isEditMode.value) {
    selectedBankId.value = bankId.value
    await loadEditData()
  } else {
    publishForm.visibility = 'public'
  }

  // 自动打开「AI 生成」弹窗（题库搭建页里那个按题型生成单题/组合题的弹窗）。
  // ⚠️ 与已下线的「AI 搭建」tab 是两回事：tab 是"批量导入资料出题"，这个弹窗是
  //    "按题型生成一道题"，用户 2026-10-18 明确要求保留。
  //    目前没有页面会带 autoOpenAi=true 跳进来，保留作为深链入口（例如将来从
  //    智能体页一键"去生成一道题"）。
  if (autoOpenAi.value) {
    nextTick(() => {
      setTimeout(() => {
        builderRef.value?.openAiDialog?.()
      }, 500)
    })
  }
})

// 监听路由变化
watch(() => route.query.bankId, async (newBankId) => {
  if (newBankId) {
    // 关键：先同步 selectedBankId，否则 loadEditData 里的「selectedBankId || bankId」
    // 会继续读到上一个题库，导致从悬浮助手/外部跳转第二个题库时不刷新
    selectedBankId.value = bankId.value
    if (builderRef.value) builderRef.value.questions = []
    await loadEditData()
  } else {
    basicForm.bankName = ''
    basicForm.subject = ''
    basicForm.coverImage = ''
    basicForm.description = ''
    publishForm.visibility = 'public'
    if (builderRef.value) {
      builderRef.value.questions = []
    }
  }
})

// ✅ 修改 saveFormCache，确保只保存纯数据
const saveFormCache = () => {
  cacheStore.setCachedForm('studioCreateForm', {
    basicForm: {
      bankName: basicForm.bankName || '',
      subject: basicForm.subject || '',
      coverImage: basicForm.coverImage || '',
      description: basicForm.description || ''
    },
    publishForm: {
      visibility: publishForm.visibility || 'public',
      allowFork: publishForm.allowFork ?? true
    }
  })
}

// ✅ 页面离开前保存缓存
onBeforeUnmount(() => {
  saveFormCache()
})




// ========== 题型转换（保持原有逻辑） ==========
const mapTypeToNumber = (type) => {
  const map = { single: 1, multiple: 2, judge: 3, fill: 4, essay: 5, composite: 6, readingComprehension: 6, cloze: 6 }
  return map[type] || 1
}

const mapBackendType = (typeNum) => {
  const map = { 1: 'single', 2: 'multiple', 3: 'judge', 4: 'fill', 5: 'essay', 6: 'composite' }
  return map[typeNum] || 'single'
}

const formatOptions = (options) => {
  if (!options || !Array.isArray(options) || options.length === 0) return null
  // 后端 options 是 JSON 列（数组），直接返回数组，不要再 JSON.stringify
  return options.map(opt => typeof opt === 'string' ? opt : (opt.text ?? opt.value ?? ''))
}

// 兼容后端返回数组 / 旧数据返回 JSON 字符串两种情况
const parseOptions = (options) => {
  if (!options) return []
  try {
    const parsed = typeof options === 'string' ? JSON.parse(options) : options
    if (Array.isArray(parsed)) return parsed.map(item => typeof item === 'string' ? item : item.text || item.value)
  } catch (e) { }
  return []
}

const formatAnswer = (answer, type) => {
  if (answer === undefined || answer === null || answer === '') {
    if (type === 'composite') return ''
    if (type === 'fill' || type === 'essay') return ''
    return ''
  }
  switch (type) {
    case 'judge': // 判断题
      return (answer === true || answer === 'true' || answer === '1') ? 'true' : 'false'
    case 'single': // 单选题
      if (typeof answer === 'number' && answer >= 0) return String(answer)
      if (typeof answer === 'string' && /^\d+$/.test(answer)) return answer
      if (typeof answer === 'string' && answer.length === 1) return String(answer.charCodeAt(0) - 65)
      return ''
    case 'multiple': // 多选题
      if (Array.isArray(answer)) {
        const valid = answer.filter(idx => typeof idx === 'number' && idx >= 0)
        return valid.map(idx => String(idx)).join(',')
      }
      return String(answer)
    default: return String(answer)
  }
}

const parseAnswer = (answerStr, typeNum) => {
  if (!answerStr || answerStr === 'null' || answerStr === '') {
    if (typeNum === 3) return false
    if (typeNum === 2) return []
    if (typeNum === 1) return 0
    return ''
  }
  switch (typeNum) {
    case 3: // 判断题
      return answerStr === 'true' || answerStr === '1' || answerStr === '√'
    case 2: // 多选题
      // 支持 "0,1,2" 或 "A,B,C" 格式
      return answerStr.split(',').map(s => s.trim()).map(item => {
        if (/^\d+$/.test(item)) return parseInt(item)  // 数字格式
        return item.charCodeAt(0) - 65  // 字母格式
      })
    case 1: // 单选题
      // 支持 "0" 或 "A" 格式
      if (/^\d+$/.test(answerStr)) return parseInt(answerStr)
      return answerStr.charCodeAt(0) - 65
    default: return answerStr
  }
}

// ========== 加载编辑数据 ==========
const loadEditData = async () => {
  const currentBankId = selectedBankId.value || bankId.value
  if (!currentBankId) return
  if (builderRef.value) builderRef.value.questions = []
  questionsLoading.value = true
  try {
    const bankRes = await getQuestionBank(currentBankId)
    if (bankRes.code === 200 && bankRes.data) {
      const bank = bankRes.data
      basicForm.bankName = bank.bankName
      basicForm.subject = bank.subject
      basicForm.coverImage = bank.coverImage || bank.cover_image || ''
      basicForm.description = bank.description || ''
      publishForm.visibility = bank.isPublic === 0 ? 'public' : 'private'
      publishForm.allowFork = bank.allowFork !== 0
    } else {
      ElMessage.error('加载题库信息失败')
    }

    const questionRes = await listQuestionMainAll({ bankId: currentBankId })
    if (questionRes.code === 200 && questionRes.data) {
      // 后端 list_all_questions 已通过 selectinload 一次性返回所有题目（含子题）
      // 直接使用列表数据，避免对每个题目再调 getQuestionMain 导致 N+1 请求
      const questions = questionRes.data.map(fullQ => {
        const base = {
          id: fullQ.id,
          backendId: fullQ.id,
          type: mapBackendType(fullQ.questionType),
          title: fullQ.questionText || '',
          content: fullQ.content || '',
          analysis: fullQ.analysis || '',
          score: fullQ.score || 5
        }
        const isComposite = fullQ.questionType === 6 || fullQ.hasSubQuestions === 1
        if (isComposite) {
          base.type = 'composite'
          base.content = fullQ.content || ''
          // 后端 format_question 返回字段名为 subQuestions（非 questionSubList）
          const subList = fullQ.subQuestions || []
          base.subQuestions = subList.map(sub => ({
            id: sub.id,
            type: mapBackendType(sub.questionType),
            question: sub.questionText || '',
            optionsJson: sub.options,
            options: parseOptions(sub.options),
            answer: parseAnswer(sub.answer, sub.questionType),
            score: sub.score || 2,
            sortOrder: sub.sortOrder !== undefined ? sub.sortOrder : 0,
            analysis: sub.analysis || ''
          }))
        } else if (['single', 'multiple', 'judge'].includes(base.type)) {
          base.options = parseOptions(fullQ.options)
          base.optionsJson = JSON.stringify(base.options)
          base.answer = parseAnswer(fullQ.answer, fullQ.questionType)
        } else if (base.type === 'fill' || base.type === 'essay') {
          base.answer = fullQ.answer || ''
        }
        return base
      })
      if (builderRef.value) builderRef.value.questions = questions
    }
  } catch (error) {
    console.error('加载编辑数据失败:', error)
    ElMessage.error('加载数据失败，请刷新重试')
  } finally {
    questionsLoading.value = false
  }
}

// 一键恢复：确认框已在 QuestionBuilder 内弹出，这里直接执行恢复
// 动态取当前选中的题库（用户可能在页面内切换多个题库），恢复对应的原始数据
const resetQuestions = async () => {
  if (!builderRef.value) return
  const currentBankId = selectedBankId.value || bankId.value
  if (currentBankId) {
    // loadEditData 内部会动态读取 selectedBankId || bankId，重新加载当前题库的原始数据
    await loadEditData()
    ElMessage.success('已恢复至该题库的原始数据')
  } else {
    builderRef.value.questions = []
    ElMessage.success('已恢复初始状态')
  }
}

const validateAnswers = (questions) => {
  for (let i = 0; i < questions.length; i++) {
    const q = questions[i]
    if (q.type === 'composite' && q.subQuestions) {
      for (let j = 0; j < q.subQuestions.length; j++) {
        const sub = q.subQuestions[j]
        const answer = sub.answer
        if (sub.type === 'judge' && typeof answer !== 'boolean') {
          ElMessage.error(`第${i + 1}题的第${j + 1}子题（判断）答案无效`)
          return false
        }
        if (sub.type === 'single' && (typeof answer !== 'number' || answer < 0)) {
          ElMessage.error(`第${i + 1}题的第${j + 1}子题（单选）答案无效`)
          return false
        }
        if (sub.type === 'multiple' && (!Array.isArray(answer) || answer.length === 0)) {
          ElMessage.error(`第${i + 1}题的第${j + 1}子题（多选）答案不能为空`)
          return false
        }
        if ((sub.type === 'fill' || sub.type === 'essay') && (!answer || answer.toString().trim() === '')) {
          ElMessage.error(`第${i + 1}题的第${j + 1}子题答案不能为空`)
          return false
        }
      }
      continue
    }
    if (q.type === 'single' && (typeof q.answer !== 'number' || q.answer < 0)) {
      ElMessage.error(`第${i + 1}题（单选）答案无效`)
      return false
    }
    if (q.type === 'multiple' && (!Array.isArray(q.answer) || q.answer.length === 0)) {
      ElMessage.error(`第${i + 1}题（多选）答案不能为空`)
      return false
    }
    if (q.type === 'judge' && typeof q.answer !== 'boolean') {
      ElMessage.error(`第${i + 1}题（判断）答案无效`)
      return false
    }
    if ((q.type === 'fill' || q.type === 'essay') && (!q.answer || q.answer.toString().trim() === '')) {
      ElMessage.error(`第${i + 1}题答案不能为空`)
      return false
    }
  }
  return true
}

// ========== 保存 ==========
const handleSave = async () => {
  saveFormCache()

  if (!basicForm.bankName || basicForm.bankName.trim().length < 2) {
    ElMessage.warning('请填写题库名称（至少2个字符）')
    return
  }
  if (!basicForm.subject) {
    ElMessage.warning('请选择或输入科目')
    return
  }

  await basicFormRef.value?.validate().catch(() => {
    ElMessage.warning('请填写完整的题库基本信息')
    return
  })

  const rawQuestions = builderRef.value?.questions || []
  const currentQuestions = JSON.parse(JSON.stringify(rawQuestions.map((q, index) => {
    const base = {
      ...q,
      sortOrder: index,
      title: q.title || '',
      content: q.content || '',
      questionAnalysis: q.analysis || '',
      score: Number(q.score) || 5,
      type: q.type || 'single',
      options: q.options ? [...q.options] : [],
      answer: q.answer
    }
    if (q.type === 'composite' && q.subQuestions) {
      base.subQuestions = q.subQuestions.map((sub, subIdx) => ({
        ...sub,
        sortOrder: subIdx,
        score: Number(sub.score) || 2,
        options: sub.options ? [...sub.options] : []
      }))
    }
    return base
  }))

  )

  // 允许空题库发布（用户可以先创建题库占位，后续再添加题目）
  if (currentQuestions.length > 0) {
    if (!validateAnswers(currentQuestions)) return
  } else {
    try {
      await ElMessageBox.confirm(
        '当前题库没有题目，确定要创建空题库吗？您可以后续再添加题目。',
        '创建空题库',
        { confirmButtonText: '确定创建', cancelButtonText: '取消', type: 'info' }
      )
    } catch {
      return
    }
  }

  saving.value = true
  const bankData: any = {
    bankName: basicForm.bankName,
    subject: basicForm.subject,
    description: basicForm.description,
    coverImage: basicForm.coverImage,
    totalQuestions: currentQuestions.length,
    status: '0',
    isPublic: publishForm.visibility === 'public' ? 0 : 1,
    allowFork: publishForm.allowFork ? 1 : 0
  }

  try {
    let targetBankId = selectedBankId.value || bankId.value
    const effectiveBankId = targetBankId

    if (effectiveBankId) {
      bankData.bankId = effectiveBankId
      const updateRes = await updateQuestionBank(bankData)
      if (updateRes.code !== 200) throw new Error(updateRes.msg || '更新题库失败')
      targetBankId = effectiveBankId

      const existingRes = await listQuestionMainAll({ bankId: effectiveBankId })
      const existingQuestions = existingRes.code === 200 ? existingRes.data : []
      const existingMap = new Map(existingQuestions.map(q => [q.id, q]))

      const toAdd = [], toUpdate = [], frontendIds = new Set()
      for (const q of currentQuestions) {
        if (q.backendId && existingMap.has(q.backendId)) {
          toUpdate.push(q)
          frontendIds.add(q.backendId)
        } else {
          toAdd.push(q)
        }
      }
      const toDelete = existingQuestions.filter(q => !frontendIds.has(q.id)).map(q => q.id)
      if (toDelete.length) await delQuestionMain(toDelete.join(','))

      for (const q of toUpdate) {
        await updateQuestionMain(JSON.parse(JSON.stringify({
          id: q.backendId, bankId: targetBankId, questionType: mapTypeToNumber(q.type), difficulty: 2,
          questionText: q.title || '', content: q.content || '',
          options: formatOptions(q.options),
          answer: q.type === 'composite' ? '' : formatAnswer(q.answer, q.type),
          questionAnalysis: q.analysis || '',
          hasSubQuestions: (q.type === 'composite' && q.subQuestions?.length) ? 1 : 0,
          sortOrder: currentQuestions.indexOf(q), score: q.score || 5, status: '0',
          questionSubList: (q.type === 'composite' && q.subQuestions) ? q.subQuestions.map((sub, idx) => ({
            id: sub.id, questionText: sub.question, questionType: mapTypeToNumber(sub.type),
            options: formatOptions(sub.options), answer: formatAnswer(sub.answer, sub.type),
            analysis: sub.analysis || '', sortOrder: sub.sortOrder !== undefined ? sub.sortOrder : idx, score: sub.score || 2
          })) : []
        })))
      }
      for (const q of toAdd) {
        await addQuestionMain(JSON.parse(JSON.stringify({
          bankId: targetBankId, questionType: mapTypeToNumber(q.type), difficulty: 2,
          questionText: q.title || '', content: q.content || '',
          options: formatOptions(q.options),
          answer: q.type === 'composite' ? '' : formatAnswer(q.answer, q.type),
          questionAnalysis: q.analysis || '',
          hasSubQuestions: (q.type === 'composite' && q.subQuestions?.length) ? 1 : 0,
          sortOrder: currentQuestions.indexOf(q), score: q.score || 5, status: '0',
          questionSubList: (q.type === 'composite' && q.subQuestions) ? q.subQuestions.map((sub, idx) => ({
            questionText: sub.question, questionType: mapTypeToNumber(sub.type),
            options: formatOptions(sub.options), answer: formatAnswer(sub.answer, sub.type),
            analysis: sub.analysis || '', sortOrder: sub.sortOrder !== undefined ? sub.sortOrder : idx, score: sub.score || 2
          })) : []
        })))
      }
      ElMessage.success('保存成功')
    } else {
      const createRes = await createQuestionBankWithReturn(bankData)
      if (createRes.code !== 200) throw new Error(createRes.msg || '创建题库失败')
      targetBankId = createRes.data?.id
      if (!targetBankId) throw new Error('创建题库成功但未返回ID')
      for (let i = 0; i < currentQuestions.length; i++) {
        const q = currentQuestions[i]
        await addQuestionMain(JSON.parse(JSON.stringify({
          bankId: targetBankId, questionType: mapTypeToNumber(q.type), difficulty: 2,
          questionText: q.title || '', content: q.content || '',
          options: formatOptions(q.options),
          answer: q.type === 'composite' ? '' : formatAnswer(q.answer, q.type),
          questionAnalysis: q.analysis || '',
          hasSubQuestions: (q.type === 'composite' && q.subQuestions?.length) ? 1 : 0,
          sortOrder: i, score: q.score || 5, status: '0',
          questionSubList: (q.type === 'composite' && q.subQuestions) ? q.subQuestions.map((sub, idx) => ({
            questionText: sub.question, questionType: mapTypeToNumber(sub.type),
            options: formatOptions(sub.options), answer: formatAnswer(sub.answer, sub.type),
            analysis: sub.analysis || '', sortOrder: sub.sortOrder !== undefined ? sub.sortOrder : idx, score: sub.score || 2
          })) : []
        })))
      }
      ElMessage.success('发布成功')
    }

    cacheStore.clearCachedForm('studioCreateForm')
    router.push('/front/myQuestion/myBank')
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.message || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}
</script>


<style scoped lang="scss">
/*
 * 题库搭建 · 创建页
 * =================
 * 与 DSH 前台的版式对齐（2026-10-17 重构）：
 *   · **不再用"白底大圆角卡片 + 阴影"**分块 —— 那是旧版儒瑞式风格，
 *     整页看起来像一堆浮起来的盒子，和对话页、我的学习都不连成一片；
 *   · 改成**通栏分块**：每块只有一条极淡的分隔线 + 一块标题区，
 *     与 `AGENTS.md` 里"页面根节点不要做成悬浮圆角卡片"的规则一致；
 *   · 颜色全部换设计令牌（`var(--os-*)`），不再写 #1f2937 / #409eff 这类硬编码；
 *   · 标题前的 emoji 全部去掉（📋 / 📝 / ⚙️），改用纯文字 + 副标题说明，
 *     与本系统线性图标的调性统一。
 */
.create-studio {
  max-width: 1180px;
  margin: 0 auto;
  padding: 4px 4px 40px;

  :deep(.el-button) {
    border-radius: var(--os-radius-sm);
  }
}

/* ==================== 分块（通栏，不套卡片） ==================== */
.os-block {
  padding: 4px 0 26px;

  & + .os-block {
    border-top: 1px solid var(--os-border-soft);
    padding-top: 26px;
  }
}

.os-block__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

/*
 * 分块标题 + 行内副标题
 * ----------------------------------------------------------------------------
 * 用户 2026-10-19：「把『名称、科目与封面，决定它出现在别人面前的第一眼』
 * 拼接到第一行的『题库搭建』后面」。
 *
 * 副标题从独立 `<p>` 改成标题行内的次级文本：
 * 分隔点用 `·`，与顶栏的「我的学习 · 题库管理」同一套层级语言。
 * 窄屏放不下时允许换到第二行，但仍与标题同属一个块。
 */
.os-block__title {
  min-width: 0;

  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.4;
    letter-spacing: -0.01em;
    color: var(--os-text);
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0 2px;
  }

  /* 行内副标题：次级色、常规字重，不抢标题 */
  .os-block__sub {
    font-size: 12.5px;
    font-weight: 400;
    line-height: 1.5;
    letter-spacing: 0;
    color: var(--os-text-4);

    &::before {
      content: '·';
      margin: 0 6px;
      color: var(--os-text-4);
    }
  }

  /* 少数分块仍用独立副标题（没有并进标题行的那种） */
  p {
    margin: 3px 0 0;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--os-text-4);
  }
}

/* 标题行右侧的工具区（载入已有题库） */
.head-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

/*
 * 「载入已有题库」下拉
 * ----------------------------------------------------------------------------
 * 现在挂在「题库名称」的 label 行右侧（见模板注释）。
 * 用 small 尺寸 + 定宽，让它读作"标签旁边的一个小工具"，而不是一个主表单控件。
 */
.bank-selector {
  width: 180px;
  flex: none;

  :deep(.el-select__wrapper) {
    border-radius: var(--os-radius-sm);
    /* 轻量化：默认的深描边会把它抬成"和输入框同级"，这里压到次级 */
    box-shadow: 0 0 0 1px var(--os-border, #e5e7eb);
    background: #fff;
  }
}

/* label 行：标签在左、下拉在右，共用一行（外层 label 已是 flex 容器） */
.label-tool-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  /* 吃掉 label 里除星号外的剩余宽度，下拉才能真的靠右 */
  flex: 1;
  min-width: 0;
  line-height: 1;
}

.label-tool-row__text {
  flex: none;
  white-space: nowrap;
}

/*
 * 名称项：label 行要让下拉能撑开，不能按"行内文字"处理
 * ----------------------------------------------------------------------------
 * Element Plus 的必填星号是 label 上的 `::before`（content: "*"，inline）。
 *
 * 这里把 label 设成 `display: flex`：`::before` 会变成**第一个 flex item**，
 * 星号 ⇢ 标签文字 ⇢ 下拉框 就能排在同一行。
 *
 * ⚠️ 之前踩过两个坑：
 *   ① label 保持 block，内层放 `display:flex` 的容器 —— 容器是块级盒子，
 *      星号被顶到上一行，标签行变成两行（首版实测就是这样）；
 *   ② 内层还是 `display:flex`，只是改成 inline-flex —— 星号回来了，
 *      但内层不再撑满宽度，下拉框贴着文字而不是靠右。
 *
 * 正确做法就是让 label 自己当 flex 容器，内层 `flex: 1` 吃掉剩余宽度。
 */
.name-item {
  :deep(.el-form-item__label) {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 0 0 6px;
    height: auto;
    line-height: 1;
    white-space: normal;

    /* 星号：不参与压缩，留一点右边距 */
    &::before {
      flex: none;
      margin-right: 2px;
    }
  }
}

@media (max-width: 900px) {
  .os-block__head {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .bank-selector {
    width: 100%;
  }

  .label-tool-row {
    flex-wrap: wrap;
    gap: 6px;
  }
}

/* ==================== 表单 ==================== */
.basic-form,
.publish-form {
  :deep(.el-form-item__label) {
    font-weight: 500;
    color: var(--os-text-2);
  }

  :deep(.el-input__wrapper),
  :deep(.el-select__wrapper) {
    border-radius: var(--os-radius-sm);
  }

  :deep(.el-textarea__inner) {
    border-radius: var(--os-radius-sm);
  }
}

/* 可见性：两张并排的可选卡（比原生 radio + 两行长文字更好认） */
.visibility-group {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.visibility-item {
  height: auto;
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--os-border);
  border-radius: var(--os-radius);
  background: #fff;
  transition: border-color var(--ds-duration-fast) var(--ds-ease-in-out),
    background-color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    border-color: var(--os-border-strong);
  }

  &:has(.is-checked) {
    border-color: var(--os-text);
    background: var(--dsw-static-neutral-bluish-50);
  }

  :deep(.el-radio__label) {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-left: 8px;
  }

  .vi-title {
    font-size: 13.5px;
    font-weight: 500;
    color: var(--os-text);
  }

  .vi-desc {
    font-size: 12px;
    line-height: 1.4;
    color: var(--os-text-4);
  }
}

/* ==================== 发布设置两列 ==================== */
.publish-grid {
  display: flex;
  align-items: flex-start;
  gap: 40px;
  flex-wrap: wrap;

  /* 左侧「可见性」吃掉剩余宽度，右侧「其他设置」按内容宽度（窄） */
  .pg-main {
    margin-bottom: 0;
    flex: 1 1 420px;
    min-width: 0;
  }

  .pg-side {
    margin-bottom: 0;
    flex: 0 0 auto;
  }
}

/*
 * ==================== 底部操作栏 ====================
 *
 * 用户 2026-10-18 两轮反馈：
 *   ①「底部的按钮很不协调」→ 实心按钮修好了（见下面 el-button--primary）；
 *   ②「要移动到中间来」→ 按钮与说明**整体居中**，不再左右分置。
 *
 * 结构：`.step-footer`（贴底白条） > `.sf-inner`（居中的一组：按钮 + 下方说明）。
 * 说明文字放在按钮**下面**而不是左右，是因为左右分置会再次产生"一头重一头轻"的观感；
 * 竖排一组更像一页表单的收尾。
 */
.step-footer {
  position: sticky;
  bottom: 0;
  z-index: 5;
  margin: 8px -16px 0;
  padding: 14px 16px 12px;
  background: #fff;
  border-top: 1px solid var(--os-border-soft);
}

.sf-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;

  .sf-hint {
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--os-text-4);
    text-align: center;
  }

  :deep(.el-button) {
    padding: 10px 36px;
    font-weight: 500;
    border-radius: var(--os-radius-sm);
  }

  /* 主按钮：实心近黑底 + 白字
     ⚠️ 不能只依赖 `--el-button-*` CSS 变量（试过：变量能读到值但背景仍是白色，
        因为 Element 的 `.el-button--primary` 规则里直接用 `background-color:
        var(--el-button-bg-color)`，而本页 scoped 的变量声明没落到按钮自身上）。
        这里直接写 `background-color` / `color`，最稳。 */
  :deep(.el-button--primary) {
    background-color: var(--os-primary);
    border-color: var(--os-primary);
    color: #fff;

    &:hover,
    &:focus {
      background-color: var(--os-primary-hover);
      border-color: var(--os-primary-hover);
      color: #fff;
    }

    &:active {
      background-color: var(--os-primary);
      border-color: var(--os-primary);
    }

    &.is-disabled,
    &.is-disabled:hover {
      background-color: var(--os-border);
      border-color: var(--os-border);
      color: var(--os-text-4);
    }
  }

  /* 窄屏：说明文字换行会更挤，直接隐藏，只留居中的按钮 */
  @media (max-width: 720px) {
    .sf-hint {
      display: none;
    }
  }
}
/*
 * 「AI 搭建」tab 下线后，`.build-tabs` 那套 tabs 样式已无宿主，一并删除。
 * 若将来恢复 tab，记得把 tabs 的 header/间距样式补回来。
 */
</style>
