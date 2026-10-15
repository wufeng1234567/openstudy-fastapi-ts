<!-- src/components/MyQuestion/QuestionCard.vue -->
<template>
  <div class="question-card" @click="$emit('view-detail', item)">
    <!-- 卡片头部 -->
    <div class="card-header">
      <div class="question-type-badge" :class="getQuestionTypeClass(item.questionDetail?.questionType)">
        {{ getQuestionTypeText(item.questionDetail?.questionType) }}
      </div>

      <div class="header-actions">
        <!-- 标星按钮（仅收藏页面显示） -->
        <el-icon v-if="showStar && questionType === 'favorite'" :class="['star-icon', { 'starred': item.isStarred }]"
          @click.stop="handleToggleStar">
          <StarFilled v-if="item.isStarred" />
          <Star v-else />
        </el-icon>

        <!-- 收藏状态标签（仅收藏页面显示） -->
        <el-tag v-if="showFavoriteStatus && questionType === 'favorite' && item.favoriteStatus"
          :type="getFavoriteStatusType(item.favoriteStatus)" size="small" class="status-tag">
          {{ getFavoriteStatusText(item.favoriteStatus) }}
        </el-tag>

        <!-- 错题标签 -->
        <el-tag v-if="questionType === 'wrong'" type="danger" size="small" class="wrong-tag">
          错题
        </el-tag>

        <!-- 斩题标签 -->
        <el-tag v-if="questionType === 'marked'" :type="getMarkedTypeTagType(item.markedType)" size="small"
          class="marked-tag">
          {{ getMarkedTypeText(item.markedType) }}
        </el-tag>
      </div>
    </div>

    <!-- 题目内容 -->
    <div class="card-content">
      <div class="question-text" v-html="formatQuestionText(item.questionDetail?.questionText)"></div>

      <!-- 选择题选项预览 -->
      <div v-if="[1, 2].includes(item.questionDetail?.questionType) && item.questionDetail?.options"
        class="options-preview">
        <div v-for="(option, index) in getPreviewOptions(item.questionDetail.options)" :key="index"
          class="option-preview">
          <span class="option-letter">{{ getOptionLabel(index) }}.</span>
          <span class="option-text">{{ option }}</span>
        </div>
      </div>

      <!-- 填空题/简答题预览 -->
      <div v-else-if="[4, 5].includes(item.questionDetail?.questionType)" class="answer-preview">
        <div class="preview-label">答案预览：</div>
        <div class="preview-text">{{ truncateText(item.questionDetail?.answer, 60) }}</div>
      </div>

      <!-- 组合题预览（文章预览） -->
      <div v-else-if="[6, 7].includes(item.questionDetail?.questionType)" class="composite-preview">
        <div class="preview-label">文章预览：</div>
        <div class="article-preview" v-html="truncateHtml(item.questionDetail?.content, 120)"></div>
      </div>

      <!-- 掌握状态 -->
      <div class="mastery-status">
        <el-tag :type="item.isMastered ? 'success' : 'warning'" size="small">
          {{ item.isMastered ? '已掌握' : '未掌握' }}
        </el-tag>
      </div>

      <!-- 题库和难度信息（同一行） -->
      <div v-if="item.bankDetail || item.questionDetail?.difficulty" class="bank-difficulty-row">
        <!-- 题库信息 -->
        <div v-if="item.bankDetail" class="bank-info">
          <el-icon>
            <Collection />
          </el-icon>
          <el-tag size="small" class="bank-tag">{{ item.bankDetail.bankName }}</el-tag>
        </div>

        <!-- 题目难度 -->
        <el-tag v-if="item.questionDetail?.difficulty" size="small"
          :class="['difficulty-tag', `difficulty-${item.questionDetail.difficulty}`]">
          {{ getDifficultyText(item.questionDetail.difficulty) }}
        </el-tag>
      </div>

      <!-- 斩题备注 -->
      <div v-if="questionType === 'marked' && item.notes" class="marked-notes">
        <div class="notes-label">斩题备注：</div>
        <div class="notes-text">{{ truncateText(item.notes, 80) }}</div>
      </div>

      <!-- 时间信息 -->
      <div class="time-info">
        <el-icon>
          <Clock />
        </el-icon>
        <span>{{ getTimeLabel() }}：{{ formatTime(getTimeValue()) }}</span>
      </div>
    </div>

    <!-- 卡片底部操作按钮 -->
    <div v-if="showCollectActions" class="card-footer">
      <el-button type="primary" size="small" plain @click.stop="$emit('view-detail', item)" class="view-detail-btn">
        <el-icon>
          <View />
        </el-icon>
        查看详情
      </el-button>

      <el-button type="danger" size="small" plain @click.stop="handleUncollect" :loading="uncollectLoading"
        class="uncollect-btn">
        <el-icon>
          <Delete />
        </el-icon>
        {{ getUncollectText() }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Star, StarFilled, Collection, Clock, View, Delete
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import type { PropType } from 'vue'

const props = defineProps({
  item: {
    type: Object as PropType<any>,
    default: () => ({})
  },
  questionType: {
    type: String as PropType<string>,
    default: 'favorite'
  },
  showStar: Boolean,
  showFavoriteStatus: Boolean,
  showCollectActions: Boolean,
  showStudyStats: Boolean,
  uncollectLoading: Boolean
})

const emit = defineEmits(['view-detail', 'toggle-star', 'uncollect'])

const questionDetail = computed(() => props.item?.questionDetail || {})
const bankDetail = computed(() => props.item?.bankDetail)
const isStarred = computed(() => props.item?.isStarred)
const favoriteStatus = computed(() => props.item?.favoriteStatus)

const getMarkedTypeText = (markedType: any) => {
  const typeMap: Record<string, string> = {
    1: '错题',
    2: '难题',
    3: '重点',
    4: '易错',
    5: '技巧'
  }
  return typeMap[markedType] || '斩题'
}

const getMarkedTypeTagType = (markedType: any) => {
  const typeMap: Record<string, string> = {
    1: 'danger',
    2: 'warning',
    3: 'primary',
    4: 'info',
    5: 'success'
  }
  return typeMap[markedType] || ''
}

const getDifficultyText = (difficulty: any) => {
  const diffMap: Record<string, string> = {
    1: '简单',
    2: '中等',
    3: '困难',
    4: '极难'
  }
  return diffMap[difficulty] || '未知'
}

const getQuestionTypeText = (type: any) => {
  const typeMap: Record<string, string> = {
    1: '单选题',
    2: '多选题',
    3: '判断题',
    4: '填空题',
    5: '简答题',
    6: '组合题',
    7: '组合题'
  }
  return typeMap[type] || '未知题型'
}

const getQuestionTypeClass = (type: any) => {
  const classMap: Record<string, string> = {
    1: 'type-single',
    2: 'type-multiple',
    3: 'type-truefalse',
    4: 'type-fillblank',
    5: 'type-essay',
    6: 'type-composite',
    7: 'type-composite'
  }
  return classMap[type] || ''
}

const getFavoriteStatusText = (status: any) => {
  const statusMap: Record<string, string> = {
    1: '正常收藏',
    2: '已掌握',
    3: '待复习',
    0: '已取消'
  }
  return statusMap[status] || '未知'
}

const getFavoriteStatusType = (status: any) => {
  const typeMap: Record<string, string> = {
    1: 'primary',
    2: 'success',
    3: 'warning',
    0: 'info'
  }
  return typeMap[status] || 'info'
}

const formatQuestionText = (text: string) => {
  if (!text) return ''
  return text.replace(/\n/g, '<br>').substring(0, 200) + (text.length > 200 ? '...' : '')
}

const truncateText = (text: string, length: number = 50) => {
  if (!text) return ''
  return text.length > length ? text.substring(0, length) + '...' : text
}

const truncateHtml = (html: string, length: number = 120) => {
  if (!html) return ''
  const div = document.createElement('div')
  div.innerHTML = html
  const text = div.textContent || div.innerText || ''
  return text.length > length ? text.substring(0, length) + '...' : text
}

const getOptionLabel = (index: number) => {
  return String.fromCharCode(65 + index)
}

const getPreviewOptions = (options: any) => {
  if (!options) return []
  try {
    const opts = typeof options === 'string' ? JSON.parse(options) : options
    return Array.isArray(opts) ? opts.slice(0, 2) : []
  } catch (e) {
    return []
  }
}

const getTimeLabel = () => {
  const labelMap: Record<string, string> = {
    favorite: '收藏时间',
    wrong: '最近做错',
    marked: '标记时间'
  }
  return labelMap[props.questionType] || '时间'
}

/** 卡片右下角展示的时间
 *
 * 错题场景下后端返回的 createTime 其实是「题目创建时间」，拿它当错题时间会误导
 * （所有题看起来都是同一时刻），所以改用记录里的 lastErrorTime。
 */
const getTimeValue = () => {
  if (props.questionType === 'wrong') {
    return props.item.lastErrorTime || props.item.errorTime || props.item.createTime
  }
  return props.item.createTime
}

const getUncollectText = () => {
  const textMap: Record<string, string> = {
    favorite: '取消收藏',
    wrong: '移除错题',
    marked: '取消斩题'
  }
  return textMap[props.questionType] || '取消'
}

const formatTime = (time: string) => {
  if (!time) return ''
  try {
    const date = new Date(time)
    return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
  } catch (e) {
    return time
  }
}

const handleToggleStar = () => {
  if (props.questionType === 'wrong' || props.questionType === 'marked') {
    return
  }
  if (props.questionType === 'favorite') {
    emit('toggle-star', props.item)
  }
}

const handleUncollect = () => {
  emit('uncollect', props.item)
}
</script>

<style scoped>
.question-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 20px;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  height: 100%;
  display: flex;
  flex-direction: column;

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;

    .question-type-badge {
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 500;
      color: #fff;

      &.type-single {
        background: #409eff;
      }

      &.type-multiple {
        background: #67c23a;
      }

      &.type-truefalse {
        background: #e6a23c;
      }

      &.type-fillblank {
        background: #909399;
      }

      &.type-essay {
        background: #f56c6c;
      }

      &.type-reading {
        background: #8e44ad;
      }

      &.type-cloze {
        background: #3498db;
      }

      &.type-composite {
        background: #6b9ac9;
      }
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;

      .star-icon {
        font-size: 18px;
        color: #dcdfe6;
        cursor: pointer;
        transition: color 0.2s;

        &:hover {
          color: #e6a23c;
        }

        &.starred {
          color: #e6a23c;
        }
      }

      .wrong-tag {
        background-color: #fef0f0;
        border-color: #fde2e2;
        color: #f56c6c;
      }

      .marked-tag {
        font-weight: 500;
      }
    }
  }

  .card-content {
    flex: 1;

    .question-text {
      font-size: 14px;
      line-height: 1.5;
      color: #303133;
      margin-bottom: 16px;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;

      :deep(img) {
        max-width: 100% !important;
        max-height: 120px !important;
        width: auto !important;
        height: auto !important;
        object-fit: contain !important;
        border-radius: 4px;
        margin: 4px 0;
        vertical-align: middle;
      }
    }

    .mastery-status {
      margin-bottom: 12px;
    }

    .bank-difficulty-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      flex-wrap: wrap;

      .bank-info {
        display: flex;
        align-items: center;
        gap: 4px;

        .el-icon {
          font-size: 14px;
          color: #909399;
        }

        .bank-tag {
          background: #ecf5ff;
          border-color: #d9ecff;
          color: #409eff;
          border-radius: 4px;
          font-size: 12px;
        }
      }

      .difficulty-tag {
        border-radius: 4px;
        font-size: 12px;
        border-width: 1px;
        border-style: solid;

        &.difficulty-1 {
          background: #f0f9eb;
          border-color: #e1f3d8;
          color: #67c23a;
        }

        &.difficulty-2 {
          background: #ecf5ff;
          border-color: #d9ecff;
          color: #409eff;
        }

        &.difficulty-3 {
          background: #fdf6ec;
          border-color: #faecd8;
          color: #e6a23c;
        }

        &.difficulty-4 {
          background: #fef0f0;
          border-color: #fde2e2;
          color: #f56c6c;
        }
      }
    }

    .options-preview {
      margin-bottom: 12px;

      .option-preview {
        display: flex;
        align-items: center;
        font-size: 13px;
        color: #606266;
        margin-bottom: 4px;

        .option-letter {
          font-weight: 500;
          margin-right: 4px;
        }

        :deep(img) {
          max-width: 80px !important;
          max-height: 40px !important;
          object-fit: contain !important;
          border-radius: 2px;
          vertical-align: middle;
        }
      }
    }

    .answer-preview {
      margin-bottom: 16px;

      .preview-label {
        font-size: 12px;
        color: #909399;
        margin-bottom: 4px;
        font-weight: 500;
      }

      .preview-text {
        font-size: 13px;
        color: #606266;
        line-height: 1.4;
        font-style: italic;
        background: #f8f9fa;
        padding: 6px 10px;
        border-radius: 4px;
        border-left: 3px solid #e6a23c;
        overflow: hidden;

        :deep(img) {
          max-width: 100% !important;
          max-height: 60px !important;
          object-fit: contain !important;
          border-radius: 2px;
          vertical-align: middle;
        }
      }
    }

    .composite-preview {
      margin-bottom: 16px;

      .preview-label {
        font-size: 12px;
        color: #909399;
        margin-bottom: 8px;
        font-weight: 500;
      }

      .article-preview {
        font-size: 13px;
        color: #606266;
        line-height: 1.6;
        background: #f8f9fa;
        padding: 8px 10px;
        border-radius: 4px;
        border-left: 3px solid #6b9ac9;
        overflow: hidden;

        :deep(img) {
          max-width: 100% !important;
          max-height: 80px !important;
          object-fit: contain !important;
          border-radius: 4px;
          margin: 4px 0;
          vertical-align: middle;
        }
      }
    }

    .marked-notes {
      margin-bottom: 16px;
      padding: 8px 12px;
      background: #f0f9ff;
      border-radius: 6px;
      border-left: 3px solid #409eff;

      .notes-label {
        font-size: 12px;
        color: #409eff;
        font-weight: 500;
        margin-bottom: 4px;
      }

      .notes-text {
        font-size: 13px;
        color: #606266;
        line-height: 1.4;
      }
    }

    .time-info {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: #909399;
      margin-bottom: 16px;

      .el-icon {
        font-size: 14px;
      }
    }
  }

  .card-footer {
    display: flex;
    gap: 8px;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #e4e7ed;

    :deep(.el-button) {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      font-size: 12px;
    }

    .view-detail-btn {
      border-color: #409eff;
      color: #409eff;

      &:hover {
        background: #ecf5ff;
        border-color: #79bbff;
        color: #79bbff;
      }
    }

    .uncollect-btn {
      border-color: #f56c6c;
      color: #f56c6c;

      &:hover {
        background: #fef0f0;
        border-color: #f89898;
        color: #f89898;
      }
    }
  }
}

.marked-tag[type="danger"] {
  background: linear-gradient(135deg, #fef0f0 0%, #fde2e2 100%);
  border-color: #fbc4c4;
  color: #f56c6c;
}

.marked-tag[type="warning"] {
  background: linear-gradient(135deg, #fdf6ec 0%, #faecd8 100%);
  border-color: #f8d4a3;
  color: #e6a23c;
}

.marked-tag[type="primary"] {
  background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%);
  border-color: #a0cfff;
  color: #409eff;
}

.marked-tag[type="info"] {
  background: linear-gradient(135deg, #f4f4f5 0%, #e9e9eb 100%);
  border-color: #c8c9cc;
  color: #909399;
}

.marked-tag[type="success"] {
  background: linear-gradient(135deg, #f0f9eb 0%, #e1f3d8 100%);
  border-color: #b3e19d;
  color: #67c23a;
}

[type="success"] {
  background: linear-gradient(135deg, #f0f9eb 0%, #e1f3d8 100%);
  border-color: #b3e19d;
  color: #67c23a;
}

[type="info"] {
  background: linear-gradient(135deg, #f4f4f5 0%, #e9e9eb 100%);
  border-color: #c8c9cc;
  color: #909399;
}

[type="warning"] {
  background: linear-gradient(135deg, #fdf6ec 0%, #faecd8 100%);
  border-color: #f8d4a3;
  color: #e6a23c;
}

[type="danger"] {
  background: linear-gradient(135deg, #fef0f0 0%, #fde2e2 100%);
  border-color: #fbc4c4;
  color: #f56c6c;
}
</style>