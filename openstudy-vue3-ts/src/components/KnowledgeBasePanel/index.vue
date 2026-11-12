<!-- components/KnowledgeBasePanel/index.vue -->
<!--
  知识库面板（可嵌进任意容器：智能体页的右侧抽屉、悬浮助手的「我的知识库」tab）

  与 `KnowledgeBaseDrawer` 的关系：
    · 抽屉 = 入口按钮 + 弹层，那一层外壳留在 KnowledgeBaseDrawer 里；
    · 本组件 = **纯内容**（建库 / 传文档 / 看状态 / 删 / 试检索），不含任何弹层外壳，
      由调用方决定「以抽屉呈现」还是「以 tab 呈现」。
    两边的后端能力完全一致 —— 功能本身只有这一份实现。

  这里的职责是**管理资料**。**问答不在这里做** ——
  用户直接在输入框提问，Agent 会自己用 `knowledge_search` 去检索
  （后端 L1 注入还会把知识库清单塞进系统提示词，模型知道有哪些库可查）。

  ⚠️ 内容**挂载后不会自动加载**：调用方在「显示它的那一刻」调 `activate()`。
     这样避免懒挂载（v-if）与自动加载（onMounted）撞成两次请求。
-->
<template>
    <div class="kb-panel kb-body">
      <!-- ── 头部 ── -->
      <div class="kb-head">
        <div class="kb-head-left">
          <span class="kb-title">我的资料</span>
          <span class="kb-sub">传进来的资料，智能体会自己检索后回答</span>
        </div>
        <div class="kb-head-right">
          <el-button size="small" :icon="Plus" :disabled="creating" @click="promptCreate">新建</el-button>
          <span v-if="closable" class="kb-close" title="收起" @click="emit('close')">
            <el-icon><Close /></el-icon>
          </span>
        </div>
      </div>

      <div class="kb-main" v-loading="loading">
        <!-- 「列表没取到」不是「没有知识库」，必须显式说出来。
             静默跳过的话下面 `.kb-empty` 会退化成「还没有知识库，新建一个…」——
             一个有十几个库的用户会被告知他一个库都没有。 -->
        <div v-if="!loading && kbLoadFailed" class="kb-load-failed">
          <span>资料列表这次没取到，下面显示的可能不是最新的。</span>
          <el-button size="small" text type="primary" @click="loadKbs()">重试</el-button>
        </div>

        <!-- ── 统一搜索框 ──
             一个框同时干两件事，但**回车默认搜全部未屏蔽的库**，不再只看「名字带关键词」的库：
               · 输入时：按名字挑库（纯本地过滤，瞬发）；
               · 回车 / 点「搜索资料」：跨库检索正文，结果按**文档**分组，每条都标出所属知识库；
               · 想收窄范围：在列表里勾选知识库（勾了 = 只搜这些）；不勾 = 搜全部。
             ⚠️ 不能做成两个输入框：「我要找 X」对用户是一个问题，逼他先判断
                「X 是库名还是正文」才是真正的负担。 -->
        <div v-if='kbs.length || query' class='kb-search'>
          <el-icon class='kb-search-icon'><Search /></el-icon>
          <input v-model='query' class='kb-search-input' :placeholder='searchPlaceholder'
            @keydown.enter='runSearch' @keydown.esc='clearSearch' />
          
          
          <span v-if='query' class='kb-search-clear' title='清空（Esc）' @click='clearSearch'>
            <el-icon><Close /></el-icon>
          </span>
          <el-button v-if='query && !resultsMode' class='kb-search-go' size='small' type='primary' :loading='searching' @click='runSearch'>搜索资料</el-button>
        </div>


        <!-- 作用域提示：让「回车会搜哪儿」永远可见，避免用户误读检索范围 -->
        <div v-if='query && !resultsMode' class='kb-scope'>
          <span class='kb-scope-hint'>
            <template v-if='selectedKbIds.length'>在勾选的 {{ selectedKbIds.length }} 个资料夹里搜资料</template>
            <template v-else>在全部 {{ enabledKbCount }} 个资料夹里搜资料（不只名字带这个词的库）</template>
          </span>
          
        </div>
        <!-- ── 搜索结果 ── -->
        <div v-if='resultsMode' class='kb-results'>
          <div class='kb-results-head'>
            <div class='kb-results-title'>
              <!--
                低置信时不能说"找到 N 段相关资料" —— 那是把"最像的几条"说成"相关的"。
                向量检索总会凑够 top_k 条（见 hybrid_search.DEFAULT_MIN_SIMILARITY 的实测），
                所以这里如实降级措辞，并在下面给一条提示。
              -->
              <template v-if='searchLowConfidence'>
                没有明显匹配，下面 {{ searchHits.length }} 段<strong>可能不相关</strong>
              </template>
              <template v-else>
                找到 <b>{{ searchHits.length }}</b> 段相关资料
              </template>
              <span class='kb-results-scope'>{{ searchedScopeLabel }}</span>
            </div>
            <el-button size='small' text @click='exitResults'>返回我的资料</el-button>
          </div>

          <!-- 低置信提示：说清"这是模型凑出来的最像的结果"，而不是假装搜到了 -->
          <div v-if='searchLowConfidence && searchHits.length' class='kb-lowconf'>
            <el-icon><Warning /></el-icon>
            <span>
              你的问题和这些资料可能对不上 —— 这些资料里也许没有相关内容。
              换个说法试试，或确认勾选的资料夹是否正确。
            </span>
          </div>

          <div v-if='!searchHits.length' class='kb-empty'>
            <div class='kb-empty-title'>没搜到「{{ searchedQuery }}」</div>
            <div class='kb-empty-desc'>
              {{ searchedScopeHint }}可能是资料里确实没有，也可能换个说法就行了。
            </div>
          </div>

          <!-- 结果按**文档**分组，而不是一串匿名片段：
               · 组头 = 文档名 + 所属知识库 + 命中段数 —— 「这篇在哪个库里」一眼可见；
               · 组头右侧可直接跳到那个知识库（跨库结果里最常用的下一步）。
               ⚠️ 分组 key 必须带 kbId：不同知识库完全可以有同名文件。 -->
          <div v-else class='kb-hit-groups'>
            <div v-for='g in hitGroups' :key='g.key' class='kb-hit-group'>
              <div class='kb-group-head'>
                <el-icon class='kb-group-icon'><Document /></el-icon>
                <div class='kb-group-title'>
                  <div class='kb-group-doc' :title='g.docName'>{{ g.docName }}</div>
                  <div class='kb-group-meta'>
                    <span v-if='g.kbName' class='kb-hit-kb'>{{ g.kbName }}</span>
                    <span v-if='g.isWiki' class='kb-hit-kb'>知识百科</span>
                    <span>{{ g.hits.length }} {{ g.isWiki ? '节' : '段' }}命中</span>
                  </div>
                </div>
                <span v-if='g.kbId' class='kb-group-open' title='打开这个资料夹' @click='gotoKb(g.kbId)'>
                  <el-icon><FolderOpened /></el-icon>
                </span>
              </div>

              <div v-for='(h, j) in g.hits' :key='h.chunkId' class='kb-hit'
                :class='{ open: expandedIds.includes(h.chunkId) }'>
                <div class='kb-hit-head' @click='toggleExpand(h.chunkId)'>
                  <span class='kb-hit-idx'>{{ j + 1 }}</span>
                  <div class='kb-hit-title'>
                    <div class='kb-hit-meta'>
                      <span>{{ h.wikiHit ? (h.wikiSection || '主题页') : `第 ${h.chunkIndex + 1} 段` }}</span>
                      <!-- 库里可能有同名文档，所以组头之外每段再标一次库名 -->
                      <span v-if='kbNameOf(h.kbId)' class='kb-hit-kb'>{{ kbNameOf(h.kbId) }}</span>
                    </div>
                  </div>
                  <span v-if='h.score != null' class='kb-hit-score' title='融合排序分（RRF，只看排名）'>
                    {{ Number(h.score).toFixed(3) }}
                  </span>
                </div>
                <div class='kb-hit-body' v-html='highlight(h.content)'></div>
                <div class='kb-hit-ops'>
                  <span class='kb-op' title='复制这段原文' @click.stop='copyHit(h)'>
                    <el-icon><DocumentCopy /></el-icon>
                  </span>
                  <span v-if='!h.wikiHit' class='kb-op' title='查看原文' @click.stop='openAnatomyOf(h)'>
                    <el-icon><View /></el-icon>
                  </span>
                  <span class='kb-hit-more' @click.stop='toggleExpand(h.chunkId)'>
                    {{ expandedIds.includes(h.chunkId) ? '收起' : '展开全文' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="kb-list-wrap">
          <!-- 范围选择条：把「这次搜哪些库」变成可点选的对象。
               ⚠️ 默认**一个都不勾 = 搜全部**（不是搜不到）——
                  与「我什么都没选，所以全都要搜」的直觉一致；想收窄再勾，
                  不用先「全选」再一个个取消。 -->
          <div class="kb-pick-bar">
            <span class="kb-pick-hint" :class="{ on: selectedKbIds.length > 0 }">
              {{ selectedKbIds.length ? `已选 ${selectedKbIds.length} 个：搜索只查这些` : '未勾选 = 搜索全部资料' }}
            </span>
            <el-button v-if="selectedKbIds.length" size="small" text type="primary" @click="clearKbSelection">取消勾选</el-button>
            <el-button v-else size="small" text @click="selectAllKbs">全部勾上</el-button>
          </div>

          <div v-for="kb in kbs" :key="kb.kbId"
            :class="['kb-item', { active: kb.kbId === activeKbId, blocked: kb.disabled === 1 }]" @click="selectKb(kb)">
            <!-- 勾选 = 把它算进搜索范围；点它**不能**顺手打开这个库，
                 所以必须 stop —— 否则每勾一次都会连带切换下面的文档区。 -->
            <el-checkbox class="kb-pick" :model-value="selectedKbIds.includes(kb.kbId)"
              :disabled="kb.disabled === 1"
              :title="kb.disabled === 1 ? '已屏蔽的库不参与检索，勾不了' : '勾上它：搜索资料时只查勾选的资料夹'"
              @click.stop @change="toggleKbPick(kb)" />
            <div class="kb-item-main">
              <div class="kb-item-name" :title="kb.name">{{ kb.name }}</div>
              <div class="kb-item-meta">
                <span>{{ kb.docCount || 0 }} 篇文档</span>
                <span>{{ kb.chunkCount || 0 }} 个分块</span>
                <!-- 屏蔽状态**常驻**显示：用户要能一眼看出「哪些库智能体现在看不到」 -->
                <span v-if="kb.disabled === 1" class="kb-item-blocked">已屏蔽</span>
              </div>
            </div>

            <!-- 屏蔽开关放在 .kb-item-ops **外面**：那边是 `opacity: 0`（hover 才显形），
                 开关放进去的话「哪个库被屏蔽了」在列表上根本看不出来 ——
                 而「一眼看出哪些库被屏蔽」正是用户拨它的目的。
                 被屏蔽的库**仍然留在列表里**（后端也故意保留），否则就没法取消屏蔽了。

                 开关「开」= 智能体**可以**查到（`kbEnabled`）。默认全开，所以后端还没下发
                 `disabled` 时（undefined）看到的是一片「可查」，不会被误读成「全被屏蔽了」。

                 ⚠️ `:model-value` 绑的是**布尔表达式**，不是 `kb.disabled` 本身，也**不要**加
                    `:active-value` / `:inactive-value` —— 见 `kbEnabled` 的注释：绑定值一旦不在
                    `[activeValue, inactiveValue]` 里，el-switch 会在挂载期**无用户操作地** emit 一次。 -->
            <span class="kb-block" @click.stop
              :title="kbEnabled(kb) ? '智能体提问与试检索都会查这个资料夹；关掉它就不再查' : '已屏蔽：智能体提问与试检索都不会再查这个资料夹'">
              <el-switch :model-value="kbEnabled(kb)" size="small" :loading="togglingKbId === kb.kbId"
                @update:model-value="toggleKbDisabled(kb, $event)" />
            </span>

            <div class="kb-item-ops">
              <span class="kb-op" title="重命名" @click.stop="promptRename(kb)">
                <el-icon><EditPen /></el-icon>
              </span>
              <span class="kb-op danger" title="删除资料夹" @click.stop="removeKb(kb)">
                <el-icon><Delete /></el-icon>
              </span>
            </div>
          </div>

          <div v-if="!loading && !kbLoadFailed && !kbs.length" class="kb-empty">
            <div class="kb-empty-title">还没有资料</div>
            <div class="kb-empty-desc">
              新建一个资料夹，把课件 / 讲义 / 笔记传进去，之后直接提问就行 ——
              智能体会先在资料里找，再回答你，并告诉你答案出自哪一段。
            </div>
            <el-button type="primary" size="small" :icon="Plus" @click="promptCreate">新建资料夹</el-button>
          </div>

        </div>

        <!-- ── 选中库的文档 ── -->
        <div v-if="activeKbId && !resultsMode" class="kb-docs">
          <div class="kb-docs-head">
            <span class="kb-docs-title">{{ activeKb?.name }}</span>
            <span class="kb-docs-hint">支持 {{ KB_FILE_EXTENSIONS.join(' / ') }}</span>
            <el-button v-if="selectedDocCount" class="kb-batch-delete" size="small" plain type="danger"
              :disabled="busy" @click="removeSelectedDocs">删除（{{ selectedDocCount }}）</el-button>
            <input ref="fileInputRef" type="file" :accept="KB_FILE_ACCEPT" multiple :disabled="busy"
              style="display: none" @change="onFilesPicked" />
            <!-- 上传入口：点开后再选「文件上传 / 粘贴文本」，把两个导入动作收进一个按钮 -->
            <el-dropdown class="kb-upload-dropdown" trigger="click" :disabled="busy" @command="onUploadCommand">
              <button type="button" class="kb-upload-btn" :class="{ disabled: busy }" :disabled="busy"
                title="上传文档：可在文件选择窗口按住 Ctrl 多选 Markdown、图片等文件">
                <el-icon>
                  <UploadFilled />
                </el-icon>
                <span>{{ uploading ? '上传中…' : '上传文档' }}</span>
                <el-icon class="kb-upload-caret"><ArrowDown /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="file">
                    <el-icon><UploadFilled /></el-icon>
                    文件上传
                  </el-dropdown-item>
                  <el-dropdown-item command="text" :disabled="importing">
                    <el-icon><DocumentCopy /></el-icon>
                    {{ importing ? '导入中…' : '粘贴文本' }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <!-- 上传进度提示（后端是同步解析 + 后台向量化，所以这里说明清楚） -->
          <div v-if="uploadTip" class="kb-tip">{{ uploadTip }}</div>

          <div class="kb-doc-list" v-loading="docsLoading">
            <div v-for="doc in documents" :key="doc.docId" class="kb-doc">
              <div class="kb-doc-check">
                <el-checkbox :model-value="selectedDocIds.includes(Number(doc.docId))"
                  @change="toggleDocSelected(Number(doc.docId))" />
              </div>
              <div class="kb-doc-main">
                <div class="kb-doc-name" :title="doc.fileName">{{ doc.fileName }}</div>
                <div class="kb-doc-meta">
                  <el-tag :type="documentTagType(doc.status)" size="small" effect="light">
                    {{ doc.statusText || doc.status }}
                  </el-tag>
                  <span v-if="isDocumentSearchable(doc.status)" class="kb-doc-chunks">
                    {{ doc.chunkCount || 0 }} 个分块
                  </span>
                  <span v-else-if="isDocumentProcessing(doc.status) || (doc.status === DOC_PARSED && pollingDocIds.includes(doc.docId))" class="kb-doc-chunks">
                    {{ doc.status === DOC_PARSED ? '已分块，向量化中…' : '处理中，稍等片刻…' }}
                  </span>
                  <span v-else-if="doc.status === DOC_PARSED" class="kb-doc-chunks is-warn">
                    已提取正文，尚未向量化 —— 可点 ↻ 重新处理
                  </span>
                  <span v-else-if="doc.status === DOC_FAILED" class="kb-doc-chunks is-error">
                    {{ doc.errorMsg || '处理失败' }}
                  </span>
                </div>
              </div>

              <div class="kb-doc-ops">
                <!-- 资料刨析：章节结构 / 正文 / 图片资产统一看（复用我的资料页的查看器） -->
                <span v-if="isDocumentSearchable(doc.status)" class="kb-op" title="查看原文"
                  @click="showAnatomy(doc)">
                  <el-icon><Document /></el-icon>
                </span>
                <span v-if="canReprocessDocument(doc.status)" class="kb-op" title="重新解析并向量化"
                  @click="reprocess(doc)">
                  <el-icon><RefreshRight /></el-icon>
                </span>
                <span class="kb-op danger" title="删除文档" @click="removeDoc(doc)">
                  <el-icon><Delete /></el-icon>
                </span>
              </div>
            </div>

            <div v-if="!docsLoading && !documents.length" class="kb-doc-empty">
              这个资料夹还没有文档，点右上角「上传文档」
            </div>
          </div>

        </div>
      </div>
    </div>

  <!-- 资料刨析：与「我的资料」页共用 DocumentAnatomyDialog -->
  <DocumentAnatomyDialog ref="anatomyRef" />

  <!-- 粘贴文本导入：把用户自己输入的正文直接收进知识库（后端 `/document/uploadText`，不走文件解析） -->
  <el-dialog v-model="textImportVisible" title="粘贴文本" width="640px" append-to-body @closed="resetTextImport">
    <div class="kb-import">
      <div class="kb-import-hint">
        把正文直接粘进来就行 —— 不用先存成 txt / Word 再上传，也不经过文件解析。
        导入后智能体一样能检索到它。
      </div>
      <el-input v-model="textImportFileName" class="kb-import-name" placeholder="未命名文档.txt" clearable>
        <template #prepend>文件名</template>
      </el-input>
      <el-input v-model="textImportContent" class="kb-import-text" type="textarea"
        :autosize="{ minRows: 10, maxRows: 18 }" resize="vertical"
        placeholder="把要收进我的资料的正文粘在这里，例如课件文字、笔记、错题解析…" />
      <div class="kb-import-count">{{ textImportContent.trim().length }} 字</div>
    </div>
    <template #footer>
      <el-button @click="textImportVisible = false">取消</el-button>
      <el-button type="primary" :loading="importing" :disabled="!textImportContent.trim()" @click="submitTextImport">
        导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
defineOptions({ name: 'KnowledgeBasePanel' })

import { ref, computed, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Close, Delete, Document, DocumentCopy, EditPen, FolderOpened, Plus, RefreshRight, Search, UploadFilled, View, Warning } from '@element-plus/icons-vue'
import {
  DOC_FAILED,
  DOC_PARSED,
  KB_FILE_ACCEPT,
  KB_FILE_EXTENSIONS,
  canReprocessDocument,
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  documentTagType,
  getDocumentStatus,
  importDocumentText,
  isDocumentProcessing,
  isDocumentSearchable,
  isSupportedKbFile,
  listDocuments,
  listKnowledgeBases,
  reprocessDocument,
  searchKnowledge,
  updateKnowledgeBase,
  uploadDocument,
  type RagDocument,
  type RagKnowledgeBase,
  type RagSearchHit
} from '@/api/ai/rag'

/** 轮询间隔与上限：向量化要调 embedding，一篇长文档几十秒量级 */
const POLL_INTERVAL = 2000
const POLL_MAX_ROUNDS = 90

/**
 * `closable`：是否显示右上角「收起」。
 *   · 抽屉里 → true（关掉抽屉）
 *   · 悬浮助手 tab 里 → false（tab 由外层 tab 栏切换，不需要一个多余的叉）
 */
withDefaults(defineProps<{ closable?: boolean }>(), { closable: false })

// 资料刨析：与「我的资料」页复用同一个查看器（章节结构、正文、图片资产）。
import DocumentAnatomyDialog from '@/views/front/workspace/components/DocumentAnatomyDialog.vue'
import { ensureMarkdownImageFiles } from '@/utils/markdownUpload'

/** 只有 closable 时才会 emit：调用方据此收起自己的容器（抽屉 / 切走 tab） */
const emit = defineEmits<{ (e: 'close'): void }>()
const loading = ref(false)
const creating = ref(false)
const uploading = ref(false)
const uploadTip = ref('')

/* ===== 粘贴文本（用户自己输入的正文，不走文件解析） ===== */
const importing = ref(false)
const textImportVisible = ref(false)
const textImportContent = ref('')
const textImportFileName = ref('')

const kbs = ref<RagKnowledgeBase[]>([])
const activeKbId = ref<number | null>(null)
const documents = ref<RagDocument[]>([])
const docsLoading = ref(false)
const selectedDocIds = ref<number[]>([])
const selectedDocCount = computed(() => selectedDocIds.value.length)

/* ===== 统一搜索 ===== */
/**
 * 唯一的搜索词，一个词承担两件事（靠 resultsMode 分流）：
 *   · 还没提交搜索 → 实时筛库名（纯本地过滤，瞬发）
 *   · 回车 / 点「搜索资料」→ 跨库语义检索（走 /rag/search）
 *
 * 为什么不拆两个框：对用户来说「找哪个库」与「找哪段内容」本来就是同一个问题
 * （「我要找 X」），拆开只会逼他先判断「这东西是库名还是正文」——
 * 而这恰恰是用户最不该被要求知道的事。
 */
const query = ref('')

/**
 * 列表这次**没取到**（响应不是数组 / 请求抛错）—— 与「一个知识库都没有」是两件事
 *
 * ⚠️ 后端的 catch-all（`app/api/v1/catch_all.py`）按**路径关键字**分流，返回的是
 *    `{code:200,total:0,rows:[]}`（**没有 `data` 键**）或 `success(None)` 这类信封 ——
 *    于是「路由被挪走 / 拼错」的表现是 **code 200 + `data` 不是数组**。
 *    原来的 `if (code === 200 && Array.isArray(data))` 会把这种响应**整块跳过**：
 *    没有 else、没有报错。首次打开时 `kbs` 保持空，模板便画出「还没有知识库，新建一个…」——
 *    **一个有十几个库的用户被告知他一个库都没有**。已经加载过的情况更隐蔽：
 *    列表静默留着**过期数据**，看起来一切正常。
 */
const kbLoadFailed = ref(false)


/* ===== 资料刨析 =====
   从文档列表或搜索结果进入，复用「我的资料」页的完整解剖查看器：
   章节结构、正文与图片、图片资产都在同一个页面里，不再单独画一张结构图。 */
const anatomyRef = ref<InstanceType<typeof DocumentAnatomyDialog> | null>(null)
const showAnatomy = (doc: RagDocument) => {
  anatomyRef.value?.open(doc)
}

const fileInputRef = ref<HTMLInputElement | null>(null)

/* ===== 搜索结果 ===== */
/** 是否已进入「结果视图」（进入后列表让位给命中片段） */
const resultsMode = ref(false)
const searching = ref(false)
const searchHits = ref<RagSearchHit[]>([])
/**
 * 结果可能不相关（后端 `lowConfidence`）
 *
 * 向量路总会返回 top_k 条，两路都没有关键词命中时，这些只是"最像的"而非"相关的"。
 * 不能直接把条数说成"找到 N 段相关资料"——那是把噪声包装成结果。
 */
const searchLowConfidence = ref(false)
/** 本次结果实际用的检索范围（结果里如实回显，避免用户误读成「搜了全部库」） */
const searchedScopeLabel = ref('')
const searchedQuery = ref('')
/** 已展开全文的片段 id */
const selectedKbIds = ref<number[]>([])
const expandedIds = ref<number[]>([])

/** 轮询定时器：组件卸载 / 抽屉关闭都要清掉，否则会一直打接口 */
let pollTimers: number[] = []
/**
 * 正在轮询的 docId
 *
 * ⚠️ 必须去重：`loadDocs` 会对所有「处理中」的文档开轮询，而它会被反复调用
 * （上传后一次、抽屉重开一次、删完文档再一次）—— 同一篇文档于是挂着好几个定时器，
 * 每个都在打 `/document/status`。文档越多、操作越多，请求量成倍涨。
 */
const pollingDocs = new Set<number>()
/** 正在轮询的 docId（响应式，供模板判断 status=3 是「向量化中」还是「卡住了」） */
const pollingDocIds = ref<number[]>([])

const kbCount = computed(() => kbs.value.length)
const activeKb = computed(() => kbs.value.find((k) => k.kbId === activeKbId.value) || null)

/**
 * 已启用（未被屏蔽）的知识库 —— 跨库检索实际会搜到的那些。
 *
 * 后端 `resolve_knowledge_bases` 在不点名 kbIds 时会**自动排除 disabled=1 的库**，
 * 所以这里的「N 个库」与真实检索范围一致，不是把屏蔽的也算进去。
 */
const enabledKbs = computed(() => kbs.value.filter((k) => k.disabled !== 1))
const enabledKbCount = computed(() => enabledKbs.value.length)

/**
 * 搜索框的占位文案：随当前上下文变，顺带告诉用户「回车会搜哪儿」。
 *
 * 选了某个库 → 提示在那个库里搜；没选 → 提示跨全部库搜。
 * 这比一句固定的「搜索…」有用得多：用户不用去猜作用域。
 */
const searchPlaceholder = computed(() =>
  activeKbId.value
    ? `在「${activeKb.value?.name || ''}」里搜资料，回车检索`
    : '搜资料名字，或直接搜资料内容（回车）'
)

/**
 * 本地筛库名 —— **只在还没提交搜索时生效**。
 *
 * 一旦进入结果视图，列表已经被结果面板顶掉了，这份过滤结果不再渲染；
 * 但 searchScopeLabel / 空态文案仍需要它，所以不按 resultsMode 短路返回值。
 */
const filteredKbs = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return kbs.value
  return kbs.value.filter((k) => String(k.name || '').toLowerCase().includes(q))
})

/**
 * 本次检索要用的 kbIds。
 *
 * 选了库 → 只搜它；没选 → 空数组，交给后端「全部未屏蔽库」那条分支。
 * ⚠️ 不要把 disabled 的库塞进来：显式点名时后端会**静默丢弃**屏蔽库，
 *    结果里就会出现「明明选了 3 个库，却只搜了 1 个」而不给任何提示。
 */
const scopeKbIds = computed<number[]>(() => {
  if (!activeKbId.value) return []
  const kb = kbs.value.find((k) => k.kbId === activeKbId.value)
  return kb && kb.disabled !== 1 ? [kb.kbId] : []
})

/** 当前检索范围的人话描述（搜索前提示 + 结果里回显，两处共用） */
const hitGroups = computed(() => buildHitGroups(searchHits.value))
const searchedScopeHint = computed(() => (searchedScopeLabel.value ? searchedScopeLabel.value + '，' : ''))
const scopeLabel = computed(() => (activeKbId.value ? activeKb.value?.name || '' : ''))

/** 片段属于哪个库（跨库结果里必须标出来，否则不同库的同名文件分不清） */
const buildHitGroups = (hits: RagSearchHit[]) => {
  const m = new Map<string, any>()
  hits.forEach((h) => {
    const k = h.wikiHit ? `wiki-${h.wikiPageId || 0}` : String(h.kbId || 0) + '-' + h.docId
    let g = m.get(k)
    if (!g) {
      g = {
        key: k,
        kbId: h.kbId,
        kbName: kbNameOf(h.kbId),
        docName: h.wikiHit
          ? (h.wikiPageTitle ? `知识百科《${h.wikiPageTitle}》` : '知识百科主题页')
          : (h.docName || ('文档#' + h.docId)),
        isWiki: !!h.wikiHit,
        hits: []
      }
      m.set(k, g)
    }
    g.hits.push(h)
  })
  return Array.from(m.values())
}

const kbNameOf = (kbId?: number) =>
  (kbId ? kbs.value.find((k) => k.kbId === kbId)?.name : '') || ''

/**
 * 两个导入入口（上传文档 / 粘贴文本）**共用**的忙标记
 *
 * ⚠️ 必须共用：它们往**同一个知识库**写文档。各自只看自己那个 ref 的话，
 * 「上传文档」跑着的时候还能再开一次粘贴导入 —— 两次导入的进度提示与轮询互相覆盖，
 * 用户看到的状态就是错的。
 */
const busy = computed(() => uploading.value || importing.value)

/* ===================== 轮询 ===================== */

const clearPollTimers = () => {
  pollTimers.forEach((t) => window.clearTimeout(t))
  pollTimers = []
  pollingDocs.clear()
}

/**
 * 上传后轮询处理状态，直到成功 / 失败 / 超时
 *
 * 后端 `/document/upload` 是「同步解析 + 后台向量化」，返回时只是 status=1，
 * 真正的「能不能检索到」要等 status=5。不轮询的话用户会以为传失败了。
 */
const pollDocument = (docId: number, round = 0) => {
  // 已经在盯着这篇了 → 不再叠加一个定时器（见 pollingDocs 的说明）
  if (round === 0) {
    if (pollingDocs.has(docId)) return
    pollingDocs.add(docId)
    pollingDocIds.value = [...pollingDocIds.value, docId]
  }

  const timer = window.setTimeout(async () => {
    try {
      const res: any = await getDocumentStatus(docId)
      if (res?.code !== 200) return
      const info = res.data || {}
      const row = documents.value.find((d) => d.docId === docId)
      if (row) {
        row.status = info.status
        row.statusText = info.statusText
        row.chunkCount = info.chunkCount
        row.errorMsg = info.errorMsg
      }
      if (!info.done && round < POLL_MAX_ROUNDS) {
        pollDocument(docId, round + 1)
        return
      }
      pollingDocs.delete(docId)
      pollingDocIds.value = pollingDocIds.value.filter(id => id !== docId)
      if (info.ok) {
        uploadTip.value = ''
        // 分块数变了 → 库上的计数也要刷新
        loadKbs()
      } else if (round >= POLL_MAX_ROUNDS) {
        uploadTip.value = '文档还在处理中，稍后回来刷新看看'
      } else {
        uploadTip.value = `「${row?.fileName || '文档'}」处理失败：${info.errorMsg || '未知原因'}`
      }
    } catch {
      // 轮询失败不打扰用户：放开去重标记，下次 loadDocs 会重新盯上它
      pollingDocs.delete(docId)
      pollingDocIds.value = pollingDocIds.value.filter(id => id !== docId)
    }
  }, POLL_INTERVAL)
  pollTimers.push(timer)
}

/* ===================== 数据加载 ===================== */

/**
 * 加载知识库列表
 *
 * `autoSelect=false` 只把列表取回来（够入口徽标用了）：**不选库、不拉文档、不起轮询**。
 *
 * ⚠️ 挂载期必须走 `false` 这条路。`autoSelect=true` 会连锁到
 *    `selectKb → loadDocs → pollDocument`，于是「进过页面但从没打开抽屉」的用户
 *    也会被挂上一串后台轮询 —— 而那些定时器只在抽屉 `@closed` 时才清理。
 *
 * 失败的安静性质要保住：**不弹提示、不抛出去**（取不到列表就不显示徽标数字，
 * 别为了一次后台请求打扰用户）。但「安静」不等于「不留痕」——
 * 取不到时把 `kbLoadFailed` 立起来：抽屉里那条空态/过期数据的提示就是靠它，
 * 否则用户看到的会是「还没有知识库」（假信息）。
 */
const loadKbs = async (autoSelect = true) => {
  loading.value = true
  try {
    const res: any = await listKnowledgeBases()
    if (res?.code === 200 && Array.isArray(res.data)) {
      kbLoadFailed.value = false
      kbs.value = res.data
      // 选中的库被删掉了 → 退回第一个
      if (activeKbId.value && !kbs.value.some((k) => k.kbId === activeKbId.value)) {
        activeKbId.value = null
        documents.value = []
      }
      if (autoSelect && !activeKbId.value && kbs.value.length) await selectKb(kbs.value[0])
    } else {
      // **不静默通过**：这不是「零个知识库」，这是「没取到列表」（见 kbLoadFailed 的注释）
      kbLoadFailed.value = true
      console.warn('[kb] 资料列表响应不是数组', res)
    }
  } catch (e) {
    kbLoadFailed.value = true
    console.warn('[kb] 加载资料失败', e)
  } finally {
    loading.value = false
  }
}

const loadDocs = async (kbId: number) => {
  docsLoading.value = true
  try {
    const res: any = await listDocuments(kbId)
    if (res?.code === 200 && Array.isArray(res.data)) {
      documents.value = res.data
      const aliveIds = new Set(documents.value.map((d) => Number(d.docId)))
      selectedDocIds.value = selectedDocIds.value.filter((id) => aliveIds.has(id))
      // 有文档还在处理 → 继续轮询（覆盖「上次没看完就关了抽屉」的情况）
      documents.value.filter((d) => isDocumentProcessing(d.status)).forEach((d) => pollDocument(d.docId))
    }
  } catch (e) {
    console.warn('[kb] 加载文档失败', e)
  } finally {
    docsLoading.value = false
  }
}

const selectKb = async (kb: RagKnowledgeBase) => {
  activeKbId.value = kb.kbId
  selectedDocIds.value = []
  uploadTip.value = ''
  await loadDocs(kb.kbId)
}

/* ===================== 统一搜索 ===================== */

/** 退出结果视图，回到知识库列表（保留关键词，方便改一改再搜） */
const exitResults = () => {
  resultsMode.value = false
  searchHits.value = []
  searchLowConfidence.value = false
  expandedIds.value = []
  searchedScopeLabel.value = ''
  searchedQuery.value = ''
}

/** 清空搜索：连结果视图一起退掉 */
const clearSearch = () => {
  query.value = ''
  exitResults()
}

/**
 * 提交搜索：跨库（或单库）检索资料。
 *
 * 这是原来那个「试检索」的升级版，区别在于：
 *   · 范围不再锁死当前库 —— 没选库就搜全部未屏蔽库（后端默认分支）；
 *   · 结果就地铺开，带来源库 / 文档名 / 段落号 / 排序分；
 *   · 命中片段可展开全文、复制、看章节结构、跳到所属库。
 */
const runSearch = async () => {
  const q = query.value.trim()
  if (!q || searching.value) return
  searching.value = true
  try {
    const ids = selectedKbIds.value.length ? selectedKbIds.value : undefined
    const res: any = await searchKnowledge(q, ids)
    if (res?.code === 200) {
      searchHits.value = res.data?.hits || []
      searchLowConfidence.value = !!res.data?.lowConfidence
      const names: string[] = (res.data?.knowledgeBases || []).map((k: any) => k.name)
      searchedScopeLabel.value = names.length
        ? (names.length === 1 ? `来自「${names[0]}」` : `来自 ${names.length} 个资料夹`)
        : ''
      searchedQuery.value = q
      expandedIds.value = []
      resultsMode.value = true
    } else {
      ElMessage.error(res?.msg || '搜索失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '搜索失败')
  } finally {
    searching.value = false
  }
}

/** 展开 / 收起某条命中片段的全文 */
const toggleKbPick = (kb: RagKnowledgeBase) => {
  if (kb.disabled === 1) return
  const i = selectedKbIds.value.indexOf(kb.kbId)
  if (i >= 0) selectedKbIds.value.splice(i, 1)
  else selectedKbIds.value.push(kb.kbId)
}
const clearKbSelection = () => { selectedKbIds.value = [] }
const selectAllKbs = () => { selectedKbIds.value = enabledKbs.value.map((k) => k.kbId) }

const toggleExpand = (chunkId: number) => {
  const i = expandedIds.value.indexOf(chunkId)
  if (i >= 0) expandedIds.value.splice(i, 1)
  else expandedIds.value.push(chunkId)
}

/**
 * 把命中的关键词高亮出来。
 *
 * ⚠️ 必须**先转义再插标记**：片段是文档正文，可能含尖括号甚至故意的 HTML，
 *    直接 v-html 就是 XSS。标记由我们生成，正文里的尖括号已转成实体。
 */
const highlight = (content: string) => {
  const escaped = String(content || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const terms = query.value.trim().split(/\s+/).filter((t) => t.length > 0)
  if (!terms.length) return escaped
  const pattern = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  try {
    return escaped.replace(new RegExp(`(${pattern})`, 'gi'), '<mark>$1</mark>')
  } catch {
    return escaped
  }
}

/** 复制某条命中片段的原文 */
const copyHit = async (h: RagSearchHit) => {
  try {
    await navigator.clipboard.writeText(h.content || '')
    ElMessage.success('已复制这段原文')
  } catch {
    ElMessage.error('复制失败，请手动选择文本')
  }
}

/** 从结果里跳到某个库（切回列表视图并选中它） */
const gotoKb = async (kbId?: number) => {
  const kb = kbId ? kbs.value.find((k) => k.kbId === kbId) : null
  if (!kb) return
  clearSearch()
  await selectKb(kb)
}

/** 从结果里直接看该片段所在文档的全部分块（复用文档列表那套预览） */
const openAnatomyOf = (h: RagSearchHit) => {
  showAnatomy({ docId: h.docId, fileName: h.docName || `文档#${h.docId}` } as RagDocument)
}

/**
 * 面板内容加载 —— 调用方在「显示本面板的那一刻」调它。
 *
 * 为什么不做成 onMounted 自动跑：本面板的宿主容器有两种（抽屉 / tab），
 * 而且宿主多半用 v-if 懒挂载 —— 挂载 + 自动加载会让「懒挂载」与「自动加载」
 * 各发一次请求。把时机交给调用方，两边都只发一次。
 *
 * ⚠️ 每次都从 activeKbId = null 重来（对齐抽屉 `@open` 的行为）：
 *    重开面板时用户期望看到的是「库列表」，而不是上次停在某个库里 ——
 *    而那个库可能已经被删了（`activeKb` 会变 null，文档区就成了空壳）。
 *
 * 去重：`loading` 期间重复调用直接返回，避免宿主 onActivated / watch 连打两次。
 */
const activate = async () => {
  if (loading.value) return
  clearSearch()
  activeKbId.value = null
  documents.value = []
  await loadKbs()
}


/* ===================== 知识库增删改 ===================== */

const promptCreate = async () => {
  let name = ''
  try {
    const r: any = await ElMessageBox.prompt('给资料夹起个名字', '新建资料夹', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：数据结构期末复习',
      inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
    })
    name = String(r?.value || '').trim()
  } catch {
    return
  }
  if (!name) return

  creating.value = true
  try {
    const res: any = await createKnowledgeBase({ name })
    if (res?.code === 200) {
      ElMessage.success('资料夹已创建')
      await loadKbs()
      const created = kbs.value.find((k) => k.kbId === res.data?.kbId)
      if (created) await selectKb(created)
    } else {
      ElMessage.error(res?.msg || '创建失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

const promptRename = async (kb: RagKnowledgeBase) => {
  let name = ''
  try {
    const r: any = await ElMessageBox.prompt('改成什么名字？', '重命名资料夹', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: kb.name,
      inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
    })
    name = String(r?.value || '').trim()
  } catch {
    return
  }
  if (!name || name === kb.name) return

  try {
    const res: any = await updateKnowledgeBase(kb.kbId, { name })
    if (res?.code === 200) {
      ElMessage.success('已重命名')
      await loadKbs()
    } else {
      ElMessage.error(res?.msg || '重命名失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '重命名失败')
  }
}

const removeKb = async (kb: RagKnowledgeBase) => {
  try {
    await ElMessageBox.confirm(
      `删除「${kb.name}」？资料夹里的 ${kb.docCount || 0} 篇文档与分块会一并清掉，不可撤销。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res: any = await deleteKnowledgeBase(kb.kbId)
    if (res?.code === 200) {
      ElMessage.success('资料夹已删除')
      if (activeKbId.value === kb.kbId) {
        activeKbId.value = null
        documents.value = []
      }
      await loadKbs()
    } else {
      ElMessage.error(res?.msg || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

/* ===================== 屏蔽（给 LLM 的一道闸门） ===================== */

/** 正在写 `disabled` 的那个库 —— 只用来给那一行的开关上 loading */
const togglingKbId = ref<number | null>(null)

/**
 * 这个库现在**能被智能体查到吗**，也就是开关的「开」状态
 *
 * ⚠️ 判据只能是 `disabled !== 1`，**不能**写成「`=== 0` 才算正常」：
 *    `disabled` 列是后加的，在这一版后端上线之前每一行的运行时值都是 `undefined`，
 *    `=== 0` 会把**每一个现存知识库**都画成「已屏蔽」—— 用户会以为自己的资料全被屏蔽了。
 *    `!== 1` 在 `undefined` / `0` 时都判「正常」，与加这个功能之前的行为一致。
 *    （也不要用 `!!kb.disabled`：`!!undefined` 虽然同样是 false，但它会把将来的
 *      `2` / `'1'` 之类一律算成「已屏蔽」，而 `!== 1` 不会。）
 *
 * ⚠️⚠️ 返回**布尔**而不是 `0`/`1`，这是**必需**的（不是顺手写的）：`el-switch` 在 setup 期
 *    会检查绑定值是否落在 `[activeValue, inactiveValue]` 里，不在就**在没有用户操作的情况下**
 *    emit 一次 `update:modelValue` / `change`（实测已安装的 `element-plus@2.14.5`：
 *    `es/components/switch/src/switch.vue_vue_type_script_setup_true_lang.mjs:71-76`，
 *    默认 `activeValue = true` / `inactiveValue = false`）。
 *    所以如果把 `kb.disabled` **原样**绑上去，`undefined`（后端还没上线这一列）和字符串 `'1'`
 *    （类型不匹配，那边是严格 `===`）都会命中那一格 ⇒ **列表里每一行各 emit 一次** ⇒
 *    打开抽屉就可能对每一行发一次 PUT。绑恒为 `true`/`false` 的表达式则永远落在默认取值域里，
 *    不可能触发。（模板里同时**不要**写 `:active-value` / `:inactive-value`。）
 */
const kbEnabled = (kb: RagKnowledgeBase) => kb.disabled !== 1

/**
 * 屏蔽 / 取消屏蔽一个知识库
 *
 * **受控式**：本地**不**改 `kb.disabled`，显示值永远来自服务端 —— 写成功之后 `loadKbs()` 重取。
 *
 * ⚠️ 为什么不用「乐观式」（先本地翻过去、失败再翻回来，`views/front/english/vocabulary/detail.vue`
 *    是那种写法）：那种回滚只在 `code !== 200` 或抛异常时发生，而后端 catch-all 会把
 *    「路由被挪走 / 字段名不一致」表现成 **`code 200` + `data: null` 的假成功** ——
 *    于是服务端什么都没存，UI 却把开关留在「已屏蔽」上：用户以为这个库被屏蔽了，
 *    下一次提问照样整库喂给模型。这正是本项目最忌讳的「看起来在防、其实没防」。
 *    受控式最坏只让开关**弹回原位**，不可能伪造状态。
 *
 * ⚠️ `on` 是**开关要去的开/关状态**（`true` = 智能体可查），写回服务端的 `disabled` 正好相反。
 *    取值来自 `el-switch` 的 `update:model-value` 事件（那个事件带的就是**新值**），
 *    所以这里不依赖「v-model 有没有先写回」这种发射顺序。
 */
const toggleKbDisabled = async (kb: RagKnowledgeBase, on: boolean) => {
  const want: 0 | 1 = on ? 0 : 1
  // ① 要去的状态就是它现在的状态 → 这不是用户操作，一个字都不写。
  //    这挡住两种东西：开关**程序化**的 emit（它报的就是当前状态），
  //    以及「上一次 PUT 还在飞、用户又点一下」造成的重复提交。
  //
  //    ⚠️ 注意这道守卫**挡不住**「值不在取值域时那次 emit」：那种 emit 报的是**相反**的状态，
  //       语义上和「用户真的要屏蔽」一模一样，守卫无从分辨 —— 那次 emit 只能靠
  //       `kbEnabled` 返回布尔（模板绑表达式）来从源头消除，不能靠这里兜。
  if ((kbEnabled(kb) ? 0 : 1) === want) return
  togglingKbId.value = kb.kbId
  try {
    const res: any = await updateKnowledgeBase(kb.kbId, { disabled: want })
    if (res?.code === 200) {
      // ② 重取列表：显示值只认服务端回值（见上面「为什么不用乐观式」）
      await loadKbs()
      ElMessage.success(
        want === 1
          ? `已屏蔽「${kb.name}」—— 智能体提问与试检索都不会再查这个资料夹`
          : `已恢复「${kb.name}」—— 智能体提问与试检索都会正常查它`
      )
    } else {
      ElMessage.error(res?.msg || '操作失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  } finally {
    togglingKbId.value = null
  }
}

/* ===================== 文档 ===================== */

const onUploadCommand = (command: string) => {
  if (busy.value) return
  if (command === 'file') {
    fileInputRef.value?.click()
  } else if (command === 'text') {
    openTextImport()
  }
}

const onFilesPicked = async (evt: Event) => {
  const input = evt.target as HTMLInputElement
  const files = Array.from(input.files || [])
  // 清空 value，否则选同一个文件不会再触发 change
  input.value = ''
  // busy 里含「粘贴导入正在进行」—— 输入框那时是 disabled 的，这里是第二道
  if (!files.length || !activeKbId.value || busy.value) return
  if (!(await ensureMarkdownImageFiles(files))) return

  const bad = files.filter((f) => !isSupportedKbFile(f.name))
  if (bad.length) {
    ElMessage.warning(`跳过不支持的文件：${bad.map((f) => f.name).join('、')}`)
  }
  const ok = files.filter((f) => isSupportedKbFile(f.name))
  if (!ok.length) return
  if (ok.length > 20) {
    ElMessage.warning('一次最多上传 20 个文件，请分批上传')
    return
  }
  const totalBytes = ok.reduce((sum, file) => sum + Number(file.size || 0), 0)
  if (totalBytes > 5 * 1024 * 1024) {
    ElMessage.warning(
      `本次选择 ${(totalBytes / 1024 / 1024).toFixed(1)}MB，单次上传总大小不能超过 5MB，请减少文件数量或压缩后再上传`
    )
    return
  }

  uploading.value = true
  const kbId = activeKbId.value
  try {
    uploadTip.value = ok.length > 1 ? `正在上传并解析 ${ok.length} 个文件…` : `正在上传并解析「${ok[0].name}」…`
    const res: any = await uploadDocument(kbId, ok)
    if (res?.code === 200) {
      const documents = Array.isArray(res.data?.documents)
        ? res.data.documents
        : (res.data?.docId ? [res.data] : [])
      const failed = Array.isArray(res.data?.failed) ? res.data.failed : []
      for (const item of failed) {
        ElMessage.error(`${item.fileName || '文件'}：${item.error || '上传失败'}`)
      }
      if (documents.length) {
        uploadTip.value = `已上传 ${documents.length} 份，正在向量化…`
        await loadDocs(kbId)
        for (const item of documents) {
          const docId = Number(item.docId || 0)
          if (docId) pollDocument(docId)
        }
      } else {
        uploadTip.value = ''
        ElMessage.error(res?.msg || '上传失败')
      }
    } else {
      uploadTip.value = ''
      ElMessage.error(res?.msg || '上传失败')
    }
  } catch (e: any) {
    uploadTip.value = ''
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

/* ===== 粘贴文本导入 ===== */

const openTextImport = () => {
  if (busy.value) return
  textImportVisible.value = true
}

const resetTextImport = () => {
  textImportContent.value = ''
  textImportFileName.value = ''
}

/**
 * 提交粘贴的正文（后端 `/document/uploadText`，**不经过文件解析**）
 *
 * ⚠️ 空正文**不发请求**：后端会回 `code 400 内容不能为空`，但那只是兜底 ——
 *    这里是第一道（按钮 `:disabled` 再挡一道）。把兜底当唯一防线，
 *    用户看到的就是一句「导入失败」而不是「按钮点不动」。
 *
 * ⚠️ 失败**不关弹窗、不清正文**：用户可能刚粘了几千字，重来一次的代价太大。
 */
const submitTextImport = async () => {
  const kbId = activeKbId.value
  const content = textImportContent.value.trim()
  if (!kbId || !content || busy.value) return

  importing.value = true
  try {
    // 文件名留空就交给 api 层（`rag.ts` 里 `fileName || '未命名文档.txt'`）——
    // 默认值只留一个出处，前端不再抄一份字面量
    const name = textImportFileName.value.trim()
    const res: any = await importDocumentText(kbId, content, name || undefined)
    if (res?.code === 200 && res.data?.docId) {
      textImportVisible.value = false
      uploadTip.value = `「${res.data.fileName || name || '未命名文档.txt'}」已导入，正在向量化…`
      await loadDocs(kbId)
      pollDocument(res.data.docId)
    } else {
      ElMessage.error(res?.msg || '导入失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const toggleDocSelected = (docId: number) => {
  const id = Number(docId)
  if (!id) return
  const idx = selectedDocIds.value.indexOf(id)
  if (idx >= 0) selectedDocIds.value.splice(idx, 1)
  else selectedDocIds.value.push(id)
}

const removeSelectedDocs = async () => {
  const ids = [...selectedDocIds.value]
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 份资料吗？删除后不可恢复。`, '批量删除资料', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  let ok = 0
  let fail = 0
  for (const id of ids) {
    try {
      const res: any = await deleteDocument(id)
      if (res?.code === 200) ok += 1
      else fail += 1
    } catch {
      fail += 1
    }
  }
  selectedDocIds.value = []
  if (activeKbId.value) await loadDocs(activeKbId.value)
  await loadKbs()
  if (ok) ElMessage.success(`已删除 ${ok} 份资料${fail ? `，${fail} 份失败` : ''}`)
  else ElMessage.error('批量删除失败，请稍后重试')
}

const removeDoc = async (doc: RagDocument) => {
  try {
    await ElMessageBox.confirm(`删除文档「${doc.fileName}」？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res: any = await deleteDocument(doc.docId)
    if (res?.code === 200) {
      ElMessage.success('文档已删除')
      if (activeKbId.value) await loadDocs(activeKbId.value)
      await loadKbs()
    } else {
      ElMessage.error(res?.msg || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

const reprocess = async (doc: RagDocument) => {
  try {
    const res: any = await reprocessDocument(doc.docId)
    if (res?.code === 200) {
      ElMessage.success('已重新开始处理')
      if (activeKbId.value) await loadDocs(activeKbId.value)
      pollDocument(doc.docId)
    } else {
      ElMessage.error(res?.msg || '重试失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '重试失败')
  }
}

/**
 * 图片 URL 归一：data URL / http(s) 原样；相对路径（`/profile/...`）拼上 API 前缀。
 *
 * `VITE_APP_BASE_API` 为空串时拼出来就是单斜杠相对路径（正确）；
 * 非空时为 `/dev-api` 等前缀。出题面板那份实现与本处同一口径。
 */
const kbImageUrl = (url: string): string => {
  const v = String(url || '').trim()
  if (!v) return ''
  if (v.startsWith('data:') || v.startsWith('http://') || v.startsWith('https://')) return v
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (v.startsWith('/') ? v : '/' + v)
}

onBeforeUnmount(clearPollTimers)

/**
 * ⚠️ 本组件**故意不在 onMounted 里自动加载**。
 *
 * 宿主（抽屉 / 悬浮助手 tab）都用 v-if 懒挂载本组件，
 * 「挂载即加载」会让懒挂载与自动加载各发一次请求；
 * 而且 tab 场景下用户切走再切回都会重建组件，白白多打一轮接口。
 * 加载时机交给调用方：它调 `activate()` 时才取数（见该函数的注释）。
 */
/**
 * 只把库列表取回来：不选中任何库、不拉文档、不起轮询。
 *
 * 给**入口徽标**用 —— 宿主只想知道「用户有几个库」，
 * 这时顺带选中第一个库并拉它的文档纯属白打请求（用户还没打开面板）。
 */
const refreshList = () => loadKbs(false)

/** 读当前库数量（宿主刷新徽标用；返回值不是响应式，调用方自己存一份） */
const getKbCount = () => kbs.value.length
defineExpose({ activate, refreshList, getKbCount })
</script>

<style scoped src="./index.style1.css"></style>
