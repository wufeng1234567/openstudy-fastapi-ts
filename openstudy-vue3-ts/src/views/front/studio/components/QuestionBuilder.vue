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
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, markRaw } from 'vue'
import draggable from 'vuedraggable'
import { Rank, InfoFilled, Delete, Search, MagicStick, Plus, Loading, Close, CircleCheck, Check, QuestionFilled, EditPen, ChatDotRound, FolderOpened, DocumentCopy, ArrowDown, Clock, Setting, FullScreen, Grid, RefreshLeft, Upload, Document, Picture } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getBankContextInfo, clearBankConversation } from '@/api/ai/ai'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import { listAiConfig } from '@/api/system/aiConfig'
import aiModelManager from '@/components/AiModelManager/index.vue'
import QuestionFullEditor from './QuestionFullEditor.vue'
import { useQuestionBuilderAiForm } from './useQuestionBuilderAiForm'
import { useQuestionBuilderList } from './useQuestionBuilderList'
import { useQuestionBuilderMaterials } from './useQuestionBuilderMaterials'
import { useQuestionBuilderEditor } from './useQuestionBuilderEditor'
import { useQuestionBuilderAiResult } from './useQuestionBuilderAiResult'
import { useQuestionBuilderAiGenerate } from './useQuestionBuilderAiGenerate'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'
// 公式编辑（2026-10-27）：Tiptap 是富文本编辑器，不能直接塞输入框组件，
// 所以挂一个「ƒx」按钮，点开符号面板后把公式插到 Tiptap 光标处。
import MathEditor from '@/components/MathEditor/index.vue'
import { textToHtml, getPlainText } from '@/utils/questionUtils'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const userId = computed(() => userStore.id)


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
}

// 点击外部关闭悬浮层
const handleOutsideClick = (e: MouseEvent) => {
  const target = e.target as Node
  if (!typePopoverVisible.value) {
    return
  }
  const triggerEl = typePopoverTriggerRef.value
  const popoverEl = typePopoverRef.value
  // 判断点击是否在悬浮层和触发按钮之外
  const inTrigger = triggerEl ? triggerEl.contains(target) : false
  const inPopover = popoverEl ? popoverEl.contains(target) : false
  if (!inTrigger && !inPopover) {
    typePopoverVisible.value = false
  }
}

// 监听悬浮层 visible 变化（无论何时改变都打印）
watch(typePopoverVisible, (newVal, oldVal) => {
  if (newVal) {
    // 打开后下一帧检查 DOM 是否真的渲染
    nextTick(() => {
      const el = typePopoverRef.value
      if (!el) {
        return
      }
      const rect = el.getBoundingClientRect()
      const style = window.getComputedStyle(el)
    })
  }
})

onMounted(() => {
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
const parsedQuestionsForPreview = ref<any>(null)
const rawJsonContent = ref('') // 原始 JSON 内容

// 题目列表
const questions = ref<any[]>([])
const currentId = ref(null)

// AI 生成相关状态
const aiGenerating = ref(false)
/**
 * 深度思考的**实时正文**（2026-10-20）
 *
 * 来源是后端 `\x1e@@THINK@@…\x1e` 标记里的增量（见 `chat_engine.THINK_OPEN`），
 * 经 `generateQuestionsStreamFull` 的 `onThinking` 回调送达。
 *
 * ⚠️ 它**不是**题目内容，绝不能拼进 `rawJsonContent` ——
 *    那样 JSON 前面会多出一大段推理，解析必失败。
 */
const aiThinking = ref('')
/** 思考卡片是否展开：默认展开（用户要看"在动"），一旦出现正文就自动收起 */
const aiThinkingOpen = ref(true)
/** 思考内容容器：用于**自动滚到底**，否则用户只能看到最早那一屏 */
const thinkBoxRef = ref<HTMLElement | null>(null)
/**
 * 是否「自动跟随」思考流（2026-10-20）
 *
 * 用户口径：「滚动条会不断自动往下面压 用户鼠标无法自由控制滚动…
 *   要既可以让用户自由控制滚动条 又要保证用户滚动到底部可以一直看到最新输出」
 *
 * `true`  —— 新内容到达时自动滚到底（默认；首次开始思考时就是这种）
 * `false` —— 用户已经往上翻去看历史了，**绝不打扰他**，视图停在原处
 *
 * 状态由 `onThinkScroll` 根据"是否贴底"自动切换，用户不需要点任何按钮：
 * 滚到底 → 恢复跟随；往上翻 → 停止跟随。
 */
const thinkAutoFollow = ref(true)
/** 判定"贴底"的容差（px）：留 24px 是因为小数像素/行高取整会有 1-2px 误差，
 *  卡得太死会让"明明滚到底了却不跟随"的 bug 反复出现 */
const THINK_STICKY_THRESHOLD = 24

/**
 * 用户手动滚动思考区时的处理
 *
 * ⚠️ 这个函数是"自由控制"与"自动跟随"不打架的关键：
 *   只有它在用户手势后更新 `thinkAutoFollow`，
 *   程序性的 `scrollTop` 赋值也会触发 scroll 事件 —— 但那时算出来
 *   仍然是"贴底"，因此 `thinkAutoFollow` 保持 true，不会误判成"用户想停下"。
 */
const onThinkScroll = () => {
  const el = thinkBoxRef.value
  if (!el) return
  const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  thinkAutoFollow.value = distanceToBottom <= THINK_STICKY_THRESHOLD
}
/**
 * 已等待秒数（2026-10-20）
 *
 * 模型推理启动约 2.5s（实测，本地也躲不掉 —— 是模型侧耗时，不是代理）。
 * 原来这段时间界面只有一行静态文字，用户无法判断"在等"还是"卡死"。
 * 显示秒数把"不确定的等待"变成"看得见的进度"。
 */
const aiWaitSeconds = ref(0)
let aiWaitTimer: ReturnType<typeof setInterval> | null = null

/*
 * 等待计时器的收尾（2026-10-20）
 *
 * ⚠️ 用 watch 而不是在每个结束路径里手动 clearInterval：
 *    `aiGenerating.value = false` 在文件里有 **9 处**
 *    （成功 / 解析失败 / 格式错误 / onError / 外层 catch…），
 *    逐处加一行必然漏改 —— 漏掉的那条路径会让计时器永远在跑，
 *    下次打开弹窗秒数从上次的数值继续涨，看着像"卡了几百秒"。
 *
 *    监听状态本身，无论从哪条路结束都能收尾 —— 一处覆盖全部。
 *
 * ⚠️ 必须放在 `aiGenerating` 声明**之后**：
 *    watch 在 setup 阶段立即求值，放在声明前会命中 TDZ
 *    直接抛 ReferenceError 白屏，而 `vite build` **抓不到这类错误**。
 */
watch(aiGenerating, (running) => {
  if (!running && aiWaitTimer) {
    clearInterval(aiWaitTimer)
    aiWaitTimer = null
  }
})
const streamBoxRef = ref(null)
const generatedCount = ref(0)
const pendingImportData = ref<any>(null) // 暂存待导入的数据
const currentGeneratingType = ref({ isComposite: false, questionType: 'single' })

// 可编辑预览数据（深拷贝，用于用户编辑）
const editablePreviewData = ref<any>(null)


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

/* ===== 公式编辑（2026-10-27）=====
   Tiptap 是富文本，公式以 `$...$` 源码形式存进 HTML（导出/练习时由统一管线渲染）。
   点「ƒx」→ 符号面板（鼠标操作）→ 确定后插到 Tiptap 光标处。 */
const stemEditorRef = ref<any>(null)
const mathEditorRef = ref<any>(null)

function openMathForStem() {
  mathEditorRef.value?.open('')
}

/** 面板确定：插到 Tiptap 光标处（组件内部会 focus 编辑区） */
function onStemMathInsert(latex: string) {
  if (!latex) return
  stemEditorRef.value?.insertText(latex)
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
const userAiConfigs = ref<any[]>([])
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
const promptHistory = ref<any[]>([])

/**
 * 一条历史记录里「用户到底输入了什么」
 *
 * 2026-10-20 修：历史记录原来只认两种输入
 *   `knowledgePoint`（固定题型）和 `compositeRequirement`（组合题），
 *   新增的 `customRequirement`（自定义出题）**完全没被记录和回填** ——
 *   用户在自定义模式下点历史标签，输入框毫无反应。
 *
 * 这里把三种输入统一成一个取值函数，避免"每加一种模式就漏改三处"
 * （记录 / 去重 / 回填）。
 */
const historyContentOf = (src: any): string => {
  const t = String(src?.questionType || '').trim()
  if (t === 'custom') return String(src?.customRequirement || '')
  if (t === 'composite') return String(src?.compositeRequirement || '')
  return String(src?.knowledgePoint || '')
}

const loadPromptHistory = () => {
  try {
    const stored = localStorage.getItem(PROMPT_HISTORY_KEY)
    if (stored) promptHistory.value = JSON.parse(stored)
  } catch (e) { }
}

const savePromptToHistory = () => {
  const type = aiForm.value.questionType
  const isComposite = type === 'composite'
  const isCustom = type === 'custom'

  const record = {
    // 保存当前题型：用于判断"这条历史属于哪类输入"
    questionType: type,
    /*
     * 三种输入**各存各的字段**，不合并成一个 content 字符串。
     * 原因：回填时要写回**对应的输入框**，合并后就不知道该写哪儿了。
     */
    knowledgePoint: (isComposite || isCustom) ? '' : (aiForm.value.knowledgePoint || ''),
    compositeRequirement: isComposite ? (aiForm.value.compositeRequirement || '') : '',
    // ↓ 2026-10-20 新增：自定义出题的需求描述
    customRequirement: isCustom ? (aiForm.value.customRequirement || '') : '',
    // 保存其他配置
    count: isComposite ? 0 : (aiForm.value.count || 3),
    wordCount: isComposite ? (aiForm.value.wordCount || 200) : 0,
    subCount: isComposite ? (aiForm.value.subCount || 5) : 0,
    model: aiForm.value.model || '',
    timestamp: Date.now()
  }

  // 去重：按「实际内容 + 题型」判重（不同题型即使文字相同也算两条）
  const currentContent = historyContentOf(record)
  const exists = currentContent
    ? promptHistory.value.some(
        item => item.questionType === record.questionType && historyContentOf(item) === currentContent
      )
    : false

  if (!exists && currentContent) {
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
const applyHistoryPrompt = (item) => {
  if (!item) return

  const itemType = String(item.questionType || '').trim()
  // 跟随历史记录的题型（含 composite / custom / 各种固定题型）
  if (itemType && itemType !== aiForm.value.questionType) {
    aiForm.value.questionType = itemType
    // 只同步题型，**不清空**素材（素材是全局附加项，与题型无关）
    aiForm.value.knowledgePoint = ''
  }

  const isComposite = aiForm.value.questionType === 'composite'
  const isCustom = aiForm.value.questionType === 'custom'

  if (isCustom) {
    aiForm.value.customRequirement = item.customRequirement || ''
  } else if (isComposite) {
    aiForm.value.compositeRequirement = item.compositeRequirement || item.knowledgePoint || ''
    if (item.wordCount) aiForm.value.wordCount = item.wordCount
    if (item.subCount) aiForm.value.subCount = item.subCount
  } else {
    aiForm.value.knowledgePoint = item.knowledgePoint || ''
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



const currentQuestion = computed(() => questions.value.find((q) => q?.id === currentId.value))

const selectedSubType = ref('single')

// AI 生成相关
const aiDialogVisible = ref(false)

const { aiForm, deepThink, selectedConfigId, onModelSelect, aiRules, createDefaultAiForm } = useQuestionBuilderAiForm()

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

const aiFormRef = ref(null)

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

const removeQuestion = async (id) => {
  const index = questions.value.findIndex(q => q.id === id)
  if (index === -1) return
  const q = questions.value[index]
  try {
    await ElMessageBox.confirm(
      `确定从当前题库移除「${q.title || '这道题'}」吗？保存后才会同步删除。`,
      '删除题目',
      { confirmButtonText: '确定移除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  questions.value.splice(index, 1)
  if (currentId.value === id) currentId.value = questions.value[0]?.id || null
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

// 获取子题题型标签类型（Element Plus Tag 的 type）
// 判断子题选项是否正确（用于组合题子题预览）
// 格式化子题答案显示（用于组合题子题预览）
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

  // 加载题库上下文
  loadBankContextInfo()
  loadUserAiConfigs()
  /*
   * 预加载知识库列表（2026-10-20 修「第一次进入获取不到，必须点刷新」）
   *
   * 根因：`loadKnowledgeBases` 上一轮重构后**一次都没有被自动调用** ——
   *   我把它从 `onAiTypeChange` 里删掉了（当时改成"展开素材面板才需要"），
   *   结果只剩模板上那个「刷新」按钮会调它。
   *   用户第一次打开弹窗、展开素材、点开下拉 → 列表是空的，必须手动点一次刷新。
   *   这属于"功能能用但要多点一下"的隐性缺陷，比直接报错更烦人。
   *
   * 为什么在**打开弹窗时**就加载、而不是等展开素材面板：
   *   · 一次请求很轻（就是个列表），没必要为省这点流量牺牲首屏体验；
   *   · 素材面板可以随时展开，等展开再请求会让用户先看到一个空下拉；
   *   · 与 `loadUserAiConfigs()`（模型列表）同一时机，语义一致：
   *     "打开弹窗就把可选项准备好"。
   *
   * 失败不阻断：`loadKnowledgeBases` 内部已 catch 并提示"可改用上传文档"。
   */
  if (kbList.value.length === 0) {
    // silent: 弹窗刚打开就弹"加载失败"很吵，且用户此刻未必想用知识库
    loadKnowledgeBases({ silent: true })
  }
}

// 更新预览数据（当用户编辑时）
const updatePreviewData = () => {
  // 触发视图更新
  parsedQuestionsForPreview.value = JSON.parse(JSON.stringify(editablePreviewData.value))
}

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
  restartWaitTimer: () => {
    aiWaitSeconds.value = 0
    if (aiWaitTimer) clearInterval(aiWaitTimer)
    aiWaitTimer = setInterval(() => { aiWaitSeconds.value += 1 }, 1000)
  }
})

// 普通 API 调用（非流式）
loadPromptHistory()
defineExpose({ questions, openAiDialog })
</script>

<style scoped lang="scss" src="./QuestionBuilder.scss"></style>
