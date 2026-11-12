<template>
    <div class="ocr-page">
        <!--
          2026-10-26 改造（用户：「拍照识词第二行多余了 返回功能不需要了」）：
          原来这里有一整行「< 返回」导航栏，但顶栏已经显示
          `英语学习 · 拍照识词`，页面层级一目了然，返回按钮纯属重复。

          删掉后，页面直接进入上传区，并改成：
            · 内容居中（`max-width` + `margin: auto`），不再挤在左上角；
            · 空状态下用 `min-height` 把上传区垂直居中，避免下方大片灰白；
            · 上传框放大，成为页面唯一视觉焦点。
        -->
        <!-- 图片 / 文档上传（2026-10-26：accept 加上文档类型） -->
        <div class="image-section">
            <div class="upload-wrapper">
                <!--
                  ⚠️ `auto-upload="false"`：文件类型不同，处理方式也不同
                      （图片走多模态识别，文档走文本解析），
                      必须在 `on-change` 里分流，不能让 el-upload 自动 POST 到 `/common/upload`。
                -->
                <el-upload ref="uploadRef" :auto-upload="false" :show-file-list="false" :limit="1"
                    :on-change="handleFileChange"
                    accept="image/png,image/jpeg,image/jpg,image/webp,.pdf,.doc,.docx,.md,.markdown,.txt"
                    class="ocr-upload" drag>
                    <div class="upload-area" v-if="!imageUrl && !parsedDocText">
                        <div class="upload-icon">
                            <el-icon :size="40">
                                <UploadFilled />
                            </el-icon>
                        </div>
                        <span class="upload-text">拖入文件，或点击选择</span>
                        <span class="upload-hint">
                            图片（JPG / PNG / WebP）· 文档（PDF / Word / Markdown / TXT）
                        </span>
                    </div>
                </el-upload>

                <!-- 文档已解析：显示文本摘要 + 预览（2026-10-26） -->
                <div class="doc-panel" v-if="isDocMode && parsedDocText">
                    <div class="doc-panel__head">
                        <div class="doc-panel__icon">
                            <el-icon :size="18"><Document /></el-icon>
                        </div>
                        <div class="doc-panel__meta">
                            <div class="doc-panel__name">{{ docInfo?.name }}</div>
                            <div class="doc-panel__stat">
                                已提取 {{ docInfo?.chars }} 个字符
                            </div>
                        </div>
                        <el-button text type="danger" size="small" @click="removeDoc">
                            移除
                        </el-button>
                    </div>
                    <pre class="doc-panel__preview">{{ parsedDocText.slice(0, 600) }}{{ parsedDocText.length > 600 ? '\n…' : '' }}</pre>
                    <div class="doc-panel__actions">
                        <el-button type="primary" @click="startDocExtract" :loading="recognizing">
                            <el-icon v-if="!recognizing"><MagicStick /></el-icon>
                            {{ recognizing ? 'AI 提取中…' : '让 AI 提取单词' }}
                        </el-button>
                        <span class="doc-panel__hint">AI 会从上面的文字里找出英文单词并配好中文释义</span>
                    </div>
                </div>

                <!-- 图片预览 -->
                <div class="image-preview" v-if="imageUrl">
                    <div class="preview-container">
                        <div class="preview-toolbar">

                            <span class="zoom-text">{{ Math.round(imageScale * 100) }}%</span>
                        </div>

                        <div class="draggable-container" @mousedown="startDrag" @mousemove="onDrag" @mouseup="stopDrag"
                            @mouseleave="stopDrag" @wheel.prevent="onWheel" @dblclick="openEditor">
                            <!-- 双击提示 -->
                            <div class="dblclick-hint">
                                <el-icon>
                                    <ZoomIn />
                                </el-icon>
                                <span>双击编辑图片</span>
                            </div>
                            <el-image ref="previewImageRef" :src="imageUrl" fit="contain" class="preview-image"
                                :preview-src-list="[imageUrl]" :style="{
                                    transform: `translate(${imagePosition.x}px, ${imagePosition.y}px) scale(${imageScale}) rotate(${rotation}deg)`,
                                    cursor: isDragging ? 'grabbing' : 'grab'
                                }" />
                        </div>
                    </div>

                    <div class="preview-actions">
                        <el-button @click="rotateImage" icon="RefreshRight">
                            旋转
                        </el-button>
                        <el-button @click="exportCurrentImage" icon="Download">
                            导出
                        </el-button>
                        <el-button type="danger" plain @click="removeImage" icon="Delete">
                            删除
                        </el-button>
                        <el-button type="primary" @click="startRecognize" :loading="recognizing">
                            <el-icon v-if="!recognizing">
                                <Search />
                            </el-icon>
                            {{ recognizing ? '识别中...' : '开始识别' }}
                        </el-button>
                    </div>
                </div>
            </div>
        </div>

        <!--
          词库选择（2026-10-26 改造）
          -----------------------------------------------------------------
          用户反馈：「目前只能选择已有的词库，不能选择新的词库」。

          改前：一个光秃秃的下拉框，只能从已有词库里挑。
                第一次用的用户（或者想按主题新建一本的人）走到这里就卡住了 ——
                他得先离开这个页面、去「我的词库」建一本、再回来重新识别一遍。

          改后：下拉框右侧加「新建」按钮，直接在原地建库并选中，
                识别结果不用重来。下拉里额外放一行「+ 新建词库」作为第二入口
                （很多人会先点开下拉找，找不到才发现旁边有按钮）。
        -->
        <div class="book-select-section" v-if="recognizedList.length > 0">
            <div class="select-label">
                选择词库
                <span class="select-label__hint">导入前可以先建一本新的</span>
            </div>

            <div class="book-select-row">
                <el-select v-model="selectedBookId" placeholder="请选择词库" size="large" class="book-select-el"
                    @change="onBookChange">
                    <el-option v-for="book in bookOptions" :key="book.bookId" :label="book.bookName"
                        :value="book.bookId">
                        <span class="book-option">
                            <span class="book-option__name">{{ book.bookName }}</span>
                            <span class="book-option__count">{{ book.wordCount || 0 }} 词</span>
                        </span>
                    </el-option>
                    <!-- 下拉底部的新建入口 -->
                    <el-option value="__create__" label="+ 新建词库" class="book-option-create" />
                </el-select>

                <el-button size="large" class="book-new-btn" @click="openCreateBook">
                    <el-icon><Plus /></el-icon>
                    新建
                </el-button>
            </div>

            <!-- 新建词库弹窗 -->
            <el-dialog v-model="createBookVisible" title="新建词库" width="420px" append-to-body
                :close-on-click-modal="!creatingBook">
                <el-form label-position="top" @submit.prevent>
                    <el-form-item label="词库名称" required>
                        <el-input v-model="createBookName" placeholder="例如：考研高频词、四级核心词"
                            maxlength="50" show-word-limit clearable
                            @keyup.enter="confirmCreateBook" />
                    </el-form-item>
                    <el-form-item label="一句话说明（可选）">
                        <el-input v-model="createBookDesc" type="textarea" :rows="2"
                            placeholder="例如：考研英语阅读常见词，偏学术语境" maxlength="120" show-word-limit />
                    </el-form-item>
                </el-form>
                <template #footer>
                    <el-button @click="createBookVisible = false" :disabled="creatingBook">取消</el-button>
                    <el-button type="primary" @click="confirmCreateBook" :loading="creatingBook">
                        创建并使用
                    </el-button>
                </template>
            </el-dialog>

            <!-- 词库预览面板 -->
            <div class="book-preview" v-if="selectedBookId && bookPreview.total > 0">
                <div class="preview-header" @click="showPreview = !showPreview">
                    <div class="preview-title">
                        <el-icon>
                            <View />
                        </el-icon>
                        <span>词库预览</span>
                    </div>
                    <div class="preview-stats">
                        <!--
                          ⚠️ 2026-10-23 修：原来分「单词 / 词组 / 句子」三项统计，
                             但 `words` 表没有 wordType 列，后两项恒为 0 —— 等于展示两个假数字。
                             现在只保留一个真实的「共 N 条」。
                        -->
                        <span class="stat-word">
                            <OsIcon name="book" :size="13" /> 共 {{ bookPreview.total }} 条
                        </span>
                    </div>
                    <el-icon class="preview-arrow" :class="{ expanded: showPreview }">
                        <ArrowDown />
                    </el-icon>
                </div>

                <div class="preview-content" v-show="showPreview">
                    <div class="preview-list">
                        <!--
                          ⚠️ 2026-10-23 修：这里原来读 `item.wordType / item.english / item.chinese`，
                             但 `loadBookPreview` 拿的是 `/words/words/list` 的原始行 —— 字段是
                             `word / translation`，且**没有 wordType 列**。结果是预览列表每行都是空白
                             （英文、中文全 undefined），三个统计里两个恒为 0。
                             现在按后端真实字段渲染；`wordType` 整个概念已去掉（表里没有）。
                        -->
                        <div v-for="item in bookPreview.items" :key="item.wordId" class="preview-item">
                            <span class="item-english">{{ item.word }}</span>
                            <span class="item-chinese">{{ item.translation }}</span>
                        </div>
                    </div>
                    <div class="preview-footer">
                        <el-button text type="primary" @click="goToVocabulary">
                            查看全部 <el-icon>
                                <ArrowRight />
                            </el-icon>
                        </el-button>
                    </div>
                </div>
            </div>
        </div>

        <!--
          导入完成面板（2026-10-26 闭环）
          --------------------------------
          用户点「一键导入全部」成功后，原来只是清空列表就"断"了 ——
          加完词不知道该干什么。这里给出三个明确的下一步。
        -->
        <div class="done-panel" v-if="donePanel && !recognizing">
            <div class="done-panel__icon">
                <el-icon :size="30">
                    <CircleCheck />
                </el-icon>
            </div>
            <h3 class="done-panel__title">已成功添加 {{ donePanel.count }} 个单词</h3>
            <p class="done-panel__desc">
                都加进了「{{ donePanel.bookName }}」。接下来可以：
            </p>
            <div class="done-panel__actions">
                <el-button type="primary" size="large" @click="goListeningNow">
                    <el-icon><Headset /></el-icon>
                    马上听写这些词
                </el-button>
                <el-button size="large" @click="goBookDetail">
                    去词库看看
                </el-button>
                <el-button size="large" text @click="restartOcr">
                    再识别一张
                </el-button>
            </div>
        </div>

        <!--
          底部引导区（2026-10-26）
          -------------------------
          截图实测：上传框只占上半屏，下半屏约 400px 是纯白空白，
          整页看起来"没做完"。
          这里补一条轻量的使用说明 + 直达入口，把空白变成有用的东西。
        -->
        <div class="ocr-tips" v-if="!imageUrl && !recognizing && !recognizedList.length && !donePanel">
            <div class="tips-head">怎么用</div>
            <ol class="tips-steps">
                <li>
                    <span class="tips-num">1</span>
                    <span>拍照或拖入一张带英文的图片（课本、笔记、试卷都行）</span>
                </li>
                <li>
                    <span class="tips-num">2</span>
                    <span>点「开始识别」，AI 会读出上面的单词并配好中文释义</span>
                </li>
                <li>
                    <span class="tips-num">3</span>
                    <span>确认无误后一键导入词库，直接开始听写</span>
                </li>
            </ol>
            <div class="tips-foot">
                已经有词库了？
                <a class="tips-link" @click="router.push('/front/english/vocabulary')">去我的词库看看</a>
            </div>
        </div>

        <!-- 流式识别中 -->
        <div class="stream-loading" v-if="recognizing">
            <div class="stream-loading-header">
                <el-icon class="is-loading" :size="20">
                    <Loading />
                </el-icon>
                <span>AI 识别中...</span>
            </div>
            <div class="stream-loading-body">
                <pre>{{ streamContent }}</pre>
            </div>
        </div>

        <!-- 识别结果区域（双视图） -->
        <div class="result-section" v-if="recognizedList.length > 0 && !recognizing">
            <div class="result-header">
                <el-radio-group v-model="resultViewMode" size="small">
                    <el-radio-button label="words">识别结果（可编辑）</el-radio-button>
                    <el-radio-button label="json">AI 原始内容</el-radio-button>
                </el-radio-group>
                <div class="header-actions">
                    <el-button size="small" text @click="copyContent" class="copy-btn">
                        <el-icon :size="16"><DocumentCopy /></el-icon>
                    </el-button>
                    <el-button v-if="resultViewMode === 'words'" type="success" size="small" @click="addAllWords" :loading="batchAdding">
                        一键导入全部 ({{ recognizedList.length }})
                    </el-button>
                </div>
            </div>

            <!-- 视图1：格式化可编辑单词列表 -->
            <div v-if="resultViewMode === 'words'" class="word-list">
                <div v-for="(word, index) in recognizedList" :key="index" class="word-card">
                    <div class="card-header">
                        <span class="word-index">{{ index + 1 }}</span>
                        <div class="header-center"></div>
                        <el-button type="danger" size="small" text @click="removeWord(index)">
                            <el-icon>
                                <Delete />
                            </el-icon>
                        </el-button>
                    </div>

                    <div class="card-body">
                        <el-input v-model="word.english" placeholder="英文/词组/句子" class="word-input" clearable />
                        <el-input v-model="word.chinese" placeholder="中文释义" class="word-input" clearable />
                        <el-input v-model="word.phonetic" placeholder="音标（可选）" class="word-input" clearable />

                        <!--
                          ⚠️ 2026-10-23 修：这里原来绑 `word.bookId`，但识别结果里写的是
                             `wordBookId`（三处创建处都是），所以这个下拉永远是空值 ——
                             单个「添加」只能靠全局 `selectedBookId` 兜底。
                             现在统一绑 `word.bookId`，并在下面两处创建时一起改名。

                          ⚠️ 另一个 `el-select v-model="word.wordType"`（单词/词组/句子）已删除：
                             `words` 表**没有 wordType 列**，选了也存不进去 —— 那是个假控件。
                        -->
                        <el-select v-model="word.bookId" placeholder="选择词库" size="small" style="width: 100%">
                            <el-option v-for="book in bookOptions" :key="book.bookId" :label="book.bookName" :value="book.bookId" />
                        </el-select>
                    </div>

                    <div class="card-footer">
                        <el-button type="primary" size="small" @click="addSingleWord(word, index)"
                            :loading="word.adding">
                            <el-icon>
                                <Plus />
                            </el-icon>
                            添加
                        </el-button>
                    </div>
                </div>
            </div>

            <!-- 视图2：AI 原始内容（自动格式化 JSON） -->
            <div v-else class="json-view">
                <pre class="json-content">{{ formattedStreamJson }}</pre>
            </div>
        </div>

        <!--
          空状态已删除（2026-10-26）
          ---------------------------
          原来这里还有一块「上传图片后点击开始识别」的占位区，但它和上面的
          上传框说的是同一件事（上传框里已经写着「点击拍照或拖入图片」）。
          两块并排出现时，右边那块看起来像"坏掉了的空白区域"，
          实际只是重复提示。保留上传框一个入口就够了。
        -->

        <!-- 图片编辑模态框 -->
        <teleport to="body">
            <div class="image-editor-modal" v-if="editorVisible" @click.self="closeEditor">
                <div class="editor-container">
                    <div class="editor-header">
                        <span class="editor-title">编辑图片</span>
                        <el-icon class="close-btn" @click="closeEditor">
                            <Close />
                        </el-icon>
                    </div>

                    <div class="editor-body">
                        <cropper ref="cropperRef" :src="editorImageUrl" :stencil-props="stencilProps"
                            :default-size="defaultSize" :default-boundaries="'fit'" :image-restriction="'none'"
                            :size-restrictions-algorithm="sizeRestrictionsAlgorithm" @change="onCropChange" />
                    </div>

                    <div class="editor-toolbar">
                        <el-button-group>
                            <el-button @click="rotate(-90)" icon="RefreshLeft">左转</el-button>
                            <el-button @click="rotate(90)" icon="RefreshRight">右转</el-button>
                            <el-button @click="flip('horizontal')">
                                <el-icon>
                                    <Switch />
                                </el-icon>
                                翻转
                            </el-button>
                        </el-button-group>

                        <el-button-group style="margin-left: 12px;">
                            <el-button @click="zoomIn" icon="ZoomIn">放大</el-button>
                            <el-button @click="zoomOut" icon="ZoomOut">缩小</el-button>
                            <el-button @click="resetCropper" icon="Refresh">重置</el-button>
                        </el-button-group>
                    </div>

                    <div class="editor-footer">
                        <el-button @click="exportImage" icon="Download">导出</el-button>
                        <div style="flex: 1"></div>
                        <el-button @click="closeEditor">取消</el-button>
                        <el-button type="primary" @click="applyCrop">应用裁剪</el-button>
                    </div>
                </div>
            </div>
        </teleport>
    </div>
</template>

<script setup lang="ts">
import OsIcon from '@/components/OsIcon/index.vue'
defineOptions({ name: 'FrontEnglishOcr' })
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
    ArrowLeft, Camera, Search, Picture, Delete, Plus, Loading,
    RefreshRight, ZoomIn, ZoomOut, Refresh, Close, Switch, Download,
    View, ArrowDown, ArrowRight,
    DocumentCopy,
    // 闭环完成面板用的两个图标（2026-10-26）
    CircleCheck, Headset,
    // 文档解析入口（2026-10-26）
    UploadFilled, Document, MagicStick
} from '@element-plus/icons-vue'
import { ocrRecognize, ocrRecognizeStream } from '@/api/english/ocr'
import { listFrontWordBooks, addWordBooks } from '@/api/wordBooks/wordBooks'
import { addWords, batchAddWords, listWords } from '@/api/words/words'
// 文档解析（2026-10-26）：后端 `/ai/question-bank/parse-files-blocks` 的封装，
// 支持 PDF / DOCX / DOC / TXT / MD / PPTX / XLSX
import { parseDocFile, isDocFile } from '@/utils/doc-parse'
// 复用聊天助手的流式接口（scene=ocr），不另写一条
import { assistantStream } from '@/api/ai/ai'

import { Cropper } from 'vue-advanced-cropper'
import 'vue-advanced-cropper/dist/style.css'

import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'




const router = useRouter()

// ⚠️ `currentUserId` 已删除（2026-10-23）：
//    它只被用来给 `/wordBooks/wordBooks/list` 传 `userId`，而后端**不接受**这个参数
//    （词书归属由登录态决定），传了也被忽略。现在改走 listFrontWordBooks，这个变量没有调用方了。

// 上传配置
/*
 * ⚠️ 2026-10-26：`uploadUrl` / `uploadHeaders` / `baseUrl` / `getToken` 全部删除。
 *
 *    它们原本服务于 `<el-upload :action="uploadUrl">` 的自动上传
 *    （文件先 POST 到 `/common/upload` 拿 URL）。改成本地分流处理后
 *    不再需要：图片用 `URL.createObjectURL()` 在浏览器内预览并保留 File，
 *    文档走 `parseDocFile()` 解析，两者都不必先"上传"。
 */

// 响应式数据
const uploadRef = ref(null)
const imageUrl = ref('')
const selectedFile = ref(null)
const recognizing = ref(false)
const batchAdding = ref(false)
const recognizedList = ref<any[]>([])
const bookOptions = ref<any[]>([])
const selectedBookId = ref(null)

/* ============================================================================
 * 新建词库（2026-10-26）
 *
 * 用户反馈：「目前只能选择已有的词库，不能选择新的词库」。
 * 原来必须先去「我的词库」建一本再回来，识别结果白识别一遍。
 * 现在在原地就能建，建完直接选中，识别结果不用重来。
 * ========================================================================== */
const createBookVisible = ref(false)
const creatingBook = ref(false)
const createBookName = ref('')
const createBookDesc = ref('')

/* ============================================================================
 * 文档解析（2026-10-26 新增）
 *
 * 用户反馈：「不支持 pdf md txt word 之类的文件解析」。
 *
 * 改前：`accept="image/png,image/jpeg,image/jpg"` —— 只能传图片。
 * 但后端其实早就有完整的文档解析能力
 * （`POST /ai/question-bank/parse-files-blocks`，走 `services/file_parser.py`，
 *  支持 PDF / DOCX / DOC / TXT / MD / PPTX / XLSX），
 * 前端 `utils/doc-parse.ts` 也早就封装好了 `parseDocFile()` ——
 * 只是这个页面没接。等于能力躺在仓库里没人用。
 *
 * 现在两种输入并存：
 *   · 图片 → 走多模态大模型识别（原有）
 *   · 文档 → 先解析出纯文本，再让大模型从文本里抽词条
 *
 * 为什么不把文档也塞给多模态模型：PDF/DOCX 是容器格式，
 * 多模态接口只吃图片；而且文档里可能有几十页文本，
 * 走纯文本抽取比让视觉模型"读"省几十倍 token。
 * ========================================================================== */
const parsedDocText = ref('')
const parsingFile = ref(false)
/** 当前处理的是文档而非图片 */
const isDocMode = ref(false)
/** 文档基本信息（展示用） */
const docInfo = ref<{ name: string; chars: number } | null>(null)

// 流式输出相关
const streamContent = ref('')
const resultViewMode = ref('words') // 'words' | 'json'

/**
 * 导入完成面板（2026-10-26 闭环）
 * ---------------------------------
 * 记录"刚把 N 个词加进了哪本词库"，用于渲染完成后的下一步入口。
 * 为 null 表示没有待展示的完成态。
 */
const donePanel = ref<{ bookId: number | null; bookName: string; count: number } | null>(null)

/** 导入成功后切到完成面板 */
function showDonePanel(bookId: number | null, count: number) {
    const book = bookOptions.value.find((b: any) => b.bookId === bookId)
    donePanel.value = {
        bookId: bookId || null,
        bookName: book?.bookName || '词库',
        count
    }
    /*
     * ⚠️ 2026-10-26：导入成功后要把图片预览收起来。
     *
     *    截图实测：图片预览占着上半屏（约 400px），完成面板被挤到下面，
     *    用户得滚动才能看到"已成功添加" —— 明明闭环做完了，却像没反应。
     *
     *    这里清掉预览（图片已经识别完、词也加进库了，留着没有意义），
     *    让完成面板独占视野。
     */
    imageUrl.value = ''
    selectedFile.value = null
    streamContent.value = ''
    const input = document.querySelector('.ocr-upload input[type=file]') as HTMLInputElement | null
    if (input) input.value = ''
}

/** 去词库详情看刚加的词 */
function goBookDetail() {
    const id = donePanel.value?.bookId
    if (!id) {
        router.push('/front/english/vocabulary')
        return
    }
    router.push(`/front/english/vocabulary/${id}`)
}

/** 直接开始听写（刚加的词就在这本词库里） */
function goListeningNow() {
    // 听写页已支持 auto/bookId/mode 查询参数（见 listening/index.vue 的 seed 处理），
    // 必须把刚导入的词书 id 带过去，否则用户跳到听写页还要自己再选一遍，且默认可能不是这本。
    const id = donePanel.value?.bookId
    router.push({
        path: '/front/english/listening',
        query: id ? { auto: '1', bookId: String(id), mode: 'dictation' } : { auto: '1', mode: 'dictation' }
    })
}

/** 再识别一张：把页面恢复到初始态 */
function restartOcr() {
    donePanel.value = null
    recognizedList.value = []
    streamContent.value = ''
    imageUrl.value = ''
    selectedFile.value = null
    resultViewMode.value = 'words'
    const input = document.querySelector('.ocr-upload input[type=file]') as HTMLInputElement | null
    if (input) input.value = ''
}

// 格式化后的 JSON
const formattedStreamJson = computed(() => {
    if (!streamContent.value) return ''
    try {
        // 提取 JSON 部分（可能包含 markdown 代码块）
        let jsonStr = streamContent.value
            .replace(/```json\s*/g, '')
            .replace(/```\s*/g, '')
            .trim()
        const parsed = JSON.parse(jsonStr)
        return JSON.stringify(parsed, null, 2)
    } catch (e) {
        // 如果不是完整 JSON，返回原始内容
        return streamContent.value
    }
})

const cacheStore = useFrontPageCacheStore()


// 词库预览相关
const showPreview = ref(true)
const bookPreview = ref({
    total: 0,
    items: []
})

// 编辑器相关
const editorVisible = ref(false)
const editorImageUrl = ref('')
const cropperRef = ref(null)
const defaultSize = ref({ width: 400, height: 400 })

// 裁剪框配置 - 显示所有 8 个控制点
const stencilProps = ref({
    aspectRatio: null,
    movable: true,
    resizable: true,
    handlers: {
        // 四边中点
        north: true,
        south: true,
        west: true,
        east: true,


    }
})

// 图片编辑相关
const rotation = ref(0)  // 旋转角度：0, 90, 180, 270
const editedImageFile = ref(null)  // 编辑后的图片文件

// 自定义尺寸限制算法（允许图片完全自由）
const sizeRestrictionsAlgorithm = (minWidth, minHeight, maxWidth, maxHeight) => {
    return {
        minWidth: 10,      // 最小宽度 10px
        minHeight: 10,     // 最小高度 10px
        maxWidth: 5000,    // 最大宽度 5000px
        maxHeight: 5000    // 最大高度 5000px
    }
}

// 旋转图片
const rotateImage = () => {
    rotation.value = (rotation.value + 90) % 360
    applyRotation()
}


// 打开编辑器时，根据图片尺寸调整默认裁剪框
// 打开编辑器
const openEditor = () => {
    if (!imageUrl.value) return

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
        // 限制最大尺寸，避免图片过大
        const maxSize = 1200
        let width = img.width
        let height = img.height

        // 如果图片太大，等比缩小
        if (width > maxSize || height > maxSize) {
            const scale = maxSize / Math.max(width, height)
            width = Math.round(width * scale)
            height = Math.round(height * scale)
        }

        // 确保尺寸是偶数
        if (width % 2 !== 0) width++
        if (height % 2 !== 0) height++

        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')
        canvas.width = width
        canvas.height = height

        ctx.drawImage(img, 0, 0, width, height)
        editorImageUrl.value = canvas.toDataURL('image/jpeg', 0.9)
        editorVisible.value = true
    }
    img.onerror = () => {
        editorImageUrl.value = imageUrl.value
        editorVisible.value = true
    }
    img.src = imageUrl.value
}

// 导出当前预览图片
const exportCurrentImage = () => {
    if (!imageUrl.value) {
        ElMessage.warning('没有可导出的图片')
        return
    }

    // 如果有编辑后的文件，导出编辑后的
    if (editedImageFile.value) {
        const url = URL.createObjectURL(editedImageFile.value)
        const link = document.createElement('a')
        link.download = editedImageFile.value.name || `image_${Date.now()}.jpg`
        link.href = url
        link.click()
        URL.revokeObjectURL(url)
        ElMessage.success('图片已导出')
        return
    }

    // 否则导出原始图片
    const link = document.createElement('a')
    link.download = `image_${Date.now()}.jpg`
    link.href = imageUrl.value
    link.click()
    ElMessage.success('图片已导出')
}

// 关闭编辑器
const closeEditor = () => {
    editorVisible.value = false
}

// 导出图片
const exportImage = () => {
    if (!cropperRef.value) {
        ElMessage.warning('没有可导出的图片')
        return
    }

    const result = cropperRef.value.getResult()
    const canvas = result.canvas

    if (canvas) {
        // 创建下载链接
        const link = document.createElement('a')
        link.download = `edited_image_${Date.now()}.jpg`
        link.href = canvas.toDataURL('image/jpeg', 0.9)
        link.click()

        ElMessage.success('图片已导出')
    } else {
        ElMessage.error('导出失败')
    }
}


// 旋转
const rotate = (angle) => {
    if (cropperRef.value) {
        cropperRef.value.rotate(angle)
    }
}

// 翻转
const flip = (direction) => {
    if (cropperRef.value) {
        cropperRef.value.flip(true, direction === 'horizontal')
    }
}

// 重置裁剪器
const resetCropper = () => {
    if (cropperRef.value) {
        cropperRef.value.reset()
    }
}

// 裁剪变化
const onCropChange = (data) => {
    // 可以在这里实时获取裁剪区域
}

// 应用裁剪（同时应用旋转和翻转）
const applyCrop = () => {
    if (!cropperRef.value) return

    // 获取当前裁剪结果（已经包含旋转和翻转）
    const result = cropperRef.value.getResult()
    const canvas = result.canvas

    if (canvas) {
        // 将编辑后的图片转为 Data URL
        const editedUrl = canvas.toDataURL('image/jpeg', 0.9)
        imageUrl.value = editedUrl

        // 生成新文件用于上传
        canvas.toBlob((blob) => {
            editedImageFile.value = new File([blob], 'edited_image.jpg', { type: 'image/jpeg' })
            selectedFile.value = editedImageFile.value
        }, 'image/jpeg', 0.9)

        // 重置预览状态
        rotation.value = 0
        imageScale.value = 1
        imagePosition.value = { x: 0, y: 0 }

        ElMessage.success('图片已保存')
        closeEditor()
    }
}



// 图片缩放和拖拽相关
const imageScale = ref(1)
const imagePosition = ref({ x: 0, y: 0 })
const isDragging = ref(false)
const startDragPosition = ref({ x: 0, y: 0 })
const previewImageRef = ref(null)

// 缩放图片
// 放大
const zoomIn = () => {
    if (cropperRef.value) {
        cropperRef.value.zoom(1.2)
    }
}

// 缩小
const zoomOut = () => {
    if (cropperRef.value) {
        cropperRef.value.zoom(0.8)
    }
}

const resetZoom = () => {
    imageScale.value = 1
    imagePosition.value = { x: 0, y: 0 }
}

// 开始拖拽
const startDrag = (e) => {
    isDragging.value = true
    startDragPosition.value = {
        x: e.clientX - imagePosition.value.x,
        y: e.clientY - imagePosition.value.y
    }
    e.preventDefault()
}

// 拖拽中
const onDrag = (e) => {
    if (!isDragging.value) return
    imagePosition.value = {
        x: e.clientX - startDragPosition.value.x,
        y: e.clientY - startDragPosition.value.y
    }
}

// 结束拖拽
const stopDrag = () => {
    isDragging.value = false
}

// 滚轮缩放
const onWheel = (e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    const newScale = imageScale.value + delta
    if (newScale >= 0.5 && newScale <= 3) {
        imageScale.value = newScale
    }
}


// 应用旋转并生成新文件
const applyRotation = () => {
    if (!imageUrl.value) return

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = imageUrl.value

    img.onload = () => {
        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')

        // 根据旋转角度设置画布尺寸
        if (rotation.value === 90 || rotation.value === 270) {
            canvas.width = img.height
            canvas.height = img.width
        } else {
            canvas.width = img.width
            canvas.height = img.height
        }

        // 平移并旋转
        ctx.translate(canvas.width / 2, canvas.height / 2)
        ctx.rotate(rotation.value * Math.PI / 180)
        ctx.drawImage(img, -img.width / 2, -img.height / 2)

        // 更新预览
        const rotatedUrl = canvas.toDataURL('image/jpeg', 0.9)
        imageUrl.value = rotatedUrl

        // 生成新文件用于上传
        canvas.toBlob((blob) => {
            editedImageFile.value = new File([blob], 'rotated_image.jpg', { type: 'image/jpeg' })
            selectedFile.value = editedImageFile.value
        }, 'image/jpeg', 0.9)
    }
}

// 重置旋转
const resetRotation = () => {
    rotation.value = 0
}

// 返回上一页
// ⚠️ 2026-10-26：「英语学习」的入口首页已下线，返回目标改成第一个子页
//    （拍照识词自己就是入口，所以返回「我的词库」—— 这是下一个最常去的页面）。
/*
 * 原 `goBack()` 已删除（2026-10-26）：返回栏从模板移除后没有调用方。
 */

// ==================== 文件入口（2026-10-26 重写） ====================
/**
 * 统一的文件处理入口：按类型分流
 *
 *   图片  → 读成 data URL 预览 + 保留 File（走多模态识别）
 *   文档  → 调 `parseDocFile()` 解析出纯文本（走 AI 文本抽取）
 *
 * ⚠️ `auto-upload="false"` 是这个分流能成立的前提。
 *    原来 el-upload 配了 `:action` + `:on-success`，文件会被它自己 POST 到
 *    `/common/upload`，拿到一个 URL —— 那条路只对图片有意义。
 *    文档不需要上传，需要的是**解析**，所以改成自己接 `on-change`。
 */
const handleFileChange = async (uploadFile: any) => {
    const raw: File | undefined = uploadFile?.raw
    if (!raw) return

    // 大小限制：图片 10MB，文档 20MB（PDF 常见几十页，给宽一点）
    const ext = (raw.name.split('.').pop() || '').toLowerCase()
    const isDoc = isDocFile(raw.name, raw.type)
    const limitMB = isDoc ? 20 : 10
    if (raw.size / 1024 / 1024 > limitMB) {
        ElMessage.error(`${isDoc ? '文档' : '图片'}大小不能超过 ${limitMB}MB`)
        uploadRef.value?.clearFiles()
        return
    }

    if (isDoc) {
        await parseDocInput(raw)
        return
    }

    // 图片分支
    const isImage = (raw.type || '').startsWith('image/') ||
        ['png', 'jpg', 'jpeg', 'webp', 'bmp'].includes(ext)
    if (!isImage) {
        ElMessage.error(`不支持的文件类型：.${ext}`)
        uploadRef.value?.clearFiles()
        return
    }

    // 重置文档态
    isDocMode.value = false
    parsedDocText.value = ''
    docInfo.value = null

    selectedFile.value = raw
    imageUrl.value = URL.createObjectURL(raw)
    rotation.value = 0
    editedImageFile.value = null
    imageScale.value = 1
    imagePosition.value = { x: 0, y: 0 }
    ElMessage.success('图片已就绪，点「开始识别」')
}

/**
 * 解析文档（PDF / Word / Markdown / TXT …）
 *
 * 后端 `parse_file()` 支持 PDF / DOCX / DOC / TXT / MD / PPTX / XLSX，
 * 前端 `parseDocFile()` 是它的封装。这里只负责：
 *   ① 拿到纯文本；
 *   ② 处理「解析出 0 字符」这种最常见的失败（扫描版 PDF / 空文档）；
 *   ③ 把结果放进 `parsedDocText`，交给 `startDocExtract()` 抽词条。
 */
const parseDocInput = async (file: File) => {
    parsingFile.value = true
    try {
        const parsed = await parseDocFile(file)
        if (!parsed) {
            ElMessage.error('文档解析失败，换个文件试试')
            return
        }
        if (parsed.error) {
            ElMessage.error(parsed.error)
            return
        }

        const text = String(parsed.textContent || '').trim()
        if (!text) {
            /*
             * 解析成功但一个字都没有 —— 最典型的是**扫描版 PDF**（图片层）。
             * 这时纯文本抽取无能为力，得让用户走图片识别。
             * 明确告诉他该怎么做，而不是只说"失败了"。
             */
            ElMessage.warning(
                '这个文档里没有可提取的文字（可能是扫描版 PDF）。可以截图后按图片上传识别。'
            )
            return
        }

        isDocMode.value = true
        parsedDocText.value = text
        docInfo.value = { name: file.name, chars: text.length }
        // 清掉图片态，两种模式互斥
        imageUrl.value = ''
        selectedFile.value = null
        recognizedList.value = []

        ElMessage.success(`已提取 ${text.length} 个字符，点「让 AI 提取单词」`)
    } catch (error: any) {
        console.error('文档解析失败:', error)
        ElMessage.error('文档解析失败：' + (error?.message || error))
    } finally {
        parsingFile.value = false
        uploadRef.value?.clearFiles()
    }
}

/** 移除文档 */
const removeDoc = () => {
    isDocMode.value = false
    parsedDocText.value = ''
    docInfo.value = null
    recognizedList.value = []
    uploadRef.value?.clearFiles()
}

/**
 * 从文档文本里抽词条
 *
 * 走和多模态识别**同一个** scene=`ocr` 的流式接口 ——
 * 该场景的提示词就是"输出词条 JSON 数组"，只是这次喂的是文本而不是图片。
 * 复用同一条链路的好处：解析、渲染、导入、去重全都不用再写一遍。
 */
const startDocExtract = async () => {
    if (!parsedDocText.value.trim()) {
        ElMessage.warning('没有可提取的文字')
        return
    }

    recognizing.value = true
    recognizedList.value = []
    streamContent.value = ''
    resultViewMode.value = 'words'

    const prompt = `下面是一份英语学习材料，请从中提取英文单词 / 词组，输出 JSON 数组。
每个元素包含 english（英文）、chinese（中文释义）、phonetic（音标，可空）。
只提取真正值得背的词条，跳过人名、语法术语和明显无关的内容。
如果材料里已经带了中文释义，优先沿用材料里的释义。

【材料开始】
${parsedDocText.value.slice(0, 12000)}
【材料结束】`

    try {
        await assistantStream(
            prompt,
            (full) => {
                streamContent.value = full
            },
            (full) => {
                streamContent.value = full
                recognizing.value = false
                parseStreamResult(full)
            },
            (err: any) => {
                console.error('文档提取失败:', err)
                ElMessage.error('AI 提取失败：' + (err?.message || err))
                recognizing.value = false
            },
            undefined,
            undefined,
            undefined,
            // 空 sessionId：一次性生成，不写聊天历史
            '',
            undefined,
            { scene: 'ocr' }
        )
    } catch (e: any) {
        console.error('文档提取异常:', e)
        ElMessage.error('AI 提取失败')
        recognizing.value = false
    }
}


// 上传失败
const handleUploadError = () => {
    ElMessage.error('文件处理失败')
}

// 删除图片
const removeImage = () => {
    imageUrl.value = ''
    selectedFile.value = null
    recognizedList.value = []
    rotation.value = 0
    editedImageFile.value = null
    imageScale.value = 1
    imagePosition.value = { x: 0, y: 0 }
    uploadRef.value?.clearFiles()
}

// ==================== 开始 OCR 识别（流式输出） ====================
// 流式输出：AI 边识别边返回结果，用户可以实时看到识别进度
// 对比非流式：需要等待全部识别完成才能看到结果
const startRecognize = async () => {
    if (!selectedFile.value) {
        ElMessage.warning('请先上传图片')
        return
    }

    // 重置状态
    recognizing.value = true
    recognizedList.value = []
    streamContent.value = ''
    resultViewMode.value = 'words'

    // 调用流式 OCR API
    ocrRecognizeStream(
        selectedFile.value,
        // onChunk 回调：每收到一个数据块就更新显示
        (fullContent) => {
            streamContent.value = fullContent
        },
        // onComplete 回调：流式完成，解析最终结果
        (fullContent) => {
            streamContent.value = fullContent
            recognizing.value = false
            // 尝试解析最终结果
            parseStreamResult(fullContent)
        },
        // onError
        (error) => {
            console.error('OCR流式识别失败:', error)
            ElMessage.error('识别请求失败')
            recognizing.value = false
        }
    )
}

// ==================== 解析流式结果 ====================
// AI 返回的内容可能包含 markdown 代码块标记，需要清理后解析 JSON
const parseStreamResult = (content) => {
    if (!content) return

    try {
        // 清理 markdown 代码块标记（```json ... ```）
        let jsonStr = content
            .replace(/```json\s*/g, '')
            .replace(/```\s*/g, '')
            .trim()
        const parsed = JSON.parse(jsonStr)
        if (Array.isArray(parsed)) {
            parseOcrResultFromWords(parsed)
            ElMessage.success(`识别完成，共 ${parsed.length} 个词条`)
        }
    } catch (e) {
        // JSON 解析失败，尝试按文本格式解析（兼容旧格式）
        console.log('流式结果不是标准 JSON，尝试文本解析')
        parseOcrResult(content)
    }
}

// ==================== 从 words 数组解析词条 ====================
// 将 AI 返回的 JSON 数组转换为前端可编辑的词条格式
const parseOcrResultFromWords = (words) => {
    if (!words || words.length === 0) {
        recognizedList.value = []
        return
    }

    // 映射为统一的词条格式
    // ⚠️ `bookId`（不是 wordBookId）：模板里的下拉绑的是 `word.bookId`，
    //    填成 wordBookId 会让每张卡片的词库选择框都是空的。
    // ⚠️ `wordType` 已去掉：`words` 表没有这一列。
    recognizedList.value = words.map((item, index) => ({
        id: index,
        english: item.english || '',
        chinese: item.chinese || '',
        phonetic: item.phonetic || '',
        bookId: selectedBookId.value,  // 默认使用全局选择的词库
        adding: false
    }))

    console.log('词条解析完成，数量:', recognizedList.value.length)
}

// ==================== 解析 OCR 结果（兼容多种格式） ====================
// 支持 JSON 格式和纯文本格式，优先使用 JSON
const parseOcrResult = (text) => {
    if (!text) return

    recognizedList.value = []

    // 1. 优先尝试 JSON 格式解析
    try {
        const parsed = JSON.parse(text)
        if (Array.isArray(parsed) && parsed.length > 0) {
            recognizedList.value = parsed.map((item, index) => ({
                id: index,
                english: item.english || '',
                chinese: item.chinese || '',
                phonetic: item.phonetic || '',
                adding: false,
                bookId: selectedBookId.value
            }))
            console.log('JSON 解析成功，词条数:', recognizedList.value.length)
            return
        }
    } catch (e) {
        console.log('非 JSON 格式，使用文本解析')
    }

    // 2. 兜底：纯文本格式解析（兼容旧版 OCR 结果）
    // 按行分割，每行尝试提取英文和中文
    const lines = text.split('\n').filter(line => line.trim() !== '')

    lines.forEach((line, index) => {
        let english = ''
        let chinese = ''
        let phonetic = ''

        // 提取音标（/.../ 格式）
        const phoneticMatch = line.match(/\/[^/]+\//)
        if (phoneticMatch) {
            phonetic = phoneticMatch[0]
            line = line.replace(phonetic, '').trim()
        }

        // 按不同分隔符分割英文和中文
        if (line.includes(':')) {
            // 冒号分隔：english: 中文释义
            const parts = line.split(':')
            english = parts[0].trim()
            chinese = parts.slice(1).join(':').trim()
        }
        else if (line.includes('  ')) {
            // 多空格分隔：english  中文释义
            const parts = line.split(/\s{2,}/)
            english = parts[0].trim()
            chinese = parts.slice(1).join(' ').trim()
        }
        else if (line.includes(' ')) {
            // 单空格分隔：取第一个空格前后
            const firstSpaceIndex = line.indexOf(' ')
            english = line.substring(0, firstSpaceIndex).trim()
            chinese = line.substring(firstSpaceIndex + 1).trim()
        }
        else {
            // 无分隔符：整行当作英文
            english = line.trim()
        }

        // 清理英文：移除音标和词性标注残留
        english = english.replace(/\/[^/]+\//g, '').trim()  // 移除音标
        english = english.replace(/\s+[nvadjp]+\.?$/i, '').trim()  // 移除词性

        // 修复粘连词组
        if (english === 'stealtheshow') english = 'steal the show'

        if (english) {
            recognizedList.value.push({
                id: index,
                english,
                chinese,
                phonetic,
                adding: false,
                bookId: selectedBookId.value
            })
        }
    })

    // 3. 过滤无效词条（标题、太短的文本等）
    recognizedList.value = recognizedList.value.filter(word => {
        const lowerEnglish = word.english.toLowerCase()
        // 过滤常见标题词
        if (['word tips', 'vocabulary', 'words', '单词', '词汇'].includes(lowerEnglish)) {
            return false
        }
        // 英文长度至少 2 个字符
        return word.english && word.english.length >= 2
    })

    console.log('文本解析完成，词条数:', recognizedList.value.length)
}

// ==================== 词条操作 ====================
// 移除单个词条（从识别结果列表中删除）
const removeWord = (index) => {
    recognizedList.value.splice(index, 1)
}

// 添加单个单词到词库
const addSingleWord = async (word, index) => {
    if (!word.bookId && !selectedBookId.value) {
        ElMessage.warning('请先选择词库')
        return
    }

    if (!word.english || !word.chinese) {
        ElMessage.warning('请填写英文和中文')
        return
    }

    word.adding = true

    // ⚠️ 后端契约：`bookId / word / translation`。
    //    `words` 表**没有 wordType 列**，所以不再传它（原代码传了也存不进去）。
    const wordData = {
        bookId: word.bookId || selectedBookId.value,
        word: word.english,
        translation: word.chinese,
        phonetic: word.phonetic || ''
    }

    try {
        const response = await addWords(wordData)
        if (response.code === 200) {
            ElMessage.success(`"${word.english}" 添加成功`)
            recognizedList.value.splice(index, 1)
            // 全部加完时给出闭环出口
            if (recognizedList.value.length === 0) {
                showDonePanel(wordData.bookId || selectedBookId.value, 1)
            }
        } else {
            ElMessage.error(response.msg || '添加失败')
        }
    } catch (error) {
        console.error('添加失败:', error)
        ElMessage.error('添加失败')
    } finally {
        word.adding = false
    }
}

// ==================== 批量添加所有词条 ====================
// 将识别结果中的所有词条批量导入到选定的词库中
const addAllWords = async () => {
    if (!selectedBookId.value) {
        ElMessage.warning('请先选择词库')
        return
    }

    if (recognizedList.value.length === 0) {
        ElMessage.warning('没有可添加的单词')
        return
    }

    const invalidWords = recognizedList.value.filter(w => !w.english || !w.chinese)
    if (invalidWords.length > 0) {
        ElMessage.warning(`有 ${invalidWords.length} 个词条缺少单词或释义，请补充完整`)
        return
    }

    batchAdding.value = true

    // ⚠️ 后端契约：`batchAddWords(bookId, words[])`（不再传 wordType）
    const batchData = recognizedList.value.map(word => ({
        word: word.english,
        translation: word.chinese,
        phonetic: word.phonetic || ''
    }))

    try {
        const response = await batchAddWords(selectedBookId.value, batchData)
        if (response.code === 200) {
            const bookId = selectedBookId.value
            const count = batchData.length
            ElMessage.success(`成功添加 ${count} 个词条`)
            recognizedList.value = []
            /*
             * 2026-10-26 闭环（用户：「要形成闭环」）
             * -------------------------------------
             * 原来导入成功后只是把列表清空 —— 用户加完词就"断"在那里，
             * 不知道接下来该干什么，也没法直接去背这些词。
             *
             * 现在导入成功会切到一个「完成面板」，给出三个下一步：
             *   · 去词库看/继续加词
             *   · 直接开始听写（刚加的词就是练习内容）
             *   · 再识别一张
             */
            showDonePanel(bookId, count)
        } else {
            ElMessage.error(response.msg || '批量添加失败')
        }
    } catch (error) {
        console.error('批量添加失败:', error)
        ElMessage.error('批量添加失败')
    } finally {
        batchAdding.value = false
    }
}

// ==================== 加载词库选项 ====================
// 获取当前用户的所有词库，用于下拉选择
const loadBookOptions = async () => {
    try {
        // ⚠️ 2026-10-23 修：原来传 `pageSize: 100` 撞在后端上限（le=100）边界上，
        //    且多传了一个后端不认的 `userId`（归属由登录态决定）。
        //    改用 listFrontWordBooks（内部按 100 翻页取全量），词库多于 100 本也不会漏。
        const response = await listFrontWordBooks()
        if (response.code === 200) {
            bookOptions.value = response.rows || []
            if (bookOptions.value.length > 0) {
                selectedBookId.value = bookOptions.value[0].bookId
                previousBookId.value = selectedBookId.value
                // 加载第一个词库的预览
                loadBookPreview(selectedBookId.value)
            }
        } else {
            ElMessage.error(response.msg || '加载词库失败')
        }
    } catch (error) {
        console.error('加载词库失败:', error)
    }
}


// 词库切换时加载预览
/*
 * ⚠️ 下拉里混了一个「+ 新建词库」选项（value = '__create__'）。
 *    它必须在这里被拦下来：`v-model` 会先把 `selectedBookId` 改成 '__create__'，
 *    如果直接往下走，`loadBookPreview('__create__')` 会拿一个非数字去请求后端 → 422。
 *    处理完把 `selectedBookId` 还原成原来那本，再打开新建弹窗。
 */
const onBookChange = (bookId) => {
    if (bookId === '__create__') {
        // 还原选择：新建完才真正切换
        selectedBookId.value = previousBookId.value
        openCreateBook()
        return
    }
    previousBookId.value = bookId
    if (bookId) {
        loadBookPreview(bookId)
    }
}

/** 上一次选中的词库 id（用于「+ 新建词库」被点中时还原选择） */
const previousBookId = ref(null)

/** 打开新建词库弹窗 */
const openCreateBook = () => {
    createBookName.value = ''
    createBookDesc.value = ''
    createBookVisible.value = true
}

/**
 * 真正创建词库并选中
 *
 * 建完立刻：
 *   ① 塞进 `bookOptions` 顶部（不用重新拉列表，省一次请求，也能马上看到）；
 *   ② 选中它并加载预览（此时是空的，预览会显示"共 0 条"，属正常）；
 *   ③ 清空识别结果里的 `bookId` 旧值 ——
 *      识别时每张卡片会带一个 `word.bookId`，如果那个值还指向旧词库，
 *      单个「添加」会绕开刚选的新词库走旧值（`word.bookId || selectedBookId`）。
 */
const confirmCreateBook = async () => {
    const name = createBookName.value.trim()
    if (!name) {
        ElMessage.warning('请填写词库名称')
        return
    }
    // 重名检查：词库名不唯一，但用户建两本同名的自己也会懵
    if (bookOptions.value.some((b) => String(b.bookName) === name)) {
        ElMessage.warning(`已经有叫「${name}」的词库了，换个名字或直接选中那本`)
        return
    }

    creatingBook.value = true
    try {
        const res = await addWordBooks({
            bookName: name,
            bookDescription: createBookDesc.value.trim() || undefined
        })
        if (res.code !== 200) {
            ElMessage.error(res.msg || '创建词库失败')
            return
        }

        /*
         * 后端 `POST /wordBooks/wordBooks` 只返回 `{code, msg}` —— **不带新书的 id**
         * （见 `api/v1/words.py`）。所以不能直接用返回值，得重新拉一次列表，
         * 按名字倒查 id，再选中它。多一次请求，但可靠。
         */
        const list = await listFrontWordBooks()
        if (list.code === 200) {
            bookOptions.value = list.rows || []
            const created = bookOptions.value.find((b) => String(b.bookName) === name)
            if (created) {
                selectedBookId.value = created.bookId
                previousBookId.value = created.bookId
                loadBookPreview(created.bookId)
            }
            // 识别结果里已有的 `bookId` 全部指向新书，避免单个「添加」走旧值
            recognizedList.value.forEach((w) => {
                w.bookId = created?.bookId ?? w.bookId
            })
        }

        createBookVisible.value = false
        ElMessage.success(`已创建词库「${name}」并选中`)
    } catch (error) {
        console.error('创建词库失败:', error)
        ElMessage.error('创建词库失败')
    } finally {
        creatingBook.value = false
    }
}

// 加载词库预览数据
const loadBookPreview = async (bookId) => {
    try {
        // ⚠️ 后端参数名是 `bookId`
        const response = await listWords({
            bookId: bookId,
            pageNum: 1,
            pageSize: 10
        })
        if (response.code === 200) {
            const items = response.rows || []
            // ⚠️ `words` 表没有 wordType 列，原先按类型分三项统计永远是 0。
            //    这里只报总数 —— 数字必须是真的。
            bookPreview.value = {
                total: response.total || 0,
                items: items.slice(0, 5) // 只显示前5条
            }
        }
    } catch (error) {
        console.error('加载词库预览失败:', error)
    }
}

// 跳转到词库管理
const goToVocabulary = () => {
    router.push('/front/english/vocabulary')
}

// 一键复制
const copyContent = async () => {
    const text = resultViewMode.value === 'json' ? formattedStreamJson.value : JSON.stringify(recognizedList.value, null, 2)
    try {
        await navigator.clipboard.writeText(text)
        ElMessage.success('已复制到剪贴板')
    } catch {
        ElMessage.error('复制失败')
    }
}



onMounted(() => {
    loadBookOptions()
})
</script>

<style scoped lang="scss" src="./index.style1.scss"></style>

<!-- 新增：全局样式，用于模态框 -->
<style lang="scss" src="./index.style2.scss"></style>