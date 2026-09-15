<template>
  <div class="create-studio">
    <!-- 题库信息 -->
    <div class="section">
      <div class="section-header">
        <div class="section-title">📋 题库信息</div>
        <el-select v-model="selectedBankId" placeholder="选择已有题库" clearable filterable size="default"
          style="width: 200px" @change="onBankChange" class="bank-selector">
          <el-option v-for="bank in myBanks" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
        </el-select>
      </div>
      <el-form ref="basicFormRef" :model="basicForm" :rules="basicRules" label-position="top" class="basic-form">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="题库名称" prop="bankName">
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
    </div>

    <!-- 题目搭建 -->
    <div class="section">
      <div class="section-title">📝 题目搭建</div>
      <el-tabs v-model="buildMode" class="build-tabs">
        <el-tab-pane label="手动搭建" name="manual">
          <QuestionBuilder ref="builderRef" :bank-id="selectedBankId || bankId"
            :loading="questionsLoading" @reset="resetQuestions" />
        </el-tab-pane>
        <el-tab-pane label="AI 搭建" name="ai">
          <AiQuestionBuilder
            :bank-id="selectedBankId || bankId"
            :bank-name="basicForm.bankName"
            :bank-subject="basicForm.subject"
            @import-complete="handleAiImportComplete"
          />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 发布设置（AI模式下隐藏） -->
    <div v-if="buildMode !== 'ai'" class="section">
      <div class="section-title">⚙️ 发布设置</div>
      <el-form label-position="top" class="publish-form">
        <el-form-item label="题库可见性">
          <el-radio-group v-model="publishForm.visibility">
            <el-radio label="public">
              <div class="radio-label">
                <span class="label-title">公开</span>
                <span class="label-desc">所有用户可见，可收藏练习</span>
              </div>
            </el-radio>
            <el-radio label="private">
              <div class="radio-label">
                <span class="label-title">私有</span>
                <span class="label-desc">仅自己可见和管理</span>
              </div>
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="其他设置">
          <el-checkbox v-model="publishForm.allowFork">允许其他人复制（Fork）</el-checkbox>
        </el-form-item>
      </el-form>
    </div>

    <!-- 底部操作栏（AI模式下隐藏） -->
    <div v-if="buildMode !== 'ai'" class="step-footer">
      <el-button type="primary" size="large" :loading="saving" @click="handleSave">
        {{ isEditMode ? '保存修改' : '发布题库' }}
      </el-button>
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
import AiQuestionBuilder from '../components/AiQuestionBuilder.vue'
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
const buildMode = ref('manual') // 'manual' 或 'ai'

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

// AI 导入完成回调
const handleAiImportComplete = async (data) => {
  // 兼容新旧格式
  const bankId = typeof data === 'object' ? data.bankId : data
  const isNew = typeof data === 'object' ? data.isNew : false

  if (bankId) {
    selectedBankId.value = bankId
    // 加载题库信息并更新顶部表单
    try {
      const res = await getQuestionBank(bankId)
      if (res.code === 200 && res.data) {
        basicForm.bankName = res.data.bankName || ''
        basicForm.subject = res.data.subject || ''
        basicForm.description = res.data.description || ''
        basicForm.coverImage = res.data.coverImage || ''
      }
    } catch (e) {
      console.error('加载题库信息失败:', e)
    }
  }
  // 刷新题库列表
  await loadMyBanks()
}

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

  // 自动打开 AI 出题弹窗
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
.create-studio {
  max-width: 100%;
  margin: 0 auto;
  padding: 12px 16px;

  :deep(.el-button) {
    border-radius: 8px;
  }

  :deep(.el-tag) {
    border-radius: 4px;
  }

  :deep(.el-radio__input.is-checked .el-radio__inner) {
    border-radius: 50%;
  }

  :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
    border-radius: 4px;
  }

  .section {
    background: #fff;
    border-radius: 16px;
    padding: 16px 20px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    border: 1px solid #e5e7eb;

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid #e5e7eb;

      .section-title {
        margin-bottom: 0;
        padding-bottom: 0;
        border-bottom: none;
      }

      .bank-selector {
        :deep(.el-select__wrapper) {
          border-radius: 8px;
        }
      }
    }

    .section-title {
      font-size: 18px;
      font-weight: 600;
      color: #1f2937;
      margin-bottom: 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid #e5e7eb;
    }
  }

  .basic-form,
  .publish-form {
    :deep(.el-form-item__label) {
      font-weight: 500;
      color: #374151;
    }

    :deep(.el-input__wrapper) {
      border-radius: 8px;
      box-shadow: 0 0 0 1px #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        box-shadow: 0 0 0 1px #d1d5db;
      }

      &.is-focus {
        box-shadow: 0 0 0 1px #409eff;
      }
    }

    :deep(.el-textarea__inner) {
      border-radius: 8px;
      border-color: #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #d1d5db;
      }

      &:focus {
        border-color: #409eff;
      }
    }

    :deep(.el-select .el-input__wrapper) {
      border-radius: 8px;
    }

    .radio-label {
      display: flex;
      flex-direction: column;

      .label-title {
        font-weight: 500;
        color: #1f2937;
      }

      .label-desc {
        font-size: 13px;
        color: #6b7280;
      }
    }
  }

  .step-footer {
    display: flex;
    justify-content: center;
    padding-top: 12px;

    :deep(.el-button) {
      border-radius: 8px;
      padding: 12px 48px;
      font-weight: 500;
    }
  }

  .build-tabs {
    :deep(.el-tabs__header) {
      margin-bottom: 20px;
    }

    :deep(.el-tabs__item) {
      font-size: 15px;
      font-weight: 500;
    }

    :deep(.el-tabs__content) {
      padding: 0;
    }
  }
}
</style>