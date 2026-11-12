import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listKnowledgeBases } from '@/api/ai/rag'

/** 素材上传、知识库选择、文档预览和素材上下文构建。 */
export function useQuestionBuilderMaterials(options: { aiForm: any }) {
  const aiForm = options.aiForm
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
const kbList = ref<any[]>([])
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
const materialItems = ref<any[]>([])
const materialParsing = ref(false)

/**
 * 解析等待提示的两个辅助状态
 *
 * `materialParsingName` —— 正在处理的文件名。多份文件是**串行**处理的，
 *   不带名字的话用户看到进度条闪一下又闪一下，不知道哪份好了。
 * `materialParsingStage` —— 当前阶段（读取 / 上传解析 / 压缩）。
 *   文档和图片耗时差两个数量级（文档走后端解析），
 *   分阶段说明能让用户理解"为什么这份慢"，而不是怀疑卡死。
 */
const materialParsingName = ref('')
const materialParsingStage = ref('正在解析…')
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
  if (aiForm.value.kbIds.length) parts.push(`${aiForm.value.kbIds.length} 个资料夹`)
  const docCount = materialItems.value.filter((it) => it.kind === 'doc').length
  const imgCount = materialItems.value.filter((it) => it.kind === 'image').length
  if (docCount) parts.push(`${docCount} 份文档`)
  if (imgCount) parts.push(`${imgCount} 张图片`)
  return parts.join(' · ')
})

/**
 * 加载知识库列表
 *
 * 调用时机（2026-10-20 修）：
 *   · `openAiDialog()` —— 打开弹窗就预加载，**这是主要入口**。
 *     原来只靠"切换题型时懒加载"，导致首次进入列表是空的、必须点「刷新」；
 *   · 模板上的「刷新」按钮 —— 用户手动重试（比如刚在别处新建了知识库）。
 *
 * 幂等：`kbLoading` 期间直接返回，避免连点刷新发出多个请求。
 * 失败不阻断出题：知识库只是可选素材，用户仍可用上传文档这条路。
 */
const loadKnowledgeBases = async (opts: { silent?: boolean } = {}) => {
  if (kbLoading.value) return
  kbLoading.value = true
  try {
    const res = await listKnowledgeBases()
    const data = res?.data ?? res?.rows ?? res ?? []
    kbList.value = Array.isArray(data) ? data : (data.rows || [])
  } catch (e) {
    console.warn('[material] 加载资料失败：', e)
    /*
     * `silent` 用于"预加载"：弹窗刚打开就弹一条失败提示会很吵，
     * 而且用户此刻可能根本不想用知识库。失败时下拉里会显示
     * "还没有知识库 + 可改用上传文档"的说明，已经足够告知。
     * 手动点「刷新」才提示 —— 那说明用户确实在找这个功能。
     */
    if (!opts.silent) {
      ElMessage.warning('资料列表加载失败，可改用上传文档')
    }
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
  materialParsingName.value = raw.name || '文件'
  materialParsingStage.value = '正在读取…'
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
      materialParsingStage.value = '正在压缩图片…'
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
     *
     * ⚠️ 这一步是**唯一慢的地方**（文档要上传后端解析）：
     *    用户感知到的"没有加载提示"就发生在这里。所以处理期间必须
     *    让 `materialParsing` 保持 true 并显示文件名（见模板的进度条）。
     */
    materialParsingStage.value = '正在上传并解析文档…'
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
    // 收尾：等待提示必须无条件关掉，否则解析失败时进度条会永远转下去
    materialParsing.value = false
    materialParsingName.value = ''
    materialParsingStage.value = '正在解析…'
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

  return {
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
    hasMaterial,
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
  }
}
