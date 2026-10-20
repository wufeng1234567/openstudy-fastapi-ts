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
        <!--
          分页器
          ⚠️ `small` 在 Element Plus 3.0 将移除，改用 `size="small"`。
             旧写法每次进题库搭建页都会刷
             `[el-pagination] small is about to be deprecated`（2026-10-18 实测）。
        -->
        <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :total="allFilteredQuestions.length"
          :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" size="small" @size-change="handleSizeChange"
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
                <el-radio v-for="(opt, idx) in currentQuestion.options" :key="idx" :value="idx">
                  {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                </el-radio>
              </el-radio-group>
              <el-checkbox-group v-else-if="currentQuestion.type === 'multiple'" v-model="currentQuestion.answer">
                <el-checkbox v-for="(opt, idx) in currentQuestion.options" :key="idx" :value="idx">
                  {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                </el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-else-if="currentQuestion.type === 'judge'" v-model="currentQuestion.answer">
                <el-radio :value="true">正确</el-radio>
                <el-radio :value="false">错误</el-radio>
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
                              <el-radio v-for="(opt, idx) in sub.options" :key="idx" :value="idx">
                                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                              </el-radio>
                            </el-radio-group>
                          </div>
                          <div v-else-if="sub.type === 'multiple'" class="sub-answer-control">
                            <el-checkbox-group v-model="sub.answer" size="small">
                              <el-checkbox v-for="(opt, idx) in sub.options" :key="idx" :value="idx">
                                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
                              </el-checkbox>
                            </el-checkbox-group>
                          </div>
                          <div v-else-if="sub.type === 'judge'" class="sub-answer-control">
                            <el-radio-group v-model="sub.answer" size="small">
                              <el-radio :value="true">正确</el-radio>
                              <el-radio :value="false">错误</el-radio>
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
          <!--
            题型选择
            ==================================================================
            2026-10-20 第二轮调整（用户纠正）：
              「知识库也好 文档也好 都是一个附加选项而非强迫选项
               并且知识库和文档应该是一个全局共用 无论是哪种题型都可以用到」
              「名字也改掉 不要叫从材料出题 应该叫做自定义出题
               也就是材料是附加选项 主要根据用户的提问进行出题
               比如用户想要3道选择两道填空5道判断这样的 一次性出多种题型
               而不是像原本那样只能出固定的题型」

            所以 `custom` 的语义是「**自定义出题**」：
              用户用一句话描述要什么（题型/数量/难度/范围），AI 照办。
              它替代不了「固定题型」—— 后者是"给我 10 道单选题"这种快速场景，
              一秒钟就能点完；而自定义需要打字。两者并存，不是彼此替代。
          -->
          <el-form-item label="题型" prop="questionType">
            <el-select v-model="aiForm.questionType" style="width: 100%" @change="onAiTypeChange">
              <el-option label="单选题" value="single" />
              <el-option label="多选题" value="multiple" />
              <el-option label="判断题" value="judge" />
              <el-option label="填空题" value="fill" />
              <el-option label="简答题" value="essay" />
              <el-option label="组合题（大题套小题）" value="composite" />
              <!-- 自定义出题：一句话描述需求，可混合多种题型 -->
              <el-option label="自定义出题（可混合多种题型）" value="custom">
                <span class="opt-with-hint">
                  自定义出题
                  <span class="opt-hint">一句话描述需求</span>
                </span>
              </el-option>
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

          <!--
            自定义出题（questionType === 'custom'）—— 以用户的需求描述为主
            ==================================================================
            2026-10-20 用户纠正后重做：
              「应该叫做自定义出题 也就是材料是附加选项 主要根据用户的提问进行出题
               比如用户想要3道选择两道填空5道判断这样的 一次性出多种题型
               而不是像原本那样只能出固定的题型」

            和「固定题型」的分工：
              · 固定题型 = "给我 10 道单选题"，点两下就完事 → 高频、快
              · 自定义   = "3 道选择 + 2 道填空 + 5 道判断，难度偏难" → 灵活、一次成型
            两者并存，不是用后者替代前者。

            ⚠️ 这里的「数量」不起作用：总题数由需求描述决定（用户可能分别要求
               3+2+5）。硬塞一个"生成数量"会让人以为要填总数，反而更困惑。
          -->
          <template v-if="aiForm.questionType === 'custom'">
            <el-form-item label="出题需求" prop="customRequirement">
              <el-input v-model="aiForm.customRequirement" type="textarea" :rows="5"
                placeholder="用一句话说清你要什么。例如：&#10;· 3 道单选题 + 2 道填空题 + 5 道判断题，关于 Java 多态&#10;· 5 道判断题，难度偏难，重点考异常处理&#10;· 2 道简答题，每题 10 分，关于数据库事务"
                :disabled="aiGenerating" maxlength="500" show-word-limit />
              <div class="form-hint">
                可以直接写多种题型和各自数量，AI 会按你的要求分批生成。
              </div>
            </el-form-item>
          </template>

          <!-- 普通题型配置 -->
          <template v-else-if="aiForm.questionType !== 'composite'">
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

          <!--
            素材来源（全局附加项）
            ==================================================================
            2026-10-20 用户纠正后重做：
              「知识库也好 文档也好 都是一个附加选项而非强迫选项
               并且知识库和文档应该是一个全局共用 无论是哪种题型都可以用到」

            所以它从"custom 专属面板"变成了**任何题型都能展开的附加区块**：
              · 默认**收起**（`el-collapse`）—— 素材是加分项，不该每次都占满屏幕，
                更不该让人以为"不出题就不能生成"；
              · 标题里用「可选」明确表态；
              · 展开后能选知识库 / 传文档，两者可同时用；
              · 完全不影响固定题型的原有流程 —— 不展开就和以前一模一样。

            数据怎么用（见 `handleAiGenerate`）：
              · 知识库 → 作为 `kbIds` 交给后端检索，命中片段自动注入提示词；
              · 文档   → 前端已解析成文本，拼进提示词正文。
            ⚠️ 这里有素材就给、没有就纯 AI 生成 —— **绝不拦截**。
          -->
          <el-collapse v-model="materialPanelOpen" class="material-collapse">
            <el-collapse-item name="material">
              <template #title>
                <div class="material-collapse__title">
                  <el-icon class="material-collapse__icon"><FolderOpened /></el-icon>
                  <span>参考素材（可选）</span>
                  <!-- 收起时也能一眼看到"已经选了什么"，不用展开确认 -->
                  <span class="material-collapse__badge" v-if="materialSummaryText">
                    {{ materialSummaryText }}
                  </span>
                </div>
              </template>

              <div class="material-block">
                <!-- 来源一：知识库 -->
                <div class="material-field">
                  <div class="material-field__label">从知识库取材</div>
                  <div class="material-row">
                    <el-select v-model="aiForm.kbIds" multiple filterable clearable collapse-tags
                      collapse-tags-tooltip placeholder="选择一个或多个知识库（可不选）"
                      style="flex: 1" :disabled="aiGenerating" :loading="kbLoading">
                      <el-option v-for="kb in kbList" :key="kb.id" :label="kb.kbName || kb.name"
                        :value="kb.id">
                        <span class="kb-option">
                          <span class="kb-option__name">{{ kb.kbName || kb.name }}</span>
                          <span class="kb-option__meta" v-if="kb.documentCount !== undefined">
                            {{ kb.documentCount }} 篇
                          </span>
                        </span>
                      </el-option>
                    </el-select>
                    <el-button size="small" text :loading="kbLoading" @click="loadKnowledgeBases">
                      刷新
                    </el-button>
                  </div>
                  <div class="form-hint" v-if="kbList.length === 0 && !kbLoading">
                    还没有知识库。<router-link to="/front/agent/chat" class="material-link">
                      在对话里让助手帮你建一个
                    </router-link>，或直接用下面的文档上传。
                  </div>
                  <div class="form-hint" v-else-if="aiForm.kbIds.length">
                    已选 {{ aiForm.kbIds.length }} 个知识库，出题时会检索其中的相关内容并把出处标在解析里。
                  </div>
                </div>

                <!--
                  来源二：上传文件（文档 + 图片，自动识别）
                  ==================================================
                  2026-10-20 用户补充要求：
                    「要支持图片上传出题 复用一个上传路径自动识别用户上传的是文档还是图片
                     并且也要有对应的文件和图片预览 可以点击查看显示 方便用户自己查看
                     要使用系统有的组件 复用 不要乱写」

                  所以这里**只有一个上传入口**，靠 `isDocFile()` 自动分流：
                    · 文档（docx/pdf/txt/md）→ `parseDocFile` 解析成纯文本
                    · 图片（png/jpg/webp…）  → 直接读成 data URL，作为视觉素材
                  用户不需要先想"这是哪种"，拖进来就行。

                  预览复用系统既有模式（与 `AiQuestionBuilder.vue` 一致）：
                    `el-image` + `:preview-src-list` → 点击放大。
                -->
                <div class="material-field">
                  <div class="material-field__label">上传文档或图片</div>
                  <el-upload drag :auto-upload="false" :show-file-list="false" multiple
                    :accept="MATERIAL_ACCEPT" :on-change="handleMaterialFileChange"
                    :disabled="aiGenerating" class="material-upload">
                    <div class="material-upload__inner">
                      <el-icon class="material-upload__icon"><Upload /></el-icon>
                      <div class="material-upload__text">
                        拖入 <em>Word / PDF / Markdown / TXT</em> 或 <em>图片</em>，或点击选择
                      </div>
                      <div class="material-upload__hint">
                        自动识别类型；文件只在本次生成时作为素材，不会存进知识库
                      </div>
                    </div>
                  </el-upload>

                  <!--
                    已添加素材清单
                    · 文档项：图标 + 字符数 + 「查看」按钮
                    · 图片项：缩略图，点击直接放大

                    ⚠️ 为什么文档必须有「查看」（2026-10-20 用户反馈「文档没法预览」）：
                      我第一版只给图片做了预览，文档只有一个图标和字符数。
                      用户传完一份 PDF 后，唯一的确认手段是"看字符数"——
                      但字符数不能说明"是不是解析对了、内容对不对"。
                      素材要用它出题，**能看见内容**是这个功能能不能被信任的前提。
                  -->
                  <div v-if="materialItems.length" class="material-doc-list">
                    <div v-for="(item, i) in materialItems" :key="item.id" class="material-doc">
                      <!-- 图片：缩略图，点击可全屏预览 -->
                      <el-image v-if="item.kind === 'image'" :src="item.imageUrl"
                        :preview-src-list="imagePreviewList" :initial-index="imagePreviewIndex(item.id)"
                        fit="cover" class="material-doc__thumb" preview-teleported hide-on-click-modal>
                        <template #error>
                          <div class="material-doc__thumb-err">
                            <el-icon><Picture /></el-icon>
                          </div>
                        </template>
                      </el-image>
                      <!-- 文档：类型图标 -->
                      <template v-else>
                        <el-icon class="material-doc__icon"><Document /></el-icon>
                        <span class="material-doc__name material-doc__name--clickable"
                          :title="item.fileName" @click="openDocPreview(item)">
                          {{ item.fileName }}
                        </span>
                        <span class="material-doc__meta">{{ item.content.length }} 字符
                          <template v-if="item.note"> · {{ item.note }}</template>
                        </span>
                        <el-button text size="small" type="primary" @click="openDocPreview(item)">
                          查看
                        </el-button>
                        <el-button text size="small" type="danger" :disabled="aiGenerating"
                          @click="removeMaterialItem(item.id)">
                          移除
                        </el-button>
                      </template>

                      <!-- 图片项的操作区（文档项已在上面单独渲染） -->
                      <template v-if="item.kind === 'image'">
                        <span class="material-doc__meta">图片</span>
                        <el-button text size="small" type="danger" :disabled="aiGenerating"
                          @click="removeMaterialItem(item.id)">
                          移除
                        </el-button>
                      </template>
                    </div>
                  </div>
                  <div v-if="materialParsing" class="material-parsing">
                    <el-icon class="is-loading"><Loading /></el-icon>
                    正在解析…
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!--
            文档内容预览（2026-10-20 用户反馈「文档没法预览」）

            ⚠️ 为什么必须有这个：用户传 PDF 是为了"让 AI 照这份材料出题"，
               如果看不见解析出来的内容，他无法确认
                 ① 文件真的读进来了（而不是只有个字符数）
                 ② 解析质量能接受（表格/公式有没有乱掉）
               看不见就等于不敢用 —— 素材功能会因此被弃用。

            实现刻意**对齐 `AiQuestionBuilder` 的解析结果对话框**（同一套形态：
            顶部统计条 + 大文本区 + 复制按钮），这样同一个系统里"看文档"的体验一致，
            用户不需要学两套。样式复用 `.parsed-dialog-*` 的思路，不另起一套命名。
          -->
          <el-dialog v-model="docPreviewVisible" :title="docPreviewTitle" width="80%" top="5vh"
            append-to-body class="material-doc-preview-dialog">
            <div class="material-preview-header">
              <el-tag type="success" size="small">{{ docPreviewContent.length }} 字符</el-tag>
              <el-tag v-if="docPreviewTruncated" type="warning" size="small">
                已截断到 {{ MATERIAL_MAX_CHARS }} 字符
              </el-tag>
              <el-button type="primary" size="small" style="margin-left: auto"
                @click="copyDocPreviewContent">
                <el-icon><DocumentCopy /></el-icon>
                复制文本
              </el-button>
            </div>

            <!--
              用 textarea + readonly 而不是 div：
                · 保留原文档的**换行与缩进**（出题很依赖段落结构）；
                · 用户可以手动选中局部文本复制（比只有一个"复制全部"按钮实用）。
            -->
            <el-input v-model="docPreviewContent" type="textarea" :rows="24" readonly
              resize="vertical" class="material-preview-body" />
          </el-dialog>

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
import { Rank, InfoFilled, Delete, Search, MagicStick, Plus, Loading, Close, CircleCheck, Check, QuestionFilled, EditPen, ChatDotRound, FolderOpened, DocumentCopy, ArrowDown, Clock, VideoPause, VideoPlay, Setting, FullScreen, Grid, RefreshLeft, Upload, Document, Picture } from '@element-plus/icons-vue'
import { generateQuestionsSync, generateReadingComprehensionSync } from '@/api/ai/ai'
import { ElMessage, ElNotification, ElMessageBox } from 'element-plus'
// 素材出题（questionType='custom'）要用知识库列表：拉用户自己的库供选择
import { listKnowledgeBases } from '@/api/ai/rag'
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

/**
 * AI 出题表单的默认值（**唯一来源**）
 *
 * ⚠️ 为什么要有这个工厂函数（2026-10-20 踩了坑才抽出来）：
 *   这个表单的字面量原来在文件里出现**两次** ——
 *   一次是 `aiForm` 的声明，一次是 `openAiDialog()` 里的整体替换。
 *   我加「素材出题」字段时只改了声明，忘了 `openAiDialog`，
 *   于是每次打开弹窗，新字段都被那次赋值**静默抹掉**：
 *     源码里有 `kbIds`、运行时 `Object.keys(aiForm)` 却没有。
 *   现象极像"dev server 给了旧代码"，害我查了一小时的构建缓存。
 *
 *   抽成工厂后，加字段只需要改这里一处，从根上消除这份重复。
 *   以后**不要**再在别处手写这个对象字面量。
 */
const createDefaultAiForm = () => ({
  questionType: 'single',
  knowledgePoint: '',
  count: 3,
  model: '',
  compositeRequirement: '',
  wordCount: 200,
  subCount: 5,
  /*
   * ↓ 素材出题（`questionType === 'custom'`）用到的字段
   *
   * kbIds / customRequirement 与上面的 knowledgePoint 是**并列的输入渠道**，
   * 不要合并：生成时它们会拼成不同段落注入提示词
   * （素材 → 作为 source_context；补充要求 → 追加在用户指令后面）。
   */
  /** 选中的知识库 id（多选，可空） */
  kbIds: [],
  /** 自由补充要求（难度/范围/风格…，可空） */
  customRequirement: ''
})

const aiForm = ref(createDefaultAiForm())

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
  }
  /*
   * 自定义出题（custom）：校验「出题需求」，不校验知识点/数量。
   *
   * ⚠️ 它现在是**唯一必填项** —— 用户必须说清要什么。
   *    而「参考素材」（知识库/文档）**完全不校验**：那是附加项
   *    （2026-10-20 用户明确纠正："知识库也好 文档也好 都是一个附加选项
   *     而非强迫选项"）。我上一版把素材做成必填，是错的。
   *
   *    所以这里只需要一条规则，也不要 count —— 自定义出题的题数
   *    由需求描述决定（用户可能分别要 3+2+5），再塞一个"数量"只会造成困惑。
   */
  if (aiForm.value.questionType === 'custom') {
    return {
      questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
      customRequirement: [
        { required: true, message: '请描述你要出什么题', trigger: 'blur' },
        { max: 500, message: '不能超过500个字符', trigger: 'blur' }
      ]
    }
  }
  return {
    questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
    knowledgePoint: [
      { required: true, message: '请输入知识点', trigger: 'blur' },
      { max: 200, message: '不能超过200个字符', trigger: 'blur' }
    ],
    count: [{ required: true, message: '请选择数量', trigger: 'change' }]
  }
})

const onAiTypeChange = () => {
  /*
   * 切换题型时**不清空参考素材**（知识库 kbIds / 已解析文档 materialDocs）。
   *
   * 2026-10-20 用户明确要求「知识库和文档应该是一个全局共用 无论是哪种题型
   * 都可以用到」—— 既然是全局附加项，它就不属于某一个题型，
   * 切题型把它清掉在语义上是矛盾的（用户从单选切到判断，
   * 难道"我刚才上传的讲义"就不算数了？）。
   *
   * 清空的是**题型专属的输入**：知识点 / 组合题要求。
   * 那是"这一次要生成的内容"，换了题型确实该重填。
   */
  if (aiForm.value.questionType === 'composite') {
    aiForm.value.compositeRequirement = ''
    aiForm.value.wordCount = 200
    aiForm.value.subCount = 5
  } else if (aiForm.value.questionType === 'custom') {
    // 自定义出题：需求描述由用户自己写，这里只清掉固定题型的知识点
    aiForm.value.knowledgePoint = ''
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

/* ============================================================================
 * 素材出题（questionType === 'custom'）
 * ============================================================================
 * 用户口径（2026-10-20）：「支持用户自己添加材料（并且要链接知识库 以及 可以支持
 *   直接上传word pdf md之类的文档直接创建对应的题库）…怎么方便用户使用 要有灵活性」
 *
 * 三条数据流：
 *   ① 知识库 id 列表 → 后端 `chat_engine` 检索原文注入提示词（已有能力，这次暴露出来）
 *   ② 上传的文档 → 前端解析成纯文本 → 拼进「补充说明」一起作为素材
 *   ③ 补充要求 → 自然语言约束（范围/难度/风格）
 *
 * 为什么文档走"前端解析 → 拼文本"，而不是"上传到知识库再检索"：
 *   · 用户要的是"就这份文件出题"，不是"在整个库里搜相关内容" ——
 *     语义不同：前者是**全文**作为素材，后者是**检索命中片段**。
 *   · 不落库 = 不污染用户的知识库（他只是想出几道题，不该多出一个库/文档）。
 *   · 也更快：上传到知识库要切块、建索引，等索引完成才能检索；
 *     而"出几道题"这种一次性需求不该等那么久。
 *   ⚠️ 代价是长文档会撑大提示词。所以下面有长度上限（`MATERIAL_MAX_CHARS`），
 *      超出时截断并**明确告知**用户截了多少，而不是静默丢内容。
 */
const MATERIAL_MAX_CHARS = 20000

/**
 * 素材上传接受的扩展名（文档 + 图片）
 *
 * 与 `handleMaterialFileChange` 里的自动识别配套：
 * 这里只是把文件选择器的筛子放宽，真正的分类靠 `isDocFile()` 判断，
 * 而不是靠这份字符串 —— 用户从"所有文件"里选也能正确分流。
 */
const MATERIAL_ACCEPT = '.txt,.md,.markdown,.pdf,.docx,.doc,image/*'

/** 知识库列表 */
const kbList = ref([])
const kbLoading = ref(false)

/**
 * 已添加的素材项
 *
 * 统一成一个数组，用 `kind` 区分：
 *   · `{ kind: 'doc',   fileName, content, note?, truncated? }`
 *   · `{ kind: 'image', fileName, imageUrl }`
 *
 * 为什么**不拆成两个数组**（我上一版是 docs + 隐式的图片）：
 *   用户拖进来的顺序是有意义的（"先看这份讲义，再参考这张图"），
 *   拆成两个数组就丢了顺序，拼接提示词时也只能按类型分组。
 *   一个数组 + kind 字段，顺序自然保留，UI 遍历也简单。
 */
const materialItems = ref([])
const materialParsing = ref(false)
/** 自增 id：给 v-for 做稳定 key（用 index 会在删除时错位，导致预览索引错乱） */
let materialSeq = 0

/**
 * 素材面板是否展开（`el-collapse` 的 v-model，用数组存展开项名字）
 *
 * 2026-10-20：默认**收起**。
 * 素材是附加项，不该每次都占满屏幕，更不该让人误以为"不给材料就不能生成"。
 */
const materialPanelOpen = ref<string[]>([])

/** 所有图片素材的 data URL 列表（给 el-image 的 preview-src-list 用，实现左右翻看） */
const imagePreviewList = computed(() =>
  materialItems.value.filter((it) => it.kind === 'image').map((it) => it.imageUrl)
)

/** 某张图片在预览列表里的下标（点击缩略图直接定位到它） */
const imagePreviewIndex = (itemId: number) => {
  const imgs = materialItems.value.filter((it) => it.kind === 'image')
  const idx = imgs.findIndex((it) => it.id === itemId)
  return idx < 0 ? 0 : idx
}

/** 是否已有可用素材 —— 只用于展示摘要，**不用于拦截生成** */
const hasMaterial = () =>
  aiForm.value.kbIds.length > 0 || materialItems.value.length > 0

/**
 * 素材摘要（收起状态下显示的角标）
 *
 * 为什么需要它：折叠收起后，用户看不到自己选了什么。
 * 如果不给摘要，他得每次展开确认 —— 而"我到底挂了哪些素材"
 * 恰恰是出题前最需要一眼确认的信息。
 */
const materialSummaryText = computed(() => {
  const parts: string[] = []
  if (aiForm.value.kbIds.length) parts.push(`${aiForm.value.kbIds.length} 个知识库`)
  const docCount = materialItems.value.filter((it) => it.kind === 'doc').length
  const imgCount = materialItems.value.filter((it) => it.kind === 'image').length
  if (docCount) parts.push(`${docCount} 份文档`)
  if (imgCount) parts.push(`${imgCount} 张图片`)
  return parts.join(' · ')
})

/** 加载知识库列表（进入 custom 模式时懒加载，避免每次打开弹窗都请求） */
const loadKnowledgeBases = async () => {
  if (kbLoading.value) return
  kbLoading.value = true
  try {
    const res = await listKnowledgeBases()
    const data = res?.data ?? res?.rows ?? res ?? []
    kbList.value = Array.isArray(data) ? data : (data.rows || [])
  } catch (e) {
    // 失败不阻断出题：用户仍然可以用上传文档这条路
    console.warn('[material] 加载知识库失败：', e)
    ElMessage.warning('知识库列表加载失败，可改用上传文档')
  } finally {
    kbLoading.value = false
  }
}

/**
 * 选中文件 → **自动识别**是文档还是图片，分别处理
 *
 * 2026-10-20 用户要求：
 *   「复用一个上传路径自动识别用户上传的是文档还是图片」
 *
 * 识别依据是 `isDocFile(name, type)`（`utils/doc-parse` 已有）：
 *   · MIME 以 `image/` 开头       → 图片
 *   · 扩展名属于 docx/doc/pdf/txt/md → 文档
 * 两者都不是 → 明确拒绝并说明支持什么，而不是默默忽略（用户会以为传上去了）。
 *
 * ⚠️ 这里是**追加**而不是替换：用户可能分几次拖入几份讲义，
 *    每次都替换会把前面的悄悄丢掉。
 */
const handleMaterialFileChange = async (uploadFile) => {
  const raw = uploadFile?.raw as File | undefined
  if (!raw) return
  materialParsing.value = true
  try {
    const { parseDocFile, isDocFile } = await import('@/utils/doc-parse')
    const { fileToDataUrl, compressImageDataUrl, dataUrlByteSize, humanSize } =
      await import('@/utils/image-compress')

    const isImage = raw.type.startsWith('image/')

    /* ── 分支一：图片 ─────────────────────────────────────────── */
    if (isImage) {
      /*
       * 图片素材：转 data URL → 压缩 → 存起来（预览 + 后续多模态都用它）。
       *
       * ⚠️ 必须压缩：手机拍的图动辄 3-8MB，base64 后还会膨胀 33%。
       *    不压缩会让内存/体积失控，发给模型时也容易被网关掐断
       *    （表现为"无法连接到页面"）。复用系统既有的 `compressImageDataUrl`，
       *    与 ChatFileUploader 同一套参数口径，视觉上几乎无损。
       */
      const before = await fileToDataUrl(raw)
      const after = await compressImageDataUrl(before)
      if (dataUrlByteSize(after) > 800 * 1024) {
        ElMessage.warning(`${raw.name} 压缩后仍有 ${humanSize(dataUrlByteSize(after))}，建议换小一点的图`)
      }
      materialItems.value.push({
        id: ++materialSeq,
        kind: 'image',
        fileName: raw.name || '图片',
        imageUrl: after
      })
      ElMessage.success(`已添加图片 ${raw.name || ''}`.trim())
      return
    }

    /* ── 分支二：文档 ─────────────────────────────────────────── */
    if (!isDocFile(raw.name, raw.type)) {
      ElMessage.warning(
        `不支持的文件类型：${raw.name}。请上传 Word / PDF / Markdown / TXT 或图片。`
      )
      return
    }

    /*
     * `parseDocFile(file)` 返回 `DocParse | null`：
     *   { fileName, textContent, blocks, images, totalTextLength, error? }
     *
     * ⚠️ 用 `textContent`（纯文本）而不是把 `blocks` 拼起来：
     *    blocks 是给**富预览**用的（含图片块），出题正文只需要文字。
     *    直接从 textContent 取，既省一次拼接，也避免把图片占位符混进提示词。
     */
    const parsed = await parseDocFile(raw)

    if (!parsed) {
      ElMessage.error(`${raw.name} 解析失败（可能是扫描件或纯图片 PDF）`)
      return
    }
    if (parsed.error) {
      ElMessage.error(`${raw.name} 解析出错：${parsed.error}`)
      return
    }

    let text = (parsed.textContent || '').trim()
    if (!text) {
      ElMessage.warning(`${raw.name} 里没有可用的文字内容（可能是扫描件或纯图片 PDF）`)
      return
    }

    // 截断保护：单份文件超限时截断，并记下"已截断"让 UI 说明
    let truncated = false
    if (text.length > MATERIAL_MAX_CHARS) {
      text = text.slice(0, MATERIAL_MAX_CHARS)
      truncated = true
    }

    materialItems.value.push({
      id: ++materialSeq,
      kind: 'doc',
      fileName: raw.name,
      content: text,
      note: truncated ? `已截断到 ${MATERIAL_MAX_CHARS} 字符` : '',
      truncated
    })
    ElMessage.success(`已读取 ${raw.name}`)
  } catch (e: any) {
    console.error('[material] 处理素材失败：', e)
    ElMessage.error(`处理 ${raw.name} 失败：${e?.message || '未知错误'}`)
  } finally {
    materialParsing.value = false
  }
}

const removeMaterialItem = (id: number) => {
  const i = materialItems.value.findIndex((it) => it.id === id)
  if (i >= 0) materialItems.value.splice(i, 1)
}

/* ── 文档内容预览（2026-10-20）────────────────────────────────────────
 *
 * 用户口径：「文档没法预览」。
 *
 * 三个状态就够了，不需要把 blocks 渲染成富文本：
 *   · `docPreviewVisible`  —— 对话框开关
 *   · `docPreviewTitle`    —— 标题带文件名（用户同时开了几份能分清）
 *   · `docPreviewContent`  —— 解析出的纯文本
 *
 * 为什么预览用**纯文本**而不是富块预览：
 *   出题真正吃进去的就是 `textContent`（见 `handleMaterialFileChange` 里的注释）。
 *   预览若显示另一种形态（带图片块的富文本），用户看到的内容和模型看到的内容
 *   就不一致 —— 那会让人误判"明明图里有字，为什么出的题不对"。
 *   **预览必须真实反映送进模型的东西**，这是可信度的基础。
 */
const docPreviewVisible = ref(false)
const docPreviewTitle = ref('文档内容')
const docPreviewContent = ref('')
const docPreviewTruncated = ref(false)

const openDocPreview = (item: { fileName: string; content: string; truncated?: boolean }) => {
  docPreviewTitle.value = item.fileName || '文档内容'
  docPreviewContent.value = item.content || ''
  docPreviewTruncated.value = !!item.truncated
  docPreviewVisible.value = true
}

const copyDocPreviewContent = async () => {
  try {
    await navigator.clipboard.writeText(docPreviewContent.value || '')
    ElMessage.success('已复制文档内容')
  } catch {
    // 非 https / 无权限时 clipboard 会失败，明确告知而不是静默
    ElMessage.error('复制失败，请手动选中文本复制')
  }
}

/**
 * 把**文档类**素材拼成一段给模型的上下文
 *
 * 输出格式刻意简单（纯文本 + 分隔标记），因为：
 *   · 模型对"用 === 分隔的文档段落"这种朴素结构理解得最好；
 *   · 出问题时用户/我们能直接看懂提示词里到底放了什么。
 *
 * ⚠️ 图片**不在这里拼**：
 *   图片不是文本，塞进字符串只会变成一串 base64 噪声。
 *   多模态模型需要的是结构化的 image 输入 —— 这块留待接入
 *   `assistant/stream` 的 images 通道（见返回值的 imageUrls）。
 *
 * ⚠️ 总长度也做上限：多份文档叠加可能远超单份上限。
 *    超出时**从末尾截断**（前面的文档完整保留），并返回 truncated 标记，
 *    由调用方决定怎么提示用户。
 */
const buildMaterialContext = () => {
  const parts: string[] = []
  materialItems.value
    .filter((it) => it.kind === 'doc')
    .forEach((doc, i) => {
      parts.push(`【材料 ${i + 1}：${doc.fileName}】\n${doc.content}`)
    })

  let text = parts.join('\n\n')
  let truncated = false
  if (text.length > MATERIAL_MAX_CHARS) {
    text = text.slice(0, MATERIAL_MAX_CHARS)
    truncated = true
  }

  // 图片单独返回，供调用方走多模态通道（不要混进 text）
  const imageUrls = materialItems.value
    .filter((it) => it.kind === 'image')
    .map((it) => it.imageUrl)

  return { text, truncated, imageUrls }
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
  /*
   * ⚠️⚠️ 这里必须与 `aiForm` 的初始声明保持**同一份字段集**（2026-10-20 踩过）。
   *
   * 这是「整体替换」而不是"逐个字段赋值"，所以任何在声明里加了、
   * 但这里漏掉的字段，都会在**每次打开弹窗时被静默抹掉**。
   *
   * 我当时只改了上面的声明（加了 kbIds / customRequirement），
   * 没同步这里，结果：
   *   · 改后的代码静态检查全过（字段确实在文件里）；
   *   · 但运行时 `Object.keys(aiForm)` 永远是 7 个旧字段；
   *   · 素材面板的 `v-if="aiForm.questionType === 'custom'"` 能进，
   *     可 `v-model="aiForm.kbIds"` 绑到一个不存在的属性上 ——
   *     表现就是"选中素材出题后，面板不出现/不工作"。
   * 排查花了一小时，因为"源码有、运行时没有"这个现象很容易被误判成
   * dev server 缓存问题（我一开始也确实这么怀疑）。
   *
   * 教训：**这类"初始化字面量"在文件里出现几次，就必须改几次。**
   * 如果以后字段继续增加，考虑抽成一个 `createDefaultAiForm()` 工厂函数，
   * 从根上消除这份重复。
   */
  /*
   * ⚠️ 用工厂函数，不要手写字面量（2026-10-20 踩过）：
   *   这里是「整体替换」`aiForm.value`，任何在 `createDefaultAiForm()` 里
   *   加了、这里却漏掉的字段，都会在每次打开弹窗时被静默抹掉 ——
   *   表现为"源码有、运行时没有"，极难排查。详见该工厂函数的注释。
   */
  aiForm.value = {
    ...createDefaultAiForm(),
    // 只有这里的 model 带记忆（上一次用的模型），其余走默认值
    model: localStorage.getItem('openstudy_ai_model_question-builder') || ''
  }
  /*
   * 每次打开弹窗都清空素材。
   *
   * 为什么**图片也一起清**：
   *   图片是压缩后的 data URL，体积可观（几百 KB 一张）。
   *   跨会话保留它们会白白占内存，而且用户很可能已经忘了上次挂过什么图
   *   —— 拿旧图出新题是比"要重传一次"更糟的体验。
   */
  materialItems.value = []
  materialParsing.value = false
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
  /*
   * ⚠️ 题型取值优先级（2026-10-20 修）：
   *   ① `aiQuestion.type` —— AI 为**每道题**标注的题型
   *   ② 调用方传的 `questionType` —— 整批统一题型
   *   ③ 兜底 'single'
   *
   * 为什么必须让 ① 优先：
   *   自定义出题（custom）允许**一次生成多种题型**（3 道选择 + 2 道填空…），
   *   后端模板已要求模型为每题输出 `type`。若这里仍用"整批的 questionType"，
   *   custom 模式下会得到一个 `type: 'custom'` 的非法题目 ——
   *   编辑器不认识它，预览会渲染成空白。
   *
   *   而固定题型场景下 `aiQuestion.type` 通常不存在（或与批次一致），
   *   所以 ② 仍然是实际生效的那一个，行为不变。
   */
  const resolvedType = mapAiTypeToInternal(
    aiQuestion?.type || aiQuestion?.questionType || questionType
  )
  const base = {
    id: newId,
    type: resolvedType,
    title: textToHtml(aiQuestion.question || aiQuestion.questionText || aiQuestion.title || ''),
    analysis: aiQuestion.analysis || '',
    score: 5
  }
  if (resolvedType === 'single' || resolvedType === 'multiple') {
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
    if (resolvedType === 'single') {
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
  } else if (resolvedType === 'judge') {
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
  /*
   * ⚠️ 这里**没有**素材必填校验（2026-10-20 用户纠正）。
   *
   * 我上一版写过一个拦截：没选知识库/没传文档就不许生成。
   * 用户明确否定：「知识库也好 文档也好 都是一个附加选项而非强迫选项」。
   *
   * 这个纠正是对的，而且我原来的理由（"怕用户以为材料被用上"）站不住：
   *   · 素材是**增强**，不是前提。绝大多数出题请求只需要一句"Java 多态"；
   *   · 强制填素材会把"点两下就能生成"变成"必须准备资料",
   *     正好劝退了最需要这个功能的人；
   *   · 真要避免误解，正确做法是**在生成时明确告诉用户用了什么**（见下方
   *     `materialUsedHint`），而不是不让他点。
   *
   * 现在：有素材就用，没有就纯 AI 生成，绝不拦截。
   */

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
      /*
       * 生成入口（固定题型 / 自定义出题 共用）
       * ==================================================================
       * 2026-10-20 第二轮重构。三条输入互相独立、全部可选：
       *   ① 知识点 / 需求描述  —— 必填（各题型各自的输入来源）
       *   ② 参考素材（知识库 + 文档）—— **可选**，任何题型都能挂
       *   ③ kbIds —— 交给后端检索，命中片段自动注入提示词
       *
       * ★ 关键变化：素材从"custom 专属"变成"全局附加" ★
       *   上一版只有 custom 用得上素材，这是错的（用户明确纠正）。
       *   现在无论选单选/多选/判断，只要展开了「参考素材」并放了东西，
       *   就会一起送进提示词。没有就纯 AI 生成 —— **不拦截、不降级**。
       *
       * ★ custom 的语义 ★
       *   它不再是"从材料出题"，而是"按我的一句话描述出题"（可混合题型）。
       *   所以它向模型传的是 `requirement`（原始需求），
       *   而不是把需求揉进 knowledge_point —— 后端模板会据此走不同分支
       *   （见 `prompts._build_question_generate` 的 `question_type == 'custom'`）。
       */
      const isCustom = aiForm.value.questionType === 'custom'

      // ① 主体输入：自定义模式用需求描述，固定题型用知识点
      const mainInput = isCustom
        ? (aiForm.value.customRequirement || '').trim()
        : aiForm.value.knowledgePoint

      /*
       * ② 文档素材（前端已解析成文本）
       *
       * 拼在主体输入之后，作为**补充材料**而不是替代它 ——
       * 用户的描述永远是主角，材料是"顺便这些也参考"。
       * 这样即使材料解析得不好，也不会把用户的真实意图冲掉。
       */
      const { text: materialText, truncated, imageUrls } = buildMaterialContext()
      if (truncated) {
        ElMessage.warning(`材料较长，已截取前 ${MATERIAL_MAX_CHARS} 字符用于出题`)
      }

      let prompt = mainInput
      if (materialText) {
        prompt += '\n\n===== 参考材料开始 =====\n' + materialText + '\n===== 参考材料结束 =====' +
          '\n\n（如果上面的材料与出题要求相关，请优先依据材料内容出题，并在解析中标注出处；' +
          '材料未覆盖的部分可以按你的知识补充。）'
      }

      await generateQuestionsStreamFull({
        knowledgePoint: isCustom ? '' : prompt,
        questionType: isCustom ? 'custom' : aiForm.value.questionType,
        count: aiForm.value.count,
        model: aiForm.value.model,
        configId: selectedConfigId.value || undefined,
        userId: userId.value,
        thinking: deepThink.value,
        bankId: currentBankId.value,
        // 知识库取材：任何题型都可挂（后端检索后注入 source_context）
        kbIds: aiForm.value.kbIds.length ? aiForm.value.kbIds : undefined,
        // 自定义出题：把完整需求单独传给后端模板（它据此走 custom 分支）
        requirement: isCustom ? prompt : undefined,
        /*
         * 图片素材 → 多模态内容块（2026-10-20）
         *
         * ⚠️ 图片**不能**拼进 prompt：
         *   base64 塞进文本会变成几十万字符的噪声，模型既看不懂也浪费上下文。
         *   后端 `AssistantStreamRequest.images` 会把它们转成 image content block。
         *
         * ⚠️ 同时有图片和文档时，文档内容已在 prompt 里、图片走 images ——
         *   两条通道互补，不冲突。
         */
        images: imageUrls.length ? imageUrls : undefined,
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
  /* 两列等高（右栏跟着左栏的高度），避免右栏凭空多出空白 */
  align-items: stretch;
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
     * 高度交给 flex 的 `stretch`（父级 `.question-builder` 已 `align-items: stretch`），
     * 两列**同高**：左边多长、右边就多长。
     *
     * 历史：这里先后写过 `min-height: 700px` → `320px`，
     * 两次都是"右侧凭空多出一块空白"（空列表时尤其明显，用户 2026-10-18 反馈
     * 「发布设置那边太多空白」）。真正的原因就是**给容器设了最小高度**。
     * 所以现在不设 min-height，让内容决定；右侧"点击左侧题目进行编辑"那句
     * 自带一点上下留白，不至于塌成一条线。
     */
    min-height: 0;
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

/* ============================================================================
 * 素材出题（questionType === 'custom'）
 * ============================================================================
 * 视觉基调：**不像"上传控件"，而像"素材清单"**。
 *   用户此刻的心智是"我要用哪些材料出题"，所以重点是让他一眼确认
 *   「我已经放了什么」。上传区做成低存在感的虚线框，已解析的文档才是主体。
 */
.material-block {
  width: 100%;
}

.material-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

/* 知识库下拉里的单行：名称在左、篇数在右 */
.kb-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.kb-option__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-option__meta {
  flex: none;
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
}

.material-link {
  color: var(--os-accent, #409eff);
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

/* 上传区：克制。它是"添加素材"的入口，不该比素材列表更抢眼 */
.material-upload {
  :deep(.el-upload) {
    width: 100%;
  }

  :deep(.el-upload-dragger) {
    padding: 16px;
    border-radius: var(--os-radius, 8px);
    border: 1px dashed var(--os-border, rgba(0, 0, 0, 0.12));
    background: var(--os-bg-subtle, #fafafa);
  }

  :deep(.el-upload-dragger:hover) {
    border-color: var(--os-primary, #409eff);
    background: var(--os-bg-hover, #f5f6f7);
  }
}

.material-upload__inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.material-upload__icon {
  font-size: 20px;
  color: var(--os-text-4, #9ca3af);
}

.material-upload__text {
  font-size: 13px;
  color: var(--os-text-2);
}

.material-upload__hint {
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
}

/* 已解析文档清单 */
.material-doc-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-doc {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--os-radius-sm, 6px);
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
  background: var(--os-bg, #fff);
  font-size: 13px;
}

.material-doc__icon {
  flex: none;
  color: var(--os-text-3);
}

.material-doc__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--os-text);
}

.material-doc__meta {
  flex: none;
  margin-left: auto;
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
}

/*
 * 图片素材缩略图（2026-10-20）
 *
 * 32px 见方、圆角、可点击放大（点击行为由 el-image 的 preview-src-list 提供，
 * 与 AiQuestionBuilder 的配图预览是同一套，不另造弹窗）。
 * 用 `object-fit: cover`（模板里 fit="cover"）保证缩略图不变形。
 */
.material-doc__thumb {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: var(--os-radius-sm, 4px);
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
  cursor: zoom-in;
  background: var(--os-bg-subtle, #fafafa);
}

.material-doc__thumb-err {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--os-text-4, #9ca3af);
}

/*
 * 文档名可点击（打开预览）
 *
 * 只改可点击态的下划线与颜色，不改变尺寸 ——
 * 列表行高本来就被缩略图/图标撑到 32px，加下划线不会引起抖动。
 */
.material-doc__name--clickable {
  cursor: pointer;

  &:hover {
    color: var(--os-accent, #409eff);
    text-decoration: underline;
  }
}

/*
 * 文档预览对话框
 *
 * 与 `AiQuestionBuilder` 的「文档解析结果」保持同一形态（见模板注释），
 * 所以这里只补必要的间距，不重做视觉。
 */
.material-preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.material-preview-body {
  :deep(.el-textarea__inner) {
    font-family: var(--os-font-code, ui-monospace, SFMono-Regular, Menlo, monospace);
    font-size: 13px;
    line-height: 1.7;
    color: var(--os-text);
    background: var(--os-bg-subtle, #fafafa);
  }
}

.material-parsing {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--os-text-3);
}

/*
 * 素材折叠面板（全局附加项，2026-10-20）
 *
 * 视觉上要"轻"：它是可选增强，不能看起来像必填区块。
 * 用一条细边框 + 中性底色，和下面的「AI 模型」同层但更弱。
 */
.material-collapse {
  margin-bottom: 18px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
  border-radius: var(--os-radius, 8px);
  background: var(--os-bg-subtle, #fafafa);
  overflow: hidden;

  :deep(.el-collapse-item__header) {
    padding: 0 12px;
    height: 42px;
    border-bottom: none;
    background: transparent;
    font-size: 13px;
  }

  :deep(.el-collapse-item__wrap) {
    background: transparent;
    border-bottom: none;
  }

  :deep(.el-collapse-item__content) {
    padding: 0 12px 12px;
  }
}

.material-collapse__title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--os-text-2);
}

.material-collapse__icon {
  color: var(--os-text-4, #9ca3af);
}

/* 收起时也要能看到"已挂了多少素材" —— 见 materialSummaryText 的注释 */
.material-collapse__badge {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--os-accent-soft, #e8f0fe);
  color: var(--os-accent-strong, #1a56db);
  font-size: 12px;
  line-height: 18px;
}

.material-field {
  margin-bottom: 14px;

  &:last-child {
    margin-bottom: 0;
  }
}

.material-field__label {
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--os-text-2);
}

/* 题型下拉里的"自定义出题"：主文案 + 右侧小注解 */
.opt-with-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.opt-hint {
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
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
