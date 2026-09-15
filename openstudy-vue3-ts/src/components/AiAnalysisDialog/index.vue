<template>
    <el-dialog v-model="visible" title="🤖 AI 题目解析" width="600px" :close-on-click-modal="false" @close="handleClose">
        <div class="model-select-bar">
            <span class="model-label">模型：</span>
            <AiModelSelector v-model="selectedProvider" width="180px" :disabled="deepThink" />
            <AiThinkingToggle v-model="deepThink" size="small" @change="handleDeepThinkChange" />
        </div>
        <div class="analysis-container">
            <!-- 题目信息 -->
            <div class="question-info">
                <div class="question-text">{{ getPlainText(question) }}</div>
                <div class="question-meta">
                    <el-tag v-if="questionType" size="small">{{ questionType }}</el-tag>
                </div>
            </div>

            <!-- 流式输出内容 -->
            <div class="analysis-content" ref="contentRef">
                <template v-if="deepThink">
                    <div v-if="reasoningContent" class="reasoning-block">
                        <div class="reasoning-title">🧠 深度思考过程</div>
                        <div class="reasoning-text">{{ reasoningContent }}</div>
                    </div>
                    <div v-if="streamContent" class="ai-segments">
                        <div v-for="(seg, i) in segments" :key="i" class="ai-segment">
                            <div v-if="seg.title" class="segment-title">{{ seg.title }}</div>
                            <div v-if="seg.body" class="segment-body" v-html="renderAiMarkdown(seg.body)"></div>
                        </div>
                    </div>
                    <div v-else-if="isGeneratingState" class="loading-tip">
                        <LoadingDots size="small" :label="deepThink ? '深度思考中' : 'AI 正在解析中'" />
                    </div>
                    <div v-else class="empty-tip">
                        开启深度思考可先推理再作答，点击「开始解析」开始
                    </div>
                </template>
                <template v-else>
                    <div v-if="streamContent" class="ai-segments">
                        <div v-for="(seg, i) in segments" :key="i" class="ai-segment">
                            <div v-if="seg.title" class="segment-title">{{ seg.title }}</div>
                            <div v-if="seg.body" class="segment-body" v-html="renderAiMarkdown(seg.body)"></div>
                        </div>
                    </div>
                    <div v-else-if="isGeneratingState" class="loading-tip">
                        <LoadingDots size="small" :label="deepThink ? '深度思考中' : 'AI 正在解析中'" />
                    </div>
                    <div v-else class="empty-tip">
                        点击「开始解析」获取 AI 解析结果
                    </div>
                </template>
            </div>
        </div>

        <template #footer>
            <div class="dialog-footer">
                <el-button @click="copyContent" v-if="streamContent">
                    <el-icon>
                        <DocumentCopy />
                    </el-icon>
                    复制解析
                </el-button>
                <el-button @click="handleClose">关闭</el-button>
                <el-button type="primary" @click="startAnalysis" :loading="isGeneratingState">
                    {{ isGeneratingState ? '解析中...' : '开始解析' }}
                </el-button>
            </div>
        </template>
    </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Loading, DocumentCopy } from '@element-plus/icons-vue'
import { analyzeQuestionStream } from '@/api/ai/ai'
import { ElMessage } from 'element-plus'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import LoadingDots from '@/components/LoadingDots/index.vue'
import useUserStore from '@/store/modules/user'
import { getPlainText } from '@/utils/questionUtils'
import { splitAiSegments, renderAiMarkdown } from '@/utils/aiMarkdown'

const userStore = useUserStore()

const props = defineProps({
    question: { type: String, default: '' },
    questionId: { type: [Number, String], default: null },  // 新增
    questionType: { type: String, default: '' },
    options: { type: String, default: '' },
    correctAnswer: { type: [String, Array], default: '' },
    cachedContent: { type: String, default: '' },  // 新增：缓存内容
    isGenerating: { type: Boolean, default: false }  // 新增：外部生成状态
})

const emit = defineEmits(['close', 'update-cache', 'generating'])

const visible = ref(true)
const streamContent = ref(props.cachedContent || '')
const selectedProvider = ref('')
const deepThink = ref(false)
const reasoningContent = ref('')

const isGenerating = ref(false)
const contentRef = ref(null)

// 深度思考开关：reasoner 模型仅 DeepSeek 官方支持，开启时锁定 provider
const handleDeepThinkChange = (val: boolean) => {
    if (val) {
        selectedProvider.value = 'deepseek'
    }
}

// 监听缓存变化
watch(() => props.cachedContent, (newVal) => {
    if (!isGenerating.value) {
        streamContent.value = newVal || ''
    }
})

// 监听外部 isGenerating 状态变化（用于父组件控制）
watch(() => props.isGenerating, (newVal) => {
    if (newVal !== undefined) {
        isGenerating.value = newVal
    }
})

// 计算属性：综合判断是否正在生成（优先使用外部 prop，内部状态作为后备）
const isGeneratingState = computed(() => {
    return props.isGenerating !== false ? props.isGenerating : isGenerating.value
})

// 分段输出：按标题拆分为独立段落，流式过程中自动增量累积
const segments = computed(() => splitAiSegments(streamContent.value))

// 复制解析内容
const copyContent = async () => {
    try {
        // 获取纯文本内容（去除 HTML 标签）
        const plainText = streamContent.value
            .replace(/<[^>]+>/g, '')  // 去除 HTML 标签
            .replace(/&nbsp;/g, ' ')   // 替换 &nbsp;
            .replace(/&lt;/g, '<')     // 替换 &lt;
            .replace(/&gt;/g, '>')     // 替换 &gt;
            .replace(/&amp;/g, '&')    // 替换 &amp;
            .trim()

        await navigator.clipboard.writeText(plainText)
        ElMessage.success('解析内容已复制到剪贴板')
    } catch (error) {
        console.error('复制失败:', error)
        ElMessage.error('复制失败，请手动复制')
    }
}

// 开始解析
const startAnalysis = async () => {
    isGenerating.value = true
    emit('generating', true)
    streamContent.value = ''

    // ✅ 添加：格式化选项
    let optionsStr = ''
    if (props.options) {
        try {
            const opts = typeof props.options === 'string' ? JSON.parse(props.options) : props.options
            if (Array.isArray(opts)) {
                optionsStr = opts.map((opt, idx) =>
                    `${String.fromCharCode(65 + idx)}. ${opt}`
                ).join('\n')
            }
        } catch (e) {
            optionsStr = props.options
        }
    }

    // ✅ 添加：格式化答案
    let answerStr = ''
    if (Array.isArray(props.correctAnswer)) {
        answerStr = props.correctAnswer.map(a =>
            typeof a === 'number' ? String.fromCharCode(65 + a) : a
        ).join(', ')
    } else if (typeof props.correctAnswer === 'number') {
        answerStr = String.fromCharCode(65 + props.correctAnswer)
    } else {
        answerStr = String(props.correctAnswer || '')
    }

    // 调用流式 API
    if (deepThink.value) {
        reasoningContent.value = ''
    }
    analyzeQuestionStream(
        props.question,
        props.questionType,
        optionsStr,
        answerStr,
        (content) => {
            streamContent.value = content
            emit('update-cache', content)
            setTimeout(() => {
                if (contentRef.value) {
                    contentRef.value.scrollTop = contentRef.value.scrollHeight
                }
            }, 50)
        },
        () => {
            isGenerating.value = false
            emit('generating', false)
        },
        (error) => {
            console.error('解析失败:', error)
            ElMessage.error('解析失败，请重试')
            isGenerating.value = false
            emit('generating', false)
        },
        deepThink.value ? 'deepseek' : selectedProvider.value,
        userStore.id,
        deepThink.value,
        (reasoning) => {
            reasoningContent.value = reasoning
            setTimeout(() => {
                if (contentRef.value) {
                    contentRef.value.scrollTop = contentRef.value.scrollHeight
                }
            }, 50)
        }
    )
}

const handleClose = () => {
    visible.value = false
    emit('generating', false)
    emit('close')
}
</script>

<style scoped lang="scss">
.model-select-bar {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
    gap: 8px;

    .model-label {
        font-size: 13px;
        color: #6b7280;
        flex-shrink: 0;
    }
}

.deep-think-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;

    .toggle-label {
        font-size: 13px;
        color: #6b7280;
        white-space: nowrap;
    }
}

.reasoning-block {
    background: #f8fafc;
    border: 1px dashed #d1d5db;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 12px;

    .reasoning-title {
        font-size: 13px;
        font-weight: 700;
        color: #6b7280;
        padding-bottom: 8px;
        margin-bottom: 8px;
        border-bottom: 1px dashed #e5e7eb;
    }

    .reasoning-text {
        font-size: 13px;
        line-height: 1.7;
        color: #9ca3af;
        white-space: pre-wrap;
        word-break: break-word;
    }
}

.analysis-container {
    .question-info {
        background: #f5f7fa;
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 16px;

        .question-text {
            font-size: 15px;
            line-height: 1.6;
            color: #303133;
            margin-bottom: 8px;
        }
    }

    .analysis-content {
        min-height: 200px;
        max-height: 400px;
        overflow-y: auto;
        padding: 20px;
        background: #fafbfc;
        border-radius: 12px;
        border: 1px solid #e4e7ed;
        line-height: 1.8;

        .ai-segments {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .ai-segment {
            background: #fff;
            border: 1px solid #eef0f3;
            border-radius: 10px;
            padding: 14px 16px;

            .segment-title {
                font-size: 15px;
                font-weight: 700;
                color: #1f2937;
                padding-bottom: 8px;
                margin-bottom: 8px;
                border-bottom: 1px dashed #e5e7eb;
                line-height: 1.5;
            }

            .segment-body {
                :deep(p) {
                    margin: 8px 0;
                }
            }
        }

        :deep(.section-title) {
            margin: 20px 0 12px 0;
            color: #303133;
            font-size: 16px;
            font-weight: 600;

            &:first-child {
                margin-top: 0;
            }
        }

        :deep(.divider) {
            margin: 16px 0;
            border: none;
            border-top: 1px solid #e4e7ed;
        }

        :deep(.step-number) {
            display: inline-block;
            font-weight: 600;
            color: #409eff;
            margin-right: 6px;
        }

        :deep(.tag) {
            display: inline-block;
            background: #ecf5ff;
            color: #409eff;
            padding: 2px 10px;
            border-radius: 4px;
            font-size: 13px;
            margin: 0 6px 6px 0;
        }

        :deep(.star) {
            color: #e6a23c;
            font-size: 16px;
        }

        :deep(.emoji-icon) {
            margin-right: 4px;
            font-size: 16px;
            vertical-align: middle;
        }

        // Markdown 渲染样式
        :deep(h1),
        :deep(h2),
        :deep(h3),
        :deep(h4),
        :deep(h5),
        :deep(h6) {
            margin: 18px 0 10px 0;
            color: #1f2937;
            font-weight: 600;
            line-height: 1.4;

            &:first-child {
                margin-top: 0;
            }
        }

        :deep(h1) {
            font-size: 20px;
        }

        :deep(h2) {
            font-size: 18px;
            padding-bottom: 6px;
            border-bottom: 1px solid #f0f0f0;
        }

        :deep(h3) {
            font-size: 16px;
        }

        :deep(h4) {
            font-size: 15px;
        }

        :deep(p) {
            margin: 8px 0;
            color: #303133;
        }

        :deep(ul),
        :deep(ol) {
            margin: 8px 0;
            padding-left: 24px;
            color: #303133;

            li {
                margin: 4px 0;
                line-height: 1.7;
            }
        }

        :deep(strong) {
            color: #1f2937;
            font-weight: 600;
        }

        :deep(em) {
            color: #4b5563;
        }

        :deep(blockquote) {
            margin: 10px 0;
            padding: 8px 14px;
            border-left: 3px solid #d1d5db;
            background: #f9fafb;
            color: #6b7280;
            border-radius: 0 6px 6px 0;

            p {
                margin: 4px 0;
            }
        }

        :deep(pre) {
            margin: 10px 0;
            padding: 12px 14px;
            background: #1f2937;
            border-radius: 8px;
            overflow-x: auto;
            line-height: 1.5;

            code {
                background: transparent;
                color: #e5e7eb;
                padding: 0;
                font-size: 13px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        }

        :deep(code) {
            background: #f3f4f6;
            color: #db2777;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
            font-family: 'Consolas', 'Monaco', monospace;
        }

        :deep(hr) {
            margin: 16px 0;
            border: none;
            border-top: 1px solid #e4e7ed;
        }

        :deep(table) {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 13px;

            th,
            td {
                border: 1px solid #e4e7ed;
                padding: 6px 10px;
                text-align: left;
            }

            th {
                background: #f5f7fa;
                font-weight: 600;
                color: #1f2937;
            }

            tr:nth-child(even) td {
                background: #fafafa;
            }
        }

        :deep(a) {
            color: #409eff;
            text-decoration: none;

            &:hover {
                text-decoration: underline;
            }
        }
    }
}

.dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;

    :deep(.el-button) {
        border-radius: 8px;
    }
}
</style>