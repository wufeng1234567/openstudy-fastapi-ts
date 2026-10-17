<template>
  <div class="question-builder">
    <!-- 题目列表（占满宽度） -->
    <div class="question-panel" v-loading="loading" element-loading-text="加载中...">
      <div class="panel-header" ref="panelHeaderRef">
        <!-- 左侧：一键恢复（题型库左侧） -->
        <el-button class="btn-restore" size="small" @click="handleRestore">
          <el-icon style="margin-right: 4px"><RefreshLeft /></el-icon>
          一键恢复
        </el-button>
        <!-- 题型库按钮（点击弹出悬浮层，不挤压布局） -->
        <div class="type-popover-trigger" ref="typePopoverTriggerRef">
          <el-button class="btn-type-lib" size="small" :class="{ 'is-filtering': !isTypeSelected('all') }"
            @click="toggleTypePopover($event)">
            <el-icon style="margin-right: 4px"><Grid /></el-icon>
            题型库
            <el-badge v-if="!isTypeSelected('all')" :value="activeTypeFilters.size" class="trigger-badge"
              type="primary" />
          </el-button>
          <!-- 题型库悬浮层：挂在按钮容器内，相对按钮定位（容器 position: relative） -->
          <transition name="type-popover">
            <div v-if="typePopoverVisible" class="type-popover" ref="typePopoverRef">
              <div class="popover-header">
                <span class="popover-title">题型库</span>
                <el-tag v-if="!isTypeSelected('all')" size="small" type="info" closable @close="setTypeFilter('all')">
                  已选 {{ activeTypeFilters.size }} 项
                </el-tag>
                <el-icon class="popover-close" @click="typePopoverVisible = false"><Close /></el-icon>
              </div>
              <draggable v-model="questionTypes" :group="{ name: 'types', pull: 'clone', put: false }" :sort="false"
                :clone="cloneQuestion" class="type-list" item-key="type" @start="onTypeDragStart">
                <template #item="{ element }">
                  <div class="type-item" :class="{ 'type-filtered': isTypeSelected(element.type) }"
                    :data-type="element.type" @mousedown="(e) => onTypeMouseDown(e, element)"
                    @mouseup="(e) => onTypeMouseUp(e, element)" @dragstart="(e) => onTypeDragStart(e, element)">
                    <el-icon>
                      <component :is="element.icon" />
                    </el-icon>
                    <span>{{ element.name }}</span>
                    <span class="type-count">{{ getTypeCount(element.type) }}</span>
                  </div>
                </template>
              </draggable>
              <div class="type-hint">点击多选筛选 · 拖拽添加</div>
            </div>
          </transition>
        </div>

        <!-- 中间：标题（空间不足时只显示「题目列表」，避免挤压右侧操作区） -->
        <span class="panel-title" ref="panelTitleRef"><span class="title-text">题目列表</span><span v-if="showTitleCount">（{{ allFilteredQuestions.length }}/{{ questions.length }} 题）</span></span>
        <!-- 隐藏测量元素：始终保存完整标题，用于判断能否完整显示（不参与布局） -->
        <span class="title-measure" ref="titleMeasureRef" aria-hidden="true">题目列表（{{ allFilteredQuestions.length }}/{{ questions.length }} 题）</span>
        <!-- 右侧：搜索 + AI 生成 -->
        <div class="panel-actions">
          <el-input v-model="searchKeyword" placeholder="搜索题目" clearable size="small" style="width: 150px"
            @input="filterQuestions">
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button class="btn-ai-generate" size="small" @click="openAiDialog">
            <el-icon style="margin-right: 4px"><MagicStick /></el-icon>
            AI 生成
          </el-button>
        </div>
      </div>

      <draggable v-model="filteredQuestions" group="questions" class="question-list" item-key="id" @end="onDragEnd">
        <template #item="{ element, index }">
          <div class="question-item" :class="{ active: currentId === element.id }" @click="selectQuestion(element.id)">
            <div class="question-header">
              <span class="question-index">{{ (currentPage - 1) * pageSize + index + 1 }}</span>
              <span class="question-type" :class="'type-' + element.type">{{ getTypeName(element.type) }}</span>
              <el-icon class="drag-handle">
                <Rank />
              </el-icon>
            </div>
            <div class="question-preview">
              {{ getPlainText(element.title) || '未命名题目' }}
            </div>
            <div class="question-actions">
              <el-button type="danger" text size="small" @click.stop="removeQuestion(element.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </template>
      </draggable>
      <div v-if="filteredQuestions.length === 0" class="empty-tip">
        <!--
          ⚠️ 这里原来写的是 `activeTypeFilter`（单数），而脚本里只有 `activeTypeFilters`（复数）
          —— Vue 每次渲染都会警告 "was accessed during render but is not defined"，
          且三元永远走 else 分支（永远显示"该类型暂无题目"）。
          判据改用现成的 `isTypeSelected('all')`。
        -->
        {{ isTypeSelected('all') ? '暂无题目，从左侧拖拽题型或使用 AI 生成' : '该类型暂无题目' }}
      </div>
      <!-- 分页 -->
      <div class="question-pagination">
        <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :total="allFilteredQuestions.length"
          :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" small @size-change="handleSizeChange"
          @current-change="handlePageChange" />
      </div>
    </div>

    <!-- 右侧：题目编辑 -->
    <div class="edit-panel">
      <div class="panel-title">
        <span>题目编辑</span>
        <el-button size="small" @click="openFullEditor">
          <el-icon>
            <FullScreen />
          </el-icon> 全屏编辑
        </el-button>
      </div>
      <div v-if="currentQuestion" class="edit-form">
        <el-form label-position="top">
          <el-form-item label="题型">
            <el-select v-model="currentQuestion.type" @change="onTypeChange" style="width: 200px">
              <el-option label="单选题" value="single" />
              <el-option label="多选题" value="multiple" />
              <el-option label="判断题" value="judge" />
              <el-option label="填空题" value="fill" />
              <el-option label="简答题" value="essay" />
              <el-option label="组合题（含子题）" value="composite" />
            </el-select>
          </el-form-item>

          <el-form-item label="题干">
            <div class="question-tiptap-wrapper">
              <TiptapEditor v-model="currentQuestion.title" placeholder="请输入题目内容，支持图片上传"
                @preview-image="openImageViewer" />
            </div>
          </el-form-item>

          <!-- 普通题型的选项编辑 -->
          <template v-if="['single', 'multiple', 'judge'].includes(currentQuestion.type)">
            <el-form-item v-if="currentQuestion.type !== 'judge'" label="选项列表">
              <div class="options-visual-editor">
                <div v-for="(opt, idx) in currentQuestion.options" :key="idx" class="option-item">
                  <span class="option-letter">{{ String.fromCharCode(65 + idx) }}.</span>
                  <el-input v-model="currentQuestion.options[idx]" placeholder="请输入选项内容" size="small" style="flex: 1"
                    @input="onOptionChange" />
                  <el-button type="danger" text size="small" @click="removeOption(idx)"
                    :disabled="currentQuestion.options.length <= 2">
                    <el-icon>
                      <Delete />
                    </el-icon>
                  </el-button>
                </div>
                <el-button v-if="currentQuestion.options.length < 6" type="primary" text size="small"
                  @click="addOption">
                  <el-icon>
                    <Plus />
                  </el-icon> 添加选项 (最多6个)
                </el-button>
                <div class="json-hint" style="margin-top: 8px">
                  <el-button text size="small" @click="showOptionsJsonDialog = true">高级编辑 (JSON)</el-button>
                </div>
              </div>
            </el-form-item>

            <!-- JSON 高级编辑对话框 -->
            <el-dialog v-model="showOptionsJsonDialog" title="选项 JSON 编辑" width="500px" append-to-body>
              <el-input v-model="currentQuestion.optionsJson" type="textarea" :rows="8"
                placeholder='["选项A", "选项B", "选项C"]' />
              <div class="json-hint">修改后点击确定，将覆盖当前选项列表</div>
              <template #footer>
                <el-button @click="showOptionsJsonDialog = false">取消</el-button>
                <el-button type="primary" @click="applyOptionsJson">确定</el-button>
              </template>
            </el-dialog>

            <!-- 正确答案 -->
            <el-form-item label="正确答案">
              <el-radio-group v-if="currentQuestion.type === 'single'" v-model="currentQuestion.answer">
                <el-radio v-for="(opt, idx) in currentQuestion.options" :key="idx" :label="idx">
                  {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                </el-radio>
              </el-radio-group>
              <el-checkbox-group v-else-if="currentQuestion.type === 'multiple'" v-model="currentQuestion.answer">
                <el-checkbox v-for="(opt, idx) in currentQuestion.options" :key="idx" :label="idx">
                  {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                </el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-else-if="currentQuestion.type === 'judge'" v-model="currentQuestion.answer">
                <el-radio label="true">正确</el-radio>
                <el-radio label="false">错误</el-radio>
              </el-radio-group>
            </el-form-item>
          </template>

          <!-- 填空 / 简答 -->
          <template v-if="currentQuestion.type === 'fill' || currentQuestion.type === 'essay'">
            <el-form-item label="正确答案">
              <el-input v-model="currentQuestion.answer" placeholder="请输入正确答案" />
            </el-form-item>
          </template>

          <!-- 组合题：材料 + 子题管理 -->
          <template v-if="currentQuestion.type === 'composite'">
            <el-form-item label="材料/文章内容">
              <div class="question-tiptap-wrapper composite-tiptap">
                <TiptapEditor v-model="currentQuestion.content" placeholder="请输入文章或材料内容。可使用 ___1___、___2___ 等占位符"
                  @preview-image="openImageViewer" />
              </div>
              <div class="json-hint">提示：占位符 ___数字___ 会在练习时自动转为输入框</div>
            </el-form-item>

            <el-form-item label="子题管理">
              <div class="sub-questions-container">
                <div class="sub-toolbar">
                  <el-select v-model="selectedSubType" placeholder="选择题型" size="small" style="width: 120px" clearable>
                    <el-option label="单选题" value="single" />
                    <el-option label="多选题" value="multiple" />
                    <el-option label="判断题" value="judge" />
                    <el-option label="填空题" value="fill" />
                    <el-option label="简答题" value="essay" />
                  </el-select>
                  <el-button type="primary" size="small" @click="addSubQuestionBySelectedType">添加子题</el-button>
                  <span class="sub-hint">也可从左侧题型库拖拽到下方区域添加子题</span>
                </div>
                <draggable v-model="currentQuestion.subQuestions" group="subQuestions" class="sub-list" item-key="id"
                  @end="onSubDragEnd" @add="onSubDragAdd">
                  <template #item="{ element: sub, index }">
                    <div class="sub-question-card">
                      <div class="sub-header">
                        <el-icon class="drag-handle">
                          <Rank />
                        </el-icon>
                        <span class="sub-index">子题 {{ index + 1 }}</span>
                        <el-select v-model="sub.type" size="small" style="width: 100px" @change="onSubTypeChange(sub)">
                          <el-option label="单选" value="single" />
                          <el-option label="多选" value="multiple" />
                          <el-option label="判断" value="judge" />
                          <el-option label="填空" value="fill" />
                          <el-option label="简答" value="essay" />
                        </el-select>
                        <el-button type="danger" size="small" text @click="removeSubQuestion(index)">
                          <el-icon>
                            <Delete />
                          </el-icon>
                        </el-button>
                      </div>
                      <div class="sub-body">
                        <div class="sub-tiptap-wrapper">
                          <TiptapEditor v-model="sub.question" placeholder="子题题干，支持图片上传"
                            @preview-image="openImageViewer" />
                        </div>
                        <div v-if="['single', 'multiple'].includes(sub.type)" class="sub-options">
                          <div class="sub-options-label">选项（JSON数组）：</div>
                          <el-input v-model="sub.optionsJson" type="textarea" :rows="2"
                            placeholder='["选项A", "选项B", "选项C"]' size="small" @blur="parseSubOptions(sub)" />
                          <div class="json-hint">格式示例：["选项A","选项B"]</div>
                        </div>
                        <div class="sub-answer">
                          <div class="sub-answer-label">正确答案：</div>
                          <div v-if="sub.type === 'single'" class="sub-answer-control">
                            <el-radio-group v-model="sub.answer" size="small">
                              <el-radio v-for="(opt, idx) in sub.options" :key="idx" :label="idx">
                                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                              </el-radio>
                            </el-radio-group>
                          </div>
                          <div v-else-if="sub.type === 'multiple'" class="sub-answer-control">
                            <el-checkbox-group v-model="sub.answer" size="small">
                              <el-checkbox v-for="(opt, idx) in sub.options" :key="idx" :label="idx">
                                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                              </el-checkbox>
                            </el-checkbox-group>
                          </div>
                          <div v-else-if="sub.type === 'judge'" class="sub-answer-control">
                            <el-radio-group v-model="sub.answer" size="small">
                              <el-radio label="true">正确</el-radio>
                              <el-radio label="false">错误</el-radio>
                            </el-radio-group>
                          </div>
                          <div v-else class="sub-answer-control">
                            <el-input v-model="sub.answer" placeholder="请输入答案" size="small" />
                          </div>
                        </div>
                        <div class="sub-score-area">
                          <span class="score-label">分值：</span>
                          <el-input-number v-model="sub.score" :min="0" :max="100" size="small"
                            controls-position="right" style="width: 110px" />
                          <span class="score-unit">分</span>
                        </div>
                      </div>
                    </div>
                  </template>
                </draggable>
                <div v-if="!currentQuestion.subQuestions.length" class="empty-sub">
                  暂无子题，请从上方下拉框选择题型添加，或从左侧拖拽题型到此区域
                </div>
              </div>
            </el-form-item>
          </template>

          <el-form-item label="答案解析">
            <el-input v-model="currentQuestion.analysis" type="textarea" :rows="2" placeholder="请输入答案解析" />
          </el-form-item>

          <el-form-item label="分值">
            <el-input-number v-model="currentQuestion.score" :min="1" :max="100" size="small" />
          </el-form-item>
        </el-form>
      </div>
      <div v-else class="empty-tip">点击左侧题目进行编辑</div>
    </div>

    <el-dialog v-model="aiDialogVisible" :title="aiForm.questionType === 'composite' ? 'AI 智能生成组合题' : 'AI 智能出题'"
      width="850px" :close-on-click-modal="false" :close-on-press-escape="!aiGenerating" :show-close="!aiGenerating"
      @close="onAiDialogClose" class="ai-generate-dialog ai-fixed-dialog">
      <!-- 上下文信息栏 -->
      <div class="context-bar" v-if="currentBankId">
        <div class="context-info">
          <el-icon>
            <InfoFilled />
          </el-icon>
          <span class="context-bank-name">{{ bankContextInfo.bankName || '加载中...' }}</span>
          <el-tag size="small" type="info">{{ bankContextInfo.totalQuestions || 0 }} 道题</el-tag>
          <el-tag size="small" :type="historyCount > 0 ? 'success' : 'info'">
            {{ historyCount }} 条历史
          </el-tag>
        </div>
        <div class="context-actions">
          <el-button text size="small" @click="handleClearContext" :loading="clearingContext">
            <el-icon>
              <Delete />
            </el-icon>
            清空上下文
          </el-button>
        </div>
      </div>
      <!-- 内部滚动区域：包含所有配置项 + 流式输出 -->
      <div class="dialog-scroll-area">
        <el-form label-position="top" :model="aiForm" :rules="aiRules" ref="aiFormRef">
          <!-- 题型选择 -->
          <el-form-item label="题型" prop="questionType">
            <el-select v-model="aiForm.questionType" style="width: 100%" @change="onAiTypeChange">
              <el-option label="单选题" value="single" />
              <el-option label="多选题" value="multiple" />
              <el-option label="判断题" value="judge" />
              <el-option label="填空题" value="fill" />
              <el-option label="简答题" value="essay" />
              <el-option label="组合题（大题套小题）" value="composite" />
            </el-select>
          </el-form-item>

          <!-- 历史记录快捷选择 -->
          <div v-if="promptHistory.length > 0" class="prompt-history">
            <div class="history-header">
              <span class="history-title">
                <el-icon>
                  <Clock />
                </el-icon>
                最近使用
              </span>
              <el-button text size="small" @click="clearPromptHistory">清空</el-button>
            </div>
            <div class="history-list">
              <div v-for="(item, index) in promptHistory" :key="index" class="history-tag-wrapper">
                <el-tag class="history-tag" @click.native="applyHistoryPrompt(item)">
                  {{ truncateText(item.knowledgePoint || item.compositeRequirement, 30) }}
                </el-tag>
                <span class="history-tag-delete" @click.stop="deleteHistoryItem(index)">
                  <el-icon>
                    <Close />
                  </el-icon>
                </span>
              </div>
            </div>
          </div>

          <!-- 普通题型配置 -->
          <template v-if="aiForm.questionType !== 'composite'">
            <el-form-item label="知识点" prop="knowledgePoint">
              <el-input v-model="aiForm.knowledgePoint" placeholder="例如：Java 多态、三角函数、英语时态" :disabled="aiGenerating"
                maxlength="200" show-word-limit />
            </el-form-item>
            <el-form-item label="生成数量" prop="count">
              <el-input-number v-model="aiForm.count" :min="1" :max="10" style="width: 100%" :disabled="aiGenerating" />
            </el-form-item>
          </template>

          <!-- 组合题配置 -->
          <template v-else>
            <el-alert type="info" :closable="false" style="margin-bottom: 16px">
              <template #title>
                <span style="font-weight: 500">组合题说明</span>
              </template>
              <p style="margin: 8px 0; line-height: 1.6; color: var(--os-text-2);">
                组合题适用于：阅读理解、完形填空、案例分析、实验大题、材料分析题等。<br />
                请详细描述您需要的大题材料和子题要求。
              </p>
            </el-alert>
            <el-form-item label="材料/题干要求" prop="compositeRequirement">
              <el-input v-model="aiForm.compositeRequirement" type="textarea" :rows="5"
                placeholder="例如：&#10;1. 一篇关于人工智能发展史的科普文章，约300字，包含3道单选题和2道判断题&#10;2. 一道化学实验大题，包含实验背景、步骤描述，下设3个填空和2个简答&#10;3. 一段Java代码，要求分析输出结果，包含3道选择题"
                :disabled="aiGenerating" maxlength="200" show-word-limit />
            </el-form-item>
            <el-form-item label="参考字数">
              <el-input-number v-model="aiForm.wordCount" :min="50" :max="3000" step="50" style="width: 100%"
                :disabled="aiGenerating" />
              <div class="form-hint">AI 会尽量接近此字数</div>
            </el-form-item>
            <el-form-item label="子题数量">
              <el-input-number v-model="aiForm.subCount" :min="2" :max="15" style="width: 100%"
                :disabled="aiGenerating" />
            </el-form-item>
          </template>

          <el-form-item label="AI 模型">
            <div class="ai-model-row">
              <!-- 模型选择器（历史记忆按 scene=question-builder 单独保存） -->
              <AiModelSelector v-model="aiForm.model" scene="question-builder" width="200px" @select="onModelSelect" :disabled="aiGenerating" />
              <el-button @click="openAiModelManager" :disabled="aiGenerating" size="small">
                <el-icon>
                  <Setting />
                </el-icon>
                管理模型
              </el-button>
              <AiThinkingToggle v-model="deepThink" size="small" :disabled="aiGenerating" />
            </div>
          </el-form-item>

          <!-- AI 生成结果展示区域 -->
          <div v-if="aiGenerating || parsedQuestionsForPreview" class="stream-container-new">
            <!-- 头部工具栏 -->
            <div class="stream-toolbar">
              <div class="stream-status-left">
                <span v-if="aiGenerating" class="status-dot generating"></span>
                <span v-else class="status-dot completed"></span>
                <span class="status-text">
                  {{ aiGenerating ? 'AI 正在生成...' : '生成完成' }}
                </span>
              </div>
              <div class="stream-actions-right">
                <!-- 复制原始 JSON -->
                <el-button text size="small" @click="copyRawJson" v-if="rawJsonContent">
                  <el-icon>
                    <DocumentCopy />
                  </el-icon>
                  复制 JSON
                </el-button>
                <!-- 视图切换按钮 -->
                <el-button-group v-if="!aiGenerating && parsedQuestionsForPreview" size="small"
                  style="margin-left: 8px;">
                  <el-button :type="viewMode === 'pretty' ? 'primary' : ''" size="small" @click="viewMode = 'pretty'">
                    美化
                  </el-button>
                  <el-button :type="viewMode === 'raw' ? 'primary' : ''" size="small" @click="viewMode = 'raw'">
                    原始
                  </el-button>
                </el-button-group>
              </div>
            </div>

            <!-- 内容展示区 -->
            <div class="stream-body-new" ref="streamBoxRef">
              <!-- 生成中：有内容时显示流式 JSON，无内容时显示 loading -->
              <pre v-if="aiGenerating && rawJsonContent" class="stream-content streaming">{{ rawJsonContent }}</pre>
              <div v-else-if="aiGenerating" class="generating-tip">
                <el-icon class="is-loading">
                  <Loading />
                </el-icon>
                <span>AI 正在生成题目，请稍候...</span>
              </div>

              <!-- 原始 JSON 视图 -->
              <pre v-else-if="viewMode === 'raw'" class="stream-content">{{ rawJsonContent || '暂无内容' }}</pre>

              <!-- 美化预览视图（可编辑） -->
              <div v-else-if="viewMode === 'pretty' && parsedQuestionsForPreview" class="pretty-preview">
                <!-- 组合题预览 -->
                <div v-if="isCompositePreview" class="composite-preview">
                  <div class="composite-passage">
                    <div class="passage-title">
                      <span>材料内容</span>
                      <el-button text size="small" @click="editPassage">
                        <el-icon>
                          <EditPen />
                        </el-icon>
                      </el-button>
                    </div>
                    <el-input v-if="editingPassage" v-model="editablePreviewData.passage" type="textarea" :rows="4"
                      @blur="editingPassage = false; updatePreviewData()"
                      @keyup.enter.ctrl="editingPassage = false; updatePreviewData()" />
                    <div v-else class="passage-content" @dblclick="editingPassage = true">
                      {{ editablePreviewData?.passage || parsedQuestionsForPreview.passage }}
                    </div>
                  </div>

                  <div class="sub-questions-list">
                    <div class="sub-title">
                      <span>子题列表（共 {{ editablePreviewData?.questions?.length ||
                        parsedQuestionsForPreview.questions?.length || 0 }} 题）</span>
                    </div>
                    <div
                      v-for="(sub, subIdx) in (editablePreviewData?.questions || parsedQuestionsForPreview.questions)"
                      :key="subIdx" class="sub-question-card">
                      <!-- 子题头部 -->
                      <div class="sub-header">
                        <span class="sub-index">{{ subIdx + 1 }}</span>
                        <el-tag size="small" :type="getSubTypeTagType(sub.type)">{{ getSubTypeName(sub.type) }}</el-tag>
                        <span class="sub-score">
                          <el-input-number v-model="sub.score" :min="0" :max="100" size="small"
                            controls-position="right" style="width: 80px" @change="updatePreviewData" /> 分
                        </span>
                      </div>

                      <!-- 子题题干（可编辑） -->
                      <div class="sub-question">
                        <el-input v-model="sub.question" type="textarea" :rows="2" placeholder="子题题干"
                          @input="updatePreviewData" />
                      </div>

                      <!-- 选择题选项 -->
                      <div v-if="['single', 'multiple'].includes(sub.type)" class="sub-options">
                        <div v-for="(opt, optIdx) in sub.options" :key="optIdx" class="preview-option">
                          <span class="option-letter">{{ String.fromCharCode(65 + optIdx) }}.</span>
                          <el-input v-model="sub.options[optIdx]" size="small" @input="updatePreviewData" />
                        </div>
                      </div>

                      <!-- 答案 -->
                      <div class="sub-answer">
                        <span class="answer-label">答案：</span>
                        <el-input v-if="sub.type === 'fill' || sub.type === 'essay'" v-model="sub.correctAnswer"
                          size="small" @input="updatePreviewData" />
                        <el-select v-else-if="sub.type === 'single'" v-model="sub.correctAnswer" size="small"
                          @change="updatePreviewData">
                          <el-option v-for="(opt, optIdx) in sub.options" :key="optIdx"
                            :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                        </el-select>
                        <el-select v-else-if="sub.type === 'multiple'" v-model="sub.correctAnswer" multiple size="small"
                          @change="updatePreviewData">
                          <el-option v-for="(opt, optIdx) in sub.options" :key="optIdx"
                            :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                        </el-select>
                        <el-switch v-else-if="sub.type === 'judge'" v-model="sub.correctAnswer" active-text="正确"
                          inactive-text="错误" @change="updatePreviewData" />
                      </div>

                      <!-- 解析 -->
                      <div class="sub-analysis">
                        <span class="analysis-label">解析：</span>
                        <el-input v-model="sub.analysis" type="textarea" :rows="2" size="small"
                          @input="updatePreviewData" />
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 普通题型预览 -->
                <div v-else class="questions-list">
                  <div v-for="(q, idx) in (editablePreviewData || parsedQuestionsForPreview)" :key="idx"
                    class="preview-question-card">
                    <div class="preview-header">
                      <span class="preview-index">{{ idx + 1 }}</span>
                      <el-tag size="small" type="primary">{{ getTypeName(aiForm.questionType) }}</el-tag>
                      <span class="preview-score">
                        <el-input-number v-model="q.score" :min="0" :max="100" size="small" style="width: 80px"
                          @change="updatePreviewData" /> 分
                      </span>
                    </div>

                    <div class="preview-body">
                      <!-- 题干 -->
                      <div class="preview-question">
                        <el-input v-model="q.question" type="textarea" :rows="2" @input="updatePreviewData" />
                      </div>

                      <!-- 选择题选项 -->
                      <div
                        v-if="['single', 'multiple', 'judge'].includes(aiForm.questionType) && aiForm.questionType !== 'judge'"
                        class="preview-options">
                        <div v-for="(opt, optIdx) in q.options" :key="optIdx" class="preview-option">
                          <span class="option-letter">{{ String.fromCharCode(65 + optIdx) }}.</span>
                          <el-input v-model="q.options[optIdx]" size="small" @input="updatePreviewData" />
                        </div>
                      </div>

                      <!-- 答案 -->
                      <div class="preview-answer">
                        <span class="answer-label">答案：</span>
                        <el-input v-if="aiForm.questionType === 'fill' || aiForm.questionType === 'essay'"
                          v-model="q.correctAnswer" size="small" @input="updatePreviewData" />
                        <el-select v-else-if="aiForm.questionType === 'single'" v-model="q.correctAnswer" size="small"
                          @change="updatePreviewData">
                          <el-option v-for="(opt, optIdx) in q.options" :key="optIdx"
                            :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                        </el-select>
                        <el-select v-else-if="aiForm.questionType === 'multiple'" v-model="q.correctAnswer" multiple
                          size="small" @change="updatePreviewData">
                          <el-option v-for="(opt, optIdx) in q.options" :key="optIdx"
                            :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                        </el-select>
                        <el-switch v-else-if="aiForm.questionType === 'judge'" v-model="q.correctAnswer"
                          active-text="正确" inactive-text="错误" @change="updatePreviewData" />
                      </div>

                      <!-- 解析 -->
                      <div class="preview-analysis">
                        <span class="analysis-label">解析：</span>
                        <el-input v-model="q.analysis" type="textarea" :rows="2" size="small"
                          @input="updatePreviewData" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-form>
      </div>

      <!-- 底部 footer 固定，只保留“取消”和“开始生成”按钮 -->

      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div>
            <el-button v-if="parsedQuestionsForPreview && !aiGenerating" type="success"
              @click="importGeneratedQuestions">
              <el-icon>
                <Check />
              </el-icon>
              导入题目 ({{ generatedCount }})
            </el-button>
            <el-button v-if="parsedQuestionsForPreview && !aiGenerating" @click="discardGeneratedQuestions">
              <el-icon>
                <Delete />
              </el-icon>
              丢弃
            </el-button>
          </div>
          <div style="display: flex; gap: 12px">
            <el-button @click="aiDialogVisible = false" :disabled="aiGenerating">取消</el-button>
            <el-button class="btn-ai-generate" v-if="!aiGenerating" @click="handleAiGenerate" :loading="aiGenerating">
              开始生成 (Ctrl+Enter)
            </el-button>
            <el-button class="btn-ai-generate" v-else disabled :loading="aiGenerating">
              生成中...
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="aiModelManagerVisible" title="AI 模型配置" width="900px" :close-on-click-modal="false"
      class="ai-model-manager-dialog">
      <aiModelManager ref="aiModelManagerRef" @saved="loadUserAiConfigs" />
    </el-dialog>

    <QuestionFullEditor v-model="fullEditorVisible" :question-data="currentQuestion" @save="handleFullEditorSave" />

    <ImageViewer v-model:visible="viewerVisible" :src="viewerSrc" />
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, watch, nextTick, onMounted, onBeforeUnmount, markRaw } from 'vue'
import draggable from 'vuedraggable'
import { Rank, InfoFilled, Delete, Search, MagicStick, Plus, Loading, Close, CircleCheck, Check, QuestionFilled, EditPen, ChatDotRound, FolderOpened, DocumentCopy, ArrowDown, Clock, VideoPause, VideoPlay, Setting, FullScreen, Grid, RefreshLeft } from '@element-plus/icons-vue'
import { generateQuestionsSync, generateReadingComprehensionSync } from '@/api/ai/ai'
import { ElMessage, ElNotification, ElMessageBox } from 'element-plus'
import { getBankContextInfo, clearBankConversation, generateQuestionsWithContext, generateQuestionsStreamFull, generateCompositeStreamFull } from '@/api/ai/ai'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import { useDsDeepThinkSync } from '@/composables/useDsDeepThinkSync'
import { listAiConfig } from '@/api/system/aiConfig'
import aiModelManager from '@/components/AiModelManager/index.vue'
import QuestionFullEditor from './QuestionFullEditor.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'
import { textToHtml, getPlainText } from '@/utils/questionUtils'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const userId = computed(() => userStore.id || userStore.userId)


// 题型定义
// 题型库数据：图标为 Vue 组件，必须用 markRaw 避免被响应式 Proxy 包装导致渲染失败
const questionTypes = ref([
  { type: 'single', name: '单选题', icon: markRaw(CircleCheck) },
  { type: 'multiple', name: '多选题', icon: markRaw(Check) },
  { type: 'judge', name: '判断题', icon: markRaw(QuestionFilled) },
  { type: 'fill', name: '填空题', icon: markRaw(EditPen) },
  { type: 'essay', name: '简答题', icon: markRaw(ChatDotRound) },
  { type: 'composite', name: '组合题（含子题）', icon: markRaw(FolderOpened) }
])

// 题型库悬浮层状态
const typePopoverVisible = ref(false)
const typePopoverTriggerRef = ref<HTMLElement | null>(null)
const typePopoverRef = ref<HTMLElement | null>(null)

const toggleTypePopover = (e?: Event) => {
  const before = typePopoverVisible.value
  typePopoverVisible.value = !typePopoverVisible.value
  console.log('[TypePopover] toggle 触发', {
    事件类型: e?.type,
    目标元素: (e?.target as HTMLElement)?.tagName + '.' + (e?.target as HTMLElement)?.className?.toString()?.slice(0, 40),
    当前台按钮DOM: typePopoverTriggerRef.value ? '存在' : '不存在',
    之前状态: before,
    之后状态: typePopoverVisible.value
  })
}

// 点击外部关闭悬浮层
const handleOutsideClick = (e: MouseEvent) => {
  const target = e.target as Node
  if (!typePopoverVisible.value) {
    console.log('[TypePopover][Outside] mousedown 触发，但悬浮层当前未打开，忽略', {
      目标元素: (target as HTMLElement)?.tagName + '.' + (target as HTMLElement)?.className?.toString()?.slice(0, 40)
    })
    return
  }
  const triggerEl = typePopoverTriggerRef.value
  const popoverEl = typePopoverRef.value
  // 判断点击是否在悬浮层和触发按钮之外
  const inTrigger = triggerEl ? triggerEl.contains(target) : false
  const inPopover = popoverEl ? popoverEl.contains(target) : false
  console.log('[TypePopover][Outside] mousedown 触发，悬浮层已打开', {
    目标元素: (target as HTMLElement)?.tagName + '.' + (target as HTMLElement)?.className?.toString()?.slice(0, 40),
    '在按钮内?': inTrigger,
    '在悬浮层内?': inPopover,
    '按钮DOM': triggerEl ? triggerEl.className : 'NULL',
    '悬浮层DOM': popoverEl ? popoverEl.className : 'NULL'
  })
  if (!inTrigger && !inPopover) {
    typePopoverVisible.value = false
    console.log('[TypePopover][Outside] 关闭悬浮层')
  }
}

// 监听悬浮层 visible 变化（无论何时改变都打印）
watch(typePopoverVisible, (newVal, oldVal) => {
  console.log('[TypePopover] visible 变化:', oldVal, '→', newVal)
  if (newVal) {
    // 打开后下一帧检查 DOM 是否真的渲染
    nextTick(() => {
      const el = typePopoverRef.value
      if (!el) {
        console.log('[TypePopover] 已打开但 DOM 未找到（ref 为 null）')
        return
      }
      const rect = el.getBoundingClientRect()
      const style = window.getComputedStyle(el)
      console.log('[TypePopover] DOM 已渲染', {
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        position: style.position,
        zIndex: style.zIndex,
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
        可视口宽: window.innerWidth,
        可视口高: window.innerHeight,
        在视口内: rect.x >= 0 && rect.y >= 0 && rect.x + rect.width <= window.innerWidth && rect.y + rect.height <= window.innerHeight
      })
    })
  }
})

onMounted(() => {
  console.log('[TypePopover] 组件已挂载，监听 document mousedown')
  document.addEventListener('mousedown', handleOutsideClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleOutsideClick)
})

const props = defineProps({
  bankId: {
    type: Number,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['reset'])

// 一键恢复：先弹确认框，用户确认后才通知父组件执行恢复
// 有当前题库时恢复该题库的原始数据（bankId 动态跟随用户切换的题库）；无题库时恢复初始状态
const handleRestore = async () => {
  const hasBank = !!props.bankId
  const message = hasBank
    ? '将丢弃当前未保存的修改，恢复至该题库的原始数据，是否继续？'
    : '当前尚未绑定题库，将清空所有未保存的题目并恢复初始状态，是否继续？'
  try {
    await ElMessageBox.confirm(message, '一键恢复确认', {
      confirmButtonText: '确认恢复',
      cancelButtonText: '取消',
      type: 'warning'
    })
    emit('reset')
  } catch {
    // 用户取消，不做任何操作
  }
}

// 使用 props
const currentBankId = computed(() => props.bankId)

// 视图模式：'raw' 显示原始JSON文本，'pretty' 显示美化卡片
const viewMode = ref('pretty')
const parsedQuestionsForPreview = ref(null)
const rawJsonContent = ref('') // 原始 JSON 内容

// 题目列表
const questions = ref([])
const currentId = ref(null)

// AI 生成相关状态
const aiGenerating = ref(false)
const streamBoxRef = ref(null)
const generatedCount = ref(0)
const pendingImportData = ref(null) // 暂存待导入的数据
const currentGeneratingType = ref({ isComposite: false, questionType: 'single' })

// 可编辑预览数据（深拷贝，用于用户编辑）
const editablePreviewData = ref(null)


// 编辑状态
const editingPassage = ref(false)

// 搜索与分页
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

// 题型筛选（支持多选）
const activeTypeFilters = ref(new Set(['all']))

// 设置题型筛选（多选模式）
const setTypeFilter = (type) => {
  if (type === 'all') {
    // 点击"全部" = 清除所有筛选
    activeTypeFilters.value = new Set(['all'])
  } else {
    // 移除"全部"
    activeTypeFilters.value.delete('all')
    // 切换选中状态
    if (activeTypeFilters.value.has(type)) {
      activeTypeFilters.value.delete(type)
      // 如果没有选中任何类型，自动选中"全部"
      if (activeTypeFilters.value.size === 0) {
        activeTypeFilters.value.add('all')
      }
    } else {
      activeTypeFilters.value.add(type)
    }
    // 触发响应式更新
    activeTypeFilters.value = new Set(activeTypeFilters.value)
  }
  currentPage.value = 1
}

// 判断是否选中
const isTypeSelected = (type) => {
  return activeTypeFilters.value.has(type)
}

// 选项 JSON 高级编辑对话框
const showOptionsJsonDialog = ref(false)

// 全屏编辑弹窗
const fullEditorVisible = ref(false)

// 图片预览
const viewerVisible = ref(false)
const viewerSrc = ref('')

const openImageViewer = (src) => {
  viewerSrc.value = src
  viewerVisible.value = true
}

// 当前题库ID（从父组件传入或路由获取）
// const currentBankId = ref(null)


// 题库上下文信息
const bankContextInfo = ref({
  bankName: '',
  totalQuestions: 0
})
const historyCount = ref(0)
const clearingContext = ref(false)

// AI 模型配置相关
const userAiConfigs = ref([])
const aiModelManagerVisible = ref(false)
const aiModelManagerRef = ref(null)

const loadUserAiConfigs = async () => {
  try {
    // available = 系统提供的官方模型 + 我自己添加的模型（用于校验用户选的模型是否可用）
    const res = await listAiConfig('available')
    if (res.code === 200 && res.rows) {
      userAiConfigs.value = res.rows
    }
  } catch (error) {
    console.error('加载用户AI配置失败:', error)
  }
}

const openAiModelManager = () => {
  aiModelManagerVisible.value = true
  nextTick(() => {
    if (aiModelManagerRef.value) {
      aiModelManagerRef.value.refresh()
    }
  })
}

// 加载题库上下文信息
const loadBankContextInfo = async () => {
  if (!currentBankId.value) return
  try {
    const res = await getBankContextInfo(currentBankId.value)
    if (res.code === 200 && res.data) {
      bankContextInfo.value = {
        bankName: res.data.bankName || '未知题库',
        totalQuestions: res.data.totalQuestions || 0
      }
      historyCount.value = res.data.historyCount || 0
    }
  } catch (error) {
    console.error('加载题库上下文失败:', error)
  }
}

// 清空上下文
const handleClearContext = async () => {
  if (!currentBankId.value) return
  try {
    await ElMessageBox.confirm('确定清空该题库的AI对话上下文吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    clearingContext.value = true
    const res = await clearBankConversation(currentBankId.value)
    if (res.code === 200) {
      ElMessage.success('上下文已清空')
      historyCount.value = 0
    } else {
      ElMessage.error(res.msg || '清空失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('清空失败')
    }
  } finally {
    clearingContext.value = false
  }
}


// ==================== 提示词历史记录 ====================
const PROMPT_HISTORY_KEY = 'ai_prompt_history'
const MAX_HISTORY_COUNT = 10
const promptHistory = ref([])

const loadPromptHistory = () => {
  try {
    const stored = localStorage.getItem(PROMPT_HISTORY_KEY)
    if (stored) promptHistory.value = JSON.parse(stored)
  } catch (e) { }
}

const savePromptToHistory = () => {
  const isComposite = aiForm.value.questionType === 'composite'

  const record = {
    // 保存当前题型，但只用于展示，点击时不强制切换
    questionType: aiForm.value.questionType,
    // 保存核心内容（组合题用 compositeRequirement，普通题用 knowledgePoint）
    knowledgePoint: isComposite ? '' : (aiForm.value.knowledgePoint || ''),
    compositeRequirement: isComposite ? (aiForm.value.compositeRequirement || '') : '',
    // 保存其他配置
    count: isComposite ? 0 : (aiForm.value.count || 3),
    wordCount: isComposite ? (aiForm.value.wordCount || 200) : 0,
    subCount: isComposite ? (aiForm.value.subCount || 5) : 0,
    model: aiForm.value.model || '',
    timestamp: Date.now()
  }





  // 去重逻辑：根据内容判断，而不是题型
  const exists = promptHistory.value.some(item => {
    const currentContent = isComposite ? record.compositeRequirement : record.knowledgePoint
    const itemContent = item.questionType === 'composite' ? item.compositeRequirement : item.knowledgePoint
    return currentContent && itemContent === currentContent
  })

  if (!exists && (record.knowledgePoint || record.compositeRequirement)) {
    promptHistory.value.unshift(record)
    if (promptHistory.value.length > MAX_HISTORY_COUNT) {
      promptHistory.value = promptHistory.value.slice(0, MAX_HISTORY_COUNT)
    }
    localStorage.setItem(PROMPT_HISTORY_KEY, JSON.stringify(promptHistory.value))
  }
}


// 删除单条历史记录
const deleteHistoryItem = (index) => {
  promptHistory.value.splice(index, 1)
  localStorage.setItem(PROMPT_HISTORY_KEY, JSON.stringify(promptHistory.value))
  ElMessage.success('已删除')
}

// 监听题目列表变化，自动选中第一题
watch(questions, (newQuestions) => {
  if (newQuestions.length > 0 && !currentId.value) {
    currentId.value = newQuestions[0].id
  }
}, { immediate: true })

// 复制原始 JSON
const copyRawJson = async () => {
  try {
    await navigator.clipboard.writeText(rawJsonContent.value)
    ElMessage.success('JSON 已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 编辑材料内容
const editPassage = () => {
  editingPassage.value = true
}

const applyHistoryPrompt = (item) => {
  if (!item) return
  const isComposite = aiForm.value.questionType === 'composite'
  if (isComposite) {
    aiForm.value.compositeRequirement = item.compositeRequirement || item.knowledgePoint || ''
    if (item.wordCount) aiForm.value.wordCount = item.wordCount
    if (item.subCount) aiForm.value.subCount = item.subCount
  } else {
    aiForm.value.knowledgePoint = item.knowledgePoint || item.compositeRequirement || ''
    if (item.count) aiForm.value.count = item.count
  }
  // 只在用户有该模型配置时才切换，避免删模型后历史记录导致报错
  if (item.model !== undefined && item.model !== null && item.model !== '') {
    const hasModel = userAiConfigs.value.some(config => config.isEnabled === 1 && config.model === item.model)
    if (hasModel) {
      aiForm.value.model = item.model
    }
  }
  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
}

const clearPromptHistory = () => {
  promptHistory.value = []
  localStorage.removeItem(PROMPT_HISTORY_KEY)
  ElMessage.success('历史记录已清空')
}

const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}


// 过滤后的题目列表（支持多选题型筛选 + 关键词搜索）
const allFilteredQuestions = computed(() => {
  const keyword = searchKeyword.value.toLowerCase()
  const filters = activeTypeFilters.value

  return questions.value.filter((q) => {
    // 多选题型筛选
    if (!filters.has('all') && !filters.has(q.type)) return false
    // 关键词搜索
    if (keyword) {
      const title = getPlainText(q?.title).toLowerCase()
      const typeName = getTypeName(q?.type)
      return title.includes(keyword) || typeName.includes(keyword)
    }
    return true
  })
})

const filteredQuestions = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return allFilteredQuestions.value.slice(start, end)
})

watch(searchKeyword, () => { currentPage.value = 1 })
watch(allFilteredQuestions, (newList) => {
  const maxPage = Math.ceil(newList.length / pageSize.value) || 1
  if (currentPage.value > maxPage) currentPage.value = maxPage
})

const handlePageChange = (page) => { currentPage.value = page }
const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
}
// ===================== 标题自适应：数量放不下时只显示「题目列表」 =====================
// 标题与左右按钮同处一行且不换行；这里实测完整标题所需宽度，
// 放不下就隐藏数量，避免被截断或被右侧按钮遮挡。
const panelHeaderRef = ref<HTMLElement | null>(null)
const panelTitleRef = ref<HTMLElement | null>(null)
const titleMeasureRef = ref<HTMLElement | null>(null)
const showTitleCount = ref(true)

let titleFitObserver: ResizeObserver | null = null

const updateTitleFit = () => {
  const titleEl = panelTitleRef.value
  const measureEl = titleMeasureRef.value
  if (!titleEl || !measureEl) return
  const available = titleEl.getBoundingClientRect().width
  const needed = measureEl.getBoundingClientRect().width
  // 直接比较实际像素宽度（含小数），避免取整误差
  showTitleCount.value = needed <= available
}

const stopTitleFitObserver = () => {
  if (titleFitObserver) {
    titleFitObserver.disconnect()
    titleFitObserver = null
  }
}

const startTitleFitObserver = () => {
  stopTitleFitObserver()
  if (typeof ResizeObserver === 'undefined') return
  titleFitObserver = new ResizeObserver(() => updateTitleFit())
  if (panelHeaderRef.value) titleFitObserver.observe(panelHeaderRef.value)
  if (panelTitleRef.value) titleFitObserver.observe(panelTitleRef.value)
  updateTitleFit()
}

// 题目数量变化（0/0 -> 5/10）时文案宽度会变，需要重新判断
watch(
  () => `${allFilteredQuestions.value.length}/${questions.value.length}`,
  () => { nextTick(() => updateTitleFit()) }
)

onMounted(() => { nextTick(() => startTitleFitObserver()) })
onBeforeUnmount(() => { stopTitleFitObserver() })

const currentQuestion = computed(() => questions.value.find((q) => q?.id === currentId.value))

const selectedSubType = ref('single')

// AI 生成相关
const aiDialogVisible = ref(false)
const deepThink = ref(localStorage.getItem('openstudy_ai_thinking') === '1')  // 深度思考开关（跟随全局偏好）

const aiFormRef = ref(null)
const aiForm = ref({
  questionType: 'single',
  knowledgePoint: '',
  count: 3,
  model: '',
  compositeRequirement: '',
  wordCount: 200,
  subCount: 5
})

// 选中的 AI 配置 id（区分同名系统/用户模型）；由 AiModelSelector 的 @select 提供
const selectedConfigId = ref(null)
const onModelSelect = (cfg) => { selectedConfigId.value = cfg?.configId ?? null }

// ⚠️ 两点都别改错：
// 1) 必须写在 `aiForm` 声明**之后** —— useDsDeepThinkSync 内部建立 watch 时会
//    同步求值一次这个 getter，写反了会撞 TDZ
//    （`Cannot access 'aiForm' before initialization`）→ 组件直接白屏。
// 2) 脚本里必须写 `aiForm.value.model`（模板里才有自动解包），
//    写成 `aiForm.model` 永远拿到 undefined → ds-free 的深度思考同步会静默失效。
// 这类顺序/取值问题 SFC 编译查不出来，动这块代码时务必人工确认。
useDsDeepThinkSync(() => aiForm.value.model, deepThink, 'openstudy_ai_thinking')

const aiRules = computed(() => {
  if (aiForm.value.questionType === 'composite') {
    return {
      questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
      compositeRequirement: [
        { required: true, message: '请输入文章主题或出题要求', trigger: 'blur' },
        { max: 200, message: '不能超过200个字符', trigger: 'blur' }
      ]
    }
  } else {
    return {
      questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
      knowledgePoint: [
        { required: true, message: '请输入知识点', trigger: 'blur' },
        { max: 200, message: '不能超过200个字符', trigger: 'blur' }
      ],
      count: [{ required: true, message: '请选择数量', trigger: 'change' }]
    }
  }
})

const onAiTypeChange = () => {
  if (aiForm.value.questionType === 'composite') {
    aiForm.value.compositeRequirement = ''
    aiForm.value.wordCount = 200
    aiForm.value.subCount = 5
  } else {
    aiForm.value.knowledgePoint = ''
    aiForm.value.count = 3
  }
  // 清空预览数据
  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
}

const onAiDialogClose = () => {
  // 清空所有数据
  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
  pendingImportData.value = null
  aiGenerating.value = false
  viewMode.value = 'pretty'
  aiDialogVisible.value = false
}

const applyOptionsJson = () => {
  const q = currentQuestion.value
  if (!q) return
  try {
    const parsed = JSON.parse(q.optionsJson)
    if (Array.isArray(parsed)) {
      q.options = parsed.map(item => typeof item === 'string' ? item : item.text || item.value)
      if (q.type === 'single' && q.answer >= q.options.length) q.answer = 0
      if (q.type === 'multiple') q.answer = q.answer.filter(idx => idx < q.options.length)
      showOptionsJsonDialog.value = false
      ElMessage.success('选项已更新')
    } else {
      ElMessage.warning('JSON 必须是一个数组')
    }
  } catch (e) {
    ElMessage.error('JSON 格式错误')
  }
}

const onOptionChange = () => {
  const q = currentQuestion.value
  if (q) q.optionsJson = JSON.stringify(q.options)
}

const getTypeName = (type) => {
  if (typeof type === 'number') {
    const map = { 1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题', 6: '组合题' }
    return map[type] || '未知'
  }
  const found = questionTypes.value.find(t => t.type === type)
  return found?.name || type
}

// 获取指定题型的数量
const getTypeCount = (type) => {
  return questions.value.filter(q => q.type === type).length
}

const filterQuestions = () => { }

const cloneQuestion = (typeItem) => {
  const newId = Date.now() + Math.random()
  let base = {
    id: newId,
    type: typeItem.type,
    title: '',
    analysis: '',
    score: 5,
    content: ''
  }
  if (typeItem.type === 'composite') {
    base.subQuestions = []
    base.content = ''
  } else if (typeItem.type === 'single' || typeItem.type === 'multiple') {
    base.options = ['选项A', '选项B']
    base.optionsJson = JSON.stringify(base.options)
    base.answer = typeItem.type === 'single' ? 0 : []
  } else if (typeItem.type === 'judge') {
    base.answer = false
  } else {
    base.answer = ''
  }
  questions.value.push(base)
  currentId.value = newId
  return base
}

const selectQuestion = (id) => { currentId.value = id }

const openFullEditor = () => {
  if (!currentQuestion.value) {
    ElMessage.warning('请先选择一道题目')
    return
  }
  fullEditorVisible.value = true
}

const handleFullEditorSave = (updatedQuestion) => {
  const index = questions.value.findIndex(q => q.id === currentId.value)
  if (index !== -1) {
    questions.value[index] = { ...questions.value[index], ...updatedQuestion }
    currentId.value = updatedQuestion.id || currentId.value
  }
  ElMessage.success('题目已更新')
}

const removeQuestion = (id) => {
  const index = questions.value.findIndex(q => q.id === id)
  if (index !== -1) {
    questions.value.splice(index, 1)
    if (currentId.value === id) currentId.value = questions.value[0]?.id || null
  }
}

const onTypeChange = () => {
  const q = currentQuestion.value
  if (!q) return
  if (q.type === 'composite') {
    if (!q.subQuestions) q.subQuestions = []
    if (q.content === undefined) q.content = ''
  } else if (q.type === 'single' || q.type === 'multiple') {
    if (!q.options) {
      q.options = ['选项A', '选项B']
      q.optionsJson = JSON.stringify(q.options)
    }
    if (q.type === 'single' && typeof q.answer !== 'number') q.answer = 0
    if (q.type === 'multiple' && !Array.isArray(q.answer)) q.answer = []
  } else if (q.type === 'judge') {
    if (typeof q.answer !== 'boolean') q.answer = false
  } else {
    if (typeof q.answer !== 'string') q.answer = ''
  }
}

const addOption = () => {
  const q = currentQuestion.value
  if (!q) return
  if (!q.options) q.options = []
  if (q.options.length >= 6) {
    ElMessage.warning('最多支持6个选项（A-F）')
    return
  }
  q.options.push('')
  syncOptionsJson(q)
}

const removeOption = (index) => {
  const q = currentQuestion.value
  if (!q) return
  if (q.options.length <= 2) {
    ElMessage.warning('至少保留2个选项')
    return
  }
  q.options.splice(index, 1)
  if (q.type === 'single') {
    if (q.answer === index) q.answer = 0
    else if (q.answer > index) q.answer -= 1
  } else if (q.type === 'multiple') {
    q.answer = q.answer.filter(idx => idx !== index).map(idx => idx > index ? idx - 1 : idx)
  }
  syncOptionsJson(q)
}

// 判断是否为组合题预览
const isCompositePreview = computed(() => {
  const data = parsedQuestionsForPreview.value
  return data && !Array.isArray(data) && data.passage && data.questions
})

const isOptionCorrect = (question, optIdx) => {
  if (aiForm.value.questionType === 'single') {
    return question.correctAnswer === optIdx
  } else if (aiForm.value.questionType === 'multiple') {
    return Array.isArray(question.correctAnswer) && question.correctAnswer.includes(optIdx)
  }
  return false
}

// 获取子题题型显示名称
const getSubTypeName = (type) => {
  const map = {
    single: '单选题',
    multiple: '多选题',
    judge: '判断题',
    fill: '填空题',
    essay: '简答题'
  }
  return map[type] || type
}

// 获取子题题型标签类型（Element Plus Tag 的 type）
const getSubTypeTagType = (type) => {
  const map = {
    single: 'primary',
    multiple: 'success',
    judge: 'warning',
    fill: 'info',
    essay: ''
  }
  return map[type] || 'info'
}



// 判断子题选项是否正确（用于组合题子题预览）
const isSubOptionCorrect = (sub, optIdx) => {
  if (sub.type === 'single') {
    return sub.correctAnswer === optIdx
  } else if (sub.type === 'multiple') {
    return Array.isArray(sub.correctAnswer) && sub.correctAnswer.includes(optIdx)
  }
  return false
}

// 格式化子题答案显示（用于组合题子题预览）
const formatSubAnswer = (sub) => {
  if (sub.type === 'judge') {
    return sub.correctAnswer ? '正确' : '错误'
  }
  return sub.correctAnswer
}

const formatAnswer = (question) => {
  if (aiForm.value.questionType === 'judge') {
    return question.correctAnswer ? '正确' : '错误'
  }
  return question.correctAnswer
}

const syncOptionsJson = (q) => { q.optionsJson = JSON.stringify(q.options) }

const addSubQuestionBySelectedType = () => {
  if (!selectedSubType.value) {
    ElMessage.warning('请先选择题型')
    return
  }
  const newSub = createEmptySub(selectedSubType.value)
  currentQuestion.value.subQuestions.push(newSub)
}

const createEmptySub = (type) => {
  const base = {
    id: Date.now() + Math.random(),
    type,
    question: '',
    answer: type === 'single' ? 0 : type === 'multiple' ? [] : type === 'judge' ? false : '',
    score: 2,
    sortOrder: currentQuestion.value.subQuestions.length,
    analysis: ''
  }
  if (type === 'single' || type === 'multiple') {
    base.options = ['选项A', '选项B']
    base.optionsJson = JSON.stringify(base.options)
  }
  return base
}

const removeSubQuestion = (index) => { currentQuestion.value.subQuestions.splice(index, 1) }

const onSubTypeChange = (sub) => {
  if (sub.type === 'single') {
    sub.answer = 0
    if (!sub.options) sub.options = ['选项A', '选项B']
    if (!sub.optionsJson) sub.optionsJson = JSON.stringify(sub.options)
  } else if (sub.type === 'multiple') {
    sub.answer = []
    if (!sub.options) sub.options = ['选项A', '选项B']
    if (!sub.optionsJson) sub.optionsJson = JSON.stringify(sub.options)
  } else if (sub.type === 'judge') {
    sub.answer = false
    sub.options = []
    sub.optionsJson = ''
  } else {
    sub.answer = ''
    sub.options = []
    sub.optionsJson = ''
  }
}

const parseSubOptions = (sub) => {
  if (!sub.optionsJson) return
  try {
    const parsed = JSON.parse(sub.optionsJson)
    if (Array.isArray(parsed)) sub.options = parsed.map(item => typeof item === 'string' ? item : item.text || item.value)
  } catch (e) {
    ElMessage.warning('子题选项格式错误')
  }
}

// 题型点击/拖拽判断
let typeMouseDownPos = null
let typeMouseDownTime = 0
let isTypeDragging = false

const onTypeMouseDown = (e, element) => {
  typeMouseDownPos = { x: e.clientX, y: e.clientY }
  typeMouseDownTime = Date.now()
  isTypeDragging = false
}

const onTypeMouseUp = (e, element) => {
  if (isTypeDragging) return  // 已经触发了拖拽，忽略

  const pos = typeMouseDownPos
  if (!pos) return

  // 计算移动距离
  const dx = Math.abs(e.clientX - pos.x)
  const dy = Math.abs(e.clientY - pos.y)
  const elapsed = Date.now() - typeMouseDownTime

  // 如果移动距离小于 5px 且时间小于 300ms，认为是点击
  if (dx < 5 && dy < 5 && elapsed < 300) {
    setTypeFilter(element.type)
  }

  typeMouseDownPos = null
}

let lastDraggedType = null
const onTypeDragStart = (evt, typeItem) => {
  lastDraggedType = typeItem.type
  isTypeDragging = true  // 标记正在拖拽
}
const onSubDragAdd = () => {
  if (lastDraggedType) {
    const newSub = createEmptySub(lastDraggedType)
    currentQuestion.value.subQuestions.push(newSub)
    lastDraggedType = null
  }
}
const onSubDragEnd = () => { }
const onDragEnd = () => { }

// ==================== 键盘快捷键 ====================
const handleKeydown = (e) => {
  if (!aiDialogVisible.value) return

  // Ctrl+Enter 开始生成
  if (e.ctrlKey && e.key === 'Enter' && !aiGenerating.value) {
    e.preventDefault()
    handleAiGenerate()
  }
}

// 监听对话框状态，添加/移除键盘事件
watch(aiDialogVisible, (val) => {
  if (val) {
    window.addEventListener('keydown', handleKeydown)
  } else {
    window.removeEventListener('keydown', handleKeydown)
  }
})

// 修改打开弹窗的方法，加载上下文
const openAiDialog = () => {
  aiForm.value = {
    questionType: 'single',
    knowledgePoint: '',
    count: 3,
    model: localStorage.getItem('openstudy_ai_model_question-builder') || '',
    compositeRequirement: '',
    wordCount: 200,
    subCount: 5
  }
  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
  pendingImportData.value = null
  aiGenerating.value = false
  aiDialogVisible.value = true
  loadPromptHistory()

  // 新增：加载题库上下文
  loadBankContextInfo()
  loadUserAiConfigs()
}

// 更新预览数据（当用户编辑时）
const updatePreviewData = () => {
  // 触发视图更新
  parsedQuestionsForPreview.value = JSON.parse(JSON.stringify(editablePreviewData.value))
}

// 修改题目题干
const editQuestionTitle = (index, newTitle) => {
  if (!editablePreviewData.value) return
  if (Array.isArray(editablePreviewData.value)) {
    editablePreviewData.value[index].question = newTitle
  }
  updatePreviewData()
}

// 修改选项
const editOption = (qIndex, optIndex, newValue) => {
  if (!editablePreviewData.value) return
  if (Array.isArray(editablePreviewData.value)) {
    editablePreviewData.value[qIndex].options[optIndex] = newValue
  }
  updatePreviewData()
}

// 修改正确答案
const editAnswer = (qIndex, newAnswer) => {
  if (!editablePreviewData.value) return
  if (Array.isArray(editablePreviewData.value)) {
    editablePreviewData.value[qIndex].correctAnswer = newAnswer
  }
  updatePreviewData()
}

// 修改解析
const editAnalysis = (qIndex, newAnalysis) => {
  if (!editablePreviewData.value) return
  if (Array.isArray(editablePreviewData.value)) {
    editablePreviewData.value[qIndex].analysis = newAnalysis
  }
  updatePreviewData()
}

// 导入生成的题目
const importGeneratedQuestions = () => {
  if (!pendingImportData.value) {
    ElMessage.warning('没有可导入的题目')
    return
  }

  const { isComposite, parsed, questionType } = pendingImportData.value

  // 临时设置 aiForm.questionType
  const originalType = aiForm.value.questionType
  aiForm.value.questionType = questionType

  processParsedData(isComposite, parsed)

  aiForm.value.questionType = originalType

  ElMessage.success(`成功导入 ${generatedCount.value} 道题目`)

  // 清空待导入数据和预览
  pendingImportData.value = null
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
  rawJsonContent.value = ''
}

// 丢弃生成的题目
const discardGeneratedQuestions = () => {
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
  pendingImportData.value = null
  rawJsonContent.value = ''
  ElMessage.info('已丢弃生成的题目')
}








const extractJsonFromAiResponse = (text) => {
  if (!text) { console.warn('【extractJson】text 为空'); return null }
  if (typeof text === 'object') return text

  try {
    const direct = JSON.parse(text)
    console.log('【extractJson】直接解析成功')
    return direct
  } catch (e) {
    console.log('【extractJson】直接解析失败，开始清理，原文长度:', text.length)
  }

  let cleaned = text
    .replace(/```json\s*|\s*```/gi, '')
    .replace(/```\s*|\s*```/g, '')
    .replace(/[\u0000-\u001F\u007F-\u009F]/g, '')
    .trim()

  console.log('【extractJson】清理后长度:', cleaned.length)
  console.log('【extractJson】清理后前300字符:', cleaned.substring(0, 300))

  let start = cleaned.indexOf('[')
  let end = cleaned.lastIndexOf(']')

  if (start === -1) {
    start = cleaned.indexOf('{')
    end = cleaned.lastIndexOf('}')
  }

  console.log('【extractJson】JSON边界: start=', start, 'end=', end)

  if (start !== -1 && end !== -1 && end > start) {
    cleaned = cleaned.substring(start, end + 1)
    console.log('【extractJson】提取后长度:', cleaned.length)
  }

  cleaned = cleaned.replace(/([{,]\s*)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:/g, '$1"$2":')
  cleaned = cleaned.replace(/,(\s*[}\]])/g, '$1')

  try {
    const result = JSON.parse(cleaned)
    console.log('【extractJson】清理后解析成功')
    return result
  } catch (e) {
    console.warn('【extractJson】清理后解析失败:', e.message)
    const fallback = text.substring(
      text.indexOf('[') !== -1 ? text.indexOf('[') : text.indexOf('{'),
      text.lastIndexOf(']') !== -1 ? text.lastIndexOf(']') + 1 : text.lastIndexOf('}') + 1
    )
    console.log('【extractJson】fallback 长度:', fallback.length)
    console.log('【extractJson】fallback 前300字符:', fallback.substring(0, 300))
    try {
      return JSON.parse(fallback)
    } catch (e2) {
      console.error('【extractJson】JSON解析完全失败:', e2.message)
      console.error('【extractJson】最终尝试解析的内容前500字符:', fallback.substring(0, 500))
      return null
    }
  }
}

// 把 AI 返回的字段名统一成「美化预览 / 导入」需要的结构
// AI 通常返回 questionText / answer，而预览与导入使用 question / correctAnswer
const toOptionIndex = (item, options) => {
  if (typeof item === 'number') return item
  const text = String(item ?? '').trim()
  if (text === '') return item
  // 1) 直接是选项文本（如 answer: "class"）
  const byText = options.findIndex(opt => String(opt).trim().toLowerCase() === text.toLowerCase())
  if (byText >= 0) return byText
  // 2) A/B/C/D 形式
  const letter = text.replace(/[.、:：)\s]/g, '').toUpperCase()
  if (/^[A-Z]$/.test(letter)) {
    const idx = letter.charCodeAt(0) - 65
    if (idx >= 0 && idx < options.length) return idx
  }
  // 3) 数字下标
  if (/^\d+$/.test(text)) {
    const idx = Number(text)
    if (idx >= 0 && idx < options.length) return idx
  }
  return item
}

// 选择题答案归一化：支持 选项文本 / A-D / 数字下标 / 逗号分隔多选
const normalizeAiAnswer = (answer, options, questionType) => {
  if (!Array.isArray(options) || options.length === 0) return answer
  const isMultiple = questionType === 'multiple' || questionType === 2
  const toArray = (val) => {
    if (Array.isArray(val)) return val.map(v => toOptionIndex(v, options)).filter(v => typeof v === 'number')
    if (typeof val === 'string' && /[,，]/.test(val)) {
      return val.split(/[,，]/).map(v => toOptionIndex(v.trim(), options)).filter(v => typeof v === 'number')
    }
    return null
  }
  if (isMultiple) {
    const arr = toArray(answer)
    if (arr) return arr
    const idx = toOptionIndex(answer, options)
    return typeof idx === 'number' ? [idx] : []
  }
  const arr = toArray(answer)
  if (arr) return arr.length ? arr[0] : answer
  return toOptionIndex(answer, options)
}

const normalizeAiQuestion = (q, defaultScore = 5, questionType = '') => {
  if (!q || typeof q !== 'object') return q
  const normalized = { ...q }
  if (normalized.question === undefined || normalized.question === null || normalized.question === '') {
    normalized.question = normalized.questionText || normalized.title || normalized.questionContent || ''
  }
  if (normalized.correctAnswer === undefined || normalized.correctAnswer === null) {
    if (normalized.answer !== undefined && normalized.answer !== null) {
      normalized.correctAnswer = normalized.answer
    }
  }
  if (normalized.score === undefined || normalized.score === null) {
    normalized.score = defaultScore
  }
  // options 若是 JSON 字符串，转成数组，供预览 v-for 使用
  if (typeof normalized.options === 'string') {
    try {
      const parsedOptions = JSON.parse(normalized.options)
      if (Array.isArray(parsedOptions)) normalized.options = parsedOptions
    } catch (e) { /* 保持原样 */ }
  }
  // 答案归一化：把「选项文本 / A-D / 数字」统一成 option 下标
  if (Array.isArray(normalized.options) && normalized.correctAnswer !== undefined && normalized.correctAnswer !== null) {
    const type = questionType || normalized.type || normalized.questionType || ''
    normalized.correctAnswer = normalizeAiAnswer(normalized.correctAnswer, normalized.options, type)
  }
  return normalized
}

const convertAiQuestionToInternal = (aiQuestion, questionType) => {
  const newId = Date.now() + Math.random() + Math.floor(Math.random() * 1000)
  const base = {
    id: newId,
    type: questionType,
    title: textToHtml(aiQuestion.question || aiQuestion.questionText || aiQuestion.title || ''),
    analysis: aiQuestion.analysis || '',
    score: 5
  }
  if (questionType === 'single' || questionType === 'multiple') {
    let rawOptions = aiQuestion.options
    let options = []
    if (Array.isArray(rawOptions)) options = rawOptions.map(opt => String(opt).trim())
    else if (typeof rawOptions === 'string') {
      try { options = JSON.parse(rawOptions) } catch { options = rawOptions.split(',').map(s => s.trim().replace(/^["']|["']$/g, '')) }
    }
    options = options.filter(opt => opt !== '')
    if (options.length === 0) options = ['选项A', '选项B']
    options = options.map(opt => opt.replace(/^[A-Z][\.\:]\s*/, ''))
    base.options = options
    base.optionsJson = JSON.stringify(options)
    let ans = aiQuestion.correctAnswer ?? aiQuestion.answer
    if (questionType === 'single') {
      if (typeof ans === 'string' && /[A-Za-z]/.test(ans)) ans = ans.toUpperCase().charCodeAt(0) - 65
      else if (typeof ans === 'number') ans = Math.min(ans, options.length - 1)
      else ans = 0
      base.answer = ans >= 0 && ans < options.length ? ans : 0
    } else {
      let arr = Array.isArray(ans) ? ans : typeof ans === 'string' ? ans.split(',').map(s => s.trim()) : []
      base.answer = arr.map(item => {
        if (typeof item === 'string' && /[A-Za-z]/.test(item)) return item.toUpperCase().charCodeAt(0) - 65
        return typeof item === 'number' ? item : 0
      }).filter(idx => idx >= 0 && idx < options.length)
    }
  } else if (questionType === 'judge') {
    let ans = aiQuestion.correctAnswer ?? aiQuestion.answer
    if (typeof ans === 'boolean') base.answer = ans
    else if (typeof ans === 'string') base.answer = ['true', '正确', '对', 't'].includes(ans.toLowerCase())
    else base.answer = false
  } else {
    base.answer = aiQuestion.correctAnswer || aiQuestion.answer || ''
  }
  return base
}

const convertCompositeFromAi = (aiData) => {
  const newId = Date.now() + Math.random()
  const composite = {
    id: newId,
    type: 'composite',
    title: textToHtml(aiData.title || '阅读理解'),
    content: textToHtml(aiData.passage || ''),
    analysis: '',
    score: 10,
    subQuestions: []
  }
  const questions = aiData.questions || []
  composite.subQuestions = questions.map((q, index) => {
    const subType = mapAiTypeToInternal(q.type)
    const sub = {
      id: Date.now() + Math.random() + index,
      type: subType,
      question: textToHtml(q.question || q.questionText || ''),
      score: q.score || 2,
      analysis: q.analysis || '',
      sortOrder: index
    }
    if (subType === 'single' || subType === 'multiple') {
      let opts = q.options || []
      if (typeof opts === 'string') { try { opts = JSON.parse(opts) } catch { opts = [] } }
      opts = opts.map(opt => String(opt).trim()).filter(opt => opt)
      if (opts.length === 0) opts = ['选项A', '选项B']
      sub.options = opts
      sub.optionsJson = JSON.stringify(opts)
      let ans = q.correctAnswer ?? q.answer
      if (subType === 'single') {
        if (typeof ans === 'string' && /[A-Za-z]/.test(ans)) ans = ans.toUpperCase().charCodeAt(0) - 65
        else if (typeof ans === 'number') ans = ans
        else ans = 0
        sub.answer = ans >= 0 && ans < opts.length ? ans : 0
      } else {
        let arr = Array.isArray(ans) ? ans : typeof ans === 'string' ? ans.split(',').map(s => s.trim()) : []
        sub.answer = arr.map(item => {
          if (typeof item === 'string' && /[A-Za-z]/.test(item)) return item.toUpperCase().charCodeAt(0) - 65
          return typeof item === 'number' ? item : 0
        }).filter(idx => idx >= 0 && idx < opts.length)
      }
    } else if (subType === 'judge') {
      let ans = q.correctAnswer ?? q.answer
      if (typeof ans === 'boolean') sub.answer = ans
      else if (typeof ans === 'string') sub.answer = ['true', '正确', '对'].includes(ans.toLowerCase())
      else sub.answer = false
    } else {
      sub.answer = q.correctAnswer || q.answer || ''
    }
    return sub
  })
  return composite
}

const mapAiTypeToInternal = (typeStr) => {
  const map = { single: 'single', multiple: 'multiple', judge: 'judge', fill: 'fill', essay: 'essay' }
  return map[typeStr] || 'single'
}

// 普通 API 调用（非流式）
const generateQuestionsNormal = async (params, isComposite) => {
  if (isComposite) {
    // 组合题接口
    const res = await generateReadingComprehensionSync({
      requirement: params.requirement,
      questionCount: params.subCount || 5,
      wordCount: params.wordCount || 300,
      model: params.model,
      configId: selectedConfigId.value || undefined
    })
    // 注意：你的 request 可能直接返回 data，也可能返回完整响应
    // 根据实际情况调整
    return res.data || res
  } else {
    // 普通题型接口
    const res = await generateQuestionsSync({
      knowledgePoint: params.knowledgePoint,
      questionType: params.questionType,
      count: params.count,
      model: params.model,
      configId: selectedConfigId.value || undefined,
      userId: userId.value,
      thinking: deepThink.value
    })
    return res.data || res
  }
}





const handleAiGenerate = async () => {
  const valid = await aiFormRef.value?.validate().catch(() => false)
  if (!valid) return

  if (parsedQuestionsForPreview.value && !aiGenerating.value) {
    try {
      await ElMessageBox.confirm(
        '当前有已生成但未导入的题目，是否丢弃并重新生成？',
        '提示',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
      )
    } catch { return }
  }

  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
  pendingImportData.value = null
  aiGenerating.value = true
  viewMode.value = 'raw'

  const isComposite = aiForm.value.questionType === 'composite'
  currentGeneratingType.value = { isComposite, questionType: aiForm.value.questionType }

  try {
    if (isComposite) {
      await generateCompositeStreamFull({
        requirement: aiForm.value.compositeRequirement,
        questionCount: aiForm.value.subCount,
        wordCount: aiForm.value.wordCount,
        model: aiForm.value.model,
        configId: selectedConfigId.value || undefined,
        userId: userId.value,
        thinking: deepThink.value,
        onChunk(fullContent) {
          rawJsonContent.value = fullContent
          nextTick(() => {
            if (streamBoxRef.value) streamBoxRef.value.scrollTop = streamBoxRef.value.scrollHeight
          })
        },
        onComplete(fullContent) {
          finishAiGenerate(fullContent, true)
        },
        onError(error) {
          console.error('【组合题生成失败】:', error)
          ElMessage.error('生成失败：' + (error?.message || '未知错误'))
          aiGenerating.value = false
        }
      })
    } else {
      await generateQuestionsStreamFull({
        knowledgePoint: aiForm.value.knowledgePoint,
        questionType: aiForm.value.questionType,
        count: aiForm.value.count,
        model: aiForm.value.model,
        configId: selectedConfigId.value || undefined,
        userId: userId.value,
        thinking: deepThink.value,
        bankId: currentBankId.value,
        onChunk(fullContent) {
          rawJsonContent.value = fullContent
          nextTick(() => {
            if (streamBoxRef.value) streamBoxRef.value.scrollTop = streamBoxRef.value.scrollHeight
          })
        },
        onComplete(fullContent) {
          finishAiGenerate(fullContent, false)
        },
        onError(error) {
          console.error('【生成失败】:', error)
          ElMessage.error('生成失败：' + (error?.message || '未知错误'))
          aiGenerating.value = false
        }
      })
    }
  } catch (error) {
    console.error('【生成失败，完整错误】:', error)
    ElMessage.error('生成失败：' + (error.message || '未知错误'))
    aiGenerating.value = false
  }
}

const finishAiGenerate = (rawData, isComposite) => {
  console.log('【finishAiGenerate】收到 rawData 类型:', typeof rawData)
  console.log('【finishAiGenerate】收到 rawData:', typeof rawData === 'string' ? rawData.substring(0, 500) : JSON.stringify(rawData).substring(0, 500))

  let actualData = rawData
  if (rawData && typeof rawData === 'object' && rawData.msg !== undefined) {
    actualData = rawData.msg
    console.log('【finishAiExtract】从 msg 提取，类型:', typeof actualData)
  }

  let parsed = actualData
  if (typeof actualData === 'string') {
    rawJsonContent.value = actualData
    console.log('【finishAiGenerate】开始解析字符串，长度:', actualData.length)
    console.log('【finishAiGenerate】前200字符:', actualData.substring(0, 200))
    console.log('【finishAiGenerate】后200字符:', actualData.substring(Math.max(0, actualData.length - 200)))
    parsed = extractJsonFromAiResponse(actualData)
    console.log('【finishAiGenerate】解析结果:', parsed)
  } else {
    rawJsonContent.value = JSON.stringify(actualData, null, 2)
    console.log('【finishAiGenerate】actualData 是对象，已转 JSON 字符串')
  }

  if (!parsed) {
    ElMessage.error('AI 返回数据解析失败，请查看原始 JSON')
    aiGenerating.value = false
    return
  }

  if (isComposite) {
    if (!parsed.passage || !parsed.questions || !Array.isArray(parsed.questions)) {
      ElMessage.error('AI 返回的组合题数据格式不正确')
      aiGenerating.value = false
      return
    }
  } else {
    if (!Array.isArray(parsed)) {
      if (parsed && typeof parsed === 'object' && (parsed.question || parsed.questionText)) {
        parsed = [parsed]
      } else {
        ElMessage.error('AI 返回的题目数据格式不正确')
        aiGenerating.value = false
        return
      }
    }
  }

  // 统一 AI 字段名（questionText -> question，answer -> correctAnswer）
  if (isComposite) {
    parsed.questions = (parsed.questions || []).map(q => normalizeAiQuestion(q, 2, q.type || q.questionType))
  } else {
    parsed = Array.isArray(parsed)
      ? parsed.map(q => normalizeAiQuestion(q, 5, aiForm.value.questionType))
      : normalizeAiQuestion(parsed, 5, aiForm.value.questionType)
  }

  generatedCount.value = isComposite ? parsed.questions?.length || 0 : (Array.isArray(parsed) ? parsed.length : 1)
  editablePreviewData.value = JSON.parse(JSON.stringify(parsed))
  parsedQuestionsForPreview.value = parsed
  pendingImportData.value = { isComposite, parsed: editablePreviewData.value, questionType: aiForm.value.questionType }
  viewMode.value = 'pretty'
  savePromptToHistory()
  ElMessage.success(`成功生成 ${generatedCount.value} 道题目，请确认后导入`)
  aiGenerating.value = false
}





const processParsedData = (isComposite, parsed) => {
  if (isComposite) {
    let composite = null
    if (parsed.passage && parsed.questions) composite = convertCompositeFromAi(parsed)
    else if (typeof parsed.passage === 'string' && !Array.isArray(parsed)) {
      const questions = parsed.questions || []
      composite = convertCompositeFromAi({ passage: parsed.passage, questions })
    } else if (Array.isArray(parsed)) {
      ElMessage.warning('AI 未返回文章内容，将仅导入子题')
      composite = { id: Date.now() + Math.random(), type: 'composite', title: '组合题（请手动填写材料）', content: '', analysis: '', score: 10, subQuestions: [] }
      parsed.forEach((q, idx) => {
        const subType = mapAiTypeToInternal(q.type || 'single')
        const sub = { id: Date.now() + Math.random() + idx, type: subType, question: textToHtml(q.question || q.questionText || ''), score: 2, analysis: q.analysis || '', sortOrder: idx }
        if (subType === 'single' || subType === 'multiple') {
          let opts = q.options || []
          if (typeof opts === 'string') try { opts = JSON.parse(opts) } catch { opts = [] }
          opts = opts.map(opt => String(opt).trim()).filter(opt => opt)
          if (opts.length === 0) opts = ['选项A', '选项B']
          sub.options = opts; sub.optionsJson = JSON.stringify(opts)
          let ans = q.correctAnswer ?? q.answer
          if (subType === 'single') {
            if (typeof ans === 'string' && /[A-Za-z]/.test(ans)) ans = ans.toUpperCase().charCodeAt(0) - 65
            else if (typeof ans === 'number') ans = ans
            else ans = 0
            sub.answer = ans >= 0 && ans < opts.length ? ans : 0
          } else {
            let arr = Array.isArray(ans) ? ans : typeof ans === 'string' ? ans.split(',').map(s => s.trim()) : []
            sub.answer = arr.map(item => {
              if (typeof item === 'string' && /[A-Za-z]/.test(item)) return item.toUpperCase().charCodeAt(0) - 65
              return typeof item === 'number' ? item : 0
            }).filter(idx => idx >= 0 && idx < opts.length)
          }
        } else if (subType === 'judge') {
          let ans = q.correctAnswer ?? q.answer
          sub.answer = typeof ans === 'boolean' ? ans : ['true', '正确', '对'].includes(String(ans).toLowerCase())
        } else { sub.answer = q.correctAnswer || q.answer || '' }
        composite.subQuestions.push(sub)
      })
    } else { ElMessage.error('组合题格式不正确'); return }
    if (composite) { questions.value.push(composite); currentId.value = composite.id; ElMessage.success('成功生成 1 道组合题') }
  } else {
    const questionArray = Array.isArray(parsed) ? parsed : [parsed]
    let addedCount = 0
    for (const q of questionArray) {
      try {
        const newQuestion = convertAiQuestionToInternal(q, aiForm.value.questionType)
        questions.value.push(newQuestion)
        addedCount++
      } catch { console.warn('转换单题失败') }
    }
    if (addedCount > 0) {
      // ElMessage.success(`成功生成并添加了 ${ addedCount } 道题目`)
      if (questions.value.length > 0) currentId.value = questions.value[questions.value.length - 1]?.id
    } else ElMessage.warning('没有成功添加任何题目')
  }
}



loadPromptHistory()
defineExpose({ questions, openAiDialog })
</script>

<style scoped lang="scss">
/* AI 模型行：下拉框 + 管理模型 + 深度思考开关 横向并排、垂直居中 */
.ai-model-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.question-builder {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  /*
   * 原来写死 `min-height: 600px`：题目为 0 条时，双栏仍撑满 600px 空白，
   * 左栏那条 `border-right` 跟着拉到底 —— 题量大时没问题，空的时候很突兀
   * （用户 2026-10-18 截图反馈「页尾一条竖线」）。
   * 现在按内容自适应：有题目时自然长，空列表时就一小块。
   */
  min-height: 0;
  width: 100%;

  :deep(.el-button) {
    border-radius: 8px;
  }

  :deep(.el-tag) {
    border-radius: 4px;
  }

  /* ========== 题型库触发按钮 ========== */
  .type-popover-trigger {
    position: relative;
    display: inline-flex;
    flex-shrink: 0;

    .btn-type-lib {
      position: relative;
      background: #fff;
      border: 1px solid var(--os-border);
      color: var(--os-text-2);
      transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);

      &:hover {
        color: var(--os-accent);
        border-color: #c6e2ff;
        background: #ecf5ff;
      }

      &.is-filtering {
        color: var(--os-accent);
        border-color: var(--os-accent);
        background: #ecf5ff;
      }

      .trigger-badge {
        position: absolute;
        top: -8px;
        right: -8px;

        :deep(.el-badge__content) {
          font-size: 10px;
          min-width: 16px;
          height: 16px;
          line-height: 16px;
          padding: 0 4px;
        }
      }
    }
  }

  /* ========== 一键恢复按钮 ========== */
  .btn-restore {
    flex-shrink: 0;
    background: #fff;
    border: 1px solid var(--os-border);
    color: var(--os-text-2);
    transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);

    &:hover {
      color: #e6a23c;
      border-color: #f3d19e;
      background: #fdf6ec;
    }
  }

  /* ========== 题型库悬浮层 ========== */
  .type-popover {
    position: absolute;
    top: calc(100% + 8px);
    left: 16px;
    width: 240px;
    background: #fff;
    border: 1px solid var(--os-border);
    border-radius: var(--os-radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 12px;
    z-index: 2000;
    display: flex;
    flex-direction: column;

    .popover-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 600;
      color: var(--os-text);
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--os-border);
      flex-shrink: 0;

      .popover-title { flex-shrink: 0; }

      .popover-close {
        margin-left: auto;
        cursor: pointer;
        color: #9ca3af;
        font-size: 16px;
        transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);
        padding: 2px;

        &:hover {
          color: var(--os-accent);
          transform: rotate(90deg);
        }
      }
    }

    .type-list {
      display: flex;
      flex-direction: column;
      gap: 4px;

      .type-item {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        background: #f8f9fa;
        border-radius: 6px;
        cursor: grab;
        transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);
        border: 1px solid var(--os-border);
        color: #6b7280;
        user-select: none;

        &:hover {
          background: var(--os-bg-hover);
          border-color: var(--os-border-strong);
          color: #4b5563;
        }

        &.type-filtered {
          background: var(--os-accent);
          color: white;
          border-color: var(--os-accent);
          box-shadow: none;

          .el-icon { color: white; }
          .type-count { background: rgba(255,255,255,0.3); color: white; }
        }

        .el-icon {
          font-size: 16px;
          flex-shrink: 0;
        }

        span {
          font-size: 12px;
          font-weight: 500;
        }

        .type-count {
          margin-left: auto;
          background: var(--os-border);
          color: #6b7280;
          padding: 0 5px;
          border-radius: 8px;
          font-size: 10px;
          min-width: 16px;
          text-align: center;
          line-height: 16px;
        }
      }
    }

    .type-hint {
      margin-top: 8px;
      font-size: 11px;
      color: #9ca3af;
      text-align: center;
      padding: 4px;
      background: var(--dsw-static-neutral-bluish-50);
      border-radius: 4px;
    }
  }

  /* 悬浮层过渡动画 */
  .type-popover-enter-active,
  .type-popover-leave-active {
    transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);
    transform-origin: top left;
  }
  .type-popover-enter-from,
  .type-popover-leave-to {
    opacity: 0;
    transform: translateY(-8px) scale(0.95);
  }

  /* ========== 中间：题目列表 ========== */
  .question-panel {
    flex: 1;
    min-width: 260px;
    background: transparent;
    border: none;
    border-right: 1px solid var(--os-border-soft);
    border-radius: 0;
    box-shadow: none;
    padding: 0 18px 0 0;
    display: flex;
    flex-direction: column;
    height: auto;
    position: relative;

    .panel-header {
      flex-shrink: 0;
      display: flex;
      /* 不换行：保证右侧操作区永远和标题在同一行 */
      flex-wrap: nowrap;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--os-border);
      position: relative;

      .panel-title {
        /* 普通 flex 项：占满剩余空间，宽度不够时收缩并按省略号截断 */
        flex: 1 1 auto;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        /* 空间充足时视觉上仍居中，保持原有观感 */
        text-align: center;
        font-size: 16px;
        font-weight: 600;
        color: var(--os-text);
        pointer-events: none;
      }

      /* 隐藏的测量元素：始终包含完整标题文案，用来判断能否完整显示 */
      .title-measure {
        position: absolute;
        left: 0;
        top: 0;
        visibility: hidden;
        white-space: nowrap;
        font-size: 16px;
        font-weight: 600;
        pointer-events: none;
      }

      .panel-actions {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-left: auto;
        flex-shrink: 0;
      }
    }

    .question-list {
      padding-right: 4px;

      .question-item {
        padding: 10px 14px;
        background: var(--dsw-static-neutral-bluish-50);
        border-radius: var(--os-radius-sm);
        margin-bottom: 8px;
        cursor: pointer;
        transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out);
        border: 1px solid transparent;

        &:hover {
          background: var(--os-bg-hover);
        }

        &.active {
          border-color: var(--os-accent);
          background: #f0f7ff;
          box-shadow: none;
        }

        .question-header {
          display: flex;
          align-items: center;
          margin-bottom: 6px;

          .question-index {
            width: 22px;
            height: 22px;
            background: var(--os-border);
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
            margin-right: 8px;
          }

          .question-type {
            flex: 1;
            font-size: 12px;
            padding: 2px 6px;
            border-radius: 4px;
            display: inline-block;
            width: fit-content;

            &.type-single { background: #e8f5e9; color: #2e7d32; }
            &.type-multiple { background: #e3f2fd; color: #1565c0; }
            &.type-judge { background: #fff3e0; color: #e65100; }
            &.type-fill { background: #f3e5f5; color: #7b1fa2; }
            &.type-essay { background: #fce4ec; color: #c62828; }
            &.type-composite { background: #e0f2f1; color: #00695c; }
          }

          .drag-handle {
            cursor: grab;
            color: #9ca3af;
          }
        }

        .question-preview {
          font-size: 13px;
          color: var(--os-text);
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          text-overflow: ellipsis;
          word-break: break-all;
        }

        .question-actions {
          text-align: right;
          margin-top: 4px;
        }
      }
    }

    .empty-tip {
      padding: 40px 0;
      text-align: center;
      color: #9ca3af;
      font-size: 14px;
    }

    .question-pagination {
      flex-shrink: 0;
      padding-top: 10px;
      border-top: 1px solid var(--os-border);
      margin-top: auto;
      display: flex;
      justify-content: center;

      :deep(.el-pagination) {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        justify-content: center;
        gap: 8px 4px;
        width: 100%;

        .el-pagination__total {
          order: 1;
          margin: 0;
          font-size: 12px;
          white-space: nowrap;
        }

        .el-pagination__sizes {
          order: 2;
          margin: 0;

          .el-select {
            width: 80px;
          }
        }

        .el-pager {
          order: 3;
          display: flex;
          align-items: center;
          gap: 2px;
          flex-wrap: nowrap;

          li {
            min-width: 28px;
            height: 28px;
            line-height: 28px;
            font-size: 13px;
          }
        }

        .btn-prev,
        .btn-next {
          order: 4;
          min-width: 28px;
          height: 28px;
          line-height: 28px;
          padding: 0;
          margin: 0;
        }

        .el-pagination__jump {
          order: 5;
          margin: 0;
          font-size: 12px;
          white-space: nowrap;
        }
      }
    }
  }

  /* ========== 右侧：题目编辑 ========== */
  .edit-panel {
    flex: 0 0 440px;
    width: 440px;
    min-width: 440px;
    background: transparent;
    border: none;
    border-radius: 0;
    box-shadow: none;
    padding: 0 0 0 18px;
    display: flex;
    flex-direction: column;
    /*
     * 原来是固定 `min-height: 700px`：列表为空时右侧编辑区也是一片 700px 高的空白，
     * 而左栏那条 `border-right` 会跟着一起拉长 —— 于是页尾出现一条**贯穿到
     * 「发布设置」旁边**的竖线（用户 2026-10-18 截图反馈）。
     * 改成按内容自适应，只在真的需要时（可选 320px 最矮）撑开。
     */
    min-height: 320px;
    height: auto;

    .panel-title {
      flex-shrink: 0;
      font-size: 16px;
      font-weight: 600;
      color: var(--os-text);
      padding-bottom: 10px;
      border-bottom: 1px solid var(--os-border);
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;

      .el-button {
        border-radius: 8px;
      }
    }

    .edit-form {
      padding-right: 4px;

      .el-form-item {
        margin-bottom: 14px;
      }

      .json-hint {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 4px;
      }

      .options-visual-editor {
        .option-item {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          flex-wrap: wrap;

          .option-letter {
            width: 24px;
            font-weight: bold;
            color: var(--os-accent);
          }

          :deep(.el-input__wrapper) {
            border-radius: 8px;
          }
        }
      }

      .sub-questions-container {
        border: 1px solid var(--os-border);
        border-radius: 8px;
        padding: 10px;
        background: var(--dsw-static-neutral-bluish-50);

        .sub-toolbar {
          display: flex;
          gap: 8px;
          margin-bottom: 10px;
          align-items: center;
          flex-wrap: wrap;

          .sub-hint {
            font-size: 12px;
            color: #9ca3af;
            margin-left: 8px;
          }
        }

        .sub-list {
          display: flex;
          flex-direction: column;
          gap: 10px;

          .sub-question-card {
            background: white;
            border-radius: 8px;
            padding: 10px;
            border: 1px solid var(--os-border);

            .sub-header {
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 8px;
              flex-wrap: wrap;

              .drag-handle {
                cursor: grab;
                color: #9ca3af;
              }

              .sub-index {
                font-weight: 500;
                font-size: 13px;
              }
            }

            .sub-body {
              display: flex;
              flex-direction: column;
              gap: 8px;

              .sub-options-label,
              .sub-answer-label {
                font-size: 13px;
                font-weight: 500;
                margin-bottom: 4px;
              }

              .sub-answer-control {
                margin-top: 4px;
              }

              .sub-score-area {
                margin-top: 10px;
                padding-top: 8px;
                border-top: 1px dashed #e4e7ed;
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;

                .score-label {
                  font-size: 13px;
                  font-weight: 500;
                  color: var(--os-text-2);
                }

                .score-unit {
                  font-size: 12px;
                  color: var(--os-text-3);
                }
              }
            }
          }
        }

        .empty-sub {
          text-align: center;
          color: #999;
          padding: 20px;
        }
      }
    }

    .empty-tip {
      padding: 80px 0;
      text-align: center;
      color: #bbb;
      font-size: 14px;
    }

    .question-tiptap-wrapper {
      width: 100%;

      :deep(.tiptap-editor) {
        min-height: 120px;
        border-radius: 8px;
      }

      :deep(.editor-content) {
        padding: 10px 14px;
        min-height: 80px;
      }
    }

    .composite-tiptap {
      :deep(.tiptap-editor) {
        min-height: 180px;
      }
    }

    .sub-tiptap-wrapper {
      margin-bottom: 8px;

      :deep(.tiptap-editor) {
        min-height: 80px;
        border-radius: 8px;
        border-color: var(--os-border);
      }

      :deep(.editor-toolbar) {
        padding: 4px 6px;

        .toolbar-btn {
          width: 26px;
          height: 26px;
        }
      }

      :deep(.editor-content) {
        padding: 8px 12px;
        min-height: 50px;
        font-size: 14px;
      }
    }
  }

  /* ========== 响应式设计 ========== */

  @media screen and (min-width: 1600px) {
    .edit-panel {
      flex: 0 0 480px;
      width: 480px;
      min-width: 480px;
    }
  }

  @media screen and (min-width: 1280px) and (max-width: 1599px) {
    .edit-panel {
      flex: 0 0 440px;
      width: 440px;
      min-width: 440px;
    }
  }

  @media screen and (min-width: 900px) and (max-width: 1279px) {
    .edit-panel {
      flex: 0 0 360px;
      width: 360px;
      min-width: 360px;
    }
  }

  @media screen and (max-width: 899px) {
    flex-wrap: wrap;

    .question-panel {
      flex: 1 1 100%;
      width: 100%;
      min-width: 100%;
    }

    .edit-panel {
      flex: 1 1 100%;
      width: 100%;
      min-width: 100%;
      margin-top: 16px;
    }
  }
}

.options-editor {
  .option-item {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;

    .option-letter {
      width: 24px;
      font-weight: bold;
      color: var(--os-accent);
    }
  }
}

.ai-generate-dialog {
  :deep(.el-dialog) {
    border-radius: var(--os-radius);
  }

  :deep(.el-dialog__body) {
    padding: 20px 24px;
  }
}

.form-hint {
  font-size: 12px;
  color: var(--os-text-3);
  margin-top: 4px;
}

.prompt-history {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--dsw-static-neutral-bluish-50);
  border-radius: 8px;

  .history-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .history-title {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: var(--os-text-2);
    font-weight: 500;
  }

  .history-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;

    .history-tag-wrapper {
      position: relative;
      display: inline-block;
      transition: transform 0.2s ease;

      &:hover {
        transform: translateY(-2px);
      }

      .history-tag {
        cursor: pointer;
        max-width: 200px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        padding-right: 24px;
        transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);
        border: 1px solid transparent;

        &:hover {
          background: #ecf5ff !important;
          border-color: var(--os-accent) !important;
          color: var(--os-accent) !important;
        }
      }

      .history-tag-delete {
        position: absolute;
        top: 50%;
        right: 6px;
        transform: translateY(-50%);
        width: 18px;
        height: 18px;
        background: transparent;
        color: var(--os-text-3);
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        opacity: 0;
        transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);

        .el-icon {
          font-size: 12px;
        }

        &:hover {
          background: #f56c6c;
          color: white;
        }
      }

      &:hover .history-tag-delete {
        opacity: 1;
      }
    }
  }
}

.ai-fixed-dialog {
  :deep(.el-dialog) {
    display: flex;
    flex-direction: column;
    max-height: 85vh;
    overflow: hidden;
  }

  :deep(.el-dialog__header) {
    flex-shrink: 0;
  }

  :deep(.el-dialog__body) {
    flex: 1;
    overflow: hidden;
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
  }

  :deep(.el-dialog__footer) {
    flex-shrink: 0;
    padding: 16px 24px;
    border-top: 1px solid #e4e7ed;
    background: #fff;
  }

  .dialog-scroll-area {
    flex: 1;
    overflow-y: auto;
    padding-right: 8px;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-track {
      background: var(--dsw-static-neutral-bluish-50);
      border-radius: 3px;
    }

    &::-webkit-scrollbar-thumb {
      background: var(--os-border);
      border-radius: 3px;

      &:hover {
        background: #c0c4cc;
      }
    }
  }
}

.stream-container-new {
  margin-top: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafbfc;
  overflow: hidden;

  .stream-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    background: var(--dsw-static-neutral-bluish-50);
    border-bottom: 1px solid #e4e7ed;

    .stream-status-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .stream-actions-right {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;

      &.generating {
        background: #67c23a;
        animation: soft-pulse 1.5s infinite;
      }

      &.completed {
        background: #67c23a;
      }
    }

    .status-text {
      font-size: 13px;
      color: var(--os-text-2);
      font-weight: 500;
    }
  }

  .stream-body-new {
    position: relative;
    padding: 16px 18px;
    max-height: 350px;
    overflow-y: auto;
    background: #fff;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-track {
      background: var(--dsw-static-neutral-bluish-50);
      border-radius: 3px;
    }

    &::-webkit-scrollbar-thumb {
      background: var(--os-border);
      border-radius: 3px;

      &:hover {
        background: #c0c4cc;
      }
    }
  }

  .stream-content {
    margin: 0;
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
    font-size: 14px;
    line-height: 1.8;
    color: #1a1a1a;
    white-space: pre-wrap;
    word-break: break-word;

    &.streaming {
      border-left: 3px solid var(--os-accent);
      padding-left: 12px;
      animation: stream-pulse 1.5s ease-in-out infinite;
    }
  }

  @keyframes stream-pulse {

    0%,
    100% {
      border-left-color: var(--os-accent);
    }

    50% {
      border-left-color: #a0cfff;
    }
  }

  @keyframes soft-pulse {

    0%,
    100% {
      opacity: 1;
    }

    50% {
      opacity: 0.5;
    }
  }

  .pretty-preview {
    padding: 4px 0;

    .preview-question-card {
      background: #fff;
      border-radius: var(--os-radius);
      padding: 16px;
      margin-bottom: 16px;
      border: 1px solid #e4e7ed;
      box-shadow: none;
      transition: box-shadow 0.2s;

      &:hover {
        box-shadow: none;
      }

      .preview-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 14px;

        .preview-index {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 26px;
          height: 26px;
          background: linear-gradient(135deg, var(--os-accent), #66b1ff);
          color: white;
          border-radius: 8px;
          font-weight: bold;
          font-size: 13px;
          box-shadow: none;
        }

        .preview-score {
          margin-left: auto;
          color: var(--os-text-3);
          font-size: 13px;
          font-weight: 500;
        }
      }

      .preview-body {
        .preview-question {
          font-weight: 500;
          font-size: 15px;
          margin-bottom: 16px;
          line-height: 1.7;
          color: #303133;
        }

        .preview-options {
          margin-bottom: 14px;

          .preview-option {
            display: flex;
            align-items: center;
            padding: 10px 14px;
            margin-bottom: 8px;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #ebeef5;
            transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);

            &.is-correct {
              background: #f0f9eb;
              border-color: #b3e19d;
              border-left: 4px solid #67c23a;
            }

            .option-letter {
              font-weight: 700;
              margin-right: 14px;
              color: var(--os-text-2);
              min-width: 20px;
            }

            .option-text {
              flex: 1;
              color: #303133;
            }

            .correct-icon {
              margin-left: 8px;
              color: #67c23a;
              font-size: 16px;
            }
          }
        }

        .preview-answer {
          margin-bottom: 14px;
          padding: 10px 14px;
          background: #f0f7ff;
          border-radius: 8px;

          .answer-label {
            font-weight: 600;
            color: #303133;
            margin-right: 8px;
          }

          .answer-value {
            color: var(--os-accent);
            font-weight: 500;
          }
        }

        .preview-analysis {
          color: var(--os-text-3);
          font-size: 13px;
          padding-top: 14px;
          margin-top: 4px;
          border-top: 1px dashed #e4e7ed;

          .analysis-label {
            font-weight: 600;
            color: var(--os-text-2);
            margin-right: 8px;
          }

          .analysis-text {
            line-height: 1.6;
          }
        }
      }
    }

    .composite-preview {
      .composite-passage {
        background: #f9fafc;
        padding: 18px;
        border-radius: var(--os-radius);
        margin-bottom: 24px;
        border: 1px solid #e4e7ed;

        .passage-title {
          display: flex;
          align-items: center;
          font-weight: 700;
          margin-bottom: 14px;
          color: #303133;
          font-size: 15px;
        }

        .passage-content {
          line-height: 1.9;
          white-space: pre-wrap;
          color: #303133;
          font-size: 14px;
        }
      }

      .sub-questions-list {
        .sub-title {
          display: flex;
          align-items: center;
          font-weight: 700;
          margin-bottom: 18px;
          color: #303133;
          font-size: 15px;
        }

        .sub-question-card {
          background: #fff;
          border-radius: var(--os-radius);
          padding: 16px;
          margin-bottom: 16px;
          border: 1px solid #e4e7ed;
          box-shadow: none;

          .sub-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 14px;

            .sub-index {
              display: inline-flex;
              align-items: center;
              justify-content: center;
              width: 26px;
              height: 26px;
              background: linear-gradient(135deg, #e6a23c, #ebb563);
              color: white;
              border-radius: 8px;
              font-weight: bold;
              font-size: 13px;
            }

            .sub-score {
              margin-left: auto;
              color: var(--os-text-3);
              font-size: 13px;
              font-weight: 500;
            }
          }

          .sub-question {
            font-weight: 500;
            font-size: 14px;
            margin-bottom: 16px;
            line-height: 1.7;
            color: #303133;
          }

          .sub-options {
            margin-bottom: 14px;

            .preview-option {
              display: flex;
              align-items: center;
              padding: 10px 14px;
              margin-bottom: 8px;
              background: #f8fafc;
              border-radius: 8px;
              border: 1px solid #ebeef5;

              &.is-correct {
                background: #f0f9eb;
                border-color: #b3e19d;
                border-left: 4px solid #67c23a;
              }

              .option-letter {
                font-weight: 700;
                margin-right: 14px;
                color: var(--os-text-2);
                min-width: 20px;
              }

              .option-text {
                flex: 1;
              }

              .correct-icon {
                margin-left: 8px;
                color: #67c23a;
              }
            }
          }

          .sub-answer {
            margin-bottom: 14px;
            padding: 10px 14px;
            background: #f0f7ff;
            border-radius: 8px;

            .answer-label {
              font-weight: 600;
              color: #303133;
              margin-right: 8px;
            }

            .answer-value {
              color: var(--os-accent);
              font-weight: 500;
            }
          }

          .sub-analysis {
            color: var(--os-text-3);
            font-size: 13px;
            padding-top: 14px;
            border-top: 1px dashed #e4e7ed;

            .analysis-label {
              font-weight: 600;
              color: var(--os-text-2);
              margin-right: 8px;
            }

            .analysis-text {
              line-height: 1.6;
            }
          }
        }
      }
    }
  }

  .context-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    margin-bottom: 16px;
    background: var(--dsw-static-neutral-bluish-50);
    border-radius: 8px;

    .context-info {
      display: flex;
      align-items: center;
      gap: 8px;

      .context-bank-name {
        font-weight: 500;
        color: #303133;
      }
    }
  }

  .kb-context-bar {
    margin-top: 8px;
  }

  .kb-hint {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--os-text-3);
    margin-top: 6px;
    margin-bottom: 16px;
    padding: 8px 12px;
    background: var(--dsw-static-neutral-bluish-50);
    border-radius: 8px;
  }
}
</style>
