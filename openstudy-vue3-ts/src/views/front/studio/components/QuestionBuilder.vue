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
              <!-- 公式按钮（2026-10-27）：Tiptap 是富文本，不能直接塞 MathInput，
                   所以挂一个按钮，点开面板后把公式插到光标处。 -->
              <div class="tiptap-math-bar">
                <button type="button" class="tip-math-btn" title="插入公式（点击打开符号面板）" @click="openMathForStem">
                  <span class="tip-fx">ƒx</span> 插入公式
                </button>
                <span class="tip-math-hint">数学符号不用手写，点开面板点符号即可</span>
              </div>
              <TiptapEditor ref="stemEditorRef" v-model="currentQuestion.title" placeholder="请输入题目内容，支持图片上传"
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
                <!--
                  ⚠️ 文案用 `historyContentOf(item)` 取值（2026-10-20 修）。
                  原来写的是 `item.knowledgePoint || item.compositeRequirement` ——
                  自定义出题记录这两个字段都是空串，标签会渲染成**空白小方块**，
                  用户根本不知道那条历史是什么、也点不到（没有可点区域）。
                  `historyContentOf` 会按题型取到 customRequirement，一并解决显示与回填。
                -->
                <el-tag class="history-tag" @click.native="applyHistoryPrompt(item)">
                  {{ truncateText(historyContentOf(item), 30) }}
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
                  <div class="material-field__label">从我的资料取材</div>
                  <div class="material-row">
                    <!--
                      ⚠️⚠️ 字段名必须用后端 `_kb_brief` 的真实输出（2026-10-20 修 422）
                      后端返回：{ kbId, name, description, docCount, chunkCount, ... }
                      我原来写的是 `kb.id` / `kb.kbName` / `kb.documentCount` —— 全都不存在：
                        · `:value="kb.id"` → **undefined** →
                          选中后 kbIds = [undefined]，
                          而后端 `kbIds: List[int]` 校验失败 → **HTTP 422**；
                        · 名称侥幸能用，是因为 `kb.kbName || kb.name` 有 `kb.name` 兜底；
                        · `docCount` 完全没显示（`kb.documentCount` 恒为 undefined）。
                      教训：跨端字段名不能想当然，要对着 service 的 `_brief()` 抄。
                    -->
                    <el-select v-model="aiForm.kbIds" multiple filterable clearable collapse-tags
                      collapse-tags-tooltip placeholder="选择一个或多个资料夹（可不选）"
                      style="flex: 1" :disabled="aiGenerating" :loading="kbLoading">
                      <el-option v-for="kb in kbList" :key="kb.kbId" :label="kb.name"
                        :value="kb.kbId">
                        <span class="kb-option">
                          <span class="kb-option__name">{{ kb.name }}</span>
                          <span class="kb-option__meta" v-if="kb.docCount !== undefined">
                            {{ kb.docCount }} 篇
                          </span>
                        </span>
                      </el-option>
                    </el-select>
                    <el-button size="small" text :loading="kbLoading" @click="loadKnowledgeBases({ silent: false })">
                      刷新
                    </el-button>
                  </div>
                  <div class="form-hint" v-if="kbList.length === 0 && !kbLoading">
                    还没有资料。<router-link to="/front/agent/chat" class="material-link">
                      在对话里让助手帮你建一个
                    </router-link>，或直接用下面的文档上传。
                  </div>
                  <div class="form-hint" v-else-if="aiForm.kbIds.length">
                    已选 {{ aiForm.kbIds.length }} 个资料夹，出题时会检索其中的相关内容并把出处标在解析里。
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

                  预览复用系统既有模式（`el-image` + `:preview-src-list` → 点击放大），
                  与站内其它图片预览保持一致。
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
                        自动识别类型；文件只在本次生成时作为素材，不会存进我的资料
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
                  <!--
                    解析中的等待提示（2026-10-20 用户反馈：
                      「上传文件没有那种上传加载的过程 比如上传pdf 或者word
                       就没有那种等待提示 图片上传到挺快的 可能和文件大小或者解析有关」）

                    为什么需要它、为什么原来不够：
                      原来只有一行小字「正在解析…」，而且**不带文件名**。
                      但 PDF/Word 要走「上传后端 → 解析 → 抽取文本」，
                      一份几十页的 PDF 可能等十几秒；图片则纯前端压缩，几乎瞬间完成。
                      两者耗时差两个数量级，用户只会觉得"我传了但没反应，是不是坏了"。

                    这一版做成**占据整行的进度条 + 文件名**：
                      · 进度条给"确实在动"的确定感（不确定进度用条纹动画）；
                      · 文件名让用户确认"在处理我传的那份"（多份时会连续出现）；
                      · 文案区分"上传/解析"两阶段，避免以为卡死。
                  -->
                  <div v-if="materialParsing" class="material-parsing-box">
                    <div class="material-parsing-box__head">
                      <el-icon class="is-loading"><Loading /></el-icon>
                      <span class="material-parsing-box__name">{{ materialParsingName || '文件' }}</span>
                      <span class="material-parsing-box__stage">{{ materialParsingStage }}</span>
                    </div>
                    <el-progress :percentage="100" :show-text="false" :stroke-width="3"
                      striped striped-flow :duration="12" class="material-parsing-box__bar" />
                    <div class="material-parsing-box__hint">
                      文档需要后端解析，页数越多越久；图片通常很快
                    </div>
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

            实现刻意**沿用站内既有的解析结果对话框形态**（同一套形态：
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
              <!--
                深度思考实时展示（2026-10-20）

                ★ 首字延迟的真相（实测数据，别再瞎猜）★
                  用户反馈「点击生成后还是等一会才会输出深度思考内容，
                    本地环境不应该卡这么久」。

                  我实测了三层（httpx 直连 / Vite 代理 / 浏览器 fetch）：
                    · 直连后端 9101     → 首个思考 **2.57s**，862 个分片
                    · 经 Vite 代理 3167 → 首个思考 **2.79s**，1865 个分片
                    代理只多 0.22s，**传输层没问题**，反缓冲头也生效了
                    （x-accel-buffering: no、无 gzip）。

                  那 2.5s 是**模型自己的推理启动时间**，本地环境也躲不掉
                  （要走网络到模型服务）。所以"提速"这条路走不通 ——
                  能做的是**让这 2.5s 可见**：用户看得见在等什么，就不觉得卡。

                ★ 三态设计 ★
                  ① 刚点下、还没收到任何思考 → 「已连接，等待模型响应 3s」
                     带**实际秒数**，这是本修复的核心：把不确定性变成确定性。
                  ② 收到思考增量        → 实时滚动显示推理正文。
                  ③ 收到正文            → 思考卡片自动折叠，把屏幕让给题目。
              -->
              <div v-if="aiGenerating && aiThinking" class="think-box">
                <div class="think-box__head" @click="aiThinkingOpen = !aiThinkingOpen">
                  <el-icon class="think-box__icon" :class="{ 'is-open': aiThinkingOpen }">
                    <ArrowDown />
                  </el-icon>
                  <span class="think-box__title">深度思考中…</span>
                  <span class="think-box__len">{{ aiThinking.length }} 字</span>
                </div>

                <!--
                  ⚠️ ref + @scroll 都必须有（2026-10-20 修「滚动条被自动往下压」）

                  用户口径：「深度思考的滚动条会不断自动往下面压 用户鼠标无法自由控制滚动
                    记住这里有个坑 要既可以让用户自由控制滚动条滚动
                    又要保证用户滚动到底部可以一直自由看到最新的输出内容」

                  ★ 这是经典的"智能跟随"问题，粗暴地每次滚到底会跟用户打架 ★

                  上一版无条件 `scrollTop = scrollHeight`，错在：
                    用户已经往上翻去看前面的推理了，下一片思考到达时
                    又把他拽回底部 —— 鼠标再怎么滚都没用。

                  正确做法（聊天软件的通用解法）：
                    · 维护 `thinkAutoFollow`（默认 true）；
                    · 用户**手动**滚动时判断：贴底 → 继续跟随；离开底部 → 停止跟随；
                    · 只有 `thinkAutoFollow` 为 true 时才自动滚到底；
                    · 用户重新滚回底部 → 自动恢复跟随（无需点按钮）。

                  这样两个诉求同时满足：翻历史时视图纹丝不动，
                  回到底部后又自动跟着新内容走。
                -->
                <div v-show="aiThinkingOpen" ref="thinkBoxRef" class="think-box__body"
                  @scroll="onThinkScroll">{{ aiThinking }}</div>
              </div>

              <!--
                生成中的占位提示

                ⚠️ 加了 `&& !aiThinking`（2026-10-20）：
                   思考内容已经在上面那块实时滚动了，这里再显示一行
                   「AI 正在生成题目，请稍候...」就是**两个等待提示并存**。
                   用户会疑惑"到底是在思考还是在生成"。
                   现在：有思考 → 只显示思考；没思考（模型不支持）→ 显示这句。

                ★ 带秒数（2026-10-20）★
                  实测模型推理启动约 2.5s（本地直连也一样，是模型侧耗时）。
                  原来这段时间只有静态的一行字，用户不知道要等多久。
                  现在显示**已等待秒数**，用户能看出"它在动、已经等了 7 秒"，
                  而不是"点了没反应"。秒数由 `aiWaitSeconds` 每秒自增。
              -->
              <pre v-if="aiGenerating && rawJsonContent" class="stream-content streaming">{{ rawJsonContent }}</pre>
              <div v-else-if="aiGenerating && !aiThinking" class="generating-tip">
                <el-icon class="is-loading">
                  <Loading />
                </el-icon>
                <span class="generating-tip__text">
                  正在等待模型响应…
                  <span class="generating-tip__sec">{{ aiWaitSeconds }}s</span>
                </span>
                <span v-if="aiWaitSeconds >= 8" class="generating-tip__hint">
                  首次调用需要预热模型，之后会快很多
                </span>
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
                    <!--
                      ── 混排：这一道是组合题（2026-10-20 方案 B）──────────────
                      一批题里可能既有普通题又有组合题，所以要**逐题分派**，
                      不能靠整批的 `isCompositePreview` 一刀切。

                      组合题的数据结构与普通题不同：
                        · 材料在 `q.content`（不是 `q.question`）
                        · 答案在 `q.subQuestions[]`（不是 `q.correctAnswer`）
                      所以必须单独一块模板，硬塞进普通题的编辑器只会渲染成空白。
                    -->
                    <template v-if="previewTypeOf(q) === 'composite'">
                      <div class="preview-header">
                        <span class="preview-index">{{ idx + 1 }}</span>
                        <el-tag size="small" type="warning">
                          {{ getTypeName('composite') }}
                        </el-tag>
                        <span class="preview-subcount">
                          共 {{ q.subQuestions?.length || 0 }} 道小题
                        </span>
                        <span class="preview-score">
                          <el-input-number v-model="q.score" :min="0" :max="100" size="small" style="width: 80px"
                            @change="updatePreviewData" /> 分
                        </span>
                      </div>

                      <div class="preview-body">
                        <div class="preview-passage-label">材料内容</div>
                        <el-input v-model="q.content" type="textarea" :rows="3" size="small"
                          placeholder="组合题的材料正文" @input="updatePreviewData" />

                        <div class="preview-sublist">
                          <div v-for="(sub, subIdx) in (q.subQuestions || [])" :key="subIdx" class="preview-subitem">
                            <div class="preview-subitem__head">
                              <span class="preview-sublabel">{{ idx + 1 }}.{{ subIdx + 1 }}</span>
                              <el-tag size="small">{{ getTypeName(previewTypeOf(sub)) }}</el-tag>
                            </div>
                            <el-input v-model="sub.question" type="textarea" :rows="2" size="small"
                              placeholder="小题题干" @input="updatePreviewData" />

                            <div v-if="['single', 'multiple'].includes(previewTypeOf(sub))" class="preview-options">
                              <div v-for="(opt, optIdx) in (sub.options || [])" :key="optIdx" class="preview-option">
                                <span class="option-letter">{{ String.fromCharCode(65 + optIdx) }}.</span>
                                <el-input v-model="sub.options[optIdx]" size="small" @input="updatePreviewData" />
                              </div>
                            </div>

                            <div class="preview-answer">
                              <span class="answer-label">答案：</span>
                              <el-input v-if="['fill', 'essay'].includes(previewTypeOf(sub))"
                                v-model="sub.correctAnswer" size="small" @input="updatePreviewData" />
                              <el-select v-else-if="previewTypeOf(sub) === 'single'" v-model="sub.correctAnswer"
                                size="small" @change="updatePreviewData">
                                <el-option v-for="(opt, optIdx) in (sub.options || [])" :key="optIdx"
                                  :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                              </el-select>
                              <el-select v-else-if="previewTypeOf(sub) === 'multiple'" v-model="sub.correctAnswer"
                                multiple size="small" @change="updatePreviewData">
                                <el-option v-for="(opt, optIdx) in (sub.options || [])" :key="optIdx"
                                  :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                              </el-select>
                              <el-switch v-else-if="previewTypeOf(sub) === 'judge'" v-model="sub.correctAnswer"
                                active-text="正确" inactive-text="错误" @change="updatePreviewData" />
                            </div>
                          </div>

                          <div v-if="!q.subQuestions || q.subQuestions.length === 0" class="preview-empty-hint">
                            这道组合题没有解析出小题，请检查原始 JSON
                          </div>
                        </div>
                      </div>
                    </template>

                    <!-- 普通题（原渲染，行为不变） -->
                    <template v-else>
                    <div class="preview-header">
                      <span class="preview-index">{{ idx + 1 }}</span>
                      <!--
                        ⚠️ 题型必须**逐题取** `previewTypeOf(q)`，不能用 `aiForm.questionType`
                        （2026-10-20 修）。

                        自定义出题一次会返回多种题型，各题 `type` 不同；
                        若这里统一读 `aiForm.questionType`（值是 `'custom'`）：
                          · 标签显示成 "custom"（不是任何真实题型名）；
                          · 下面的选项/答案分支全部匹配不上 → 选项框、答案框都不渲染，
                            用户看到"答案：解析："后面一片空白，以为生成失败了。
                        固定题型下 `q.type` 与 `aiForm.questionType` 一致，行为不变。
                      -->
                      <el-tag size="small" type="primary">{{ getTypeName(previewTypeOf(q)) }}</el-tag>
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

                      <!-- 选择题选项：仅 single / multiple 需要（judge 用开关，不需要选项） -->
                      <div v-if="['single', 'multiple'].includes(previewTypeOf(q))" class="preview-options">
                        <div v-for="(opt, optIdx) in q.options" :key="optIdx" class="preview-option">
                          <span class="option-letter">{{ String.fromCharCode(65 + optIdx) }}.</span>
                          <el-input v-model="q.options[optIdx]" size="small" @input="updatePreviewData" />
                        </div>
                      </div>

                      <!-- 答案（按逐题题型分派编辑器） -->
                      <div class="preview-answer">
                        <span class="answer-label">答案：</span>
                        <el-input
                          v-if="['fill', 'essay'].includes(previewTypeOf(q))"
                          v-model="q.correctAnswer" size="small" @input="updatePreviewData" />
                        <el-select v-else-if="previewTypeOf(q) === 'single'" v-model="q.correctAnswer" size="small"
                          @change="updatePreviewData">
                          <el-option v-for="(opt, optIdx) in q.options" :key="optIdx"
                            :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                        </el-select>
                        <el-select v-else-if="previewTypeOf(q) === 'multiple'" v-model="q.correctAnswer" multiple
                          size="small" @change="updatePreviewData">
                          <el-option v-for="(opt, optIdx) in q.options" :key="optIdx"
                            :label="String.fromCharCode(65 + optIdx)" :value="optIdx" />
                        </el-select>
                        <el-switch v-else-if="previewTypeOf(q) === 'judge'" v-model="q.correctAnswer"
                          active-text="正确" inactive-text="错误" @change="updatePreviewData" />
                      </div>

                      <!-- 解析 -->
                      <div class="preview-analysis">
                        <span class="analysis-label">解析：</span>
                        <el-input v-model="q.analysis" type="textarea" :rows="2" size="small"
                          @input="updatePreviewData" />
                      </div>
                    </div>
                    </template>
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

    <!-- 公式符号面板（2026-10-27）：点「ƒx」打开，确定后插到题干光标处 -->
    <MathEditor ref="mathEditorRef" title="插入公式" @confirm="onStemMathInsert" />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import draggable from 'vuedraggable'
import { Rank, InfoFilled, Delete, Search, MagicStick, Plus, Loading, Close, Check, EditPen, FolderOpened, DocumentCopy, ArrowDown, Clock, Setting, FullScreen, Grid, RefreshLeft, Upload, Document, Picture } from '@element-plus/icons-vue'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import aiModelManager from '@/components/AiModelManager/index.vue'
import QuestionFullEditor from './QuestionFullEditor.vue'
import { useQuestionBuilderAiForm } from './useQuestionBuilderAiForm'
import { useQuestionBuilderAiDialog } from './useQuestionBuilderAiDialog'
import { useQuestionBuilderEdit } from './useQuestionBuilderEdit'
import { useQuestionBuilderAiConfig } from './useQuestionBuilderAiConfig'
import { useQuestionBuilderPromptHistory } from './useQuestionBuilderPromptHistory'
import { useQuestionBuilderList } from './useQuestionBuilderList'
import { useQuestionBuilderMaterials } from './useQuestionBuilderMaterials'
import { useQuestionBuilderEditor } from './useQuestionBuilderEditor'
import { useQuestionBuilderAiResult } from './useQuestionBuilderAiResult'
import { useQuestionBuilderAiGenerate } from './useQuestionBuilderAiGenerate'
import { useQuestionBuilderTypes } from './useQuestionBuilderTypes'
import { useQuestionBuilderTypePopover } from './useQuestionBuilderTypePopover'
import { useQuestionBuilderAiStream } from './useQuestionBuilderAiStream'
import { useQuestionBuilderDialogActions } from './useQuestionBuilderDialogActions'
import { useQuestionBuilderPreviewEdit } from './useQuestionBuilderPreviewEdit'
import { useQuestionBuilderState } from './useQuestionBuilderState'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'
// 公式编辑（2026-10-27）：Tiptap 是富文本编辑器，不能直接塞输入框组件，
// 所以挂一个「ƒx」按钮，点开符号面板后把公式插到 Tiptap 光标处。
import MathEditor from '@/components/MathEditor/index.vue'
import { textToHtml, getPlainText } from '@/utils/questionUtils'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const userId = computed(() => userStore.id)


// 题型库悬浮层状态（显隐、点击外部关闭、生命周期监听已抽到同目录 composable）
const { typePopoverVisible, typePopoverTriggerRef, typePopoverRef, toggleTypePopover } = useQuestionBuilderTypePopover()

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

// 使用 props
const currentBankId = computed(() => props.bankId)
const {
  bankContextInfo,
  historyCount,
  clearingContext,
  userAiConfigs,
  aiModelManagerVisible,
  aiModelManagerRef,
  loadUserAiConfigs,
  openAiModelManager,
  loadBankContextInfo,
  handleClearContext
} = useQuestionBuilderAiConfig({ currentBankId })

// 本地响应式状态（抽到同目录 composable；watch(questions) 的事件时序仍留在 SFC）
const {
  viewMode, parsedQuestionsForPreview, rawJsonContent, questions, currentId,
  editablePreviewData, editingPassage, searchKeyword, currentPage, pageSize,
  showOptionsJsonDialog, fullEditorVisible, viewerVisible, viewerSrc,
  stemEditorRef, mathEditorRef, currentQuestion, selectedSubType,
  aiDialogVisible, aiFormRef
} = useQuestionBuilderState()

// AI 生成相关状态（流式正文、思考跟随、等待计时已抽到同目录 composable）
const {
  aiGenerating,
  aiThinking,
  aiThinkingOpen,
  thinkBoxRef,
  thinkAutoFollow,
  onThinkScroll,
  aiWaitSeconds,
  restartWaitTimer,
  streamBoxRef,
  generatedCount,
  pendingImportData,
  currentGeneratingType
} = useQuestionBuilderAiStream()

// 题型定义、名称映射与多选筛选（抽到同目录 composable；questionTypes / getTypeName 也在此返回）
const { questionTypes, getTypeName, activeTypeFilters, setTypeFilter, isTypeSelected } = useQuestionBuilderTypes(currentPage)

// 当前题库ID（从父组件传入或路由获取）
// const currentBankId = ref(null)


// 监听题目列表变化，自动选中第一题
watch(questions, (newQuestions) => {
  if (newQuestions.length > 0 && !currentId.value) {
    currentId.value = newQuestions[0].id
  }
}, { immediate: true })

/**
 * 点击历史记录 → 回填到对应输入框
 *
 * 2026-10-20 修：原来只处理 composite / knowledgePoint 两种，
 * `customRequirement`（自定义出题）从来没有被回填过 ——
 * 用户在自定义模式下点历史标签，输入框毫无反应，看起来像"历史坏了"。
 *
 * ⚠️ 关键决定：**是否连同题型一起切换**？
 *   这里选择**跟随历史记录切换题型**（`item.questionType` 存在时）。
 *   理由：历史记录存的是"上次那种模式下的完整输入"。
 *   比如一条 custom 记录里有「3 道单选 + 2 道填空」，
 *   若当前在「单选题」模式直接把它塞进 knowledgePoint，
 *   出题时 questionType 仍是 single，那句需求会被当成"知识点" —— 语义全错。
 *   切到 custom 再回填，才是用户点它时期待的结果。
 *
 *   （原注释写的是"只用于展示，点击时不强制切换"——那是只有两种输入时的
 *     旧权衡；现在三种输入的语义差异很大，不切反而更容易出错。）
 */
const {
  openFullEditor,
  handleFullEditorSave,
  removeQuestion,
  onTypeChange,
  addOption,
  removeOption,
  isCompositePreview,
  addSubQuestionBySelectedType,
  removeSubQuestion,
  onSubTypeChange,
  parseSubOptions,
  onTypeMouseDown,
  onTypeMouseUp,
  onTypeDragStart,
  onSubDragAdd,
  onSubDragEnd,
  onDragEnd
} = useQuestionBuilderEdit({
  questions,
  currentId,
  currentQuestion,
  fullEditorVisible,
  selectedSubType,
  setTypeFilter,
  parsedQuestionsForPreview
})



// AI 生成相关
const { aiForm, deepThink, selectedConfigId, onModelSelect, aiRules, createDefaultAiForm } = useQuestionBuilderAiForm()
const {
  promptHistory,
  historyContentOf,
  loadPromptHistory,
  savePromptToHistory,
  deleteHistoryItem,
  applyHistoryPrompt,
  clearPromptHistory
} = useQuestionBuilderPromptHistory({
  aiForm,
  userAiConfigs,
  rawJsonContent,
  parsedQuestionsForPreview,
  editablePreviewData
})

const {
  MATERIAL_MAX_CHARS,
  MATERIAL_ACCEPT,
  kbList,
  kbLoading,
  materialItems,
  materialParsing,
  materialParsingName,
  materialParsingStage,
  materialPanelOpen,
  imagePreviewList,
  imagePreviewIndex,
  materialSummaryText,
  loadKnowledgeBases,
  handleMaterialFileChange,
  removeMaterialItem,
  docPreviewVisible,
  docPreviewTitle,
  docPreviewContent,
  docPreviewTruncated,
  openDocPreview,
  copyDocPreviewContent,
  buildMaterialContext
} = useQuestionBuilderMaterials({ aiForm })

// 一键恢复 / AI 出题弹窗的题型切换与关闭重置（抽到同目录 composable）
const { handleRestore, onAiTypeChange, onAiDialogClose } = useQuestionBuilderDialogActions({
  props, emit, aiForm, rawJsonContent, parsedQuestionsForPreview,
  editablePreviewData, pendingImportData, aiGenerating, viewMode, aiDialogVisible
})

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
// 预览/编辑区交互辅助（抽到同目录 composable）
const {
  openImageViewer, openMathForStem, onStemMathInsert, copyRawJson,
  editPassage, applyOptionsJson, onOptionChange, updatePreviewData
} = useQuestionBuilderPreviewEdit({
  viewerVisible, viewerSrc, stemEditorRef, mathEditorRef, editingPassage,
  showOptionsJsonDialog, currentQuestion, rawJsonContent,
  parsedQuestionsForPreview, editablePreviewData
})

const {
  allFilteredQuestions,
  filteredQuestions,
  handlePageChange,
  handleSizeChange,
  panelHeaderRef,
  panelTitleRef,
  titleMeasureRef,
  showTitleCount
} = useQuestionBuilderList({
  questions,
  searchKeyword,
  activeTypeFilters,
  currentPage,
  pageSize,
  getTypeName: (type) => getTypeName(type)
})

/**
 * 预览里**这一道题**的真实题型
 *
 * 为什么需要它（2026-10-20 修）：预览模板原来通篇用 `aiForm.questionType` 判断，
 * 而自定义出题（custom）模式下它的值是 `'custom'` —— 不是任何真实题型：
 *   · 题型标签显示成 "custom"；
 *   · 选项区、答案编辑器全部匹配不上分支 → 渲染成空白，
 *     用户看到"答案：解析："后面什么都没有，以为生成失败。
 *
 * 解析顺序：逐题的 `type` → `questionType` → 回落到 `aiForm.questionType`
 * （固定题型时前两者通常不存在，回落即原行为，不会改变已有体验）。
 */
const { previewTypeOf, getTypeCount, cloneQuestion, selectQuestion } = useQuestionBuilderEditor({
  questions,
  currentId,
  questionTypes,
  aiForm
})

// 修改题目题干
// 修改选项
// 导入生成的题目
const {
  finishAiGenerate,
  importGeneratedQuestions,
  discardGeneratedQuestions
} = useQuestionBuilderAiResult({
  aiForm,
  parsedQuestionsForPreview,
  editablePreviewData,
  pendingImportData,
  rawJsonContent,
  generatedCount,
  viewMode,
  aiGenerating,
  questions,
  currentId,
  savePromptToHistory
})

const { handleAiGenerate } = useQuestionBuilderAiGenerate({
  aiFormRef,
  aiForm,
  parsedQuestionsForPreview,
  aiGenerating,
  rawJsonContent,
  editablePreviewData,
  pendingImportData,
  aiThinking,
  aiThinkingOpen,
  viewMode,
  currentGeneratingType,
  selectedConfigId,
  deepThink,
  userId,
  currentBankId,
  streamBoxRef,
  thinkBoxRef,
  thinkAutoFollow,
  buildMaterialContext,
  MATERIAL_MAX_CHARS,
  finishAiGenerate,
  restartWaitTimer,
})

const { handleKeydown, openAiDialog } = useQuestionBuilderAiDialog({
  aiDialogVisible,
  aiGenerating,
  aiForm,
  createDefaultAiForm,
  handleAiGenerate,
  materialItems,
  materialParsing,
  rawJsonContent,
  parsedQuestionsForPreview,
  editablePreviewData,
  pendingImportData,
  loadPromptHistory,
  loadBankContextInfo,
  loadUserAiConfigs,
  kbList,
  loadKnowledgeBases
})

// 普通 API 调用（非流式）
loadPromptHistory()
defineExpose({ questions, openAiDialog })
</script>

<style scoped lang="scss" src="./QuestionBuilder.scss"></style>
