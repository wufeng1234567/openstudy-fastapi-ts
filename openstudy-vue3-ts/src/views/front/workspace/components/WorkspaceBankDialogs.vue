<template>
  <el-dialog v-model="bankImportVisible" title="从题库导入" width="700px" append-to-body>
    <div class="kbp-bank">
      <p class="kbp-bank__hint">
        把已有题库关联到当前资料夹。题库不会复制到资料夹里，只建立逻辑连接；关联后知识图谱会读取题库中的知识点与题目关系。
      </p>
      <div class="kbp-bank__bar">
        <el-input v-model="bankImportKeyword" clearable placeholder="搜索题库名称或科目" />
        <el-button size="small" plain :loading="bankImportLoading" @click="api.refreshBankImportList">刷新</el-button>
      </div>
      <div v-loading="bankImportLoading" class="kbp-bank__list">
        <article v-for="bank in filteredBankImportBanks" :key="bank.bankId || bank.id" class="kbp-bank__item">
          <div class="kbp-bank__main">
            <div class="kbp-bank__title-row">
              <b>{{ bank.bankName || bank.name || '未命名题库' }}</b>
              <el-tag v-if="bank.linked" size="small" type="success" effect="plain">已关联</el-tag>
            </div>
            <span class="kbp-bank__meta">
              {{ bank.subject || '未设置科目' }} · {{ bank.questionCount || bank.totalQuestions || 0 }} 道题
            </span>
            <p v-if="bank.description" class="kbp-bank__desc">{{ bank.description }}</p>
          </div>
          <el-button
            size="small"
            :type="bank.linked ? 'success' : 'primary'"
            plain
            :loading="bankImportLoadingId === (bank.bankId || bank.id)"
            :disabled="bank.linked"
            @click="api.importQuestionBank(bank)"
          >
            {{ bank.linked ? '已关联' : '关联到资料夹' }}
          </el-button>
        </article>
        <div v-if="!bankImportLoading && !filteredBankImportBanks.length" class="kbp-bank__empty">
          没有找到可关联的题库。先去「题库搭建」创建或导入题库。
        </div>
      </div>
      <p class="kbp-bank__foot">
        关联后题库仍归题库模块管理；知识图谱只读取其中的知识点、题目关系和薄弱题信息，不会复制题干。
      </p>
    </div>
    <template #footer>
      <el-button @click="bankImportVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="bankKnowledgeVisible" :title="`题库知识点 · ${bankKnowledgeTitle}`" width="720px" append-to-body>
    <div v-loading="bankKnowledgeLoading" class="kbp-bank-knowledge">
      <p v-if="bankKnowledge.summary" class="kbp-bank-knowledge__summary">{{ bankKnowledge.summary }}</p>
      <section class="kbp-bank-knowledge__section">
        <h4>知识点</h4>
        <div v-if="bankKnowledge.entities?.length" class="kbp-bank-knowledge__chips">
          <button type="button" class="kbp-bank-knowledge__chip"
            :class="{ 'is-active': !selectedBankEntityName }" @click="selectedBankEntityName = ''">
            全部
          </button>
          <button v-for="entity in bankKnowledge.entities" :key="entity.name" type="button"
            class="kbp-bank-knowledge__chip" :class="{ 'is-active': selectedBankEntityName === entity.name }"
            @click="api.selectBankKnowledgeEntity(entity.name)">
            {{ entity.name }}<em v-if="entity.type"> · {{ entity.type }}</em>
            <span v-if="entity.questionIds?.length">{{ entity.questionIds.length }} 题</span>
          </button>
        </div>
        <p v-else class="kbp-bank-knowledge__empty">还没有抽取到知识点，关联后会在后台自动抽取。</p>
        <div v-if="bankKnowledge.relations?.length" class="kbp-bank-knowledge__relations">
          <span v-for="rel in bankKnowledge.relations" :key="`${rel.source}-${rel.target}-${rel.type}`">
            {{ rel.source }} → {{ rel.target }}<em>（{{ rel.type }}）</em>
          </span>
        </div>
      </section>
      <section class="kbp-bank-knowledge__section">
        <h4>
          对应题目
          <span v-if="selectedBankEntityName">「{{ selectedBankEntityName }}」{{ filteredBankKnowledgeQuestions.length }} 道</span>
          <span v-else>示例 {{ filteredBankKnowledgeQuestions.length }} 道</span>
        </h4>
        <div v-if="filteredBankKnowledgeQuestions.length" class="kbp-bank-knowledge__questions">
          <article v-for="question in filteredBankKnowledgeQuestions" :key="question.id"
            class="kbp-bank-knowledge__question" @click="api.openBankQuestion(question)">
            <b>#{{ question.id }}</b>
            <p>{{ question.text }}</p>
            <em v-if="question.analysis">解析：{{ question.analysis }}</em>
            <span class="kbp-bank-knowledge__jump">查看题目 →</span>
          </article>
        </div>
        <p v-else class="kbp-bank-knowledge__empty">
          {{ selectedBankEntityName ? '这个知识点暂未匹配到可展示的题目。' : '暂无题目样例。' }}
        </p>
      </section>
    </div>
    <template #footer>
      <el-button @click="bankKnowledgeVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="questionJumpVisible" title="题目详情" width="720px" append-to-body>
    <div v-loading="questionJumpLoading" class="kbp-question-jump">
      <template v-if="questionJumpData">
        <div class="kbp-question-jump__meta">
          <el-tag size="small" type="info" effect="plain">题目 #{{ questionJumpData.id }}</el-tag>
          <el-tag v-if="questionJumpData.questionType" size="small" effect="plain">题型 {{ questionJumpData.questionType }}</el-tag>
        </div>
        <LatexRenderer class="kbp-question-jump__stem" :content="questionJumpData.questionText || questionJumpData.content || ''" />
        <div v-if="questionJumpData.options" class="kbp-question-jump__options">
          <pre>{{ formatQuestionOptions(questionJumpData.options) }}</pre>
        </div>
        <div v-if="questionJumpData.answer" class="kbp-question-jump__answer">
          <b>答案</b>
          <LatexRenderer :content="questionJumpData.answer" />
        </div>
        <div v-if="questionJumpData.analysis" class="kbp-question-jump__answer">
          <b>解析</b>
          <LatexRenderer :content="questionJumpData.analysis" />
        </div>
      </template>
      <p v-else-if="!questionJumpLoading" class="kbp-bank-knowledge__empty">题目详情加载失败。</p>
    </div>
    <template #footer>
      <el-button @click="api.goBankPractice">去题库练习</el-button>
      <el-button @click="questionJumpVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'

const props = defineProps<{
  filteredBankImportBanks: any[]
  bankImportLoading: boolean
  bankImportLoadingId: number
  bankKnowledge: any
  bankKnowledgeLoading: boolean
  bankKnowledgeTitle: string
  filteredBankKnowledgeQuestions: any[]
  questionJumpData: any
  questionJumpLoading: boolean
  formatQuestionOptions: (value: any) => string
  api: {
    refreshBankImportList: () => void
    importQuestionBank: (bank: any) => void
    selectBankKnowledgeEntity: (name: string) => void
    openBankQuestion: (question: any) => void
    goBankPractice: () => void
  }
}>()

const bankImportVisible = defineModel<boolean>('bankImportVisible', { required: true })
const bankImportKeyword = defineModel<string>('bankImportKeyword', { required: true })
const bankKnowledgeVisible = defineModel<boolean>('bankKnowledgeVisible', { required: true })
const selectedBankEntityName = defineModel<string>('selectedBankEntityName', { required: true })
const questionJumpVisible = defineModel<boolean>('questionJumpVisible', { required: true })
</script>
