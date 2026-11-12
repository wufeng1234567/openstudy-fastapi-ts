<template>
  <el-dialog v-model="organizeReportVisible" title="整理记录" width="760px" append-to-body>
    <div class="kbp-report" v-loading="organizePlansLoading">
      <div class="kbp-report__stats">
        <div><b>{{ organizePlans.length }}</b><span>整理次数</span></div>
        <div><b>{{ api.organizePlanCount('applied') }}</b><span>已应用</span></div>
        <div><b>{{ api.organizePlanCount('ready') }}</b><span>待确认</span></div>
        <div><b>{{ api.organizePlanCount('failed') }}</b><span>失败</span></div>
      </div>
      <div v-if="organizePlans.length" class="kbp-report__list">
        <div v-for="plan in organizePlans" :key="plan.planId" class="kbp-report__row">
          <div class="kbp-report__main">
            <span class="kbp-report__name" :title="plan.docName">{{ plan.docName }}</span>
            <span class="kbp-report__meta">
              {{ plan.createTime }} · {{ plan.mode === 'deep' ? '智能整理' : '旧版整理' }}
            </span>
          </div>
          <span class="kbp-report__changes">{{ plan.changed }} 处变更</span>
          <el-tag :type="api.planStatusType(plan.status)" size="small" effect="plain">
            {{ api.planStatusText(plan.status) }}
          </el-tag>
          <el-button v-if="!plan.legacy" text size="small" @click="api.openOrganizePlan(plan)">查看变更</el-button>
          <el-button v-else text size="small" @click="api.openOrganizePlan(plan)">查看历史</el-button>
          <el-button text size="small" type="danger" @click.stop="api.deleteOrganizeRecord(plan)">删除</el-button>
        </div>
      </div>
      <div v-else class="kbp-anatomy__empty">还没有整理记录。</div>
    </div>
  </el-dialog>

  <el-dialog v-model="editorVisible" :title="`编辑资料 · ${editorDoc?.fileName || ''}`" width="1040px" top="5vh" append-to-body>
    <div class="kbp-editor" v-loading="editorLoading">
      <div class="kbp-editor__bar">
        <el-tag type="info" effect="plain">富文本 · Word / Markdown 兼容</el-tag>
        <span>支持加粗、标题、列表、表格和插入图片；保存后重新解析并建立检索索引。</span>
        <el-button text size="small" @click="versionsVisible = true">版本对照</el-button>
        <el-button text size="small" @click="editorPreview = !editorPreview">
          {{ editorPreview ? '继续编辑' : '预览排版' }}
        </el-button>
      </div>
      <TiptapEditor v-if="!editorPreview" v-model="editorHtml" class="kbp-editor__rich"
        placeholder="在这里编辑正文，支持富文本、公式和插入图片。" />
      <div v-else class="kbp-editor__preview">
        <LatexRenderer :content="editorMarkdown" />
      </div>
    </div>
    <template #footer>
      <div class="kbp-editor__footer">
        <div>
          <el-button @click="api.exportCurrent('markdown')">导出 Markdown</el-button>
          <el-button @click="api.exportCurrent('docx')">导出 Word</el-button>
        </div>
        <div>
          <el-button @click="editorVisible = false">取消</el-button>
          <el-button type="primary" :loading="editorSaving" @click="api.saveEditor">保存并重新解析</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import TiptapEditor from '@/components/TiptapEditor/index.vue'

defineProps<{
  organizePlans: any[]
  organizePlansLoading: boolean
  editorLoading: boolean
  editorDoc: any
  editorSaving: boolean
  editorMarkdown: string
  api: {
    organizePlanCount: (status: string) => number
    planStatusType: (status: string) => string
    planStatusText: (status: string) => string
    openOrganizePlan: (plan: any) => void
    deleteOrganizeRecord: (plan: any) => void
    exportCurrent: (format: 'markdown' | 'docx') => void
    saveEditor: () => void
  }
}>()

const organizeReportVisible = defineModel<boolean>('organizeReportVisible', { required: true })
const editorVisible = defineModel<boolean>('editorVisible', { required: true })
const editorHtml = defineModel<string>('editorHtml', { required: true })
const editorPreview = defineModel<boolean>('editorPreview', { required: true })
const versionsVisible = defineModel<boolean>('versionsVisible', { required: true })
</script>
