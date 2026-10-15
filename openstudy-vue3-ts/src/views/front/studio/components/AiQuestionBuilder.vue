<template>
  <div class="ai-question-builder">
    <!-- 文件上传区域 -->
    <div class="upload-section">
      <div class="section-title">
        <el-icon><Upload /></el-icon>
        <span>上传题库文件</span>
      </div>
      <el-upload
        class="upload-area"
        drag
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        :file-list="fileList"
        multiple
        accept=".txt,.md,.pdf,.docx"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 TXT、MD、PDF、Word(.docx) 文件，单个文件不超过 10MB，最多 10 个文件
          </div>
        </template>
      </el-upload>
      <div v-if="parsing" class="parsing-status">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在解析文件...</span>
      </div>
    </div>

    <!-- 解析结果预览 -->
    <div v-if="parsedContent" class="parsed-section">
      <div class="section-title">
        <el-icon><Document /></el-icon>
        <span>解析结果</span>
        <el-tag type="success" size="small" style="margin-left: 8px">{{ parsedContent.length }} 字符</el-tag>
        <el-tag v-if="imageList.length > 0" type="warning" size="small" style="margin-left: 4px">
          {{ imageList.length }} 张图片
        </el-tag>
        <el-button type="primary" text size="small" @click="parsedContentDialogVisible = true" style="margin-left: auto">
          <el-icon><FullScreen /></el-icon>
          查看全部
        </el-button>
      </div>
      <!-- ✅ 富预览：图文交错展示 -->
      <div class="blocks-preview" v-if="parsedBlocks.length > 0">
        <div
          v-for="block in parsedBlocks"
          :key="block.orderIndex"
          class="block-item"
          :class="'block-' + block.type"
        >
          <!-- 文本块 -->
          <div v-if="block.type === 'text' && block.content" class="text-block">
            {{ block.content }}
          </div>
          <!-- 图片块 -->
          <div v-else-if="block.type === 'image' && block.imageUrl" class="image-block-wrapper">
            <el-image
              :src="getFullImageUrl(block.imageUrl)"
              fit="contain"
              class="block-image"
              :preview-src-list="[getFullImageUrl(block.imageUrl)]"
              preview-teleported
            >
              <template #error>
                <div class="block-image-error">
                  <el-icon><Document /></el-icon>
                  <span>图片加载失败</span>
                </div>
              </template>
            </el-image>
            <div class="block-image-label">配图 #{{ block.orderIndex }}</div>
          </div>
        </div>
      </div>
      <!-- 降级：无 blocks 时显示纯文本 -->
      <el-input
        v-else
        v-model="parsedContent"
        type="textarea"
        :rows="6"
        readonly
        class="parsed-content"
      />
    </div>

    <!-- 解析结果全屏对话框 -->
    <el-dialog v-model="parsedContentDialogVisible" title="文档解析结果" width="80%" top="5vh" append-to-body>
      <div class="parsed-dialog-header">
        <el-tag type="success">共 {{ parsedContent.length }} 字符</el-tag>
        <el-tag v-if="imageList.length > 0" type="warning">{{ imageList.length }} 张图片</el-tag>
        <el-button type="primary" size="small" @click="copyParsedContent">
          <el-icon><DocumentCopy /></el-icon>
          复制文本
        </el-button>
      </div>
      <!-- 对话框中的富预览 -->
      <div class="blocks-preview dialog-blocks-preview" v-if="parsedBlocks.length > 0">
        <div
          v-for="block in parsedBlocks"
          :key="'dialog-' + block.orderIndex"
          class="block-item"
          :class="'block-' + block.type"
        >
          <div v-if="block.type === 'text' && block.content" class="text-block">
            {{ block.content }}
          </div>
          <div v-else-if="block.type === 'image' && block.imageUrl" class="image-block-wrapper">
            <el-image
              :src="getFullImageUrl(block.imageUrl)"
              fit="contain"
              class="block-image"
              :preview-src-list="[getFullImageUrl(block.imageUrl)]"
              preview-teleported
            >
              <template #error>
                <div class="block-image-error">
                  <el-icon><Document /></el-icon>
                  <span>图片加载失败</span>
                </div>
              </template>
            </el-image>
            <div class="block-image-label">配图 #{{ block.orderIndex }}</div>
          </div>
        </div>
      </div>
      <el-input
        v-else
        v-model="parsedContent"
        type="textarea"
        :rows="30"
        readonly
        class="parsed-dialog-content"
      />
    </el-dialog>

    <!-- 图片上传（DeepSeek Vision） -->
    <div class="image-upload-section">
      <div class="section-title">
        <el-icon><Picture /></el-icon>
        <span>补充图片（可选）</span>
      </div>
      <div class="image-upload-hint">
        上传图片后，AI 会结合文本内容和图片一起分析生成题目（需使用 DeepSeek Flash 视觉模型）
      </div>
      <div class="vision-images-wrap">
        <!-- 已上传图片：可预览、可删除 -->
        <div v-for="(img, index) in visionImages" :key="index" class="vision-thumb-item">
          <el-image
            :src="img"
            fit="contain"
            class="vision-thumb"
            :preview-src-list="visionImages"
            :initial-index="index"
            preview-teleported
          >
            <template #error>
              <div class="vision-thumb-error">加载失败</div>
            </template>
          </el-image>
          <el-icon class="vision-thumb-delete" @click.stop="removeVisionImage(index)"><Delete /></el-icon>
        </div>
        <!-- 上传按钮 -->
        <label class="vision-upload-btn" v-if="visionImages.length < 10">
          <input
            type="file"
            multiple
            accept="image/jpeg,image/png,image/gif,image/webp"
            class="vision-upload-input"
            @change="handleVisionFilesSelect"
          />
          <el-icon class="vision-upload-icon"><Plus /></el-icon>
        </label>
      </div>
      <div class="el-upload__tip">
        支持 JPG、PNG、GIF、WebP，单张不超过 5MB，最多 10 张（已选 {{ visionImages.length }} 张）
      </div>
    </div>

    <!-- 取材来源：纯 AI 生成 / 从我的知识库出题 -->
    <div class="source-section">
      <div class="section-title">
        <el-icon><Collection /></el-icon>
        <span>取材来源</span>
      </div>
      <el-radio-group v-model="sourceMode" class="source-radio-group" @change="onSourceModeChange">
        <el-radio-button value="ai">
          <el-icon><MagicStick /></el-icon>
          <span>纯 AI 生成</span>
        </el-radio-button>
        <el-radio-button value="kb">
          <el-icon><Collection /></el-icon>
          <span>从我的知识库出题</span>
        </el-radio-button>
      </el-radio-group>

      <div v-if="sourceMode === 'kb'" class="kb-picker">
        <el-select
          v-model="selectedKbId"
          placeholder="选择知识库"
          filterable
          clearable
          :loading="kbLoading"
          style="width: 100%"
        >
          <el-option
            v-for="kb in kbOptions"
            :key="kb.kbId"
            :label="kb.name"
            :value="kb.kbId"
            :disabled="kb.disabled === 1"
          >
            <span>{{ kb.name }}</span>
            <span class="kb-opt-doc">
              {{ kb.disabled === 1 ? '（已屏蔽）' : `${kb.docCount || 0} 篇资料` }}
            </span>
          </el-option>
        </el-select>
        <div class="source-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>
            选中后，AI 会先在你上传的资料里检索原文，再据此出题，并在解析里注明出处。
            若知识库为空，请先到「知识库」页面上传资料。
          </span>
        </div>
        <div v-if="!kbLoading && kbOptions.length === 0" class="source-empty">
          你还没有知识库，先去上传一份资料吧。
        </div>
      </div>
      <div v-else class="source-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>直接根据下面的文件内容 / 你的要求生成，不引用知识库。</span>
      </div>
    </div>

    <!-- 生成模式选择 -->
    <div class="mode-section">
      <div class="section-title">
        <el-icon><Setting /></el-icon>
        <span>生成模式</span>
        <div class="model-selector-wrap">
          <!-- 模型选择器（历史记忆按 scene=ai-builder 单独保存） -->
          <AiModelSelector v-model="selectedModel" scene="ai-builder" width="180px" @select="onModelSelect" />
          <!-- 深度思考开关（原子轨道图标，颜色表示状态） -->
          <AiThinkingToggle v-model="deepThink" size="small" />
        </div>
      </div>
      <el-radio-group v-model="generateMode" class="mode-radio-group">
        <el-radio-button value="all">
          <el-icon><Document /></el-icon>
          <span>全部转换</span>
        </el-radio-button>
        <el-radio-button value="custom">
          <el-icon><Edit /></el-icon>
          <span>自定义要求</span>
        </el-radio-button>
      </el-radio-group>
      <div class="mode-desc">
        <template v-if="generateMode === 'all'">
          <el-icon><InfoFilled /></el-icon>
          <span>将完整题库内容一道不漏地全部转换为 JSON 格式，适合已整理好的题库</span>
        </template>
        <template v-else>
          <el-icon><InfoFilled /></el-icon>
          <span>根据你的自定义要求生成题目，可以指定题型、数量、难度等</span>
        </template>
      </div>
    </div>

    <!-- 系统提示词配置（仅自定义模式显示） -->
    <div v-if="generateMode === 'custom'" class="prompt-section">
      <div class="section-title">
        <el-icon><Setting /></el-icon>
        <span>系统提示词</span>
        <el-button type="primary" text size="small" @click="resetPrompt" style="margin-left: auto">
          恢复默认
        </el-button>
      </div>
      <el-input
        v-model="systemPrompt"
        type="textarea"
        :rows="8"
        placeholder="配置 AI 生成题目的提示词..."
      />
      <div class="prompt-hint">
        提示：可以指定题型、难度、数量、输出格式等要求
      </div>
    </div>

    <!-- 用户要求（仅自定义模式显示） -->
    <div v-if="generateMode === 'custom'" class="requirement-section">
      <div class="section-title">
        <el-icon><ChatDotRound /></el-icon>
        <span>用户要求</span>
      </div>
      <el-input
        v-model="userRequirement"
        type="textarea"
        :rows="4"
        placeholder="描述你想要生成的题目要求...&#10;例如：&#10;- 只生成选择题和判断题&#10;- 选择题 10 道，判断题 5 道&#10;- 难度中等&#10;- 重点关注第三章的内容"
      />
      <div class="prompt-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>不填写则根据内容自动生成所有题型</span>
      </div>
    </div>

    <!-- 生成按钮 -->
    <div class="action-section">
      <el-button
        type="primary"
        size="large"
        @click="startGenerate"
        :loading="generating"
        :disabled="!parsedContent"
      >
        <el-icon><MagicStick /></el-icon>
        {{ generating ? '生成中...' : '开始生成题目' }}
      </el-button>
      <el-button
        v-if="generating"
        type="danger"
        size="large"
        @click="stopGenerate"
      >
        <el-icon><VideoPause /></el-icon>
        停止生成
      </el-button>
      <div v-if="!parsedContent" class="action-hint">
        请先上传并解析文件
      </div>
    </div>

    <!-- 实时预览区域 -->
    <div v-if="rawOutput || generatedQuestions.length > 0" class="preview-section">
      <div class="section-title">
        <el-icon><View /></el-icon>
        <span>生成结果预览</span>
        <el-tag v-if="generatedQuestions.length > 0" type="success" size="small" style="margin-left: 8px">
          共 {{ generatedQuestions.length }} 题
        </el-tag>
        <el-tag v-if="generating" type="warning" size="small" style="margin-left: 8px">
          生成中... {{ rawOutput.length }} 字符
        </el-tag>
      </div>

      <!-- 原始输出（流式显示） -->
      <div v-if="rawOutput" class="raw-output">
        <div class="raw-output-header">
          <div class="raw-output-header-left" @click="showRawOutput = !showRawOutput">
            <span>
              <el-icon><View /></el-icon>
              AI 实时输出
              <el-tag v-if="generating" type="success" size="small" class="streaming-tag">
                <span class="streaming-dot"></span>
                生成中
              </el-tag>
            </span>
            <el-icon class="toggle-icon" :class="{ expanded: showRawOutput }">
              <ArrowDown />
            </el-icon>
          </div>
          <div v-show="showRawOutput" class="raw-output-header-right">
            <el-tag type="info" size="small">{{ rawOutput.length }} 字符</el-tag>
            <el-button type="primary" text size="small" @click="rawOutputDialogVisible = true">
              <el-icon><FullScreen /></el-icon>
              放大
            </el-button>
          </div>
        </div>
        <div v-show="showRawOutput" class="raw-output-body">
          <div class="raw-output-viewport" ref="rawOutputRef" @scroll.passive="onMainScroll">
            <div class="raw-output-content">
              <pre class="raw-output-text">{{ rawOutput }}<span v-if="generating" class="streaming-cursor">▊</span></pre>
            </div>
          </div>
          <div v-if="!isAutoScroll && rawOutput" class="scroll-to-bottom" @click="scrollToBottomAndFollow">
            <el-icon><ArrowDown /></el-icon>
            <span>回到底部</span>
          </div>
        </div>
      </div>

      <!-- 流式输出全屏对话框 -->
      <el-dialog v-model="rawOutputDialogVisible" title="AI 原始输出" width="80%" top="5vh" append-to-body>
        <div class="raw-output-dialog-header">
          <div class="raw-output-dialog-header-left">
            <el-tag type="warning">共 {{ rawOutput.length }} 字符</el-tag>
            <el-tag v-if="generating" type="success" size="small">
              <span class="streaming-dot"></span>
              生成中
            </el-tag>
          </div>
          <el-button type="primary" size="small" @click="copyRawOutput">
            <el-icon><DocumentCopy /></el-icon>
            复制内容
          </el-button>
        </div>
        <div class="raw-output-dialog-body-wrapper">
          <div class="raw-output-dialog-viewport" ref="rawOutputDialogRef" @scroll.passive="onDialogScroll">
            <div class="raw-output-dialog-body">
              <pre class="raw-output-dialog-content">{{ rawOutput }}<span v-if="generating" class="streaming-cursor">▊</span></pre>
            </div>
          </div>
          <div v-if="!isDialogAutoScroll && generating" class="scroll-to-bottom dialog-scroll-btn" @click="scrollDialogToBottom">
            <el-icon><ArrowDown /></el-icon>
            <span>回到底部</span>
          </div>
        </div>
      </el-dialog>

      <!-- 解析后的题目列表 -->
      <div v-if="generatedQuestions.length > 0" class="question-list">
        <div
          v-for="(q, index) in generatedQuestions"
          :key="index"
          class="question-card"
          :class="{ 'question-error': q._error }"
        >
          <div class="question-header">
            <el-tag :type="getTypeTag(q.questionType)" size="small">
              {{ getTypeName(q.questionType) }}
            </el-tag>
            <span class="question-index">#{{ index + 1 }}</span>
            <div class="question-actions">
              <el-button type="primary" text size="small" @click="editQuestion(index)">
                <el-icon><Edit /></el-icon>
                编辑
              </el-button>
              <el-button type="danger" text size="small" @click="removeQuestion(index)">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </div>
          </div>

          <div class="question-content">
            <!-- ✅ 关联图片展示 -->
            <div v-if="getQuestionImage(index)" class="question-image-container">
              <el-image
                :src="getFullImageUrl(getQuestionImage(index))"
                fit="contain"
                class="question-image"
                :preview-src-list="[getFullImageUrl(getQuestionImage(index))]"
                preview-teleported
              >
                <template #error>
                  <div class="image-error-sm">
                    <el-icon><Document /></el-icon>
                    <span>图片加载失败</span>
                  </div>
                </template>
              </el-image>
              <el-tag size="small" type="warning" class="image-tag">配图</el-tag>
            </div>
            <div class="question-stem">{{ stripMarkers(q.questionText) }}</div>
            <div v-if="q.options && q.options.length > 0" class="question-options">
              <div
                v-for="(opt, idx) in q.options"
                :key="idx"
                class="option-item"
                :class="{ 'option-correct': isCorrectOption(q, idx) }"
              >
                <span class="option-letter">{{ String.fromCharCode(65 + idx) }}.</span>
                <span>{{ opt }}</span>
              </div>
            </div>
            <div class="question-answer">
              <strong>答案：</strong>
              <span class="answer-text">{{ formatAnswer(q) }}</span>
            </div>
            <div v-if="q.analysis" class="question-analysis">
              <strong>解析：</strong>{{ q.analysis }}
            </div>
          </div>
        </div>
      </div>

      <!-- 导入/创建按钮 -->
      <div v-if="generatedQuestions.length > 0 || parsedContent" class="import-section">
        <el-button
          type="success"
          size="large"
          @click="importToBank"
          :loading="importing"
        >
          <el-icon><CircleCheck /></el-icon>
          {{ generatedQuestions.length > 0 ? `导入到题库 (${generatedQuestions.length} 题)` : '创建题库' }}
        </el-button>
        <el-button
          v-if="generatedQuestions.length > 0"
          type="warning"
          size="large"
          @click="clearQuestions"
        >
          <el-icon><Delete /></el-icon>
          清空
        </el-button>
      </div>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑题目" width="650px" append-to-body>
      <el-form :model="editingQuestion" label-position="top">
        <el-form-item label="题型">
          <el-select v-model="editingQuestion.questionType" style="width: 200px">
            <el-option label="单选题" :value="1" />
            <el-option label="多选题" :value="2" />
            <el-option label="判断题" :value="3" />
            <el-option label="填空题" :value="4" />
            <el-option label="简答题" :value="5" />
          </el-select>
        </el-form-item>
        <el-form-item label="题干">
          <el-input v-model="editingQuestion.questionText" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-if="[1, 2].includes(editingQuestion.questionType)" label="选项">
          <div v-for="(opt, idx) in editingQuestion.options" :key="idx" class="edit-option">
            <span class="option-letter">{{ String.fromCharCode(65 + idx) }}.</span>
            <el-input v-model="editingQuestion.options[idx]" size="small" style="flex: 1" />
            <el-button type="danger" text size="small" @click="editingQuestion.options.splice(idx, 1)" :disabled="editingQuestion.options.length <= 2">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
          <el-button type="primary" text size="small" @click="editingQuestion.options.push('')" v-if="editingQuestion.options.length < 6">
            <el-icon><Plus /></el-icon>
            添加选项
          </el-button>
        </el-form-item>
        <el-form-item label="答案">
          <el-radio-group v-if="editingQuestion.questionType === 1" v-model="editingQuestion.answer">
            <el-radio v-for="(opt, idx) in editingQuestion.options" :key="idx" :label="String(idx)">
              {{ String.fromCharCode(65 + idx) }}
            </el-radio>
          </el-radio-group>
          <el-checkbox-group v-else-if="editingQuestion.questionType === 2" v-model="editingQuestion.answerArray">
            <el-checkbox v-for="(opt, idx) in editingQuestion.options" :key="idx" :label="String(idx)">
              {{ String.fromCharCode(65 + idx) }}
            </el-checkbox>
          </el-checkbox-group>
          <el-radio-group v-else-if="editingQuestion.questionType === 3" v-model="editingQuestion.answer">
            <el-radio label="true">正确</el-radio>
            <el-radio label="false">错误</el-radio>
          </el-radio-group>
          <el-input v-else v-model="editingQuestion.answer" placeholder="请输入答案" />
        </el-form-item>
        <el-form-item label="解析">
          <el-input v-model="editingQuestion.analysis" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 题库信息对话框 -->
    <BankInfoDialog
      v-model="bankInfoDialogVisible"
      :bank-id="props.bankId"
      :bank-name="props.bankName"
      :bank-subject="props.bankSubject"
      :question-count="generatedQuestions.length"
      @confirm="handleBankInfoConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, Document, Setting, ChatDotRound, MagicStick,
  VideoPause, View, Edit, Delete, CircleCheck, Plus, InfoFilled, FullScreen, DocumentCopy, ArrowDown, Loading, Picture, Collection
} from '@element-plus/icons-vue'
import { addQuestionMain } from '@/api/questionMain/questionMain'
import { parseFileBlocks, assistantStream } from '@/api/ai/ai'
import { listKnowledgeBases } from '@/api/ai/rag'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import { useDsDeepThinkSync } from '@/composables/useDsDeepThinkSync'
import BankInfoDialog from './BankInfoDialog.vue'
import useUserStore from '@/store/modules/user'
import { getToken } from '@/utils/auth'

const userStore = useUserStore()

const props = defineProps({
  bankId: {
    type: [Number, String],
    default: null
  },
  bankName: {
    type: String,
    default: ''
  },
  bankSubject: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['import-complete'])

// 全部转换模式的提示词
const ALL_CONVERT_PROMPT = `你是一个题目格式转换助手。你的任务是将用户提供的完整题库内容，一道不漏地全部转换为 JSON 格式。

【核心任务】
用户发给你的是一个完整的题库，你需要把里面的所有题目一道不漏地转换成 JSON 格式。

【严格要求】
1. 必须转换所有题目，一道都不能遗漏
2. 不要省略任何题目，不要用"..."或"等"代替
3. 选择题必须保留完整选项和正确答案
4. 判断题答案：√ 对应 "true"，× 对应 "false"
5. 填空题答案用逗号分隔多个空
6. 简答题和画图题也要转换，questionType 设为 5

【输出格式 - 非常重要】
你的回复必须以 JSON_START 开头，以 JSON_END 结尾，中间是纯 JSON 数组。

具体格式要求：
1. 第一行写：JSON_START
2. 第二行开始是 JSON 数组（以 [ 开头）
3. JSON 数组结束后，最后一行写：JSON_END
4. 中间不能有任何其他文字

示例结构（注意：这不是完整内容，只是格式示意）：
JSON_START
[{"questionType":1,"questionText":"题目","options":["A","B"],"answer":"0","analysis":""}]
JSON_END

如果开启了深度思考，请在 JSON_START 之前输出思考过程。

【图片处理 - 非常重要】
我已经上传了题目相关的图片。请你：
1. 仔细查看每张图片的内容
2. 根据文档内容和图片内容，判断每张图片应该对应哪道题
3. 在题干(questionText)中用【图N】标记表示该题需要配图（N从0开始，对应上传图片的顺序）
4. 一道题可以有多张图片，如"【图0】【图1】"
5. 如果图片与某道题无关，不要添加标记
6. 请根据图片实际内容（图表、公式、示意图等）准确关联

示例：
- 如果第1张图片是一个电路图，对应第3题：{"questionType":1,"questionText":"根据【图0】所示电路图，计算电流值",...}
- 如果第2张图片是一个表格，对应第5题：{"questionType":1,"questionText":"根据【图1】中的数据表，回答以下问题",...}

【题型编码 - 严格遵守】
- 1 = 单选题：options 必须是选项数组，answer 是选项索引 "0","1","2","3"
- 2 = 多选题：options 必须是选项数组，answer 是索引用逗号分隔 "0,1,2"
- 3 = 判断题：options 必须是空数组 []，answer 是 "true" 或 "false"（不要用 "√" 或 "×"）
- 4 = 填空题：options 必须是空数组 []，answer 是填空内容
- 5 = 简答题/画图题：options 必须是空数组 []，answer 是参考答案

【判断题特别注意】
判断题的 options 必须是空数组 []，不要填入 ["true","false"]！`

// 自定义模式的默认提示词
const CUSTOM_PROMPT = `你是一个专业的题目生成助手。请根据用户提供的内容和要求生成高质量的题目。

【输出要求】
1. 每个题目必须包含：questionType、questionText、options、answer、analysis
2. 选择题的 options 必须是数组，answer 是选项索引
3. 判断题 answer 为 "true" 或 "false"
4. 填空题 answer 多个空用逗号分隔
5. 简答题 answer 为参考答案文本

【输出格式 - 非常重要】
你的回复必须以 JSON_START 开头，以 JSON_END 结尾，中间是纯 JSON 数组。

具体格式要求：
1. 第一行写：JSON_START
2. 第二行开始是 JSON 数组（以 [ 开头）
3. JSON 数组结束后，最后一行写：JSON_END
4. 中间不能有任何其他文字

示例结构（注意：这不是完整内容，只是格式示意）：
JSON_START
[{"questionType":1,"questionText":"题目","options":["A","B"],"answer":"0","analysis":"解析"}]
JSON_END

如果开启了深度思考，请在 JSON_START 之前输出思考过程。

【图片处理 - 非常重要】
我已经上传了题目相关的图片。请你：
1. 仔细查看每张图片的内容
2. 根据文档内容和图片内容，判断每张图片应该对应哪道题
3. 在题干(questionText)中用【图N】标记表示该题需要配图（N从0开始，对应上传图片的顺序）
4. 一道题可以有多张图片
5. 如果图片与某道题无关，不要添加标记

【题型编码 - 严格遵守】
- 1 = 单选题：options 必须是选项数组，answer 是选项索引 "0","1","2","3"
- 2 = 多选题：options 必须是选项数组，answer 是索引用逗号分隔 "0,1,2"
- 3 = 判断题：options 必须是空数组 []，answer 是 "true" 或 "false"（不要用 "√" 或 "×"）
- 4 = 填空题：options 必须是空数组 []，answer 是填空内容
- 5 = 简答题/画图题：options 必须是空数组 []，answer 是参考答案

【判断题特别注意】
判断题的 options 必须是空数组 []，不要填入 ["true","false"]！`

// 文件相关
const fileList = ref([])
const parsing = ref(false)
const parsedContent = ref('')
const parsedContentDialogVisible = ref(false)

// ✅ 新增：结构化块解析相关
const parsedTextContent = ref('')   // 纯文本（供 AI 出题用）
const parsedBlocks = ref([])        // 有序块列表 [{type, content, orderIndex, imageUrl}]
const imageList = ref([])           // 图片列表 [{orderIndex, imageUrl, imageName}]
const imageBaseUrl = import.meta.env.VITE_APP_BASE_API || ''  // API 基础 URL
// 预览相关

// ✅ Vision 图片（可选，发给 DeepSeek Vision 模型）
const visionImages = ref([])  // base64 data URL 数组
const VISION_MAX_COUNT = 10
const VISION_MAX_SIZE = 5 * 1024 * 1024

// 生成相关
const systemPrompt = ref(ALL_CONVERT_PROMPT)
const userRequirement = ref('')
const generating = ref(false)
// 生成模式：all=全部转换，custom=自定义要求
const generateMode = ref('all')

// 取材来源：ai=纯 AI 生成，kb=从我的知识库出题
const sourceMode = ref('ai')
const selectedKbId = ref(null)
const kbOptions = ref([])
const kbLoading = ref(false)

// 切换取材来源：选「知识库」时按需拉取知识库列表（只拉一次）
const onSourceModeChange = (val) => {
  if (val === 'kb') loadKnowledgeBases()
}
async function loadKnowledgeBases() {
  kbLoading.value = true
  try {
    const res = await listKnowledgeBases()
    if (res.code === 200) {
      kbOptions.value = Array.isArray(res.data) ? res.data : (res.rows || [])
    }
  } catch (e) {
    console.error('获取知识库列表失败:', e)
  } finally {
    kbLoading.value = false
  }
}

// AI 模型选择：当前选中的模型名（历史记忆按 scene=ai-builder 单独保存）
const selectedModel = ref('')
// 选中的 AI 配置 id（区分同名系统/用户模型）
const selectedConfigId = ref(null)
const onModelSelect = (cfg) => { selectedConfigId.value = cfg?.configId ?? null }
const deepThink = ref(localStorage.getItem('openstudy_ai_thinking') === '1')  // 深度思考开关，跟随全局偏好

useDsDeepThinkSync(selectedModel, deepThink, 'openstudy_ai_thinking')
const abortController = ref(null)          // 用于停止生成

// 监听模式变化，切换提示词
watch(generateMode, (newMode) => {
  if (newMode === 'all') {
    systemPrompt.value = ALL_CONVERT_PROMPT
    userRequirement.value = ''
  } else {
    systemPrompt.value = CUSTOM_PROMPT
  }
})

const rawOutput = ref('')
const showRawOutput = ref(true)  // 默认展开
const rawOutputDialogVisible = ref(false)
const rawOutputRef = ref(null)
const rawOutputDialogRef = ref(null)
const isAutoScroll = ref(true)  // 是否在底部（用于显示/隐藏按钮）
const isDialogAutoScroll = ref(true)  // 对话框是否在底部
const generatedQuestions = ref([])

// 监听题目变化，重新计算图片映射
watch(generatedQuestions, () => {
  if (generatedQuestions.value.length > 0) {
    computeImageMapping()
  }
}, { deep: true })

// 编辑相关
const editDialogVisible = ref(false)
const editingQuestion = reactive({
  index: -1,
  questionType: 1,
  questionText: '',
  options: [],
  answer: '',
  answerArray: [],
  analysis: ''
})

// 导入相关
const importing = ref(false)
const bankInfoDialogVisible = ref(false)

// 重置提示词
const resetPrompt = () => {
  if (generateMode.value === 'all') {
    systemPrompt.value = ALL_CONVERT_PROMPT
  } else {
    systemPrompt.value = CUSTOM_PROMPT
  }
}

// 复制解析结果
const copyParsedContent = () => {
  navigator.clipboard.writeText(parsedContent.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

// 复制原始输出
const copyRawOutput = () => {
  navigator.clipboard.writeText(rawOutput.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

// 点击"回到底部"按钮 - 滚动到底部
const scrollToBottomAndFollow = () => {
  const el = rawOutputRef.value
  if (el) {
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight
    })
  }
}

// 放大对话框 - 回到底部
const scrollDialogToBottom = () => {
  const el = rawOutputDialogRef.value
  if (el) {
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight
    })
  }
}

// 检测是否在底部（用于显示/隐藏"回到底部"按钮）
const checkIsAtBottom = (el) => {
  if (!el) return true
  const threshold = 100
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold
}

// 主区域滚动事件
const onMainScroll = () => {
  isAutoScroll.value = checkIsAtBottom(rawOutputRef.value)
}

// 对话框滚动事件
const onDialogScroll = () => {
  isDialogAutoScroll.value = checkIsAtBottom(rawOutputDialogRef.value)
}

// 获取图片完整 URL
const getFullImageUrl = (url) => {
  if (!url) return ''
  // base64 data URL 直接返回，不拼接
  if (url.startsWith('data:') || url.startsWith('http')) return url
  return imageBaseUrl + url
}

// ✅ 根据文档位置映射获取题目对应的图片 URL
// 优先解析 AI 返回的 【图N】 标记，实现精确匹配
// 降级使用位置比例分配（去重，确保每张图只分配给一题）
const questionImageMap = ref({})  // { questionIndex: imageUrl }

// 构建带图片标记的文本（供 AI 出题用）
const buildMarkedText = () => {
  let marked = ''
  let imgCounter = 0
  for (const block of parsedBlocks.value) {
    if (block.type === 'text' && block.content) {
      marked += block.content + '\n'
    } else if (block.type === 'image' && block.imageUrl) {
      marked += `【图${imgCounter}】\n`
      imgCounter++
    }
  }
  return marked
}

// 从 AI 生成的题目中解析 【图N】 标记，构建精确映射
const computeImageMapping = () => {
  questionImageMap.value = {}
  if (!imageList.value.length || !generatedQuestions.value.length) return

  const sortedImages = [...imageList.value].sort((a, b) => a.orderIndex - b.orderIndex)
  const usedOrderIndices = new Set()

  // 只解析 AI 保留的 【图N】 标记（不做回退分配）
  for (let qi = 0; qi < generatedQuestions.value.length; qi++) {
    const q = generatedQuestions.value[qi]
    const text = (q.questionText || '') + ' ' + (q.analysis || '')
    const markerMatch = text.match(/【图(\d+)】/g)
    if (markerMatch) {
      for (const m of markerMatch) {
        const idx = parseInt(m.match(/\d+/)[0])
        if (idx < sortedImages.length && !usedOrderIndices.has(idx)) {
          questionImageMap.value[qi] = sortedImages[idx].imageUrl
          usedOrderIndices.add(idx)
          break // 一题只配一张图
        }
      }
    }
  }

  console.log('[AI Builder] Image mapping result:', Object.keys(questionImageMap.value).length, 'questions with images')
}

const getQuestionImage = (questionIndex) => {
  return questionImageMap.value[questionIndex] || null
}

// 去除文本中的 【图N】 标记（仅用于前端展示）
const stripMarkers = (text) => {
  if (!text) return text
  return text.replace(/【图\d+】/g, '').trim()
}

// 文件变更（自动解析）
const handleFileChange = (file, files) => {
  // 游客无法上传文件
  if (userStore.isGuest) {
    ElMessage.warning('游客仅可浏览，登录后才能使用该功能')
    // 移除刚添加的文件
    const index = files.findIndex(f => f.uid === file.uid)
    if (index > -1) {
      files.splice(index, 1)
    }
    return
  }
  fileList.value = files
  // 自动解析
  if (files.length > 0) {
    parseFiles()
  }
}

// 文件移除
const handleFileRemove = (file, files) => {
  fileList.value = files
  if (files.length === 0) {
    parsedContent.value = ''
    parsedTextContent.value = ''
    parsedBlocks.value = []
    imageList.value = []
  }
}

const handleVisionFilesSelect = (e) => {
  const files = Array.from(e.target.files || [])
  if (!files.length) return

  const remaining = VISION_MAX_COUNT - visionImages.value.length
  if (remaining <= 0) {
    ElMessage.warning(`最多上传 ${VISION_MAX_COUNT} 张图片`)
    e.target.value = ''
    return
  }

  const toProcess = files.slice(0, remaining)
  const rejected = files.length - toProcess.length
  if (rejected > 0) {
    ElMessage.warning(`超出部分 ${rejected} 张已忽略`)
  }

  const validFiles = []
  for (const file of toProcess) {
    if (file.size > VISION_MAX_SIZE) {
      ElMessage.warning(`${file.name} 超过 5MB 限制，已跳过`)
      continue
    }
    validFiles.push(file)
  }

  const promises = validFiles.map(file => {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (ev) => resolve(ev.target?.result || '')
      reader.onerror = () => resolve('')
      reader.readAsDataURL(file)
    })
  })

  Promise.all(promises).then(results => {
    visionImages.value.push(...results.filter(Boolean))
  })

  e.target.value = ''
}

const removeVisionImage = (index) => {
  visionImages.value.splice(index, 1)
}

// 解析文件（使用结构化块 API，提取文本 + 图片）
const parseFiles = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请先上传文件')
    return
  }

  // 游客无法上传文件（POST 请求被拦截）
  if (userStore.isGuest) {
    ElMessage.warning('游客仅可浏览，登录后才能使用该功能')
    return
  }

  parsing.value = true
  try {
    const rawFiles = fileList.value.map(f => f.raw)
    const res = await parseFileBlocks(rawFiles)

    if (res.code === 200) {
       const data = res.data
       // 纯文本内容（用于 AI 出题）
       parsedTextContent.value = data.textContent
       parsedContent.value = data.textContent
       // 有序块列表（用于富预览）
       parsedBlocks.value = data.blocks || []
       // 图片列表
       imageList.value = data.images || []
       
       const imgCount = imageList.value.length
       ElMessage.success(`文件解析成功，共 ${data.totalTextLength} 字符${imgCount > 0 ? `，提取 ${imgCount} 张图片` : ''}`)
    } else {
      ElMessage.error(res.msg || '解析失败')
    }
  } catch (error) {
    ElMessage.error('文件解析失败: ' + (error.message || error))
  } finally {
    parsing.value = false
  }
}

// 开始生成
const startGenerate = async () => {
  if (!parsedContent.value) {
    ElMessage.warning('请先解析文件')
    return
  }

  // 游客无法使用 AI 生成功能
  if (userStore.isGuest) {
    ElMessage.warning('游客仅可浏览，登录后才能使用该功能')
    return
  }

  // 选了「从知识库出题」但没选具体库 → 提示（否则会静默变成纯 AI 生成）
  if (sourceMode.value === 'kb' && !selectedKbId.value) {
    ElMessage.warning('请选择要作为取材来源的知识库')
    return
  }

  generating.value = true
  rawOutput.value = ''
  generatedQuestions.value = []

  // 使用带图片标记的文本（AI 会保留 【图N】 标记用于精确匹配）
  const aiContent = buildMarkedText() || parsedContent.value

  // 根据模式构建不同的提示词
  let fullPrompt = ''
  if (generateMode.value === 'all') {
    // 全部转换模式
    fullPrompt = `${systemPrompt.value}

【以下是完整的题库内容，请将里面的每一道题都转换为 JSON 格式，不要遗漏任何一道题】

${aiContent}`
  } else {
    // 自定义模式
    fullPrompt = `${systemPrompt.value}

【以下是题库内容】

${aiContent}

${userRequirement.value ? '【用户要求】\n' + userRequirement.value : '【默认要求】\n根据内容生成各种类型的题目，覆盖主要知识点。'}`
  }

  try {
    // 通过后端 API 流式生成（对接 /ai/assistant/stream）
    await sendViaBackendStream(fullPrompt)
  } catch (error) {
    ElMessage.error('生成失败: ' + (error.message || error))
  } finally {
    generating.value = false
    abortController.value = null
  }
}

// 通过后端 API 流式生成（对接 /ai/assistant/stream）
// 注意：后端模型无法看到图片本身，只能基于文本内容生成；
// 已通过 buildMarkedText() 的 【图N】 标记在题干中标注配图位置
const sendViaBackendStream = (content) => {
  return new Promise((resolve, reject) => {
    let accumulatedContent = ''
    let parseDebounceTimer = null
    let chunkCount = 0
    let settled = false

    console.log('[AI Builder] Starting sendViaBackendStream, content length:', content.length)

    // 取材来源：选「知识库」时把库 id 传给后端，由后端检索原文后注入提示词
    const kbIds = sourceMode.value === 'kb' && selectedKbId.value ? [selectedKbId.value] : []

    // 创建 AbortController 用于停止生成
    abortController.value = new AbortController()
    const { signal } = abortController.value

    // 当请求被中止时（assistantStream 在 abort 时静默返回，不触发 onComplete/onError），
    // 手动 resolve 以避免 Promise 挂起
    signal.addEventListener('abort', () => {
      if (settled) return
      settled = true
      console.log('[AI Builder][Backend] 生成已手动停止')
      if (parseDebounceTimer) clearTimeout(parseDebounceTimer)
      tryParseQuestions(accumulatedContent)
      resolve()
    })

    const model = selectedModel.value || undefined
    const userId = (typeof window !== 'undefined' && window.__userStore?.id) || undefined

    // 回调函数
    const onChunk = (fullText) => {
      accumulatedContent = fullText
      chunkCount++
      if (chunkCount === 1 || chunkCount % 10 === 0) {
        console.log('[AI Builder][Backend] Received chunk #' + chunkCount + ', length:', fullText.length)
      }
      rawOutput.value = accumulatedContent
      if (parseDebounceTimer) clearTimeout(parseDebounceTimer)
      parseDebounceTimer = setTimeout(() => {
        tryParseQuestions(rawOutput.value)
      }, 500)
    }

    const onComplete = (fullText) => {
      if (settled) return
      settled = true
      console.log('[AI Builder][Backend] Generation complete, total chunks:', chunkCount)
      if (parseDebounceTimer) clearTimeout(parseDebounceTimer)
      tryParseQuestions(fullText || accumulatedContent)
      if (generatedQuestions.value.length > 0) {
        ElMessage.success(`成功生成 ${generatedQuestions.value.length} 道题目`)
      } else {
        ElMessage.warning('未能解析出有效题目，请检查 AI 输出')
      }
      resolve()
    }

    const onError = (err) => {
      if (settled) return
      settled = true
      if (err?.name === 'AbortError') {
        console.log('[AI Builder][Backend] 生成已停止')
        resolve()
        return
      }
      console.error('[AI Builder][Backend] Stream error:', err)
      reject(err)
    }

    // 统一走**同一个入口**（scene=question-bank）：
    // 后端 chat_engine 会把图片作为多模态内容块、文档正文抽出来并入提示词，
    // 与 OS 助手共用同一条链路 —— 不再有「搭建题库单独调一个接口」这回事。
    // sessionId 传空串：题库搭建是一次性生成，不写聊天历史。
    assistantStream(
      content,
      onChunk,
      onComplete,
      onError,
      signal,
      model,
      userId,
      '',
      deepThink.value,
      {
        scene: 'question-bank',
        // visionImages 是 base64 data URL 字符串数组，assistantStream 两种写法都支持
        images: visionImages.value,
        configId: selectedConfigId.value || undefined,
        // 知识库取材（选了「从我的知识库出题」时非空）
        kbIds
      }
    )
  })
}

// 尝试解析题目 JSON（健壮版本，支持深度思考模式）
const tryParseQuestions = (content) => {
  if (!content) {
    console.log('[AI Builder] tryParseQuestions: content is empty')
    return
  }

  console.log('[AI Builder] tryParseQuestions called, content length:', content.length, 'mode:', generateMode.value)

  // 标准 JSON 模式
  // 步骤1：提取 JSON 内容（优先使用标记提取）
  let jsonContent = extractJsonFromContent(content)
  console.log('[AI Builder] Extracted JSON content length:', jsonContent?.length || 0)

  // 步骤2：尝试解析
  const questions = parseJsonSafely(jsonContent)
  console.log('[AI Builder] parseJsonSafely result:', questions?.length || 0, 'questions')

  if (questions && questions.length > 0) {
    generatedQuestions.value = questions.map(q => {
      const questionType = q.questionType || 1
      let options = q.options || []
      let answer = String(q.answer ?? '')

      // 修复判断题格式
      if (questionType === 3) {
        // 判断题不应该有 options，清空
        options = []
        // 确保 answer 是 "true" 或 "false"
        if (answer === '√' || answer === '对' || answer === '正确' || answer === 'T' || answer === '1') {
          answer = 'true'
        } else if (answer === '×' || answer === '错' || answer === '错误' || answer === 'F' || answer === '0') {
          answer = 'false'
        }
      }

      return {
        questionType,
        questionText: q.questionText || q.question || '',
        options,
        answer,
        analysis: q.analysis || ''
      }
    })
    console.log('[AI Builder] ✅ Parsed', questions.length, 'questions successfully')
    // 计算图片映射（解析 【图N】 标记或按位置匹配）
    computeImageMapping()
    console.log('[AI Builder] Image mappings:', questionImageMap.value)
  } else {
    console.warn('[AI Builder] ❌ Failed to parse questions')
  }
}

// 从内容中提取 JSON（支持多种格式）
const extractJsonFromContent = (content) => {
  // 使用正则匹配标记（独占一行的 JSON_START 和 JSON_END）
  const startMarkerRegex = /^JSON_START\s*$/m
  const endMarkerRegex = /^JSON_END\s*$/m

  const startMatch = content.match(startMarkerRegex)
  const endMatch = content.match(endMarkerRegex)

  const startIdx = startMatch ? startMatch.index : -1
  const endIdx = endMatch ? endMatch.index : -1

  // 如果找到了结束标记，说明 JSON 完整
  if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {
    const jsonStart = startIdx + startMatch[0].length
    const jsonPart = content.substring(jsonStart, endIdx).trim()
    console.log('[AI Builder] ✅ Extracted JSON using markers, length:', jsonPart.length)
    return jsonPart
  }

  // 如果只找到了开始标记，说明 JSON 还在生成中
  if (startIdx !== -1 && endIdx === -1) {
    const jsonStart = startIdx + startMatch[0].length
    const jsonPart = content.substring(jsonStart).trim()
    console.log('[AI Builder] ⏳ Found start marker, partial JSON, length:', jsonPart.length)
    return jsonPart
  }

  // 尝试其他方法...

  // 方法2：使用 ```json ``` 代码块提取
  const codeBlockRegex = /```json\s*([\s\S]*?)```/
  const codeBlockMatch = content.match(codeBlockRegex)
  if (codeBlockMatch) {
    console.log('[AI Builder] Extracted JSON from code block')
    return codeBlockMatch[1].trim()
  }

  // 方法3：提取 [...] JSON 数组（跳过思考过程）
  // 查找所有 [ 的位置，然后尝试找到对应的 ]
  const arrayStarts = []
  for (let i = 0; i < content.length; i++) {
    if (content[i] === '[') {
      // 检查前面是否有 questionType 或其他 JSON 特征
      const before = content.substring(Math.max(0, i - 50), i).toLowerCase()
      const after = content.substring(i, Math.min(content.length, i + 100)).toLowerCase()
      // 如果 [ 前面有思考过程文字，跳过
      if (before.includes('我们') || before.includes('需要') || before.includes('题目')) {
        // 检查后面是否是 JSON 对象
        if (after.includes('"questiontype"') || after.includes('"questiontext"') || after.includes('{')) {
          arrayStarts.push(i)
        }
      } else {
        arrayStarts.push(i)
      }
    }
  }

  // 尝试每个可能的数组开始位置
  for (let i = arrayStarts.length - 1; i >= 0; i--) {
    const start = arrayStarts[i]
    // 找到对应的 ]
    let depth = 0
    let end = -1
    for (let j = start; j < content.length; j++) {
      if (content[j] === '[') depth++
      if (content[j] === ']') depth--
      if (depth === 0) {
        end = j
        break
      }
    }

    if (end !== -1 && end > start) {
      const candidate = content.substring(start, end + 1)
      // 验证是否包含 JSON 题目特征
      if (candidate.includes('"questionType"') || candidate.includes('"questionText"')) {
        console.log('[AI Builder] Extracted JSON using smart array detection')
        return candidate
      }
    }
  }

  // 方法4：使用正则匹配 JSON 数组（处理嵌套）
  const jsonArrayRegex = /\[[\s\S]*\]/
  const arrayMatch = content.match(jsonArrayRegex)
  if (arrayMatch) {
    console.log('[AI Builder] Extracted JSON using regex')
    return arrayMatch[0]
  }

  // 返回原内容
  return content
}

// 安全解析 JSON
const parseJsonSafely = (jsonStr) => {
  if (!jsonStr) {
    console.log('[AI Builder] parseJsonSafely: jsonStr is empty')
    return null
  }

  console.log('[AI Builder] parseJsonSafely called, length:', jsonStr.length)
  console.log('[AI Builder] JSON preview:', jsonStr.substring(0, 200))

  // 清理 JSON 字符串
  let cleaned = jsonStr
    .replace(/```json\s*/g, '')  // 移除代码块标记
    .replace(/```\s*/g, '')
    .replace(/^\s*[\r\n]/gm, '')  // 移除空行
    .trim()

  console.log('[AI Builder] Cleaned JSON length:', cleaned.length)

  // 尝试直接解析
  try {
    const result = JSON.parse(cleaned)
    if (Array.isArray(result)) {
      console.log('[AI Builder] ✅ Direct parse success, items:', result.length)
      return result
    }
  } catch (e) {
    console.log('[AI Builder] Direct parse failed:', e.message)
  }

  // 尝试修复常见问题
  const fixed = fixJsonCommonIssues(cleaned)
  console.log('[AI Builder] Fixed JSON length:', fixed.length)

  try {
    const result = JSON.parse(fixed)
    if (Array.isArray(result)) {
      console.log('[AI Builder] ✅ Parse after fix success, items:', result.length)
      return result
    }
  } catch (e) {
    console.log('[AI Builder] Parse after fix failed:', e.message)
  }

  // 尝试提取并修复
  const extracted = extractAndFixJson(cleaned)
  console.log('[AI Builder] Extracted JSON length:', extracted.length)

  try {
    const result = JSON.parse(extracted)
    if (Array.isArray(result)) {
      console.log('[AI Builder] ✅ Parse after extract success, items:', result.length)
      return result
    }
  } catch (e) {
    console.warn('[AI Builder] ❌ All parse attempts failed:', e.message)
    console.log('[AI Builder] Final JSON content:', extracted.substring(0, 500))
  }

  return null
}

// 修复常见 JSON 问题
const fixJsonCommonIssues = (json) => {
  let fixed = json

  // 修复：字符串内的未转义双引号
  fixed = fixed.replace(/:\s*"([^"]*)"([^",\]}]*)"(?=[,\]}])/g, ': "$1$2"')

  // 修复：尾部逗号
  fixed = fixed.replace(/,\s*([\]}])/g, '$1')

  // 修复：缺失的逗号（对象之间）
  fixed = fixed.replace(/}\s*{/g, '},{')
  fixed = fixed.replace(/}\s*\[/g, '},[')
  fixed = fixed.replace(/]\s*{/g, '],{')

  // 修复：补全括号
  const openBrackets = (fixed.match(/\[/g) || []).length
  const closeBrackets = (fixed.match(/\]/g) || []).length
  if (openBrackets > closeBrackets) {
    fixed += ']'.repeat(openBrackets - closeBrackets)
  }

  const openBraces = (fixed.match(/\{/g) || []).length
  const closeBraces = (fixed.match(/\}/g) || []).length
  if (openBraces > closeBraces) {
    fixed += '}'.repeat(openBraces - closeBraces)
  }

  return fixed
}

// 提取并修复 JSON
const extractAndFixJson = (content) => {
  // 找到第一个 [ 和最后一个 ]
  const start = content.indexOf('[')
  const end = content.lastIndexOf(']')

  if (start === -1 || end === -1 || end <= start) {
    return content
  }

  let extracted = content.substring(start, end + 1)

  // 移除可能的思考过程残留（在 [ 之前的文字）
  // 已经通过 substring 处理了

  // 修复可能的截断问题
  if (!extracted.endsWith(']')) {
    // 尝试找到最后一个完整的对象
    const lastCompleteObj = extracted.lastIndexOf('}')
    if (lastCompleteObj !== -1) {
      extracted = extracted.substring(0, lastCompleteObj + 1) + ']'
    }
  }

  return extracted
}

// 停止生成
const stopGenerate = () => {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  generating.value = false
}

// 删除题目
const removeQuestion = (index) => {
  generatedQuestions.value.splice(index, 1)
}

// 清空题目
const clearQuestions = () => {
  ElMessageBox.confirm('确定要清空所有生成的题目吗？', '确认', { type: 'warning' }).then(() => {
    generatedQuestions.value = []
    rawOutput.value = ''
    parsedBlocks.value = []
    imageList.value = []
    questionImageMap.value = {}
  }).catch(() => {})
}

// 编辑题目
const editQuestion = (index) => {
  const q = generatedQuestions.value[index]
  editingQuestion.index = index
  editingQuestion.questionType = q.questionType
  editingQuestion.questionText = q.questionText
  editingQuestion.options = [...(q.options || [])]
  editingQuestion.answer = q.answer
  editingQuestion.answerArray = q.answer ? q.answer.split(',') : []
  editingQuestion.analysis = q.analysis || ''
  editDialogVisible.value = true
}

// 保存编辑
const saveEdit = () => {
  const index = editingQuestion.index
  let answer = editingQuestion.answer

  // 多选题答案处理
  if (editingQuestion.questionType === 2) {
    answer = editingQuestion.answerArray.sort().join(',')
  }

  generatedQuestions.value[index] = {
    questionType: editingQuestion.questionType,
    questionText: editingQuestion.questionText,
    options: [...editingQuestion.options],
    answer: answer,
    analysis: editingQuestion.analysis
  }
  editDialogVisible.value = false
  ElMessage.success('保存成功')
}

// 替换【图N】标记为实际图片 HTML
const replaceImageMarkers = (text, sortedImages, imageBaseUrl, serverImageUrls = []) => {
  if (!text || !sortedImages.length) return text

  return text.replace(/【图(\d+)】/g, (match, idx) => {
    const imgIndex = parseInt(idx)
    if (imgIndex >= 0 && imgIndex < sortedImages.length) {
      // 只使用已上传的服务器 URL，不 fallback 到 base64
      const serverUrl = serverImageUrls[imgIndex]
      if (serverUrl) {
        return `<img src="${serverUrl}" style="max-width:100%;height:auto;margin:10px 0;border-radius:4px;" />`
      }
      return '' // 上传失败则跳过图片
    }
    return match
  })
}

// 导入到题库（或创建题库）
const importToBank = async () => {
  // 弹出题库信息对话框
  bankInfoDialogVisible.value = true
}

// 题库信息确认后的回调
const handleBankInfoConfirm = async (bankInfo) => {
  console.log('[AI Builder] handleBankInfoConfirm called with:', bankInfo)
  const { bankId, isNew } = bankInfo

  if (!bankId) {
    ElMessage.error('题库ID不能为空')
    return
  }

  // 如果没有题目，只创建题库不导入
  if (generatedQuestions.value.length === 0) {
    ElMessage.success('题库创建成功！您可以稍后添加题目。')
    emit('import-complete', { bankId, isNew })
    return
  }

  importing.value = true
  let successCount = 0
  let failCount = 0
  let firstError = null

  // 先上传所有 base64 图片到服务器，拿到短 URL
  const sortedImages = [...imageList.value].sort((a, b) => a.orderIndex - b.orderIndex)
  const serverImageUrls = []
  if (sortedImages.length > 0) {
    console.log('[AI Builder] 开始上传图片到服务器，共', sortedImages.length, '张')
  }
  for (let idx = 0; idx < sortedImages.length; idx++) {
    const img = sortedImages[idx]
    if (!img.imageUrl) { serverImageUrls.push(''); continue }
    try {
      const res = await fetch(img.imageUrl)
      const blob = await res.blob()
      const ext = img.imageUrl.match(/data:image\/(\w+)/)?.[1] || 'png'
      const formData = new FormData()
      formData.append('file', new File([blob], `parsed_${idx}.${ext}`, { type: blob.type }))
      console.log('[AI Builder] 上传图片', idx, '大小:', (blob.size / 1024).toFixed(1), 'KB')
      // 使用原生 fetch 绕过 axios 拦截器
      const token = getToken() || ''
      const uploadRes = await fetch('/dev-api/common/upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
        body: formData,
      }).then(r => r.json())
      const fileName = uploadRes?.fileName || ''
      console.log('[AI Builder] 图片', idx, '上传结果:', fileName, uploadRes)
      serverImageUrls.push(fileName)
    } catch (e) {
      console.error('[AI Builder] 图片上传失败:', idx, e)
      serverImageUrls.push('')
    }
  }

  console.log('[AI Builder] Starting import to bank:', bankId, 'isNew:', isNew, 'questions:', generatedQuestions.value.length, 'uploadedImages:', serverImageUrls.length)

  for (let i = 0; i < generatedQuestions.value.length; i++) {
    const q = generatedQuestions.value[i]

    // 处理题目文本：用服务器 URL 替换【图N】标记
    let questionText = q.questionText || q.title || ''
    questionText = replaceImageMarkers(questionText, sortedImages, '', serverImageUrls)

    // 处理解析文本：同样替换图片标记
    let analysis = replaceImageMarkers(q.analysis || '', sortedImages, '', serverImageUrls)

    // 构建题目数据，确保必填字段不为空
    const questionData = {
      bankId: Number(bankId),
      questionType: Number(q.questionType) || 1,
      questionText: questionText,
      options: q.options && q.options.length > 0 ? JSON.stringify(q.options) : null,
      answer: String(q.answer ?? ''),
      analysis: analysis,
      difficulty: 2,
      hasSubQuestions: 0,
      sortOrder: i + 1,
      status: '0'  // 0=正常，确保练习页面能看到
    }

    // 验证必填字段
    if (!questionData.questionText) {
      console.warn('[AI Builder] Skipping question', i + 1, '- no questionText')
      failCount++
      if (!firstError) firstError = `第${i + 1}题：题目内容为空`
      continue
    }

    if (!questionData.answer && questionData.questionType !== 6) {
      console.warn('[AI Builder] Question', i + 1, 'has no answer, setting default')
      questionData.answer = '暂无答案'
    }

    try {
      console.log('[AI Builder] Importing question', i + 1)
      console.log('[AI Builder] Data:', JSON.stringify(questionData))
      const res = await addQuestionMain(questionData)
      console.log('[AI Builder] Question', i + 1, 'success:', res)
      successCount++
    } catch (error) {
      failCount++
      const errorMsg = typeof error === 'string' ? error : (error.message || error.msg || '导入失败')
      if (!firstError) firstError = `第${i + 1}题：${errorMsg}`
      console.error('[AI Builder] Question', i + 1, 'failed:', error)
    }
  }

  console.log('[AI Builder] Import completed, success:', successCount, 'fail:', failCount)

  if (successCount > 0) {
    ElMessage.success(`导入完成：成功 ${successCount} 题${failCount > 0 ? `，失败 ${failCount} 题` : ''}`)
    emit('import-complete', { bankId, isNew })
  } else {
    ElMessage.error(`导入失败：${firstError || '所有题目导入失败'}`)
  }

  importing.value = false
}

// 辅助函数
const getTypeName = (type) => {
  const names = { 1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题' }
  return names[type] || '未知'
}

const getTypeTag = (type) => {
  const tags = { 1: '', 2: 'success', 3: 'warning', 4: 'info', 5: 'danger' }
  return tags[type] || ''
}

const isCorrectOption = (q, idx) => {
  if (q.questionType === 1) {
    return String(idx) === String(q.answer)
  }
  if (q.questionType === 2) {
    const answers = String(q.answer).split(',')
    return answers.includes(String(idx))
  }
  return false
}

const formatAnswer = (q) => {
  if (q.questionType === 1) {
    const idx = parseInt(q.answer)
    return isNaN(idx) ? q.answer : String.fromCharCode(65 + idx) + ' (' + q.answer + ')'
  }
  if (q.questionType === 2) {
    return String(q.answer).split(',').map(a => {
      const idx = parseInt(a)
      return isNaN(idx) ? a : String.fromCharCode(65 + idx)
    }).join(', ') + ' (' + q.answer + ')'
  }
  if (q.questionType === 3) {
    return q.answer === 'true' ? '正确' : '错误'
  }
  return q.answer
}

// 页面离开前提示
onBeforeUnmount(() => {
  if (generatedQuestions.value.length > 0 && generating.value) {
    ElMessage.warning('正在生成中，离开页面将丢失结果')
  }
  // 中断未完成的流式请求，避免后台继续消耗资源
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
})
</script>

<style scoped lang="scss">
.ai-question-builder {
  padding: 20px;
}

.section-title {
  font-size: 16px;
  font-weight: bold;
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #303133;
}

.section-title .el-icon {
  font-size: 18px;
  color: #409eff;
}

.model-selector-wrap {
  margin-left: auto;
  /* 下拉框 + 深度思考开关横向并排、垂直居中，避免块级按钮换行撑歪标题行 */
  display: flex;
  align-items: center;
  gap: 8px;

  .model-selector :deep(.el-input__wrapper) {
    border-radius: 8px;
    box-shadow: 0 0 0 1px #e5e7eb;
    background: #fff;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .model-selector :deep(.el-input__wrapper:hover) {
    box-shadow: 0 0 0 1px #d1d5db;
  }

  .model-selector :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 0 0 1px #b3b3b3;
  }
}

.upload-section,
.parsed-section,
.image-upload-section,
.prompt-section,
.requirement-section,
.action-section,
.preview-section {
  margin-bottom: 24px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.upload-area {
  width: 100%;
}

.image-upload-hint {
  margin-bottom: 12px;
  font-size: 13px;
  color: #909399;
}

.vision-images-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
}

.vision-thumb-item {
  position: relative;
  width: 120px;
  height: 120px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}

.vision-thumb {
  width: 100%;
  height: 100%;
  display: block;
}

.vision-thumb-error {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 12px;
  color: #909399;
  background: #f5f7fa;
}

.vision-thumb-delete {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  border-radius: 50%;
  cursor: pointer;
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 1;
}

.vision-thumb-item:hover .vision-thumb-delete {
  opacity: 1;
}

.vision-upload-btn {
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s;
  background: #fafafa;
}

.vision-upload-btn:hover {
  border-color: #409eff;
}

.vision-upload-input {
  display: none;
}

.vision-upload-icon {
  font-size: 24px;
  color: #8c939d;
}

.vision-upload-btn:hover .vision-upload-icon {
  color: #409eff;
}

.parsed-content :deep(textarea) {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.prompt-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.action-section {
  text-align: center;
}

.action-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #909399;
}

.raw-output {
  margin-bottom: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  overflow: hidden;
}

.raw-output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  font-size: 14px;
  color: #606266;
  background: #f5f7fa;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;

  &:hover {
    background: #e8eaed;
  }

  span {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .toggle-icon {
    transition: transform 0.2s;
    &.expanded {
      transform: rotate(180deg);
    }
  }
}

.raw-output-body {
  padding: 12px;
}

.raw-output-content :deep(textarea) {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  background: #1e1e2e;
  color: #a6e3a1;
}

.question-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.question-card {
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.question-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.question-card.question-error {
  border-color: #f56c6c;
  background: #fef0f0;
}

.question-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.question-index {
  font-weight: bold;
  color: #409eff;
  font-size: 14px;
}

.question-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}

.question-content {
  margin: 10px 0;
}

.question-stem {
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 12px;
  color: #303133;
}

.question-options {
  margin: 12px 0;
  padding-left: 16px;
}

.option-item {
  margin: 6px 0;
  font-size: 13px;
  color: #606266;
  padding: 4px 8px;
  border-radius: 4px;
}

.option-item.option-correct {
  background: #f0f9eb;
  color: #67c23a;
  font-weight: bold;
}

.option-letter {
  font-weight: bold;
  margin-right: 8px;
  color: #409eff;
}

.question-answer,
.question-analysis {
  font-size: 13px;
  color: #606266;
  margin-top: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.answer-text {
  color: #67c23a;
  font-weight: bold;
}

.import-section {
  margin-top: 24px;
  text-align: center;
  padding: 20px;
  background: #f0f9eb;
  border-radius: 8px;
  border: 1px solid #e1f3d8;
}

.edit-option {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.edit-option .option-letter {
  font-weight: bold;
  color: #409eff;
  min-width: 20px;
}

.mode-section {
  margin-bottom: 24px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

/* ---- 取材来源（纯 AI 生成 / 从知识库出题）---- */
.source-section {
  margin-bottom: 24px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.source-radio-group {
  margin-bottom: 12px;

  .el-radio-button__inner {
    display: flex;
    align-items: center;
    gap: 6px;
  }
}

.kb-picker {
  margin-top: 4px;
}

.kb-opt-doc {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.source-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;

  .el-icon {
    margin-top: 2px;
    flex-shrink: 0;
  }
}

.source-empty {
  margin-top: 8px;
  font-size: 13px;
  color: #e6a23c;
}

.mode-radio-group {
  margin-bottom: 12px;

  .el-radio-button {
    .el-radio-button__inner {
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }
}

.mode-desc {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;

  .el-icon {
    margin-top: 2px;
    color: #409eff;
  }
}

.parsed-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.parsed-dialog-content {
  :deep(textarea) {
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
  }
}

.parsing-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 16px;
  background: #f0f9ff;
  border: 1px solid #d4e6ff;
  border-radius: 6px;
  color: #409eff;
  font-size: 14px;

  .is-loading {
    animation: rotating 1s linear infinite;
  }
}

.raw-output {
  margin-bottom: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.raw-output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;

  .raw-output-header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    cursor: pointer;

    &:hover {
      color: #409eff;
    }
  }

  .raw-output-header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .streaming-tag {
    margin-left: 8px;
  }

  .streaming-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    background: #67c23a;
    border-radius: 50%;
    margin-right: 4px;
    animation: streaming-pulse 1s ease-in-out infinite;
  }
}

@keyframes streaming-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.raw-output-body {
  position: relative;
  padding: 12px;
}

.raw-output-viewport {
  height: 300px;
  overflow-y: auto;
  background: #1e1e2e;
  border-radius: 6px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #2d2d3f;
  }

  &::-webkit-scrollbar-thumb {
    background: #4a4a5a;
    border-radius: 3px;

    &:hover {
      background: #5a5a6a;
    }
  }
}

.raw-output-content {
  padding: 16px;
  min-height: 100%;
}

.raw-output-text {
  margin: 0;
  font-family: 'Courier New', Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #a6e3a1;
  white-space: pre-wrap;
  word-break: break-all;
}

.streaming-cursor {
  display: inline;
  color: #a6e3a1;
  animation: cursor-blink 0.8s ease-in-out infinite;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.scroll-to-bottom {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #409eff;
  color: white;
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.4);
  transition: all 0.2s;
  z-index: 10;

  &:hover {
    background: #66b1ff;
    transform: translateX(-50%) translateY(-2px);
    box-shadow: 0 4px 16px rgba(64, 158, 255, 0.5);
  }
}

.raw-output-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;

  .raw-output-dialog-header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.raw-output-dialog-body-wrapper {
  position: relative;
}

.raw-output-dialog-viewport {
  height: 60vh;
  overflow-y: auto;
  background: #1e1e2e;
  border-radius: 6px;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: #2d2d3f;
  }

  &::-webkit-scrollbar-thumb {
    background: #4a4a5a;
    border-radius: 4px;
  }
}

.raw-output-dialog-body {
  padding: 20px;
  min-height: 100%;
}

.dialog-scroll-btn {
  bottom: 20px;
}

.raw-output-dialog-content {
  margin: 0;
  font-family: 'Courier New', Consolas, monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #a6e3a1;
  white-space: pre-wrap;
  word-break: break-all;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

// ====== ✅ 区块富预览样式 ======

.blocks-preview {
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 0;
  font-size: 13px;
  line-height: 1.6;

  &.dialog-blocks-preview {
    max-height: 70vh;
  }

  .block-item {
    border-bottom: 1px solid #f0f0f0;

    &:last-child {
      border-bottom: none;
    }

    &.block-image {
      background: #fafafa;
    }
  }

  .text-block {
    padding: 10px 14px;
    color: #303133;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
    font-size: 12px;
  }

  .image-block-wrapper {
    padding: 12px;
    text-align: center;

    .block-image {
      max-width: 100%;
      max-height: 300px;
      border-radius: 6px;
      border: 1px solid #e5e7eb;
    }

    .block-image-error {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 30px;
      background: #f5f5f5;
      border-radius: 6px;
      color: #999;
      font-size: 13px;
    }

    .block-image-label {
      margin-top: 6px;
      font-size: 11px;
      color: #c0c4cc;
    }
  }
}

// ====== ✅ 题目配图样式 ======
.question-image-container {
  position: relative;
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #fafafa;
  display: inline-block;
  max-width: 100%;

  .question-image {
    max-width: 100%;
    max-height: 300px;
    display: block;
    cursor: zoom-in;
  }

  .image-tag {
    position: absolute;
    top: 6px;
    left: 6px;
  }

  .image-error-sm {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 20px;
    color: #999;
    font-size: 12px;
  }
}</style>
