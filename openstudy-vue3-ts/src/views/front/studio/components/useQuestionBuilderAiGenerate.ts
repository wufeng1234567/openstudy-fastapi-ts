import { nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { generateQuestionsStreamFull, generateCompositeStreamFull } from '@/api/ai/ai'

/** AI 出题执行链：校验、素材拼接、流式请求和等待计时。 */
export function useQuestionBuilderAiGenerate(options: {
  aiFormRef: any
  aiForm: any
  parsedQuestionsForPreview: any
  aiGenerating: any
  rawJsonContent: any
  editablePreviewData: any
  pendingImportData: any
  aiThinking: any
  aiThinkingOpen: any
  viewMode: any
  currentGeneratingType: any
  selectedConfigId: any
  deepThink: any
  userId: any
  currentBankId: any
  streamBoxRef: any
  thinkBoxRef: any
  thinkAutoFollow: any
  buildMaterialContext: () => any
  MATERIAL_MAX_CHARS: number
  finishAiGenerate: (raw: any, isComposite: boolean) => void
  restartWaitTimer: () => void
}) {
  const {
    aiFormRef, aiForm, parsedQuestionsForPreview, aiGenerating, rawJsonContent,
    editablePreviewData, pendingImportData, aiThinking, aiThinkingOpen, viewMode,
    currentGeneratingType, selectedConfigId, deepThink, userId, currentBankId,
    streamBoxRef, thinkBoxRef, thinkAutoFollow, buildMaterialContext,
    MATERIAL_MAX_CHARS, finishAiGenerate
  } = options

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
  // 思考状态必须**每次重新生成都清空**：上一次的推理留在界面上，
  // 用户会误以为是这次的内容（尤其两次生成的题目主题相似时）。
  aiThinking.value = ''
  aiThinkingOpen.value = true
  /*
   * 启动等待计时（2026-10-20）
   *
   * 必须在**发请求之前**就开始计数 —— 用户感知的等待从点击那一刻算起，
   * 而不是从第一个分片到达算起。这也是"点了没反应"的关键：
   * 原来界面上没有任何东西能证明请求已发出。
   */
  options.restartWaitTimer()
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
        /*
         * 前端拼材料时的约束（2026-10-20 修「题干被'材料'污染」）
         *
         * 用户口径：「他出的题目被提示词污染了 连续好几道都说'材料 材料'
         *   问题是我上传的文件只是一个参考材料 用户刷题的时候是看不到材料的」
         *
         * 实测废题：「材料中列为 O(n log n) 级别的排序算法包括？」——
         * 学生做题时看不到材料，这题根本没法答。
         *
         * 后端 `prompts._material_rules()` 已经加了铁律，但**这条路径走的是
         * `requirement`/`knowledge_point`**（材料由前端拼进正文），
         * 不一定经过后端那段模板（custom 分支会带上，固定题型也会带，
         * 但为了不依赖后端的拼接顺序，这里也把最关键的一条写在材料边界上）。
         *
         * 只保留**最关键**的一条，不复制后端那整套 —— 重复约束会让提示词臃肿，
         * 反而稀释重点。
         */
        prompt += '\n\n===== 参考材料开始 =====\n' + materialText + '\n===== 参考材料结束 =====' +
          '\n\n（上面的材料只用于确定"考什么、答案是什么"，**学生做题时看不到它**。' +
          '因此题目必须能独立作答：' +
          '**禁止在题干或选项里出现"材料中/文中/上述/原文"这类指代**，' +
          '要把具体内容直接写进题干。' +
          '例如不要出"材料中列出的最短路径算法包括？"，' +
          '而要出"下列算法中，属于最短路径算法的有？"。' +
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
        /*
         * ⚠️ 必须过滤成**纯净的正整数数组**（2026-10-20 修 422 的第二道防线）。
         *
         * 后端 `kbIds: List[int]` 是强校验：一旦混进 undefined / null / 字符串，
         * FastAPI 直接 422，且错误信息只是 "value is not a valid integer" ——
         * 用户完全不知道是自己选的知识库有问题。
         *
         * 根因（模板字段名写错 `kb.id` 而应为 `kb.kbId`）已经修了，但这里再兜一层：
         *   · 过滤掉非数字项；
         *   · 空数组就传 undefined（后端按"不取材"处理）。
         * 这样即使将来后端起名又改、或列表返回脏数据，最多是"没带上知识库"，
         * 而不是让整个出题请求挂掉。
         */
        kbIds: (() => {
          const ids = (aiForm.value.kbIds || [])
            .map((v: any) => Number(v))
            .filter((n: number) => Number.isInteger(n) && n > 0)
          return ids.length ? ids : undefined
        })(),
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
        /*
         * 深度思考增量（2026-10-20）
         *
         * 只累积到 `aiThinking`，**不碰 `rawJsonContent`** ——
         * 思考正文混进 JSON 会让解析直接失败。
         * 一旦出现正文，就把思考卡片自动收起，把屏幕让给题目
         * （用户仍可点开回看）。
         */
        onThinking(delta) {
          aiThinking.value += delta
          /*
           * 智能跟随（2026-10-20 修「滚动条被自动往下压」）
           *
           * ⚠️ 必须判断 `thinkAutoFollow`，不能无条件滚到底：
           *    用户往上翻去看历史推理时，下一片思考到达又把他拽回底部，
           *    鼠标完全失控 —— 这正是用户报的第二个 bug。
           *
           * 用 nextTick 是因为 DOM 还没更新：本回调里刚改了 `aiThinking`，
           * 立刻读 `scrollHeight` 拿到的还是旧高度，滚不到真正的底部。
           */
          if (thinkAutoFollow.value) {
            nextTick(() => {
              if (thinkBoxRef.value) {
                thinkBoxRef.value.scrollTop = thinkBoxRef.value.scrollHeight
              }
            })
          }
          if (rawJsonContent.value && aiThinkingOpen.value) {
            aiThinkingOpen.value = false
          }
        },
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

  return { handleAiGenerate }
}
