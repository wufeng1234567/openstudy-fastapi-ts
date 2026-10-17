<template>
    <el-dialog v-model="visible" title="AI 题目解析" width="600px" :close-on-click-modal="false" @close="handleClose">
        <div class="model-select-bar">
            <span class="model-label">模型：</span>
            <AiModelSelector v-model="selectedModel" scene="analysis" width="180px" :disabled="deepThink" @select="onModelSelect" />
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
            <!-- overflow-anchor: none —— 关闭浏览器的滚动锚定。流式过程中上方
                 内容持续重排，浏览器会自动调整 scrollTop 去「保持锚点」，
                 结果就是用户的滚动位置被反复推走，表现为抢手。 -->
            <div class="analysis-content" ref="contentRef" style="overflow-anchor: none;">
                <template v-if="deepThink">
                    <!-- 思考块限高 + 内部滚动：否则它在答案上方持续长高，
                         会把下面的正文不断往下推，用户读到的位置一直变。 -->
                    <div v-if="reasoningContent" class="reasoning-block" ref="reasoningRef"
                        style="max-height: 160px; overflow-y: auto; overflow-anchor: none;">
                        <div class="reasoning-title"><OsIcon name="lightbulb" :size="14" /> 深度思考过程</div>
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
import OsIcon from '@/components/OsIcon/index.vue'
import { ref, computed, watch } from 'vue'
import { Loading, DocumentCopy } from '@element-plus/icons-vue'
import { analyzeQuestionStream } from '@/api/ai/ai'
import { ElMessage } from 'element-plus'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import { useDsDeepThinkSync } from '@/composables/useDsDeepThinkSync'
import { useSmoothAutoScroll } from '@/composables/useSmoothAutoScroll'
import LoadingDots from '@/components/LoadingDots/index.vue'
import useUserStore from '@/store/modules/user'
import { getPlainText, extractImageUrls } from '@/utils/questionUtils'
import { splitAiSegments, renderAiMarkdown } from '@/utils/aiMarkdown'

const userStore = useUserStore()

const props = defineProps({
    question: { type: String, default: '' },
    questionId: { type: [Number, String], default: null },  // 新增
    questionType: { type: String, default: '' },
    options: { type: String, default: '' },
    correctAnswer: { type: [String, Array], default: '' },
    cachedContent: { type: String, default: '' },  // 新增：缓存内容
    isGenerating: { type: Boolean, default: false },  // 新增：外部生成状态
    // 组合题（阅读理解 / 完形填空）的小题：`[{ question, options, correctAnswer }]`
    subQuestions: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'update-cache', 'generating'])

const visible = ref(true)
const streamContent = ref(props.cachedContent || '')
// 当前选中的模型名；历史记忆按 scene=analysis 单独保存
const selectedModel = ref('')
// 选中的 AI 配置 id（区分同名系统/用户模型）
const selectedConfigId = ref(null)
const onModelSelect = (cfg) => { selectedConfigId.value = cfg?.configId ?? null }
const deepThink = ref(false)

useDsDeepThinkSync(selectedModel, deepThink)
const reasoningContent = ref('')

const isGenerating = ref(false)
const contentRef = ref(null)

// 流式输出时的「丝滑跟随滚动」：
// 只在用户本来就在底部附近时才自动跟随；用户往上翻会立即停止抢滚动条，
// 回到底部附近又自动恢复。同一帧内多次内容更新只滚一次（rAF 合并）。
// 如需「回到底部」按钮，再解构出 isFollowing / scrollToBottom 即可。
const reasoningRef = ref(null)

// 正文区：流式跟随滚动（用户往上翻就停止抢滚动条，回到底部自动恢复）
const { keepAtBottom } = useSmoothAutoScroll(contentRef)
// 思考区：它现在是独立的限高滚动容器，需要自己的跟随实例
const { keepAtBottom: keepReasoningAtBottom } = useSmoothAutoScroll(reasoningRef)

// 深度思考开关
//
// ⚠️ 旧实现在开启时会把 provider 强制改成 'deepseek'（原注释：「reasoner 模型
// 仅 DeepSeek 官方支持，开启时锁定 provider」）。这个前提**已不成立**：
//   · ds-free 通过同步 DS 网页端的「深度思考」按钮同样支持思考
//     （见 composables/useDsDeepThinkSync）
//   · zhipu / siliconflow 的思考由后端 thinking 参数处理
// 而且它会把用户选的 ds-free **直接改掉**（连下拉框都会跳回付费模型），
// 表现为「一开深度思考就自动切到付费 API」。所以这里不再动 provider。
const handleDeepThinkChange = (_val: boolean) => {
    // 开关状态由 useDsDeepThinkSync 负责与 DS 网页端双向同步，此处无需额外处理。
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

    // ✅ 组合题：把小题题干 / 选项 / 答案拼成文本，连同其图片一起交给 AI
    //    旧实现只发主材料，小题（含小题里的图）全部丢失。
    const subQuestionsText = buildSubQuestionsText(props.subQuestions)

    // ✅ 收集图片：主题干 + 材料 + 各小题题干里内嵌的 <img>（旧实现 getPlainText 会把图整段丢掉）
    const images = collectAnalysisImages()

    // 文本里去掉 <img> 标签本身（图片已作为多模态块单独发送）。
    // 否则模型会收到 `<img src="...">` 这种字面标签，容易误判成「我看到了图片但读不了」
    // （用户 2026-10-12 实测的原话）。
    const questionText = stripImgTags(props.question)

    // 调用流式 API
    if (deepThink.value) {
        reasoningContent.value = ''
    }
    analyzeQuestionStream(
        questionText,
        props.questionType,
        optionsStr,
        answerStr,
        (content) => {
            streamContent.value = content
            emit('update-cache', content)
            keepAtBottom()
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
        // 原实现是 `deepThink ? 'deepseek' : selectedProvider` —— 前提是
        // 「只有官方 deepseek 支持深度思考」。这个前提已不成立，
        // 思考由后端 thinking 参数统一处理。这里尊重用户的选择，
        // 否则一开思考就会被强制切走，等于用不了。
        selectedModel.value,
        userStore.id,
        deepThink.value,
        (reasoning) => {
            reasoningContent.value = reasoning
            // 思考过程滚思考区，不要去滚正文区（否则思考阶段会把正文一直拽到底）
            keepReasoningAtBottom()
        },
        images,
        subQuestionsText,
        selectedConfigId.value || undefined
    )
}

/**
 * 去掉文本里的 `<img ...>` 标签（图片已作为多模态块单独发送，正文里留着字面标签
 * 会让模型误以为「只拿到了图片链接、看不到图」）。
 * 其它标签（<p>/<strong> 等）保留原样，交由后端提示词处理。
 */
function stripImgTags(html: any): string {
    if (!html || typeof html !== 'string') return typeof html === 'string' ? html : ''
    return html.replace(/<img\b[^>]*>/gi, '').trim()
}

/**
 * 把组合题小题拼成给 AI 的文本：
 * `第1小题（单选）\n题干\nA. …\nB. …\n答案：A`
 * 无小题时返回空串。文本里的 `<img>` 由 collectAnalysisImages 单独抽走喂模型，
 * 这里保留纯文本（getPlainText 去标签）。
 */
function buildSubQuestionsText(subs: any[]): string {
    if (!Array.isArray(subs) || subs.length === 0) return ''
    return subs
        .map((sq: any, idx: number) => {
            const stem = getPlainText(sq?.question || sq?.questionText || sq?.question_text || '')
            let block = `第${idx + 1}小题：${stem}`
            const opts = sq?.options
            if (Array.isArray(opts) && opts.length) {
                block += '\n' + opts.map((o: any, i: number) => `${String.fromCharCode(65 + i)}. ${getPlainText(o)}`).join('\n')
            }
            const ans = sq?.correctAnswer ?? sq?.answer
            if (ans !== undefined && ans !== null && ans !== '') {
                const ansText = Array.isArray(ans)
                    ? ans.map((a: any) => (typeof a === 'number' ? String.fromCharCode(65 + a) : a)).join(', ')
                    : (typeof ans === 'number' && (sq?.type === 'single' || sq?.type === 'multiple')
                        ? String.fromCharCode(65 + ans)
                        : String(ans))
                block += `\n答案：${ansText}`
            }
            return block
        })
        .join('\n\n')
}

/**
 * 收集本题所有图片 URL（按出现顺序、去重）：
 * 主题干 question 里的 <img> + 每个小题题干/选项里的 <img>。
 * 后端会把 `/profile/upload/...` 相对路径读盘转成 data URL 再喂多模态模型。
 */
function collectAnalysisImages(): string[] {
    const all: string[] = []
    const seen = new Set<string>()
    const push = (urls: string[]) => {
        for (const u of urls) {
            if (!u || seen.has(u)) continue
            seen.add(u)
            all.push(u)
        }
    }
    push(extractImageUrls(props.question))
    if (Array.isArray(props.subQuestions)) {
        for (const sq of props.subQuestions) {
            push(extractImageUrls(sq?.question || sq?.questionText || sq?.question_text))
            if (Array.isArray(sq?.options)) {
                for (const o of sq.options) push(extractImageUrls(o))
            }
        }
    }
    return all
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
