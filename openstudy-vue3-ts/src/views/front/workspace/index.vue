<!--
  知识库（整页）
  ============================================================================
  2026-10-22 由「我的空间」升级而来。

  为什么是现在这个样子
  --------------------
  用户原话：「把我的空间改名知识库 就行然后他的具体功能升级为 目前知识库抽屉的那种
             就是统一管理各种知识库 每个知识库包含各种文档」。

  所以这个页面 = 原来的**知识库抽屉**（`components/KnowledgeBasePanel`）的能力，
  从抽屉里搬出来，变成一个有侧栏、有主区、能常驻浏览的完整页面：

      左：知识库列表（新建 / 改名 / 删除 / 屏蔽）
      右：选中库的文档（上传文件/粘贴文本 / 看状态 / 删除 / 重解析 / 看刨析）
      顶：全站统计（几个库、几份资料、多少可检索、占多大）

  与对话页那个抽屉的分工
  ---------------------
  · 本页 = **管理**（建库、批量传、整理、删）；
  · 对话页抽屉 = **选范围**（这次提问让 AI 查哪些库）。
  两者读同一套后端数据，所以任何一边的改动另一边立刻能看到。

  ⚠️ 默认库（`isDefault=1`）可以改名，但不能删除 —— 它是系统给每个人
     自动建的落脚点；改名只改变展示名称，`is_workspace=1` 的默认标识保持不变。
-->
<template>
  <div class="kb-page">
    <!-- 全局文件选择器：书架/图片墙空态也必须能上传，不能只绑在资料夹列表里 -->
    <input
      ref="fileInputRef"
      type="file"
      :accept="KB_FILE_ACCEPT"
      multiple
      style="display: none"
      @change="onFilesPicked"
    />
    <!-- 路由导航属于最顶层：通过 Teleport 注入布局顶栏，而不是留在内容区 -->
    <Teleport v-if="canTeleport" to="#os-workspace-nav">
      <div class="kbp-workspace-nav">
        <header class="kbp-head kbp-head--clean">
          <nav class="kbp-crumbs" aria-label="当前位置">
            <button type="button" class="kbp-crumbs__root" @click="viewMode = 'list'">我的资料</button>
            <span class="kbp-crumbs__sep">/</span>
            <span class="kbp-crumbs__current">{{ activeKb?.name || '全部资料' }}</span>
            <template v-if="viewMode !== 'list'">
              <span class="kbp-crumbs__sep">/</span>
              <span class="kbp-crumbs__leaf">{{ viewModeLabel }}</span>
            </template>
          </nav>
          <div class="kbp-head__actions">
            <span class="kbp-head__meta">
              {{ stats.kbCount }} 个资料夹
              <i>·</i>
              {{ stats.readyCount }} 份可检索
              <i>·</i>
              {{ stats.totalSizeText || '0 B' }}
            </span>
            <el-button size="small" text class="kbp-receive-share" @click="receiveDialogVisible = true">
              <el-icon><Download /></el-icon>
              获取资料分享
            </el-button>
          </div>
        </header>

        <nav class="kbp-tabs" role="tablist" aria-label="资料视图">
          <button
            v-for="tab in workspaceTabs"
            :key="tab.key"
            type="button"
            class="kbp-tab"
            :class="{ 'is-active': viewMode === tab.key }"
            role="tab"
            :aria-selected="viewMode === tab.key"
            @click="viewMode = tab.key"
          >
            <OsIcon :name="tab.icon" :size="15" />
            <span>{{ tab.label }}</span>
          </button>
        </nav>
      </div>
    </Teleport>

    <!-- 智能整理：即使关闭预览弹窗，后台进度也要可见、可再次打开 -->
    <div v-if="organizeTask.active" class="kbp-reprocess kbp-reprocess--organize">
      <div class="kbp-reprocess__head">
        <span class="kbp-reprocess__spinner"></span>
        <b>正在整理「{{ organizeTask.fileName }}」</b>
        <span class="kbp-reprocess__stage">{{ organizeTask.statusText }}</span>
        <button type="button" class="kbp-reprocess__open" @click="organizeVisible = true">查看进度</button>
        <span class="kbp-reprocess__elapsed">{{ Math.round(organizeTask.percent) }}%</span>
      </div>
      <div class="kbp-reprocess__bar">
        <span :style="{ width: `${organizeTask.percent}%` }"></span>
      </div>
      <div class="kbp-reprocess__hint">整理在后台进行，可以先浏览其他资料；关闭预览不会中断任务。</div>
    </div>

    <!-- 重新解析/向量化：后台任务可见、可理解、不阻塞浏览 -->
    <div v-if="reprocessTask.active" class="kbp-reprocess">
      <div class="kbp-reprocess__head">
        <span class="kbp-reprocess__spinner"></span>
        <b>正在重新整理「{{ reprocessTask.fileName }}」</b>
        <span class="kbp-reprocess__stage">{{ reprocessTask.statusText }}</span>
        <span class="kbp-reprocess__elapsed">已用时 {{ reprocessElapsed }}s</span>
      </div>
      <div class="kbp-reprocess__bar">
        <span :style="{ width: `${reprocessTask.percent}%` }"></span>
      </div>
      <div class="kbp-reprocess__hint">
        解析、切分和向量化在后台进行，预计需要几十秒；期间可以先浏览其他资料，完成后自动刷新。
      </div>
    </div>

    <!--
      ⚠️ 一个知识库都没有时**不渲染两栏区**（v-if）。
         否则会出现「左边：还没有知识库 / 右边：左边选一个知识库」这种
         两块空面板互相指路的尴尬画面 —— 那是典型的"没设计过空态"。
         这种情况下直接用下面那张整页引导替代。
         注意：默认库是自动创建的，所以这个分支实际上只在接口返回异常时出现，
         但兜底必须画对。
    -->
    <div v-if="viewMode === 'list' && (loading || (kbs.length && !loadFailed))" class="kbp-body">
      <!-- ============ 左：知识库列表 ============ -->
      <aside class="kbp-side">
        <div class="kbp-side__head">
          <span class="kbp-side__title">全部资料</span>
          <el-button size="small" :icon="Plus" :disabled="creating" @click="promptCreate">
            新建
          </el-button>
        </div>

        <div class="kbp-side__search">
          <el-input v-model="folderKeyword" size="small" clearable placeholder="搜索资料夹" :prefix-icon="Search" />
        </div>

        <div class="kbp-side__list" v-loading="loading">
          <button
            v-for="kb in filteredKbs"
            :key="kb.kbId"
            type="button"
            class="kbp-kb"
            :class="{ 'is-active': kb.kbId === activeKbId, 'is-blocked': kb.disabled === 1 }"
            @click="selectKb(kb.kbId)"
            @contextmenu.prevent.stop="openKbMenu($event, kb)"
          >
            <span class="kbp-kb__icon">
              <OsIcon :name="kb.isDefault ? 'folder' : 'database'" :size="16" />
            </span>
            <span class="kbp-kb__main">
              <span class="kbp-kb__name-row">
                <span class="kbp-kb__name">{{ kb.name }}</span>
                <span v-if="kb.isDefault" class="kbp-kb__tag">默认</span>
                <span v-if="kb.disabled === 1" class="kbp-kb__tag is-blocked">已屏蔽</span>
                <span v-if="kb.sourceType === 'share'" class="kbp-kb__tag is-share">来自分享</span>
              </span>
              <span class="kbp-kb__meta">
                {{ kb.docCount }} 份资料<template v-if="kb.disabled !== 1"> · 可检索</template>
              </span>
            </span>
            <!-- 只保留一个「更多」按钮，具体动作统一进冒泡菜单，和文档行保持一致 -->
            <span class="kbp-kb__ops">
              <span class="kbp-kb__op" title="更多操作" @click.stop="openKbMenu($event, kb)">
                <OsIcon name="more" :size="14" />
              </span>
            </span>
          </button>

          <div v-if="!loading && !filteredKbs.length" class="kbp-side__empty">
            <p>{{ folderKeyword ? '没有匹配的资料夹' : '还没有资料' }}</p>
            <span>{{ folderKeyword ? '换个关键词试试' : '建一个资料夹来放课件和真题' }}</span>
            <el-button v-if="!folderKeyword" size="small" type="primary" :icon="Plus" @click="promptCreate">
              新建资料夹
            </el-button>
          </div>
        </div>

        <!-- 资料夹右键 / 更多操作：全局只保留一个冒泡菜单，打开新的会先关闭旧的 -->
        <div v-if="kbMenu.visible" class="kbp-context-menu"
          :style="{ left: `${kbMenu.x}px`, top: `${kbMenu.y}px` }" @click.stop>
          <button type="button" class="kbp-context-item" @click="handleKbCommand('rename', kbMenu.kb)">
            <OsIcon name="pen-line" :size="14" />
            重命名
          </button>
          <button type="button" class="kbp-context-item" @click="handleKbCommand('share', kbMenu.kb)">
            <el-icon><Share /></el-icon>
            分享资料夹
          </button>
          <button type="button" class="kbp-context-item" @click="handleKbCommand('toggle-disabled', kbMenu.kb)">
            <OsIcon :name="kbMenu.kb?.disabled === 1 ? 'eye' : 'eye-off'" :size="14" />
            {{ kbMenu.kb?.disabled === 1 ? '恢复检索' : '屏蔽检索' }}
          </button>
          <button v-if="Number(kbMenu.kb?.isDefault || 0) !== 1" type="button" class="kbp-context-item is-danger"
            @click="handleKbCommand('delete', kbMenu.kb)">
            <OsIcon name="trash" :size="14" />
            删除资料夹
          </button>
        </div>
      </aside>

      <!-- ============ 右：当前库的文档 ============ -->
      <section class="kbp-main">
        <template v-if="activeKb">
          <div class="kbp-main__head">
            <div class="kbp-main__title-row">
              <span class="kbp-main__title">{{ activeKb.name }}</span>
              <el-tag v-if="activeKb.isDefault" size="small" type="info" effect="plain">默认</el-tag>
              <el-tag v-if="activeKb.disabled === 1" size="small" type="warning" effect="plain">
                已屏蔽，不参与检索
              </el-tag>
            </div>
            <div class="kbp-main__actions">
              <el-button size="small" text @click="openShare(activeKb)">
                <el-icon><Share /></el-icon>
                分享资料夹
              </el-button>
              <el-button v-if="selectedDocCount" size="small" plain type="danger" :disabled="busy"
                @click="removeSelectedDocs">
                <OsIcon name="trash" :size="14" />
                删除（{{ selectedDocCount }}）
              </el-button>
              <el-button size="small" text @click="openOrganizeReport">
                <OsIcon name="alert" :size="14" />
                整理记录
                <span v-if="organizeReport.pending || organizeReport.failed" class="kbp-report-dot">
                  {{ organizeReport.pending + organizeReport.failed }}
                </span>
              </el-button>
              <el-dropdown class="kbp-upload-dropdown" trigger="click" :disabled="busy"
                @command="onUploadCommand">
                <button type="button" class="kbp-upload" :class="{ 'is-disabled': busy }" :disabled="busy"
                  title="上传文档：可在文件选择窗口按住 Ctrl 多选 Markdown、图片等文件">
                  <OsIcon name="arrow-up" :size="14" />
                  <span>{{ uploading ? '上传中…' : '上传文档' }}</span>
                  <OsIcon name="chevron-down" :size="12" />
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="file">
                      <OsIcon name="arrow-up" :size="14" />
                      选择文件（Ctrl 可多选）
                    </el-dropdown-item>
                    <el-dropdown-item command="text" :disabled="importing">
                      <OsIcon name="file-text" :size="14" />
                      {{ importing ? '导入中…' : '粘贴文本' }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>

          <!-- 拖拽上传：整块文档区都是投放目标 -->
          <div
            class="kbp-drop"
            :class="{ 'is-over': dragOver }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <div v-if="dragOver" class="kbp-drop__mask">
              <OsIcon name="arrow-up" :size="26" />
              <span>松手就传到「{{ activeKb.name }}」</span>
            </div>

            <div v-if="uploadTip" class="kbp-tip">{{ uploadTip }}</div>

            <div class="kbp-docs" v-loading="docsLoading">
              <div v-for="doc in activeKb.files" :key="doc.docId" class="kbp-doc"
                :data-doc-id="doc.docId"
                :class="{ 'is-jump-target': jumpTargetDocId === Number(doc.docId) }">
                <div class="kbp-doc__check">
                  <el-checkbox :model-value="selectedDocIds.includes(Number(doc.docId))"
                    @change="toggleDocSelected(Number(doc.docId))" />
                </div>
                <div class="kbp-doc__icon">
                  <OsIcon name="file-text" :size="17" />
                </div>
                <div class="kbp-doc__main">
                  <div class="kbp-doc__name-row">
                    <span class="kbp-doc__name" :title="doc.fileName">{{ doc.fileName }}</span>
                    <el-tag v-if="Number(doc.version || 1) > 1" type="success" size="small" effect="plain">
                      v{{ doc.version }}
                    </el-tag>
                    <el-tag :type="doc.disabled === 1 ? 'warning' : docTagType(doc.status)" size="small" effect="plain">
                      {{ doc.disabled === 1 ? '已屏蔽' : doc.statusText }}
                    </el-tag>
                    <span v-if="doc.sourceType === 'share'" class="kbp-kb__tag is-share">来自分享</span>
                  </div>
                  <div class="kbp-doc__meta">
                    <span>{{ doc.sizeText }}</span>
                    <span v-if="doc.chunkCount">· {{ doc.chunkCount }} 个片段</span>
                    <span v-if="doc.imageCount">· {{ doc.imageCount }} 张图</span>
                    <span v-if="doc.note" class="kbp-doc__note">· {{ doc.note }}</span>
                    <span class="kbp-doc__time">{{ doc.createTime }}</span>
                  </div>
                  <div v-if="doc.status === 4 && doc.errorMsg" class="kbp-doc__err">
                    {{ doc.errorMsg }}
                  </div>
                </div>
                <div class="kbp-doc__ops">
                  <span
                    class="kbp-doc__op"
                    :class="{ 'is-blocked': doc.disabled === 1 }"
                    :title="doc.disabled === 1 ? '已屏蔽，点击恢复这份资料的检索' : '可检索，点击屏蔽这份资料'"
                    @click="toggleDocSearchable(doc)"
                  >
                    <OsIcon :name="doc.disabled === 1 ? 'eye-off' : 'eye'" :size="14" />
                  </span>
                  <button type="button" class="kbp-doc__op kbp-doc__clinic"
                    data-tip="资料诊疗室" aria-label="资料诊疗室"
                    @click="openClinic(doc)">
                    <OsIcon name="activity" :size="14" />
                  </button>
                  <span class="kbp-doc__op" title="智能整理" @click="startOrganize(doc)">
                    <OsIcon name="sparkles" :size="14" />
                  </span>
                  <el-dropdown trigger="click" @command="(command: string) => handleDocMore(doc, command)">
                    <span class="kbp-doc__op" title="更多操作">
                      <OsIcon name="more" :size="14" />
                    </span>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="micro">生成微课</el-dropdown-item>
                        <el-dropdown-item command="share">分享资料</el-dropdown-item>
                        <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
                        <el-dropdown-item command="docx">导出 Word</el-dropdown-item>
                        <el-dropdown-item command="reprocess">重新解析并向量化</el-dropdown-item>
                        <el-dropdown-item command="delete" divided>删除资料</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>

              <div v-if="!docsLoading && !activeKb.files.length" class="kbp-docs__empty">
                <div class="kbp-empty__art">
                  <OsIcon name="inbox" :size="30" />
                </div>
                <p class="kbp-empty__title">这个资料夹还是空的</p>
                <span class="kbp-empty__desc">
                  把课件、真题、笔记传进来，智能体出题时就能翻到它们
                </span>
                <div class="kbp-empty__actions">
                  <el-dropdown trigger="click" :disabled="busy" @command="onUploadCommand">
                    <button type="button" class="kbp-empty__btn is-primary" :disabled="busy">
                      <OsIcon name="arrow-up" :size="14" />
                      <span>上传文档</span>
                      <OsIcon name="chevron-down" :size="12" />
                    </button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="file">
                          <OsIcon name="arrow-up" :size="14" /> 选择文件（Ctrl 可多选）
                        </el-dropdown-item>
                        <el-dropdown-item command="text">
                          <OsIcon name="file-text" :size="14" /> 粘贴文本
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
                <span class="kbp-empty__formats">
                  支持 Word / PDF / Markdown / TXT，带公式和图片也能读；也可以直接粘贴文本
                </span>
              </div>
            </div>
          </div>

          <!--
            语义检索（RAG）—— 2026-10-22 重做
            =================================
            原来这块是「纯字符串匹配」且写死只搜默认库，在别的库里搜什么都搜不到；
            而且结果只有文件名，点不了、看不了，用户拿到一句"找到了"就没了。

            现在：
              · 走后端真正的混合检索（向量 + 全文 + RRF），**默认只搜当前选中的库**；
              · 每条结果展示一个命中片段，只保留「定位原文」一个动作：
                进资料刨析后自动滚动并用黄色标记标出用户搜索词所在位置。
          -->
          <section v-if="activeKb.files.length" ref="tryPanelRef" class="kbp-try">
            <div class="kbp-try__head">
              <span class="kbp-try__title">试试 AI 会怎么找</span>
              <span class="kbp-try__hint">
                在「{{ activeKb.name }}」里按意思找，不是只匹配字面
              </span>
            </div>
            <div class="kbp-try__row">
              <el-input
                v-model="tryQuery"
                placeholder="例如：随机事件、二叉树的时间复杂度"
                clearable
                @keyup.enter="doTry"
                @input="onTryInput"
              />
              <el-button type="primary" :loading="trying" @click="doTry">找找看</el-button>
            </div>

            <transition-group v-if="tryHits.length" name="kbp-fade" tag="div" class="kbp-try__result">
              <!--
                低置信提示（2026-10-22）
                ------------------------
                向量检索**总会**返回 top_k 条，哪怕库里根本没有相关内容。
                后端用「关键词那一路有没有命中」判断置信度，这里如实告诉用户
                「这些可能不相关」——而不是让他误以为真的搜到了。
              -->
              <div v-if="lowConfidence" class="kbp-try__warn">
                <OsIcon name="alert" :size="14" />
                <span>
                  这些结果可能和你的问题关系不大 —— 这些资料里也许没有相关内容。
                  可以换个说法，或确认是否选对了资料夹。
                </span>
              </div>

              <div
                v-for="(h, i) in tryPageHits"
                :key="h.chunkId || `${h.docId}-${i}`"
                class="kbp-try__hit"
                :class="{ 'is-best': i === 0 && !lowConfidence }"
              >
                <span class="kbp-try__rank">{{ (tryPage - 1) * TRY_PAGE_SIZE + i + 1 }}</span>
                <div class="kbp-try__file-main">
                  <div class="kbp-try__file-name-row">
                    <!--
                      文件名也高亮：用户搜「数据结构」，命中的那份文件名里就带着这几个字，
                      不给它标出来反而要去正文里找 —— 而文件名往往是最强的"就是这份"信号。
                      ⚠️ v-html 的内容由 `highlight()` 生成，**正文先转义再插标记**，
                         不能反过来（见该函数注释）。
                    -->
                    <span class="kbp-try__file-name" v-html="highlight(h.docName || h.fileName || '未命名文档')"></span>
                    <span v-if="i === 0 && !lowConfidence" class="kbp-try__badge">最匹配</span>
                  </div>
                  <div class="kbp-try__file-meta">
                    <span v-if="h.kbName" class="kbp-try__kb">{{ h.kbName }}</span>
                    <span>第 {{ Number(h.chunkIndex || 0) + 1 }} 段</span>
                    <span v-if="h.score != null" class="kbp-try__score">匹配度 {{ Number(h.score).toFixed(3) }}</span>
                  </div>
                  <div class="kbp-try__snippet kbp-try__snippet--hit" v-html="highlight(buildHitSnippet(h.content))"></div>
                </div>
                <div class="kbp-try__ops">
                  <button type="button" class="kbp-try__op" @click="openHit(h)">
                    定位原文
                  </button>
                </div>
              </div>
              <div v-if="tryHits.length > TRY_PAGE_SIZE" class="kbp-try__pager">
                <el-pagination
                  v-model:current-page="tryPage"
                  :page-size="TRY_PAGE_SIZE"
                  :total="tryHits.length"
                  layout="prev, pager, next"
                  small
                />
              </div>
            </transition-group>

            <div v-else-if="tried" class="kbp-try__empty">
              <template v-if="tryReason">{{ tryReason }}</template>
              <template v-else>
                没找到相关的内容。可以换个说法试试 —— 检索是按意思匹配的，
                不必和原文用一样的词。
              </template>
            </div>
          </section>
        </template>

        <div v-else-if="!loading" class="kbp-main__empty">
          <div class="kbp-empty__art">
            <OsIcon name="folder" :size="30" />
          </div>
          <p class="kbp-empty__title">左边选一个资料夹</p>
          <span class="kbp-empty__desc">选中后这里会显示它里面的资料</span>
        </div>
      </section>
    </div>

    <!-- 完整书架视图 -->
    <section v-else-if="viewMode === 'shelf' && (loading || (kbs.length && !loadFailed))" class="kbp-shelf-page">
      <div class="kbp-shelf-page__head">
        <div>
          <h2>{{ activeKb?.name || '我的资料' }}</h2>
          <p>{{ activeKb?.files?.length || 0 }} 份资料 · 点击卡片看刨析</p>
        </div>
        <el-button size="small" @click="viewMode = 'list'">返回资料夹</el-button>
      </div>
      <div v-if="activeKb?.files?.length" class="kbp-shelf-grid">
        <button v-for="doc in activeKb.files" :key="doc.docId" type="button" class="kbp-shelf-card"
          @click="showAnatomy(doc)">
          <div class="kbp-shelf-card__top">
            <OsIcon name="file-text" :size="18" />
            <el-tag :type="docTagType(doc.status)" size="small" effect="plain">{{ doc.statusText }}</el-tag>
          </div>
          <div class="kbp-shelf-card__name" :title="doc.fileName">{{ doc.fileName }}</div>
          <div class="kbp-shelf-card__facets">
            <span v-if="doc.sourceType === 'share'" class="kbp-kb__tag is-share">来自分享</span>
            <span v-if="doc.imageCount">{{ doc.imageCount }} 图</span>
            <span v-if="doc.chunkCount">{{ doc.chunkCount }} 分块</span>
          </div>
          <div class="kbp-shelf-card__bottom">{{ doc.sizeText }} · {{ doc.createTime }}</div>
        </button>
      </div>
      <div v-else class="kbp-docs__empty kbp-view-empty">
        <div class="kbp-empty__art">
          <OsIcon name="book-open" :size="30" />
        </div>
        <p class="kbp-empty__title">书架还是空的</p>
        <span class="kbp-empty__desc">上传课件、真题或笔记后，这里会按资料显示成书架卡片。</span>
        <div class="kbp-empty__actions">
          <button type="button" class="kbp-empty__btn is-primary" :disabled="busy" @click="onPick">
            <OsIcon name="arrow-up" :size="14" />
            <span>上传文档</span>
          </button>
        </div>
      </div>
    </section>

    <!-- 画廊：0.4.0 起替换原图片墙，增加描述/OCR/来源/引用 -->
    <GalleryPanel
      v-else-if="viewMode === 'gallery' && (loading || (kbs.length && !loadFailed))"
      :active-kb-id="activeKbId"
      :active-kb-name="activeKb?.name"
      @use-image="onGalleryUseImage"
      @locate="onGalleryLocate"
      @back="viewMode = 'list'"
    />

    <!-- 资料知识地图：0.4.1 的页面级关系视图，不画实体图 -->
    <KnowledgeMapPanel
      v-else-if="viewMode === 'map' && (loading || (kbs.length && !loadFailed))"
      :active-kb-id="activeKbId"
      @open-doc="onMapOpenDoc"
      @back="viewMode = 'list'"
    />

    <!-- 全页空态：一个知识库都没有时，用一张完整引导替代整个两栏区 -->
    <div v-if="viewMode === 'list' && !loading && !kbs.length && loadFailed" class="kbp-blank">
      <div class="kbp-blank__box">
        <div class="kbp-blank__art is-warn">
          <OsIcon name="alert" :size="32" />
        </div>
        <h2 class="kbp-blank__title">我的资料没能加载出来</h2>
        <p class="kbp-blank__desc">
          可能是网络或服务暂时不可用。这不代表你的资料丢了，
          重试一下通常就好。
        </p>
        <button type="button" class="kbp-blank__btn" :disabled="loading" @click="load(false)">
          <OsIcon name="zap" :size="15" />
          <span>重新加载</span>
        </button>
      </div>
    </div>

    <!-- 全页空态：一个知识库都没有时，用一张完整引导替代整个两栏区 -->
    <div v-else-if="viewMode === 'list' && !loading && !kbs.length" class="kbp-blank">
      <div class="kbp-blank__box">
        <div class="kbp-blank__art">
          <OsIcon name="folder-plus" :size="34" />
        </div>
        <h2 class="kbp-blank__title">先建一个资料夹</h2>
        <p class="kbp-blank__desc">
          资料夹就是你的资料收纳处。把课件、真题、笔记放进去，
          智能体出题时会自己翻这些资料，不用你每次都重新传。
        </p>
        <button type="button" class="kbp-blank__btn" :disabled="creating" @click="promptCreate">
          <OsIcon name="plus" :size="15" />
          <span>新建资料夹</span>
        </button>
        <span class="kbp-blank__hint">建好后可以往里拖文件</span>
      </div>
    </div>

    <!-- 单文档刨析：结构 / 正文与图片 / 图片资产轨 -->
    <el-dialog v-model="anatomyVisible" :title="`资料刨析 · ${anatomyDocName}`" width="1100px" append-to-body
      class="kbp-anatomy-dialog">
      <div v-loading="anatomyLoading" class="kbp-anatomy">
        <div class="kbp-anatomy__stats">
          <span><b>{{ anatomyStats.contentLength }}</b> 字</span>
          <span><b>{{ anatomyStats.imageCount }}</b> 张图</span>
          <span><b>{{ anatomyStats.headingCount }}</b> 个标题</span>
          <span><b>{{ anatomyStats.chunkCount }}</b> 个分块</span>
        </div>

        <div class="kbp-anatomy__grid">
          <section class="kbp-anatomy__outline">
            <h4>资料结构</h4>
            <div v-if="anatomyQuestionGroups.length" class="kbp-anatomy__question-groups">
              <div class="kbp-anatomy__question-groups-label">按题型整理</div>
              <div v-for="group in anatomyQuestionGroups" :key="group.name" class="kbp-anatomy__question-group"
                @click="jumpToQuestionGroup(group)">
                <span>{{ group.name }}</span>
                <b>{{ group.count }} 题</b>
              </div>
            </div>
            <div v-if="anatomyOutlineItems.length" class="kbp-anatomy__outline-list">
              <div v-for="(item, idx) in anatomyOutlineItems" :key="idx" class="kbp-anatomy__outline-item"
                :style="{ paddingLeft: `${12 + item.level * 14}px` }">
                {{ item.name }}
              </div>
            </div>
            <div v-else-if="!anatomyQuestionGroups.length" class="kbp-anatomy__empty">
              {{ anatomyOutlineReason || '这份资料没有可提取的章节结构。' }}
            </div>
          </section>

          <section class="kbp-anatomy__content">
            <h4 class="kbp-anatomy__content-head">
              <span>正文与图片</span>
              <button type="button" class="kbp-anatomy__fullscreen" title="全屏查看正文与图片"
                @click="openAnatomyFullscreen">全屏观看</button>
            </h4>
            <div v-if="anatomySegments.length" class="kbp-anatomy__content-inner">
              <template v-for="(seg, si) in anatomySegments" :key="si">
                <div v-if="seg.type === 'image'" class="kbp-anatomy__segment"
                  :data-raw-start="seg.start" :data-raw-end="seg.end">
                  <el-image :src="seg.url" fit="contain" class="kbp-anatomy__inline-image"
                    :preview-src-list="[seg.url]" preview-teleported @load="onAnatomyImageLoad" />
                </div>
                <div v-else class="kbp-anatomy__segment"
                  :data-raw-start="seg.start" :data-raw-end="seg.end">
                  <LatexRenderer :content="seg.text" class="kbp-anatomy__rendered" />
                </div>
              </template>
            </div>
            <div v-else class="kbp-anatomy__empty">没有可展示的正文，可能还在解析中。</div>
          </section>

          <section class="kbp-anatomy__assets">
            <h4>图片资产 <span>{{ anatomyImages.length }}</span></h4>
            <div v-if="anatomyImages.length" class="kbp-anatomy__image-grid">
              <div v-for="(img, idx) in anatomyImages" :key="img.key" class="kbp-anatomy__image-card">
                <el-image :src="img.url" fit="cover" :preview-src-list="[img.url]" preview-teleported />
                <span>图 {{ idx + 1 }}</span>
                <button type="button" class="kbp-anatomy__copy" @click="copyImageMarkdown(img.url, anatomyDocName, idx + 1)">
                  复制
                </button>
              </div>
            </div>
            <div v-else class="kbp-anatomy__empty">这份资料里没有提取到图片。</div>
          </section>
        </div>
      </div>
    </el-dialog>

    <!-- 资料正文全屏观看：保留刨析的结构/图片资产信息，正文单独放大 -->
    <el-dialog v-model="anatomyFullscreen" :title="`资料正文 · ${anatomyDocName}`" fullscreen append-to-body
      class="kbp-anatomy-fullscreen-dialog">
      <div class="kbp-anatomy-fullscreen__body">
        <div v-if="anatomySegments.length">
          <template v-for="(seg, si) in anatomySegments" :key="`full-${si}`">
            <el-image v-if="seg.type === 'image'" :src="seg.url" fit="contain"
              class="kbp-anatomy__inline-image" :preview-src-list="[seg.url]" preview-teleported />
            <LatexRenderer v-else :content="seg.text" class="kbp-anatomy__rendered" />
          </template>
        </div>
        <div v-else class="kbp-anatomy__empty">没有可展示的正文，可能还在解析中。</div>
      </div>
    </el-dialog>

    <!-- 统一入口：资料体检 / 资料刨析 / 学习处方共用一套工作台 -->
    <DocumentClinicDialog ref="clinicRef" :show-edit="true" @organize="startOrganizeFromHealth"
      @ask="askFromHealth" @edit="openEditor" />

    <!-- 知识库分享 / 领取（参考题库分享） -->
    <ShareKnowledgeDialog v-model="shareDialogVisible" :default-kb-id="shareKbId" />
    <ShareKnowledgeDialog v-model="docShareDialogVisible" :doc="shareDoc" />
    <ReceiveKnowledgeDialog v-model="receiveDialogVisible" />

    <!-- 图片资产 → 插入题目解析 -->
    <el-dialog v-model="questionPickerVisible" title="插入题目解析" width="820px" append-to-body>
      <div class="kbp-question-picker">
        <div class="kbp-question-picker__toolbar">
          <el-input v-model="questionKeyword" clearable placeholder="搜索题目题干"
            @keyup.enter="loadQuestionPicker(1)" />
          <el-select v-model="questionBankFilter" clearable filterable placeholder="全部题库"
            class="kbp-question-picker__bank" @change="loadQuestionPicker(1)">
            <el-option v-for="bank in questionBanks" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
          </el-select>
          <el-button type="primary" @click="loadQuestionPicker(1)">搜索</el-button>
          <span class="kbp-question-picker__image">
            当前图片：{{ questionPickerImage?.docName }} · 图 {{ questionPickerImage?.seq }}
          </span>
        </div>
        <p class="kbp-question-picker__hint">只显示你创建的题库中的题目，可按题库筛选，确保有编辑权限。</p>
        <el-table :data="questionRows" v-loading="questionPickerLoading" max-height="420" size="small">
          <el-table-column label="题目" min-width="360">
            <template #default="{ row }">
              <span class="kbp-question-picker__text">
                {{ String(row.questionText || row.content || '未命名题目').slice(0, 100) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="所属题库" width="160">
            <template #default="{ row }">
              <span class="kbp-question-picker__bank-name">{{ row.bankName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="题型" width="90">
            <template #default="{ row }">{{ row.questionTypeText || row.questionType || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" type="primary" :loading="questionInsertingId === row.id"
                @click="insertImageIntoQuestion(row)">
                插入解析
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="questionPage" :page-size="QUESTION_PAGE_SIZE"
          :total="questionTotal" layout="prev, pager, next" small
          @current-change="loadQuestionPicker" />
      </div>
    </el-dialog>

    <!-- 图片资产 → 加入笔记 -->
    <el-dialog v-model="notePickerVisible" title="加入笔记" width="820px" append-to-body>
      <div class="kbp-question-picker">
        <div class="kbp-question-picker__toolbar">
          <el-input v-model="noteKeyword" clearable placeholder="搜索笔记标题"
            @keyup.enter="loadNotePicker(1)" />
          <el-button type="primary" @click="loadNotePicker(1)">搜索</el-button>
          <span class="kbp-question-picker__image">
            当前图片：{{ notePickerImage?.docName }} · 图 {{ notePickerImage?.seq }}
          </span>
        </div>
        <el-table :data="noteRows" v-loading="notePickerLoading" max-height="420" size="small">
          <el-table-column label="笔记" min-width="420">
            <template #default="{ row }">
              <span class="kbp-question-picker__text">
                {{ String(row.title || row.noteTitle || '未命名笔记').slice(0, 100) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" type="primary" :loading="noteInsertingId === row.id"
                @click="insertImageIntoNote(row)">
                加入笔记
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="notePage" :page-size="NOTE_PAGE_SIZE"
          :total="noteTotal" layout="prev, pager, next" small
          @current-change="loadNotePicker" />
      </div>
    </el-dialog>

    <!-- 整理记录：展示真实整理计划历史，而不是只有文档状态统计 -->
    <el-dialog v-model="organizeReportVisible" title="整理记录" width="760px" append-to-body>
      <div class="kbp-report" v-loading="organizePlansLoading">
        <div class="kbp-report__stats">
          <div><b>{{ organizePlans.length }}</b><span>整理次数</span></div>
          <div><b>{{ organizePlanCount('applied') }}</b><span>已应用</span></div>
          <div><b>{{ organizePlanCount('ready') }}</b><span>待确认</span></div>
          <div><b>{{ organizePlanCount('failed') }}</b><span>失败</span></div>
        </div>
        <div v-if="organizePlans.length" class="kbp-report__list">
          <div v-for="plan in organizePlans" :key="plan.planId" class="kbp-report__row">
            <div class="kbp-report__main">
              <span class="kbp-report__name" :title="plan.docName">{{ plan.docName }}</span>
              <span class="kbp-report__meta">
                {{ plan.createTime }} · {{ plan.mode === 'deep' ? '智能整理' : '旧版整理' }}
              </span>
            </div>
            <span class="kbp-report__changes">{{ plan.changed }} 处变更</span>
            <el-tag :type="planStatusType(plan.status)" size="small" effect="plain">
              {{ planStatusText(plan.status) }}
            </el-tag>
            <el-button v-if="!plan.legacy" text size="small" @click="openOrganizePlan(plan)">查看变更</el-button>
            <el-button v-else text size="small" @click="openOrganizePlan(plan)">查看历史</el-button>
            <el-button text size="small" type="danger" @click.stop="deleteOrganizeRecord(plan)">删除</el-button>
          </div>
        </div>
        <div v-else class="kbp-anatomy__empty">还没有整理记录。</div>
      </div>
    </el-dialog>

    <!-- 单文档智能整理：快速/深度预览 -->
    <OrganizeDiffDialog
      v-model:visible="organizeVisible"
      :mode="organizeMode"
      :status="organizeStatus"
      :stage="organizeStage"
      :progress="organizeProgress"
      :elapsed="organizeElapsed"
      :error="organizeError"
      :changes="organizeChanges"
      :suggestions="organizeSuggestions"
      :applied="organizeApplied"
      :record-view="organizeRecordView"
      @apply="applyOrganizePreview"
      @rollback="rollbackOrganizePreview"
      @rerun="rerunOrganize"
      @recheck="recheckOrganize"
    />

    <!-- 二次编辑：Word / Markdown 共用的正文编辑器 -->
    <el-dialog v-model="editorVisible" :title="`编辑资料 · ${editorDoc?.fileName || ''}`" width="1040px" top="5vh" append-to-body>
      <div class="kbp-editor" v-loading="editorLoading">
        <div class="kbp-editor__bar">
          <el-tag type="info" effect="plain">富文本 · Word / Markdown 兼容</el-tag>
          <span>支持加粗、标题、列表、表格和插入图片；保存后重新解析并建立检索索引。</span>
          <el-button text size="small" @click="versionsVisible = true">版本对照</el-button>
          <el-button text size="small" @click="editorPreview = !editorPreview">
            {{ editorPreview ? '继续编辑' : '预览排版' }}
          </el-button>
        </div>
        <TiptapEditor
          v-if="!editorPreview"
          v-model="editorHtml"
          class="kbp-editor__rich"
          placeholder="在这里编辑正文，支持富文本、公式和插入图片。"
        />
        <div v-else class="kbp-editor__preview">
          <LatexRenderer :content="editorMarkdown" />
        </div>
      </div>
      <template #footer>
        <div class="kbp-editor__footer">
          <div>
            <el-button @click="exportCurrent('markdown')">导出 Markdown</el-button>
            <el-button @click="exportCurrent('docx')">导出 Word</el-button>
          </div>
          <div>
            <el-button @click="editorVisible = false">取消</el-button>
            <el-button type="primary" :loading="editorSaving" @click="saveEditor">保存并重新解析</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 版本对照：时间线 + 左右 diff + 体检变化；只挂在编辑器内 -->
    <VersionHistoryDialog
      v-model="versionsVisible"
      :doc="editorDoc"
      @restored="onDocumentVersionRestored"
    />

    <!-- 粘贴文本 -->
    <el-dialog v-model="textImportVisible" title="粘贴文本" width="640px" append-to-body @closed="resetTextImport">
      <div class="kbp-import">
        <p class="kbp-import__hint">
          把正文直接粘进来就行，不用先存成文件。导入后智能体一样能检索到。
        </p>
        <el-input
          v-model="textImportContent"
          type="textarea"
          :rows="10"
          placeholder="把课件文字、笔记、错题解析粘在这里…"
        />
        <div class="kbp-import__row">
          <span class="kbp-import__label">起个名字</span>
          <el-input v-model="textImportFileName" placeholder="例如：概率论第四章笔记" maxlength="80" />
        </div>
      </div>
      <template #footer>
        <el-button @click="textImportVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitTextImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import OsIcon from '@/components/OsIcon/index.vue'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import { marked } from 'marked'
import TurndownService from 'turndown'
import { getWorkspaceOverview, uploadToWorkspace, searchWorkspace, listWorkspaceStandaloneImages, getAssetUsageSummary, recordAssetUsage, previewWorkspaceOrganize, getWorkspaceOrganizePlan, getWorkspaceOrganizeRecord, listWorkspaceOrganizePlans, applyWorkspaceOrganize, deleteWorkspaceOrganizeRecord, rollbackWorkspacePlan, setDocumentSearchable, createContentReference } from '@/api/ai/workspace'
import OrganizeDiffDialog from './components/OrganizeDiffDialog.vue'
import DocumentClinicDialog from './components/DocumentClinicDialog.vue'
import GalleryPanel from './components/GalleryPanel.vue'
import KnowledgeMapPanel from './components/KnowledgeMapPanel.vue'
import VersionHistoryDialog from './components/VersionHistoryDialog.vue'
import ShareKnowledgeDialog from './components/ShareKnowledgeDialog.vue'
import ReceiveKnowledgeDialog from './components/ReceiveKnowledgeDialog.vue'
import { listQuestionMain, getQuestionMain, updateQuestionMain } from '@/api/questionMain/questionMain'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { listNote, getNote, updateNote } from '@/api/notes/note'
import useUserStore from '@/store/modules/user'
import useTopbarStore from '@/store/modules/topbar'
import {
  KB_FILE_ACCEPT,
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  getDocumentContent,
  getDocumentOutline,
  getDocumentStatus,
  getDocumentStatusBatch,
  updateDocumentContent,
  exportDocument,
  importDocumentText,
  reprocessDocument,
  updateKnowledgeBase,
  uploadDocument
} from '@/api/ai/rag'
import { Plus } from '@element-plus/icons-vue'
import { Download, Search, Share } from '@element-plus/icons-vue'
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/ruoyi'
import {
  ensureMarkdownImageFiles,
  missingMarkdownImageFiles,
  pickMissingImagesFromDirectory
} from '@/utils/markdownUpload'

/* ===================== 状态 ===================== */

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const creating = ref(false)
const uploading = ref(false)
const uploadTip = ref('')
const dragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const docsLoading = ref(false)
/**
 * 加载失败标记
 *
 * 为什么不能只靠 `kbs.length === 0` 判断空态：
 *   接口挂了和「真的一个库都没有」在这件事上长得一模一样，
 *   但用户看到的应该是**两种完全不同的画面** ——
 *   前者要说"没加载出来，重试"，后者要说"来建第一个库"。
 *   混在一起的话，服务故障会被伪装成"你的资料没了"，这是最吓人的那种误导。
 */
const loadFailed = ref(false)

const kbs = ref<any[]>([])
const activeKbId = ref<number | null>(null)
const folderKeyword = ref('')
const kbMenu = reactive<{ visible: boolean; x: number; y: number; kb: any }>({
  visible: false,
  x: 0,
  y: 0,
  kb: null,
})
const shareDialogVisible = ref(false)
const docShareDialogVisible = ref(false)
const shareDoc = ref<{ docId: number; fileName: string } | null>(null)
const receiveDialogVisible = ref(false)
const shareKbId = ref<number | null>(null)
/** 从聊天「查看处理进度」跳转过来时，临时高亮并滚动到目标文档。 */
const jumpTargetDocId = ref<number | null>(null)
const jumpQueryApplied = ref(false)
const stats = reactive<any>({ kbCount: 0, docCount: 0, readyCount: 0, totalSizeText: '0 B' })
const topbarStore = useTopbarStore()

watch(
  () => [stats.docCount, stats.readyCount] as const,
  () => {
    topbarStore.setCount(stats.docCount ? `${stats.docCount} 份资料` : '')
  },
  { immediate: true }
)

const activeKb = computed(() => kbs.value.find((k) => k.kbId === activeKbId.value) || null)

/** 左侧资料夹搜索：只过滤展示，不影响当前选中的库。 */
const filteredKbs = computed(() => {
  const keyword = folderKeyword.value.trim().toLowerCase()
  if (!keyword) return kbs.value
  return kbs.value.filter((kb) => String(kb.name || '').toLowerCase().includes(keyword))
})

/** 批量删除：只保存当前库的文档 id，换库/刷新文档列表时清空 */
const selectedDocIds = ref<number[]>([])
const selectedDocCount = computed(() => selectedDocIds.value.length)

const busy = computed(() => uploading.value || importing.value)

/** 「重新解析并向量化」的后台任务提示（全局可见，不阻塞继续浏览） */
const reprocessTask = reactive({
  active: false,
  docId: 0,
  fileName: '',
  statusText: '',
  percent: 0,
  error: ''
})
const reprocessElapsed = ref(0)
let reprocessTimer: ReturnType<typeof setInterval> | null = null

const organizeReportVisible = ref(false)
const organizePlansLoading = ref(false)
const organizePlans = ref<any[]>([])
const organizeVisible = ref(false)
const organizeMode = ref<'quick' | 'deep'>('deep')
const organizeStatus = ref('starting')
const organizeStage = ref('starting')
const organizeProgress = ref(0)
const organizeElapsed = ref(0)
const organizeError = ref('')
const organizeApplied = ref(false)
const organizeRecordView = ref(false)
const organizePlanId = ref<number | null>(null)
const organizeChanges = ref<any[]>([])
const organizeSuggestions = ref<any[]>([])
const organizeDocTarget = ref<any>(null)
const organizeTask = reactive({
  active: false,
  docId: 0,
  fileName: '',
  statusText: '',
  percent: 0
})
const editorVisible = ref(false)
const editorLoading = ref(false)
const editorSaving = ref(false)
const editorDoc = ref<any>(null)
const editorContent = ref('')
const editorHtml = ref('')
const editorImageMap = ref<Record<string, string>>({})
const editorPreview = ref(false)
const versionsVisible = ref(false)
const deepOrganizeOptions = reactive({
  structure: true,
  imageLinking: true,
  duplicateDetection: true,
  cleanupSuggestions: true
})
let organizeClock: ReturnType<typeof setInterval> | null = null
let organizePoll: ReturnType<typeof setTimeout> | null = null
let organizeStartedAt = 0

/* 富文本编辑：Tiptap HTML ↔ Markdown，保留原有图片标记 */
const turndownService = new TurndownService({
  headingStyle: 'atx',
  bulletListMarker: '-',
  codeBlockStyle: 'fenced'
})
turndownService.addRule('os-image-marker', {
  filter: (node: any) => node.nodeName === 'IMG' && !!node.getAttribute('data-os-image'),
  replacement: (_content: string, node: any) => `【图${node.getAttribute('data-os-image')}】`
})
turndownService.addRule('os-math', {
  filter: (node: any) => node.nodeName === 'SPAN' && !!node.getAttribute('data-os-math'),
  replacement: (_content: string, node: any) => {
    try {
      return decodeURIComponent(node.getAttribute('data-os-math') || '')
    } catch {
      return node.textContent || ''
    }
  }
})
turndownService.addRule('markdown-table', {
  filter: (node: any) => node.nodeName === 'TABLE',
  replacement: (_content: string, node: any) => {
    const rows = [...node.querySelectorAll('tr')].map((row: any) =>
      [...row.querySelectorAll('th,td')].map((cell: any) =>
        String(cell.textContent || '').replace(/\|/g, '\\|').replace(/\n+/g, ' ').trim()
      )
    )
    if (!rows.length) return ''
    const width = Math.max(...rows.map((row: string[]) => row.length))
    const normalized = rows.map((row: string[]) => {
      const padded = [...row]
      while (padded.length < width) padded.push('')
      return padded
    })
    const header = normalized[0]
    const body = normalized.slice(1)
    const lines = [
      `| ${header.join(' | ')} |`,
      `| ${header.map(() => '---').join(' | ')} |`,
      ...body.map((row: string[]) => `| ${row.join(' | ')} |`)
    ]
    return `\n\n${lines.join('\n')}\n\n`
  }
})

function markdownToEditorHtml(markdown: string): string {
  // Tiptap 的 MathNode 会把整个 LaTeX 片段作为原子节点保存，避免 Markdown
  // 往返把 `\overline` 之类的反斜杠当转义符吃掉。
  const protectedMath = String(markdown || '').replace(
    /\$\$[\s\S]*?\$\$|\$[^$\n]+?\$/g,
    (formula) => `<span data-os-math="${encodeURIComponent(formula)}"></span>`
  )
  const withImages = protectedMath.replace(/【图(\d+)】/g, (_m, n) => {
    const url = editorImageMap.value[String(n)]
    return url ? `<img data-os-image="${n}" src="${anatomyImageUrl(url)}" />` : `【图${n}】`
  }).replace(
    /!\[([^\]]*)\]\(([^)\s]+)\)/g,
    (_all, alt, url) => `<img src="${String(url).replace(/"/g, '&quot;')}" alt="${String(alt).replace(/"/g, '&quot;')}" />`,
  )
  try {
    return marked.parse(withImages, { gfm: true, breaks: true }) as string
  } catch {
    return `<p>${withImages.replace(/</g, '&lt;')}</p>`
  }
}

function htmlToEditorMarkdown(html: string): string {
  return turndownService.turndown(html || '').trim()
}

const editorMarkdown = computed(() => htmlToEditorMarkdown(editorHtml.value))
const viewMode = ref<'list' | 'shelf' | 'gallery' | 'map'>('list')
const canTeleport = ref(false)
const workspaceTabs = [
  { key: 'list' as const, label: '资料夹', icon: 'folder' },
  { key: 'shelf' as const, label: '书架', icon: 'book-open' },
  { key: 'gallery' as const, label: '画廊', icon: 'layout-grid' },
  { key: 'map' as const, label: '知识地图', icon: 'activity' }
]
const viewModeLabel = computed(
  () => workspaceTabs.find((tab) => tab.key === viewMode.value)?.label || '资料夹'
)
const standaloneImages = ref<any[]>([])
const assetUsage = ref<Record<string, number>>({})

/* 图片插入题目 */
const questionPickerVisible = ref(false)
const questionPickerLoading = ref(false)
const questionPickerImage = ref<any>(null)
const questionKeyword = ref('')
const questionBankFilter = ref<number | null>(null)
const questionBanks = ref<any[]>([])
const questionRows = ref<any[]>([])
const questionTotal = ref(0)
const questionPage = ref(1)
const QUESTION_PAGE_SIZE = 10
const questionInsertingId = ref<number | null>(null)

/* 图片插入笔记 */
const notePickerVisible = ref(false)
const notePickerLoading = ref(false)
const notePickerImage = ref<any>(null)
const noteKeyword = ref('')
const noteRows = ref<any[]>([])
const noteTotal = ref(0)
const notePage = ref(1)
const NOTE_PAGE_SIZE = 10
const noteInsertingId = ref<number | null>(null)

/* 试试 AI 怎么找 */
const tryQuery = ref('')
const tryPanelRef = ref<HTMLElement | null>(null)
const trying = ref(false)
const tried = ref(false)
const tryHits = ref<any[]>([])
const tryPage = ref(1)
const TRY_PAGE_SIZE = 10
const tryPageHits = computed(() => {
  const start = (tryPage.value - 1) * TRY_PAGE_SIZE
  return tryHits.value.slice(start, start + TRY_PAGE_SIZE)
})
/** 后端给的「为什么没结果」人话原因（如「没有可检索的知识库」），有就优先显示 */
const tryReason = ref('')
/**
 * 结果可能不相关（后端 `lowConfidence`）
 *
 * 判据 = 向量路和关键词路都没命中，只是向量返回了"最像的几条"。
 * 这时不能装作搜到了，也不能直接吞掉结果（可能是换词提问）——
 * 折中：照常列出来，但在上面加一条明确提示。
 */
const lowConfidence = ref(false)
/**
 * **本次检索用的词**（高亮依据）
 *
 * 单独存一份、而不是直接用 `tryQuery`：输入框是随时可改的，
 * 结果列表却对应"上一次点找找看时"的那个词。两者混用会导致
 * 用户一改输入框，已有结果的高亮就乱跳。
 */
const trySearchedQuery = ref('')

/** 清空 AI 检索的结果区域：点击面板外、清空输入时都应调用。 */
function clearTryResults() {
  tryHits.value = []
  tryPage.value = 1
  tried.value = false
  tryReason.value = ''
  lowConfidence.value = false
  trySearchedQuery.value = ''
}

function onTryInput() {
  if (!tryQuery.value.trim()) clearTryResults()
}

/* 分块 */

/* ===================== 单文档刨析 ===================== */
/** 共享刨析查看器：打开、切文档、高亮定位都由组件内部处理 */
const clinicRef = ref<InstanceType<typeof DocumentClinicDialog> | null>(null)
const anatomyVisible = ref(false)
const anatomyLoading = ref(false)
const anatomyFullscreen = ref(false)
const anatomyDocName = ref('')
const anatomyContent = ref('')
/** 从搜索跳转过来时要高亮的检索词；空串 = 普通刨析查看 */
const anatomyHighlight = ref('')
const anatomyTargetChunkId = ref<number | null>(null)
const anatomyTargetChunkIndex = ref<number | null>(null)
const anatomyTargetChunkCount = ref(0)
const anatomyTargetText = ref('')
const anatomyScrollTargetOffset = ref<number | null>(null)
const anatomyExcludedRanges = ref<any[]>([])
const anatomyImageMap = ref<Record<string, string>>({})
const anatomyTree = ref<any>(null)
const anatomyOutlineReason = ref('')
const anatomyStats = reactive({
  contentLength: 0,
  imageCount: 0,
  headingCount: 0,
  chunkCount: 0
})

/** 图片 URL 归一：相对路径拼上 API 前缀，data/http 地址原样返回 */
function anatomyImageUrl(url: string): string {
  const v = String(url || '').trim()
  if (!v) return ''
  if (v.startsWith('data:') || v.startsWith('http://') || v.startsWith('https://')) return v
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (v.startsWith('/') ? v : '/' + v)
}

/** 复制图片 Markdown，方便用户粘贴到题目/笔记编辑器 */
async function copyImageMarkdown(url: string, docName: string, seq: number) {
  if (!url) return
  const alt = `${docName || '资料'}·图${seq}`
  const text = `![${alt}](${url})`
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const input = document.createElement('textarea')
      input.value = text
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
    }
    ElMessage.success('已复制图片 Markdown')
  } catch {
    ElMessage.warning('复制失败，请打开图片后手动复制')
  }
}

/** 图片资产列表：键保留下来，正文里的【图N】要靠它回指 */
const anatomyImages = computed(() =>
  Object.entries(anatomyImageMap.value)
    .map(([key, url]) => ({ key, url: anatomyImageUrl(url) }))
    .filter((x) => !!x.url)
)

/** 整理报告 / 待确认队列：只统计整理计划，不要把普通上传中的文档算成“整理记录”。 */
const organizeReport = computed(() => {
  const plans = organizePlans.value || []
  const pendingPlans = plans.filter((p: any) => p.status === 'ready')
  const failedPlans = plans.filter((p: any) => p.status === 'failed')
  return {
    total: plans.length,
    ready: plans.filter((p: any) => p.status === 'applied').length,
    pending: pendingPlans.length,
    failed: failedPlans.length,
    pendingFiles: [...pendingPlans, ...failedPlans]
  }
})

/** 当前资料夹的图片墙：把所有文档的 imageMap 摊平成资产卡 */
const kbImages = computed(() => {
  const out: Array<{ url: string; rawUrl: string; docName: string; seq: number; assetKey: string }> = []
  for (const doc of activeKb.value?.files || []) {
    for (const [seq, url] of Object.entries(doc.imageMap || {})) {
      const raw = String(url || '')
      const full = anatomyImageUrl(raw)
      if (full) {
        out.push({
          url: full,
          rawUrl: raw,
          docName: doc.fileName,
          seq: Number(seq) + 1,
          assetKey: `doc:${doc.docId}:${seq}`
        })
      }
    }
  }
  // 聊天里直接粘贴/上传的图片：已由 chat_upload_image 持久化，这里只展示
  standaloneImages.value.forEach((img, idx) => {
    const raw = String(img.url || '')
    const full = anatomyImageUrl(raw)
    if (full) {
      out.push({
        url: full,
        rawUrl: raw,
        docName: '聊天图片',
        seq: idx + 1,
        assetKey: `chat:${img.imageId}`
      })
    }
  })
  return out
})

/** 把结构树压成带层级的列表；80 个节点后截断，避免侧栏无限长 */
const anatomyOutlineItems = computed(() => {
  const out: Array<{ name: string; level: number }> = []
  const walk = (node: any, level: number) => {
    if (!node || out.length >= 80) return
    out.push({ name: String(node.name || '未命名'), level })
    for (const child of node.children || []) walk(child, level + 1)
  }
  if (anatomyTree.value) walk(anatomyTree.value, 0)
  return out
})

/** 题库类文档：没有章节标题时，按题型给一个可读的结构摘要 */
const anatomyQuestionGroups = computed(() => {
  const text = anatomyContent.value
  if (!text) return []
  const re = /^\s*(\d+)[.、]\s*[［\[]?(单选题|多选题|填空题|简答题|判断题|选择题|计算题|论述题)[\]\]]?/gm
  const groups = new Map<string, { name: string; count: number; first: number }>()
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const name = m[2]
    const no = Number(m[1])
    const item = groups.get(name)
    if (item) {
      item.count += 1
    } else {
      groups.set(name, { name, count: 1, first: no })
    }
  }
  return [...groups.values()]
})

/**
 * 按“正文字符偏移”滚动，而不是按 scrollHeight 比例。
 * 图片高度不可预测，比例法会被图片挤偏；DOM 段落锚点不会。
 */
function scrollAnatomyToOffset(offset: number): boolean {
  const content = document.querySelector('.kbp-anatomy__content-inner') as HTMLElement | null
  if (!content) return false
  const blocks = [...content.querySelectorAll<HTMLElement>('[data-raw-start]')]
  if (!blocks.length) return false
  const targetOffset = Math.max(0, Math.min(anatomyContent.value.length, Number(offset) || 0))
  anatomyScrollTargetOffset.value = targetOffset
  let target = blocks.find((block) => {
    const start = Number(block.dataset.rawStart || 0)
    const end = Number(block.dataset.rawEnd || start)
    return targetOffset >= start && targetOffset < end
  })
  if (!target) target = blocks[blocks.length - 1]
  const top = target.getBoundingClientRect().top - content.getBoundingClientRect().top + content.scrollTop
  content.scrollTop = Math.max(0, top - content.clientHeight * 0.18)
  return true
}

function onAnatomyImageLoad() {
  const offset = anatomyScrollTargetOffset.value
  if (offset == null) return
  // 图片加载会改变它上方内容的高度；加载完成后再按同一个字符锚点校正一次。
  nextTick(() => scrollAnatomyToOffset(offset))
}

function jumpToQuestionGroup(group: { first: number }) {
  const match = new RegExp(`^\\s*${Number(group.first)}[.、]`, 'm').exec(anatomyContent.value)
  if (!match) return
  scrollAnatomyToOffset(match.index)
}

function isAnatomyExcluded(start: number, end: number): boolean {
  return anatomyExcludedRanges.value.some((range: any) => {
    const rs = Number(range?.start)
    const re = Number(range?.end)
    return Number.isFinite(rs) && Number.isFinite(re) && rs < end && re > start
  })
}

function blankExcludedText(text: string, start: number, end: number): string {
  if (!anatomyExcludedRanges.value.length) return text
  let out = text
  for (const range of anatomyExcludedRanges.value) {
    const rs = Number(range?.start)
    const re = Number(range?.end)
    if (!Number.isFinite(rs) || !Number.isFinite(re) || re <= start || rs >= end) continue
    const from = Math.max(0, rs - start)
    const to = Math.min(out.length, re - start)
    if (to > from) out = out.slice(0, from) + ' '.repeat(to - from) + out.slice(to)
  }
  return out
}

/** 把正文里的【图N】拆成图文交错段；每段带原始字符偏移，供锚点定位 */
const anatomySegments = computed(() => {
  const text = anatomyContent.value
  if (!text) return []
  if (!/【图\d+】/.test(text)) {
    return [{ type: 'text', text: blankExcludedText(text, 0, text.length), start: 0, end: text.length }]
  }
  const segs: any[] = []
  const re = /【图(\d+)】/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      segs.push({
        type: 'text',
        text: blankExcludedText(text.slice(last, m.index), last, m.index),
        start: last,
        end: m.index
      })
    }
    if (isAnatomyExcluded(m.index, m.index + m[0].length)) {
      last = m.index + m[0].length
      continue
    }
    const url = anatomyImageMap.value[m[1]] || ''
    if (url) {
      segs.push({ type: 'image', url: anatomyImageUrl(url), start: m.index, end: m.index + m[0].length })
    } else {
      segs.push({ type: 'text', text: m[0], start: m.index, end: m.index + m[0].length })
    }
    last = m.index + m[0].length
  }
  if (last < text.length) {
    segs.push({
      type: 'text',
      text: blankExcludedText(text.slice(last), last, text.length),
      start: last,
      end: text.length
    })
  }
  return segs
})

/* 粘贴文本 */
const importing = ref(false)
const textImportVisible = ref(false)
const textImportContent = ref('')
const textImportFileName = ref('')

/* ===================== 加载 ===================== */

async function load(keepActive = true) {
  loading.value = true
  loadFailed.value = false
  try {
    const res: any = await getWorkspaceOverview()
    if (res.code === 200 && res.data) {
      kbs.value = res.data.knowledgeBases || []
      Object.assign(stats, res.data.stats || {})

      // 从聊天跳转过来时优先打开指定资料夹；否则保持当前选中的库，库被删了就退回默认库。
      const requestedKbId = Number(route.query.kbId || 0)
      if (requestedKbId && kbs.value.some((k) => Number(k.kbId) === requestedKbId)) {
        activeKbId.value = requestedKbId
      } else if (!keepActive || !kbs.value.some((k) => k.kbId === activeKbId.value)) {
        activeKbId.value = res.data.defaultKbId || kbs.value[0]?.kbId || null
      }
      // 文档被删/换库后，清掉已经不存在的批量选择
      const aliveIds = new Set(
        ((kbs.value.find((k: any) => k.kbId === activeKbId.value)?.files || []) as any[]).map((d: any) => Number(d.docId))
      )
      selectedDocIds.value = selectedDocIds.value.filter((id) => aliveIds.has(id))
      await applyJumpQuery()
    } else {
      loadFailed.value = true
    }
  } catch (e: any) {
    loadFailed.value = true
    console.warn('[kb] 加载资料失败', e)
  } finally {
    loading.value = false
  }
}

/**
 * 处理 /front/workspace?kbId=xx&docId=xx&open=1 的聊天跳转。
 * 不能只 router.push 到资料首页：用户需要的是「这份文档」，不是默认资料夹。
 */
async function applyJumpQuery() {
  if (jumpQueryApplied.value) return
  const docId = Number(route.query.docId || 0)
  if (!docId) {
    jumpQueryApplied.value = true
    return
  }
  jumpQueryApplied.value = true
  await nextTick()
  const doc = activeKb.value?.files?.find((d: any) => Number(d.docId) === docId)
  if (!doc) return
  jumpTargetDocId.value = docId
  await nextTick()
  const el = document.querySelector<HTMLElement>(`.kbp-doc[data-doc-id="${docId}"]`)
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  if (String(route.query.open || '') === '1') {
    showAnatomy(doc)
  }
}

watch(
  () => [route.query.kbId, route.query.docId, route.query.open],
  () => {
    jumpQueryApplied.value = false
    jumpTargetDocId.value = null
    load(false)
  }
)

async function loadStandaloneImages() {
  try {
    const res: any = await listWorkspaceStandaloneImages(100)
    if (res.code === 200 && Array.isArray(res.data)) {
      standaloneImages.value = res.data
    }
  } catch (e: any) {
    console.warn('[我的资料] 加载聊天图片失败', e)
  }
}

async function loadAssetUsage() {
  try {
    const res: any = await getAssetUsageSummary()
    if (res.code === 200 && res.data) assetUsage.value = res.data
  } catch (e: any) {
    console.warn('[我的资料] 加载图片用途失败', e)
  }
}

async function refreshOrganizePlans(silent = false) {
  if (!silent) organizePlansLoading.value = true
  try {
    const res: any = await listWorkspaceOrganizePlans(40)
    organizePlans.value = res.code === 200 ? (res.data || []) : []
  } catch (e: any) {
    if (!silent) ElMessage.error('读取整理记录失败：' + (e?.message || e))
  } finally {
    if (!silent) organizePlansLoading.value = false
  }
}

async function openOrganizeReport() {
  organizeReportVisible.value = true
  await refreshOrganizePlans()
}

async function deleteOrganizeRecord(plan: any) {
  try {
    await ElMessageBox.confirm(
      `删除「${plan.docName}」的这条整理记录？只删除记录，不会回退已经应用的文档变更。`,
      '删除整理记录',
      {
        confirmButtonText: '删除记录',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  try {
    const res: any = await deleteWorkspaceOrganizeRecord(Number(plan.planId))
    if (res.code !== 200) {
      ElMessage.error(res.msg || '删除失败')
      return
    }
    ElMessage.success('整理记录已删除')
    await openOrganizeReport()
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message || e))
  }
}

function organizePlanCount(status: string) {
  return organizePlans.value.filter((p) => p.status === status).length
}

function planStatusText(status: string) {
  return ({
    running: '进行中',
    ready: '待确认',
    applied: '已应用',
    rejected: '未通过',
    failed: '失败',
    rolled_back: '已回退'
  } as Record<string, string>)[status] || status
}

function planStatusType(status: string) {
  if (status === 'applied') return 'success'
  if (status === 'failed' || status === 'rejected') return 'danger'
  if (status === 'ready') return 'warning'
  return 'info'
}

async function openOrganizePlan(plan: any) {
  try {
    const res: any = plan.legacy
      ? await getWorkspaceOrganizeRecord(Number(plan.planId))
      : await getWorkspaceOrganizePlan(plan.planId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '读取整理计划失败')
      return
    }
    const data = res.data || {}
    organizeReportVisible.value = false
    organizeVisible.value = true
    organizeRecordView.value = true
    organizeMode.value = data.mode === 'deep' ? 'deep' : 'quick'
    // 旧版日志只有字段快照，不能执行新的回退操作；这里只读展示。
    organizeApplied.value = data.status === 'applied' && !plan.legacy
    organizeError.value = data.error || ''
    organizePlanId.value = data.planId || plan.planId
    organizeStatus.value = data.status || plan.status
    organizeStage.value = data.stage || plan.stage || 'done'
    organizeProgress.value = Number(data.progress || 100)
    let visibleChanges = data.changes || []
    let visibleSuggestions = data.suggestions || []
    // 已应用的记录只展示用户当时确认过的项目，而不是把整份预览再播一遍。
    if (data.status === 'applied' && Array.isArray(data.appliedChangeIds)) {
      const appliedIds = new Set(data.appliedChangeIds)
      visibleChanges = visibleChanges.filter((change: any) => appliedIds.has(change.id) || change.field === 'facets')
      const appliedExclusionIds = new Set(data.appliedExclusionIds || [])
      visibleSuggestions = visibleSuggestions.filter((suggestion: any) => appliedExclusionIds.has(suggestion.id))
    }
    organizeChanges.value = visibleChanges
    organizeSuggestions.value = visibleSuggestions
    organizeElapsed.value = 0
    organizeDocTarget.value = activeKb.value?.files.find((d: any) => Number(d.docId) === Number(data.docId)) || null
  } catch (e: any) {
    ElMessage.error('读取整理计划失败：' + (e?.message || e))
  }
}

async function openEditor(doc: any) {
  if (!doc?.docId) return
  editorDoc.value = doc
  editorPreview.value = false
  editorContent.value = ''
  editorHtml.value = ''
  editorImageMap.value = {}
  editorVisible.value = true
  editorLoading.value = true
  try {
    const res: any = await getDocumentContent(doc.docId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '读取正文失败')
      editorVisible.value = false
      return
    }
    editorContent.value = res.data?.content || ''
    editorImageMap.value = res.data?.imageMap || {}
    editorHtml.value = markdownToEditorHtml(editorContent.value)
  } catch (e: any) {
    editorVisible.value = false
    ElMessage.error('读取正文失败：' + (e?.message || e))
  } finally {
    editorLoading.value = false
  }
}

async function onDocumentVersionRestored() {
  const doc = editorDoc.value
  if (!doc?.docId) return
  versionsVisible.value = false
  editorVisible.value = false
  reprocessTask.active = true
  reprocessTask.docId = doc.docId
  reprocessTask.fileName = doc.fileName
  reprocessTask.statusText = '历史版本已恢复，正在重新解析…'
  reprocessTask.percent = 10
  reprocessTask.error = ''
  reprocessElapsed.value = 0
  stopReprocessClock()
  reprocessTimer = setInterval(() => {
    reprocessElapsed.value += 1
  }, 1000)
  try {
    await load()
    const result = await pollReprocess(doc.docId)
    reprocessTask.active = false
    stopReprocessClock()
    await load()
    if (result.ok) {
      ElMessage.success(`「${doc.fileName}」已恢复，并重新建立索引`)
    } else {
      ElMessage.error(`历史版本已恢复，但重新解析失败：${result.message}`)
    }
  } catch (e: any) {
    reprocessTask.active = false
    stopReprocessClock()
    ElMessage.error('恢复后重新解析失败：' + (e?.message || e))
  }
}

async function saveEditor() {
  const doc = editorDoc.value
  if (!doc?.docId) return
  const markdown = editorMarkdown.value
  if (!markdown.trim()) {
    ElMessage.warning('正文不能为空')
    return
  }
  editorSaving.value = true
  try {
    const res: any = await updateDocumentContent(doc.docId, markdown)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '保存失败')
      return
    }
    editorVisible.value = false
    reprocessTask.active = true
    reprocessTask.docId = doc.docId
    reprocessTask.fileName = doc.fileName
    reprocessTask.statusText = '正文已保存，正在重新解析…'
    reprocessTask.percent = 10
    reprocessTask.error = ''
    reprocessElapsed.value = 0
    stopReprocessClock()
    reprocessTimer = setInterval(() => {
      reprocessElapsed.value += 1
    }, 1000)
    await load()
    const result = await pollReprocess(doc.docId)
    reprocessTask.active = false
    stopReprocessClock()
    await load()
    if (result.ok) {
      ElMessage.success(
        `「${doc.fileName}」已保存并重新向量化${result.chunkCount ? `，共 ${result.chunkCount} 个分块` : ''}`
      )
    } else {
      ElMessage.error(`「${doc.fileName}」保存成功，但重新解析失败：${result.message}`)
    }
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.message || e))
  } finally {
    editorSaving.value = false
  }
}

function openMicroCourse(doc: any) {
  router.push({ path: '/front/microCourse', query: { docId: String(doc.docId) } })
}

function handleDocMore(doc: any, command: string) {
  if (command === 'micro') {
    openMicroCourse(doc)
    return
  }
  if (command === 'share') return openDocShare(doc)
  if (command === 'markdown' || command === 'docx') return exportDoc(doc, command)
  if (command === 'reprocess') return reprocess(doc)
  if (command === 'delete') return removeDoc(doc)
}

async function exportDoc(doc: any, format: 'markdown' | 'docx', content?: string) {
  if (!doc?.docId) return
  try {
    const blob: any = await exportDocument(doc.docId, format, content)
    if (!(blob instanceof Blob) || blob.size === 0 || !blobValidate(blob)) {
      let msg = '导出失败'
      try {
        const parsed = JSON.parse(await blob.text())
        msg = parsed?.msg || parsed?.message || msg
      } catch { /* 非 JSON 错误体 */ }
      ElMessage.error(msg)
      return
    }
    const stem = String(doc.fileName || '资料').replace(/\.[^.]+$/, '')
    saveAs(new Blob([blob]), `${stem}.${format === 'docx' ? 'docx' : 'md'}`)
    ElMessage.success(`正在导出${format === 'docx' ? ' Word' : ' Markdown'}`)
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || e))
  }
}

function exportCurrent(format: 'markdown' | 'docx') {
  if (editorDoc.value) {
    exportDoc(editorDoc.value, format, editorMarkdown.value)
  }
}

function startOrganize(doc: any) {
  if (!doc?.docId) return
  ElMessageBox.confirm(
    `智能整理会分析「${doc.fileName}」的正文、章节和图片，生成预览方案。\n不会自动修改正文，只有你确认后才应用。`,
    '开始智能整理',
    {
      confirmButtonText: '开始分析',
      cancelButtonText: '取消',
      type: 'info'
    }
  )
    .then(() => {
      organizeDocTarget.value = doc
      organizeMode.value = 'deep'
      beginOrganize(doc, 'deep')
    })
    .catch(() => {
      // 用户取消，不启动任何任务
    })
}

function startOrganizeClock() {
  stopOrganizeClock()
  organizeStartedAt = Date.now()
  organizeElapsed.value = 0
  organizeClock = setInterval(() => {
    organizeElapsed.value = (Date.now() - organizeStartedAt) / 1000
  }, 300)
}

function stopOrganizeClock() {
  if (organizeClock) {
    clearInterval(organizeClock)
    organizeClock = null
  }
  if (organizePoll) {
    clearTimeout(organizePoll)
    organizePoll = null
  }
}

function applyPlanPayload(data: any) {
  organizePlanId.value = Number(data.planId || 0) || null
  organizeStatus.value = data.status || 'running'
  organizeStage.value = data.stage || 'starting'
  organizeProgress.value = Number(data.progress || 0)
  organizeChanges.value = data.changes || []
  organizeSuggestions.value = data.suggestions || []
  organizeError.value = data.error || ''
  if (organizeTask.active) {
    organizeTask.statusText = data.stage === 'failed' ? '整理失败' : '正在分析文档'
    organizeTask.percent = Math.max(4, Number(data.progress || organizeTask.percent || 4))
  }
}

async function beginOrganize(doc: any, mode: 'deep') {
  stopOrganizeClock()
  organizeVisible.value = true
  organizeMode.value = 'deep'
  organizeStatus.value = 'starting'
  organizeStage.value = 'starting'
  organizeProgress.value = 0
  organizeChanges.value = []
  organizeSuggestions.value = []
  organizeError.value = ''
  organizeApplied.value = false
  organizeRecordView.value = false
  organizePlanId.value = null
  organizeTask.active = true
  organizeTask.docId = doc.docId
  organizeTask.fileName = doc.fileName
  organizeTask.statusText = '正在提交整理任务…'
  organizeTask.percent = 4
  startOrganizeClock()
  try {
    const res: any = await previewWorkspaceOrganize({
      docId: doc.docId,
      mode,
      options: { ...deepOrganizeOptions }
    })
    if (res.code !== 200) {
      organizeStatus.value = 'failed'
      organizeError.value = res.msg || '整理失败'
      organizeTask.active = false
      stopOrganizeClock()
      return
    }
    applyPlanPayload(res.data || {})
    if (organizeStatus.value === 'ready') {
      organizeTask.active = false
      stopOrganizeClock()
      return
    }
    pollOrganizePlan()
  } catch (e: any) {
    organizeStatus.value = 'failed'
    organizeError.value = e?.message || String(e)
    organizeTask.active = false
    stopOrganizeClock()
  }
}

async function pollOrganizePlan() {
  const planId = organizePlanId.value
  if (!planId) return
  try {
    const res: any = await getWorkspaceOrganizePlan(planId)
    if (res.code !== 200) {
      organizeStatus.value = 'failed'
      organizeError.value = res.msg || '读取整理计划失败'
      stopOrganizeClock()
      return
    }
    applyPlanPayload(res.data || {})
    if (organizeStatus.value === 'ready' || organizeStatus.value === 'failed') {
      organizeTask.active = false
      stopOrganizeClock()
      return
    }
    organizePoll = setTimeout(pollOrganizePlan, 600)
  } catch (e: any) {
    organizeStatus.value = 'failed'
    organizeError.value = e?.message || String(e)
    organizeTask.active = false
    stopOrganizeClock()
  }
}

async function applyOrganizePreview(changeIds: string[], exclusionIds: string[]) {
  if (!organizePlanId.value) return
  try {
    const res: any = await applyWorkspaceOrganize({
      planId: organizePlanId.value,
      changeIds,
      exclusionIds
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '应用整理失败')
      return
    }
    organizeApplied.value = true
    organizeStatus.value = 'applied'
    organizeTask.active = false
    uploadTip.value = ''
    // 重新索引由 apply 后端统一在 BackgroundTasks 中启动，前端不能再调一次，
    // 否则同一文档会被两个流水线同时处理，状态可能一直卡在“解析中”。
    await load()
    if (res.data?.needsReindex && organizeDocTarget.value?.docId) {
      const doc = organizeDocTarget.value
      reprocessTask.active = true
      reprocessTask.docId = doc.docId
      reprocessTask.fileName = doc.fileName
      reprocessTask.statusText = '整理已应用，正在重新建立索引…'
      reprocessTask.percent = 10
      reprocessTask.error = ''
      reprocessElapsed.value = 0
      stopReprocessClock()
      reprocessTimer = setInterval(() => { reprocessElapsed.value += 1 }, 1000)
      const result = await pollReprocess(doc.docId)
      reprocessTask.active = false
      stopReprocessClock()
      await load()
      ElMessage.success(result.ok
        ? '整理已应用，索引已重建完成'
        : '整理已应用，但索引重建失败：' + result.message)
    } else {
      ElMessage.success('整理已应用')
    }
  } catch (e: any) {
    ElMessage.error('应用整理失败：' + (e?.message || e))
  }
}

function freshOrganizeDoc(): any {
  const target = organizeDocTarget.value
  if (!target?.docId) return null
  return activeKb.value?.files.find((d: any) => Number(d.docId) === Number(target.docId)) || target
}

function rerunOrganize() {
  const doc = freshOrganizeDoc()
  if (!doc) return
  beginOrganize(doc, 'deep')
}

/** 整理应用后点「复检」：关掉手术台，重新打开同一份资料的体检报告 */
function recheckOrganize() {
  const doc = freshOrganizeDoc()
  if (!doc?.docId) return
  organizeVisible.value = false
  showHealth(doc)
}

async function rollbackOrganizePreview() {
  if (!organizePlanId.value) return
  try {
    const res: any = await rollbackWorkspacePlan(organizePlanId.value)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '回退失败')
      return
    }
    organizeApplied.value = false
    organizeStatus.value = 'rolled_back'
    uploadTip.value = ''
    // 回退同样由后端 BackgroundTasks 统一重建索引。
    await load()
    if (res.data?.needsReindex && organizeDocTarget.value?.docId) {
      const doc = organizeDocTarget.value
      reprocessTask.active = true
      reprocessTask.docId = doc.docId
      reprocessTask.fileName = doc.fileName
      reprocessTask.statusText = '回退已生效，正在重新建立索引…'
      reprocessTask.percent = 10
      reprocessTask.error = ''
      reprocessElapsed.value = 0
      stopReprocessClock()
      reprocessTimer = setInterval(() => { reprocessElapsed.value += 1 }, 1000)
      const result = await pollReprocess(doc.docId)
      reprocessTask.active = false
      stopReprocessClock()
      await load()
      ElMessage.success(result.ok ? '已回退本次整理，索引已重建' : '已回退，但索引重建失败：' + result.message)
    } else {
      ElMessage.success('已回退本次整理')
    }
  } catch (e: any) {
    ElMessage.error('回退失败：' + (e?.message || e))
  }
}

function facetText(facets: any): string {
  if (!facets || typeof facets !== 'object') return '—'
  const parts = []
  if (facets.wordCount) parts.push(`${facets.wordCount} 字`)
  if (facets.formulaCount) parts.push(`${facets.formulaCount} 公式`)
  if (facets.imageCount) parts.push(`${facets.imageCount} 图片`)
  if (facets.tableCount) parts.push(`${facets.tableCount} 表格`)
  return parts.length ? parts.join(' / ') : '—'
}

function openQuestionPicker(img: any) {
  questionPickerImage.value = img
  questionKeyword.value = ''
  questionBankFilter.value = null
  questionPage.value = 1
  questionPickerVisible.value = true
  void loadQuestionBanks()
  loadQuestionPicker(1)
}

async function loadQuestionBanks() {
  try {
    const res: any = await listMyQuestionBank()
    questionBanks.value = res.code === 200 && Array.isArray(res.data) ? res.data : []
  } catch {
    questionBanks.value = []
  }
}

async function loadQuestionPicker(page = 1) {
  questionPage.value = page
  questionPickerLoading.value = true
  try {
    const params: any = { pageNum: page, pageSize: QUESTION_PAGE_SIZE, status: 0, ownedOnly: true }
    if (questionKeyword.value.trim()) params.keyword = questionKeyword.value.trim()
    if (questionBankFilter.value) params.bankId = questionBankFilter.value
    const res: any = await listQuestionMain(params)
    questionRows.value = res.rows || []
    questionTotal.value = Number(res.total || 0)
  } catch (e: any) {
    ElMessage.error('加载题目失败：' + (e?.message || e))
  } finally {
    questionPickerLoading.value = false
  }
}

/** 把图片按 Markdown 追加到题目解析（默认）或题干；写成功后才记录用途 */
async function insertImageIntoQuestion(row: any, field: 'questionAnalysis' | 'questionText' = 'questionAnalysis') {
  const img = questionPickerImage.value
  if (!img || !row?.id) return
  questionInsertingId.value = row.id
  try {
    const detailRes: any = await getQuestionMain(row.id)
    if (detailRes.code !== 200 || !detailRes.data) {
      ElMessage.error(detailRes.msg || '读取题目失败')
      return
    }
    const q = detailRes.data
    const old = String(q[field] || '')
    const alt = `${img.docName || '资料'}·图${img.seq}`
    const markdown = `![${alt}](${img.rawUrl || img.url})`
    const next = old ? `${old}\n\n${markdown}` : markdown

    const upd: any = await updateQuestionMain({ ...q, [field]: next })
    if (upd.code !== 200) {
      ElMessage.error(upd.msg || '写入题目失败')
      return
    }
    const usage: any = await recordAssetUsage({
      assetKey: img.assetKey,
      assetUrl: img.rawUrl || img.url,
      targetType: 'question',
      targetId: row.id
    })
    if (usage.code === 200) {
      await loadAssetUsage()
    }
    await recordAssetReference(img, 'question', row.id)
    ElMessage.success('已插入题目解析')
  } catch (e: any) {
    ElMessage.error('插入题目失败：' + (e?.message || e))
  } finally {
    questionInsertingId.value = null
  }
}

function openNotePicker(img: any) {
  notePickerImage.value = img
  noteKeyword.value = ''
  notePage.value = 1
  notePickerVisible.value = true
  loadNotePicker(1)
}

async function loadNotePicker(page = 1) {
  notePage.value = page
  notePickerLoading.value = true
  try {
    const params: any = {
      pageNum: page,
      pageSize: NOTE_PAGE_SIZE,
      userId: userStore.id
    }
    if (noteKeyword.value.trim()) params.title = noteKeyword.value.trim()
    const res: any = await listNote(params)
    noteRows.value = res.rows || []
    noteTotal.value = Number(res.total || 0)
  } catch (e: any) {
    ElMessage.error('加载笔记失败：' + (e?.message || e))
  } finally {
    notePickerLoading.value = false
  }
}

async function insertImageIntoNote(row: any) {
  const img = notePickerImage.value
  if (!img || !row?.id) return
  noteInsertingId.value = row.id
  try {
    const detailRes: any = await getNote(row.id)
    if (detailRes.code !== 200 || !detailRes.data) {
      ElMessage.error(detailRes.msg || '读取笔记失败')
      return
    }
    const note = detailRes.data
    const alt = `${img.docName || '资料'}·图${img.seq}`
    const markdown = `![${alt}](${img.rawUrl || img.url})`
    const oldMd = String(note.markdownContent || note.content || '')
    const oldHtml = String(note.content || '')
    const nextMd = oldMd ? `${oldMd}\n\n${markdown}` : markdown
    const nextHtml = oldHtml
      ? `${oldHtml}\n<p><img src="${img.rawUrl || img.url}" alt="${alt}" /></p>`
      : `<p><img src="${img.rawUrl || img.url}" alt="${alt}" /></p>`

    const upd: any = await updateNote({ id: row.id, markdownContent: nextMd, content: nextHtml })
    if (upd.code !== 200) {
      ElMessage.error(upd.msg || '写入笔记失败')
      return
    }
    const usage: any = await recordAssetUsage({
      assetKey: img.assetKey,
      assetUrl: img.rawUrl || img.url,
      targetType: 'note',
      targetId: row.id
    })
    if (usage.code === 200) {
      await loadAssetUsage()
    }
    await recordAssetReference(img, 'note', row.id)
    ElMessage.success('已加入笔记')
  } catch (e: any) {
    ElMessage.error('加入笔记失败：' + (e?.message || e))
  } finally {
    noteInsertingId.value = null
  }
}

/** 图片插入题目/笔记后同时写统一引用；失败不影响主操作，且不伪造成功。 */
async function recordAssetReference(img: any, targetType: 'note' | 'question', targetId: number) {
  const key = String(img?.assetKey || '')
  const parts = key.split(':')
  if (parts.length < 2) return
  try {
    if (parts[0] === 'doc') {
      await createContentReference({
        sourceType: 'document_image',
        sourceId: Number(parts[1]),
        sourceSubId: parts[2],
        targetType,
        targetId,
        quote: String(img.sectionTitle || img.caption || '').slice(0, 800)
      })
    } else if (parts[0] === 'chat') {
      await createContentReference({
        sourceType: 'chat_image',
        sourceId: Number(parts[1]),
        targetType,
        targetId,
        quote: String(img.caption || '').slice(0, 800)
      })
    }
  } catch {
    // 引用账本是附加价值：主插入已成功时，不能因为引用失败让用户以为插入失败。
  }
}

function findDocRecord(docId: number) {
  for (const kb of kbs.value) {
    const found = (kb.files || []).find((doc: any) => Number(doc.docId) === Number(docId))
    if (found) return found
  }
  const fromActive = (activeKb.value?.files || []).find((doc: any) => Number(doc.docId) === Number(docId))
  return fromActive || null
}

function onGalleryUseImage(img: any) {
  if (!img) return
  if (img.target === 'question') openQuestionPicker(img)
  else openNotePicker(img)
}

function onGalleryLocate(payload: { docId: number; offset: number; targetText?: string }) {
  const doc = findDocRecord(payload.docId)
  if (!doc) {
    ElMessage.warning('没有找到这张图对应的资料，可能已经被移动或删除')
    return
  }
  showAnatomy(doc, { offset: payload.offset, targetText: payload.targetText || '' })
}

function onMapOpenDoc(payload: { docId: number; offset?: number; targetText?: string }) {
  const doc = findDocRecord(payload.docId)
  if (!doc) {
    ElMessage.warning('没有找到这份资料，可能已经被移动或删除')
    return
  }
  if (payload.offset != null) {
    showAnatomy(doc, { offset: payload.offset, targetText: payload.targetText || '' })
  } else {
    showHealth(doc)
  }
}

function selectKb(kbId: number) {
  if (activeKbId.value === kbId) return
  activeKbId.value = kbId
  selectedDocIds.value = []
  // 换库时清掉上一个库的检索结果，否则会张冠李戴
  tryHits.value = []
  tryPage.value = 1
  tried.value = false
  tryQuery.value = ''
}

function openShare(kb: any) {
  closeKbMenu()
  shareKbId.value = Number(kb?.kbId) || null
  shareDialogVisible.value = true
}

function openKbMenu(event: MouseEvent, kb: any) {
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const menuWidth = 188
  const menuHeight = kb?.isDefault ? 150 : 188
  const x = Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8)
  const y = Math.min(rect.bottom + 4, window.innerHeight - menuHeight - 8)
  kbMenu.kb = kb
  kbMenu.x = Math.max(8, x)
  kbMenu.y = Math.max(8, y)
  kbMenu.visible = true
}

function closeKbMenu() {
  kbMenu.visible = false
  kbMenu.kb = null
}

function onGlobalClick(event: Event) {
  closeKbMenu()
  const target = event.target as Node | null
  if (tryPanelRef.value && target && target instanceof Node && !tryPanelRef.value.contains(target)) {
    clearTryResults()
  }
}

onMounted(() => {
  document.addEventListener('click', onGlobalClick)
  window.addEventListener('scroll', onGlobalClick, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onGlobalClick)
  window.removeEventListener('scroll', onGlobalClick, true)
})

function openDocShare(doc: any) {
  shareDoc.value = { docId: Number(doc.docId), fileName: String(doc.fileName || '未命名文档') }
  docShareDialogVisible.value = true
}

function handleKbCommand(command: string, kb: any) {
  if (!kb) return
  closeKbMenu()
  if (command === 'rename') return promptRename(kb)
  if (command === 'share') return openShare(kb)
  if (command === 'toggle-disabled') return toggleDisabled(kb)
  if (command === 'delete' && !kb.isDefault) return removeKb(kb)
}

/* ===================== 知识库增删改 ===================== */

async function promptCreate() {
  try {
    const r: any = await ElMessageBox.prompt('给资料夹起个名字', '新建资料夹', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：概率论、数据结构期末',
      inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
    })
    creating.value = true
    const res: any = await createKnowledgeBase({ name: r.value.trim() })
    if (res.code === 200) {
      ElMessage.success('资料夹已创建')
      await load()
      if (res.data?.kbId) activeKbId.value = res.data.kbId
    } else {
      ElMessage.error(res.msg || '创建失败')
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('创建失败：' + (e?.message || e))
  } finally {
    creating.value = false
  }
}

async function promptRename(kb: any) {
  try {
    const r: any = await ElMessageBox.prompt('改成什么名字？', '重命名资料夹', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: kb.name,
      inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
    })
    const res: any = await updateKnowledgeBase(kb.kbId, { name: r.value.trim() })
    if (res.code === 200) {
      ElMessage.success('已重命名')
      await load()
    } else {
      ElMessage.error(res.msg || '重命名失败')
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('重命名失败：' + (e?.message || e))
  }
}

async function removeKb(kb: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${kb.name}」吗？里面的 ${kb.docCount} 份资料会一起删掉，不能恢复。`,
      '删除资料夹',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res: any = await deleteKnowledgeBase(kb.kbId)
    if (res.code === 200) {
      ElMessage.success('已删除')
      if (activeKbId.value === kb.kbId) activeKbId.value = null
      await load(false)
    } else {
      ElMessage.error(res.msg || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message || e))
  }
}

async function toggleDisabled(kb: any) {
  const next = kb.disabled === 1 ? 0 : 1
  try {
    const res: any = await updateKnowledgeBase(kb.kbId, { disabled: next })
    if (res.code === 200) {
      ElMessage.success(next === 1 ? '已屏蔽，智能体不会再检索它' : '已恢复检索')
      await load()
    } else {
      ElMessage.error(res.msg || '操作失败')
    }
  } catch (e: any) {
    if (e?.__repeatSubmit) return
    ElMessage.error('操作失败：' + (e?.message || e))
  }
}

async function toggleDocSearchable(doc: any) {
  const next = doc.disabled !== 1
  try {
    const res: any = await setDocumentSearchable(doc.docId, next)
    if (res.code === 200) {
      ElMessage.success(next ? '已恢复这份资料的检索' : '已屏蔽这份资料，智能体不会检索它')
      await load()
    } else {
      ElMessage.error(res.msg || '操作失败')
    }
  } catch (e: any) {
    if (e?.__repeatSubmit) return
    ElMessage.error('操作失败：' + (e?.message || e))
  }
}

/* ===================== 文档上传 ===================== */

function onPick() {
  fileInputRef.value?.click()
}

function onUploadCommand(command: string) {
  if (busy.value) return
  if (command === 'file') onPick()
  else if (command === 'text') openTextImport()
}

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (files.length) await uploadFiles(files)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (busy.value || !activeKb.value) return
  const list = e.dataTransfer?.files
  if (list?.length) uploadFiles(Array.from(list))
}

async function uploadFiles(list: File[]) {
  const kb = activeKb.value
  if (!kb) return
  if (!list.length || busy.value) return

  let uploadList = [...list]
  // 如果用户只选了 .md，但 Markdown 引用了本地图片，尽量在浏览器授权后
  // 从文档所在目录自动补齐图片；用户不需要自己区分哪些是图片、哪些是文档。
  const missingGroups = await missingMarkdownImageFiles(uploadList)
  if (missingGroups.length) {
    const names = [...new Set(missingGroups.flatMap((item) => item.missing))]
    if ((window as any).showDirectoryPicker) {
      try {
        const extra = await pickMissingImagesFromDirectory(names)
        if (extra.length) uploadList = [...uploadList, ...extra]
      } catch {
        // 用户取消目录授权，继续走下面的明确提示。
      }
    }
  }
  if (!(await ensureMarkdownImageFiles(uploadList))) return
  if (uploadList.length > 20) {
    ElMessage.warning('一次最多上传 20 个文件，请分批上传')
    return
  }
  const totalBytes = uploadList.reduce((sum, file) => sum + Number(file.size || 0), 0)
  if (totalBytes > 5 * 1024 * 1024) {
    ElMessage.warning(
      `本次选择 ${(totalBytes / 1024 / 1024).toFixed(1)}MB，单次上传总大小不能超过 5MB，请减少文件数量或压缩后再上传`
    )
    return
  }
  uploading.value = true
  let ok = 0
  let fail = 0
  const uploadedDocIds: number[] = []
  try {
    uploadTip.value = uploadList.length > 1 ? `正在上传 ${uploadList.length} 个文件…` : `正在上传 ${uploadList[0].name}…`
    // 多个文件一次请求；后端同时校验单文件和总大小（≤5MB）。
    const res: any = kb.isDefault
      ? await uploadToWorkspace(uploadList)
      : await uploadDocument(kb.kbId, uploadList)
    if (res.code === 200) {
      const documents = Array.isArray(res.data?.documents)
        ? res.data.documents
        : (res.data?.docId ? [res.data] : [])
      const failed = Array.isArray(res.data?.failed) ? res.data.failed : []
      ok = documents.length
      fail = failed.length
      for (const item of failed) {
        ElMessage.error(`${item.fileName || '文件'}：${item.error || '上传失败'}`)
      }
      for (const item of documents) {
        const uploadedId = Number(item.docId || 0)
        if (uploadedId) uploadedDocIds.push(uploadedId)
      }
      if (!ok && res.msg) ElMessage.error(res.msg)
      const ocrCount = documents.filter((item: any) => item.ocrApplied).length
      if (ocrCount) {
        ElMessage.success(`${ocrCount} 张手写图片已完成 OCR 校对`)
      }
      // 同名资料默认生成新版本：把「已更新为第 N 版」明确告诉用户，
      // 避免误以为又出现了一份重名文件。
      const versioned = documents.filter((item: any) => item.versioned)
      for (const item of versioned) {
        ElMessage.success(`「${item.fileName}」已更新为第 ${item.version} 版，旧版本可在编辑器「历史版本」中恢复`)
      }
      const unchanged = documents.filter((item: any) => item.unchanged)
      if (unchanged.length) {
        ElMessage.info('同名资料内容未变化，未重复创建版本')
      }
    } else {
      fail = uploadList.length
      ElMessage.error(res.msg || '上传失败')
    }
    if (ok) {
      ElMessage.success(`已上传 ${ok} 份${fail ? `，${fail} 份失败` : ''}，正在后台解析并建立索引`)
      uploadTip.value = '上传完成：正在解析、提取图片/公式并建立索引；不会自动执行智能整理，整理需要你手动点击「整理」。'
      await load()
      // 后台流水线不是瞬时的：按文档状态轮询，直到解析完成/失败，避免只刷新一次后停在旧状态。
      if (uploadedDocIds.length) pollUploadedDocuments(uploadedDocIds)
    } else {
      uploadTip.value = ''
    }
  } catch (err: any) {
    ElMessage.error('上传失败：' + (err?.message || err))
  } finally {
    uploading.value = false
  }
}

function toggleDocSelected(docId: number) {
  const id = Number(docId)
  if (!id) return
  const idx = selectedDocIds.value.indexOf(id)
  if (idx >= 0) selectedDocIds.value.splice(idx, 1)
  else selectedDocIds.value.push(id)
}

async function removeSelectedDocs() {
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
      if (res.code === 200) ok += 1
      else fail += 1
    } catch {
      fail += 1
    }
  }
  selectedDocIds.value = []
  await load()
  if (ok) ElMessage.success(`已删除 ${ok} 份资料${fail ? `，${fail} 份失败` : ''}`)
  else ElMessage.error('批量删除失败，请稍后重试')
}

async function removeDoc(doc: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${doc.fileName}」吗？`, '删除资料', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res: any = await deleteDocument(doc.docId)
    if (res.code === 200) {
      ElMessage.success('已删除')
      await load()
    } else {
      ElMessage.error(res.msg || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message || e))
  }
}

function stopReprocessClock() {
  if (reprocessTimer) {
    clearInterval(reprocessTimer)
    reprocessTimer = null
  }
}

function reprocessPercent(status: number): number {
  if (status === 1) return 10
  if (status === 2) return 32
  if (status === 3) return 68
  if (status === 5) return 100
  return 0
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollUploadedDocuments(docIds: number[]) {
  const pending = new Set(docIds.map(Number).filter(Boolean))
  let failed = 0
  try {
    // 一轮只发一个批量请求（原来 N 份资料 = N 个请求/轮，9 份就是 9 个）
    for (let i = 0; i < 90 && pending.size; i++) {
      await delay(1200)
      try {
        const res: any = await getDocumentStatusBatch([...pending])
        if (res.code === 200 && Array.isArray(res.data)) {
          for (const item of res.data) {
            const docId = Number(item.docId)
            const status = Number(item.status || 0)
            if (status === 4) {
              failed++
              pending.delete(docId)
            } else if (status === 5) {
              pending.delete(docId)
            }
          }
        }
      } catch {
        // 单轮失败不打断，下一轮继续；批量接口本身已按用户鉴权逐条校验
      }
      if (pending.size) await load()
    }
  } finally {
    await load()
    uploadTip.value = ''
    if (failed) ElMessage.error(`${failed} 份资料解析失败，可在文档行点击「更多 → 重新解析」`)
  }
}

async function pollReprocess(docId: number): Promise<{ ok: boolean; message: string; chunkCount?: number }> {
  for (let i = 0; i < 150; i++) {
    await delay(1200)
    try {
      const res: any = await getDocumentStatus(docId)
      if (res.code !== 200 || !res.data) continue
      const data = res.data
      const status = Number(data.status || 1)
      reprocessTask.statusText = data.statusText || '整理中…'
      reprocessTask.percent = reprocessPercent(status)
      if (status === 5) {
        return { ok: true, message: '已完成', chunkCount: Number(data.chunkCount || 0) }
      }
      if (status === 4) {
        return { ok: false, message: data.errorMsg || '解析或向量化失败' }
      }
    } catch {
      // 单次轮询失败不打断，继续等下一个周期
    }
  }
  return { ok: false, message: '等待超时，任务可能仍在后台运行，可稍后刷新查看' }
}

async function reprocess(doc: any) {
  if (reprocessTask.active) {
    if (reprocessTask.docId === doc.docId) {
      ElMessage.info('这份资料正在重新解析，请稍候')
    } else {
      ElMessage.warning('还有一份资料正在重新解析，等它完成后再试')
    }
    return
  }
  if (Number(doc.status) === 2) {
    ElMessage.info('这份资料正在解析/向量化中，请等状态变成「可检索」后再重新解析')
    return
  }

  try {
    await ElMessageBox.confirm(
      `重新解析「${doc.fileName}」会重新切分并向量化这段资料，期间检索可能暂时不完整。`,
      '重新解析并向量化',
      {
        confirmButtonText: '开始重新解析',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  reprocessTask.active = true
  reprocessTask.docId = doc.docId
  reprocessTask.fileName = doc.fileName
  reprocessTask.statusText = '正在提交任务…'
  reprocessTask.percent = 4
  reprocessTask.error = ''
  reprocessElapsed.value = 0
  stopReprocessClock()
  reprocessTimer = setInterval(() => {
    reprocessElapsed.value += 1
  }, 1000)

  try {
    const res: any = await reprocessDocument(doc.docId)
    if (res.code !== 200) {
      reprocessTask.active = false
      stopReprocessClock()
      ElMessage.error(res.msg || '重新处理失败')
      return
    }
    reprocessTask.statusText = res.data?.statusText || '已加入队列，等待解析…'
    reprocessTask.percent = 10
    await load()

    const result = await pollReprocess(doc.docId)
    reprocessTask.active = false
    stopReprocessClock()
    await load()
    if (result.ok) {
      ElMessage.success(
        `「${doc.fileName}」已重新解析并完成向量化${result.chunkCount ? `，共 ${result.chunkCount} 个分块` : ''}`
      )
    } else {
      ElMessage.error(`「${doc.fileName}」重新解析失败：${result.message}`)
    }
  } catch (e: any) {
    reprocessTask.active = false
    stopReprocessClock()
    ElMessage.error('重新处理失败：' + (e?.message || e))
  }
}

/**
 * 单文档刨析：结构 + 原文/图片 + 图片资产轨。
 *
 * 数据全部来自现有接口：
 *   · getDocumentContent —— raw_content + imageMap
 *   · getDocumentOutline —— outline_tree_service 生成的章节树
 *   · doc.chunkCount —— 当前文档的分块数
 *
 * 不伪造标题数/页码：拿不到就显示 0 或“无章节”。
 */
function clearAnatomyMarks(root: HTMLElement) {
  root.querySelectorAll('mark.kbp-search-mark').forEach((mark) => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent || ''), mark)
    ;(parent as Element).normalize?.()
  })
}

/** 在刨析正文的真实 DOM 上标黄；只包普通文本节点，绝不碰 KaTeX 内部 */
function applyAnatomyHighlight() {
  const roots = [
    document.querySelector('.kbp-anatomy__content-inner'),
    document.querySelector('.kbp-anatomy-fullscreen__body')
  ].filter(Boolean) as HTMLElement[]
  roots.forEach(clearAnatomyMarks)

  const phrase = anatomyHighlight.value.trim()
  if (!phrase) return
  const needle = phrase.toLowerCase()

  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    const nodes: Node[] = []
    let node: Node | null
    while ((node = walker.nextNode())) nodes.push(node)

    for (const textNode of nodes) {
      const parent = textNode.parentElement
      if (!parent || parent.closest('.katex, .katex-mathml, .katex-html, .latex-error, .kbp-search-mark')) continue
      let current: Text | null = textNode as Text
      while (current && current.nodeValue) {
        const idx = current.nodeValue.toLowerCase().indexOf(needle)
        if (idx < 0) break
        const matchNode = current.splitText(idx)
        const afterNode = matchNode.splitText(needle.length)
        const mark = document.createElement('mark')
        mark.className = 'kbp-search-mark'
        mark.textContent = matchNode.nodeValue
        matchNode.parentNode?.replaceChild(mark, matchNode)
        current = afterNode
      }
    }
  }

  const rawTarget = anatomyTargetText.value.trim()
  const target = rawTarget.replace(/【图\d+】/g, '').trim()
  const source = anatomyContent.value || ''
  let targetOffset: number | null = null
  if (source) {
    let idx = rawTarget ? source.indexOf(rawTarget) : -1
    if (idx < 0 && target) idx = source.indexOf(target)
    if (idx < 0 && target) idx = source.indexOf(target.slice(0, Math.min(80, target.length)))
    if (idx < 0 && target) idx = source.indexOf(target.slice(0, 30))
    if (idx >= 0) targetOffset = idx
  }

  // 图片会改变 scrollHeight；优先用带原始字符偏移的 DOM 段落锚点定位。
  if (targetOffset != null && scrollAnatomyToOffset(targetOffset)) return

  const totalChunks = anatomyTargetChunkCount.value || anatomyStats.chunkCount
  if (targetOffset == null && anatomyTargetChunkIndex.value != null && totalChunks > 0 && source) {
    const estimated = source.length * ((Number(anatomyTargetChunkIndex.value) + 0.5) / totalChunks)
    if (scrollAnatomyToOffset(estimated)) return
  }

  const first = document.querySelector('.kbp-anatomy mark.kbp-search-mark')
  first?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

async function openAnatomyFullscreen() {
  anatomyFullscreen.value = true
  await nextTick()
  applyAnatomyHighlight()
}

/* ===================== 资料诊疗室（体检 / 刨析 / 装配统一入口） ===================== */
function openClinic(doc: any) {
  if (!doc?.docId) return
  clinicRef.value?.open(doc, 'health')
}

function showAnatomy(doc: any, opts?: { highlight?: string; chunkId?: number; chunkIndex?: number; chunkCount?: number; targetText?: string; offset?: number }) {
  if (!doc?.docId) return
  clinicRef.value?.open(doc, 'anatomy', opts)
}

function showHealth(doc: any) {
  if (!doc?.docId) return
  clinicRef.value?.open(doc, 'health')
}

function showPrescription(doc: any) {
  if (!doc?.docId) return
  clinicRef.value?.open(doc, 'prescription')
}

function startOrganizeFromHealth(doc: any) {
  startOrganize(doc)
}

function locateHealthSection(doc: any, section: any) {
  // 用后端给出的精确字符偏移定位，excerpt 只作为兜底（空白规范化后不保证能在原文命中）。
  showAnatomy(doc, {
    offset: Number(section?.start || 0),
    targetText: String(section?.title || '')
  })
}

async function askFromHealth(doc: any, issue: any) {
  const name = String(doc?.fileName || '这份资料').replace(/\.[^.]+$/, '')
  const section = String(issue?.sectionTitle || '').trim()
  const prompt = issue?.fixAction === 'questions'
    ? `用《${name}》${section ? `的「${section}」` : '按章节'}生成一套分层练习：每个章节 3 道基础题 + 2 道变式题，并给出答案与解析。`
    : `帮我整理《${name}》并检查知识覆盖情况。`
  try {
    await router.push({
      path: '/front/agent/chat',
      state: { seedQuestion: prompt }
    })
    ElMessage.success('已把练习要求带到对话，确认后发送')
  } catch {
    ElMessage.info(prompt)
  }
}

async function showAnatomyLegacy(doc: any, opts?: { highlight?: string; chunkId?: number; chunkIndex?: number; chunkCount?: number; targetText?: string; offset?: number }) {
  anatomyVisible.value = true
  anatomyLoading.value = true
  anatomyFullscreen.value = false
  anatomyDocName.value = doc.fileName || '未命名资料'
  anatomyHighlight.value = String(opts?.highlight || '')
  anatomyTargetChunkId.value = opts?.chunkId ?? null
  anatomyTargetChunkIndex.value = opts?.chunkIndex ?? null
  anatomyTargetChunkCount.value = Number(opts?.chunkCount || doc.chunkCount || 0)
  anatomyTargetText.value = String(opts?.targetText || '')
  anatomyScrollTargetOffset.value = null
  anatomyContent.value = ''
  anatomyExcludedRanges.value = []
  anatomyImageMap.value = {}
  anatomyTree.value = null
  anatomyOutlineReason.value = ''
  anatomyStats.contentLength = 0
  anatomyStats.imageCount = 0
  anatomyStats.headingCount = 0
  anatomyStats.chunkCount = Number(opts?.chunkCount || doc.chunkCount || 0)

  try {
    const [contentRes, outlineRes] = await Promise.all([
      getDocumentContent(doc.docId),
      getDocumentOutline(doc.docId)
    ])

    if (contentRes.code === 200) {
      const data = contentRes.data || {}
      anatomyContent.value = data.content || ''
      anatomyExcludedRanges.value = data.excludedRanges || []
      anatomyImageMap.value = data.imageMap || {}
      anatomyStats.contentLength = Number(data.contentLength || anatomyContent.value.length || 0)
      anatomyStats.imageCount = Object.keys(anatomyImageMap.value).length
    }

    if (outlineRes.code === 200) {
      const data = outlineRes.data || {}
      if (data.hasOutline && data.tree) {
        anatomyTree.value = data.tree
        anatomyStats.headingCount = Number(data.totalHeadings || data.count || 0)
      } else {
        anatomyOutlineReason.value = data.reason || '这份资料没有可提取的章节结构。'
      }
    }
  } catch (e: any) {
    ElMessage.error('读取资料刨析失败：' + (e?.message || e))
  } finally {
    anatomyLoading.value = false
    await nextTick()
    applyAnatomyHighlight()
  }
}

/* ===================== 粘贴文本 ===================== */

function openTextImport() {
  if (busy.value) {
    ElMessage.warning('有导入正在进行，等它跑完')
    return
  }
  textImportContent.value = ''
  textImportFileName.value = ''
  textImportVisible.value = true
}

function resetTextImport() {
  textImportContent.value = ''
  textImportFileName.value = ''
}

async function submitTextImport() {
  const kb = activeKb.value
  if (!kb) return
  const content = textImportContent.value.trim()
  if (!content) {
    ElMessage.warning('先粘点内容进来')
    return
  }
  importing.value = true
  try {
    const res: any = await importDocumentText(
      kb.kbId,
      content,
      textImportFileName.value.trim() || '粘贴的文本'
    )
    if (res.code === 200) {
      ElMessage.success('已导入，后台正在分块')
      textImportVisible.value = false
      await load()
      setTimeout(() => load(), 4000)
    } else {
      ElMessage.error(res.msg || '导入失败')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || e))
  } finally {
    importing.value = false
  }
}

/* ===================== 试试 AI 怎么找 ===================== */

/**
 * 语义检索
 *
 * ⚠️ 必须把当前选中的库传过去（`kbIds`）。
 * 不传的话后端会搜"该用户的全部知识库"，用户明明在「数据结构」库里，
 * 却在结果里看到「cpp」库的文件 —— 那才是真正的困惑来源。
 */
async function doTry() {
  const q = tryQuery.value.trim()
  if (!q) {
    ElMessage.warning('先输入一句描述')
    return
  }
  const kb = activeKb.value
  if (!kb) return

  trying.value = true
  tried.value = false
  tryReason.value = ''
  tryHits.value = []
  tryPage.value = 1
  lowConfidence.value = false
  trySearchedQuery.value = q
  try {
    const res: any = await searchWorkspace(q, 50, [kb.kbId])
    if (res.code === 200) {
      tryHits.value = res.data.hits || []
      tryReason.value = res.data.reason || ''
      lowConfidence.value = !!res.data.lowConfidence
      tried.value = true
    } else {
      ElMessage.error(res.msg || '查找失败')
    }
  } catch (e: any) {
    ElMessage.error('查找失败：' + (e?.message || e))
  } finally {
    trying.value = false
  }
}

/** 打开命中片段：只保留一个动作——进资料刨析并高亮定位 */
function openHit(hit: any) {
  const doc = activeKb.value?.files.find((f: any) => Number(f.docId) === Number(hit.docId))
  showAnatomy(
    {
      ...(doc || {}),
      docId: hit.docId,
      fileName: hit.docName || hit.fileName || doc?.fileName || '未命名资料'
    },
    { highlight: trySearchedQuery.value, chunkIndex: hit.chunkIndex, chunkId: hit.chunkId, chunkCount: Number(doc?.chunkCount || 0), targetText: String(hit.content || '') }
  )
}

/**
 * 命中关键词高亮（与知识库面板 `KnowledgeBasePanel.highlight` 同一套做法）
 *
 * 三条要点，都是踩过的坑：
 *   1. **先转义、再插标记**。片段是文档正文，可能含尖括号甚至故意的 HTML；
 *      顺序反了就是把用户内容当代码执行（XSS）。标记 `<mark>` 由我们自己拼，
 *      正文里的 `<` `>` 已经变成实体，所以安全。
 *   2. **高亮词取「本次检索用的那个词」**（`trySearchedQuery`），不是输入框当前值 ——
 *      用户搜完再去改输入框，结果列表不该跟着乱跳。
 *   3. 正则元字符要转义，否则搜 `C++` 这种词会直接抛异常。
 */
function highlight(content: string): string {
  const escaped = String(content || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  const terms = trySearchedQuery.value.trim().split(/\s+/).filter((t) => t.length > 0)
  if (!terms.length) return escaped

  // 长词优先：「数据结构」要先于「数据」匹配，否则会被切成两段高亮
  terms.sort((a, b) => b.length - a.length)
  const pattern = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  try {
    return escaped.replace(new RegExp(`(${pattern})`, 'gi'), '<mark>$1</mark>')
  } catch {
    return escaped
  }
}

function cleanMathForSnippet(input: string): string {
  return String(input || '')
    .replace(/\$([^$]+)\$/g, (_, body) => body
      .replace(/\\overline\{([^{}]+)\}/g, '$1')
      .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '($1)/($2)')
      .replace(/\\[a-zA-Z]+\{([^{}]*)\}/g, '$1')
      .replace(/\\[a-zA-Z]+/g, '')
      .replace(/[{}]/g, ''))
    .replace(/【图\d+】/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** 搜索命中片段：优先截取用户搜索词附近，而不是永远截正文开头 */
function buildHitSnippet(content: string): string {
  const text = cleanMathForSnippet(content)
  const q = trySearchedQuery.value.trim()
  if (!text || !q) return text.slice(0, 180)
  const lower = text.toLowerCase()
  let pos = lower.indexOf(q.toLowerCase())
  if (pos < 0) {
    const first = q.split(/\s+/).find((t) => t.length > 0) || ''
    pos = first ? lower.indexOf(first.toLowerCase()) : -1
  }
  if (pos < 0) return text.slice(0, 180)
  const start = Math.max(0, pos - 46)
  const end = Math.min(text.length, pos + q.length + 110)
  return `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`
}

/* ===================== 工具 ===================== */

function docTagType(status: number) {
  if (status === 5) return 'success'
  if (status === 4) return 'danger'
  if (status === 2) return 'warning'
  return 'info'
}

onMounted(() => {
  load(false)
  loadStandaloneImages()
  loadAssetUsage()
  refreshOrganizePlans(true)
  // 布局层顶栏的 Teleport 目标在父组件挂载完成后才稳定存在。
  nextTick(() => {
    canTeleport.value = true
  })
})

onBeforeUnmount(() => {
  stopOrganizeClock()
  topbarStore.clear()
})
</script>

<style scoped lang="scss">
.kb-page {
  max-width: 1360px;
  margin: 0 auto;
  padding: 16px 24px 60px;
}

/* ---------- 全局顶栏里的工作台路由导航 ---------- */
.kbp-workspace-nav {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
}

.kbp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin: 0;
}

.kbp-head--clean {
  padding: 0 2px;
}

.kbp-crumbs {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  color: #8a91a0;
  font-size: 12px;
}

.kbp-crumbs__root {
  overflow: hidden;
  max-width: 140px;
  padding: 0;
  border: 0;
  background: none;
  color: #6b7280;
  cursor: pointer;
  font: inherit;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-crumbs__root:hover {
  color: #4f6bed;
}

.kbp-crumbs__sep {
  color: #c4c9d4;
}

.kbp-crumbs__current {
  overflow: hidden;
  max-width: 260px;
  color: #374151;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-crumbs__leaf {
  color: #4f6bed;
  font-weight: 600;
}

.kbp-head__meta {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: #9aa1af;
  font-size: 11px;
}

.kbp-head__meta i {
  color: #d1d5db;
  font-style: normal;
}

.kbp-head__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}

.kbp-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 42px;
  margin: 0;
  padding: 0 2px;
}

.kbp-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px 10px;
  border: 0;
  border-radius: 8px 8px 0 0;
  background: transparent;
  color: #7d8596;
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
  transition: color 0.15s, background 0.15s;
}

.kbp-tab:hover {
  background: #f6f8fc;
  color: #374151;
}

.kbp-tab.is-active {
  color: #4f6bed;
  font-weight: 600;
}

.kbp-tab.is-active::after {
  position: absolute;
  right: 9px;
  bottom: -1px;
  left: 9px;
  height: 2px;
  border-radius: 2px;
  background: #4f6bed;
  content: '';
}

.kbp-receive-share {
  color: var(--os-text-3, #6b7280);
  font-size: 12px;
}

.kbp-receive-share:hover {
  color: var(--os-accent, #4176e6);
}

.kbp-view-empty {
  width: 100%;
  min-height: 360px;
}

.kbp-head__title {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.kbp-head__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
  max-width: 520px;
}

.kbp-reprocess {
  margin: 0 0 16px;
  padding: 12px 16px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
}

.kbp-reprocess__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--os-text-1, #111827);
  font-size: 13px;
}

.kbp-reprocess__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #93c5fd;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: kbp-spin 0.8s linear infinite;
}

.kbp-reprocess__stage {
  color: #1d4ed8;
  font-weight: 600;
}

.kbp-reprocess__elapsed {
  margin-left: auto;
  color: var(--os-text-3, #6b7280);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.kbp-reprocess__open {
  margin-left: auto;
  padding: 0;
  border: 0;
  background: none;
  color: #1d4ed8;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.kbp-reprocess__open + .kbp-reprocess__elapsed {
  margin-left: 0;
}

.kbp-reprocess__bar {
  height: 5px;
  margin-top: 9px;
  overflow: hidden;
  border-radius: 3px;
  background: #dbeafe;
}

.kbp-reprocess__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2563eb;
  transition: width 0.35s ease;
}

.kbp-reprocess__hint {
  margin-top: 7px;
  color: #475569;
  font-size: 11.5px;
  line-height: 1.5;
}

@keyframes kbp-spin {
  to { transform: rotate(360deg); }
}

.kbp-stats {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: none;
}

.kbp-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.kbp-stat__num {
  font-size: 20px;
  font-weight: 700;
  color: var(--os-text, #111827);
  font-variant-numeric: tabular-nums;
}

.kbp-stat__label {
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-stat__divider {
  width: 1px;
  height: 26px;
  background: var(--os-border, #e5e7eb);
}

.kbp-view-switch {
  flex: none;
}

.kbp-head__actions .kbp-view-switch {
  flex: none;
}

/* ---------- 完整书架 / 图片墙 ---------- */
.kbp-shelf-page,
.kbp-image-page {
  min-height: 480px;
}

.kbp-shelf-page__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.kbp-shelf-page__head h2 {
  margin: 0 0 5px;
  font-size: 19px;
  color: var(--os-text, #111827);
}

.kbp-shelf-page__head p {
  margin: 0;
  font-size: 12.5px;
  color: var(--os-text-3, #6b7280);
}

.kbp-shelf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.kbp-shelf-card {
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-height: 150px;
  padding: 14px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 9px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.kbp-shelf-card:hover {
  border-color: var(--os-primary, #2563eb);
  box-shadow: 0 5px 18px rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}

.kbp-shelf-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--os-primary, #2563eb);
}

.kbp-shelf-card__name {
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--os-text-1, #111827);
}

.kbp-shelf-card__facets {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.kbp-shelf-card__facets span {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--os-surface-2, #f3f4f6);
  color: var(--os-text-3, #6b7280);
  font-size: 11px;
}

.kbp-shelf-card__bottom {
  margin-top: auto;
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

/* ---------- 两栏 ---------- */
/*
 * `align-items: start` 改掉（2026-10-22）：
 *   原来两栏各自按内容高度收缩，右边只有一行文档、左边只有三个库时，
 *   整块内容只占屏幕上半截，下半屏一片白 —— 用户原话「空白多用户观感差」。
 *   现在两栏**等高拉伸**，由外层给出一个随视口走的最小高度，
 *   内容少时面板也是完整的一整块，不会看着像"没加载完"。
 */
.kbp-body {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  /* 左右两栏融合成一个面板：中间只留一条分割线，不再留 18px 空白 */
  gap: 0;
  align-items: stretch;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  /* 视口高度 - 顶栏 - 页头 - 上下留白；下限定 420 避免小屏被压扁 */
  min-height: clamp(420px, calc(100vh - 260px), 720px);
}

/* ---------- 左：库列表 ---------- */
.kbp-side {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: none;
  border-right: 1px solid var(--os-border, #e5e7eb);
  border-radius: 0;
  background: transparent;
  overflow: hidden;
}

.kbp-side__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 12px 10px;
  flex: none;
  border-bottom: 1px solid var(--os-border-light, #f1f3f5);
}

.kbp-side__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.kbp-side__search {
  flex: none;
  padding: 8px 12px 4px;
}

.kbp-side__search :deep(.el-input__wrapper) {
  border-radius: 7px;
  box-shadow: 0 0 0 1px var(--os-border-soft, rgba(0, 0, 0, 0.06)) inset;
}

.kbp-kb-dropdown {
  display: block;
  width: 100%;
}

.kbp-context-menu {
  position: fixed;
  z-index: 3000;
  width: 188px;
  padding: 5px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
}

.kbp-context-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: none;
  border-radius: 7px;
  padding: 8px 10px;
  background: transparent;
  color: var(--os-text-2, #4b5563);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.kbp-context-item:hover {
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text, #0f1115);
}

.kbp-context-item.is-danger {
  color: #c45656;
}

.kbp-context-item.is-danger:hover {
  background: #fef0f0;
  color: #c45656;
}

.kbp-side__list {
  flex: 1;
  min-height: 0;
  padding: 6px;
  overflow-y: auto;
}

.kbp-side__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 36px 14px;
  text-align: center;
  color: var(--os-text-3, #9ca3af);

  p {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--os-text-2, #4b5563);
  }

  span {
    font-size: 11.5px;
    line-height: 1.5;
  }

  .el-button {
    margin-top: 4px;
  }
}

.kbp-kb {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: var(--os-bg-subtle, #fafafa);
  }

  &.is-active {
    background: var(--os-bg-active, #eef2ff);
  }

  &.is-blocked .kbp-kb__name {
    color: var(--os-text-3, #9ca3af);
  }

  &:hover .kbp-kb__ops {
    opacity: 1;
  }
}

.kbp-kb__icon {
  flex: none;
  color: var(--os-text-3, #9ca3af);

  .is-active & {
    color: var(--os-accent, #2563eb);
  }
}

.kbp-kb__main {
  flex: 1;
  min-width: 0;
}

.kbp-kb__name-row {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 5px;
}

.kbp-kb__name {
  flex: 1;
  min-width: 0;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-kb__tag {
  flex: none;
  padding: 0 5px;
  font-size: 10px;
  line-height: 15px;
  border-radius: 4px;
  background: var(--os-accent-50, #eff6ff);
  color: var(--os-accent, #2563eb);

  &.is-blocked {
    background: #fef3c7;
    color: #b45309;
  }

  &.is-share {
    background: #eef2ff;
    color: #4f46e5;
  }
}

.kbp-kb__meta {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-kb__ops {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}

.kbp-kb__op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  color: var(--os-text-3, #9ca3af);

  &:hover {
    background: var(--os-bg-hover, #f3f4f6);
    color: var(--os-text, #111827);
  }

  &.is-danger:hover {
    background: #fee2e2;
    color: #ef4444;
  }

  &.is-blocked {
    color: #d97706;
    opacity: 1;
  }
}

/* ---------- 右：文档区 ---------- */
.kbp-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 16px 18px 18px;
}

.kbp-main__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.kbp-main__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.kbp-main__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-main__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.kbp-upload-dropdown {
  display: inline-flex;
}

.kbp-upload,
.kbp-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  font-size: 13px;
  font-family: inherit;
  border-radius: 7px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }

  &.is-disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  input {
    display: none;
  }
}

/* ---------- 拖拽投放区 ---------- */
/*
 * 撑满右侧面板剩余高度（`flex:1`）。
 * 面板本身是 flex 列（见 .kbp-main），所以这里能一直长到面板底部 ——
 * 空态就用这个高度做真正的垂直居中，而不是靠一层层 padding 硬撑。
 */
.kbp-drop {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  transition: background 0.15s;

  &.is-over {
    background: var(--os-accent-50, #eff6ff);
    outline: 2px dashed var(--os-accent, #2563eb);
    outline-offset: 3px;
  }
}

.kbp-drop__mask {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  font-size: 13px;
  font-weight: 600;
  color: var(--os-accent, #2563eb);
}

.kbp-tip {
  margin-bottom: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--os-accent-50, #eff6ff);
  font-size: 12px;
  color: var(--os-accent, #2563eb);
}

.kbp-docs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  /* 不再是固定的 120px 最小高度 —— 由父级 flex 分配，空态时也铺满 */
  flex: 1;
  min-height: 0;
}

.kbp-doc {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 9px;
  border: 1px solid transparent;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-border, #e5e7eb);
    background: var(--os-bg-subtle, #fafafa);
  }

  &.is-jump-target {
    border-color: var(--os-accent, #2563eb);
    background: var(--os-accent-50, #eff6ff);
    box-shadow: 0 0 0 1px var(--os-accent-50, #eff6ff);
  }

  &:hover .kbp-doc__ops {
    opacity: 1;
  }
}

.kbp-doc__check {
  flex: none;
  display: flex;
  align-items: center;
  margin-top: 1px;
}

.kbp-doc__check :deep(.el-checkbox) {
  margin-right: 0;
}

.kbp-doc__icon {
  flex: none;
  margin-top: 2px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-doc__main {
  flex: 1;
  min-width: 0;
}

.kbp-doc__name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kbp-doc__name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-doc__meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-doc__note {
  color: var(--os-text-2, #6b7280);
}

.kbp-doc__time {
  margin-left: auto;
}

.kbp-doc__err {
  margin-top: 4px;
  font-size: 11.5px;
  color: #ef4444;
  line-height: 1.5;
}

.kbp-doc__facet {
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--os-surface-2, #f3f4f6);
  color: var(--os-text-2, #4b5563);
  font-size: 11px;
}

.kbp-doc__ops {
  display: flex;
  gap: 2px;
  flex: none;
  opacity: 0;
  transition: opacity 0.15s;
}

.kbp-doc__op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  font-family: inherit;
  color: var(--os-text-3, #9ca3af);
  cursor: pointer;

  &:hover {
    background: var(--os-bg-hover, #f3f4f6);
    color: var(--os-text, #111827);
  }

  &.kbp-doc__clinic {
    position: relative;
    width: 24px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--os-text-3, #9ca3af);

    &:hover {
      background: var(--os-bg-hover, #f3f4f6);
      color: var(--os-text, #111827);
    }

    /* 只在鼠标移上去时显示说明，平时只保留一个图标 */
    &::after {
      position: absolute;
      bottom: calc(100% + 7px);
      left: 50%;
      z-index: 30;
      padding: 4px 8px;
      border-radius: 5px;
      background: #1f2937;
      color: #fff;
      content: attr(data-tip);
      font-size: 11px;
      font-weight: 400;
      line-height: 1.3;
      opacity: 0;
      pointer-events: none;
      white-space: nowrap;
      transform: translate(-50%, 2px);
      transition: opacity 0.14s ease, transform 0.14s ease;
    }

    &:hover::after {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  &.is-danger:hover {
    background: #fee2e2;
    color: #ef4444;
  }

  &.is-busy {
    color: #2563eb;
    background: #eff6ff;
    opacity: 1;
    cursor: wait;
    animation: kbp-pulse 1.1s ease-in-out infinite;
  }

  &.is-blocked {
    color: #d97706;
    opacity: 1;
  }

  &.is-busy .os-icon {
    animation: kbp-spin 0.9s linear infinite;
  }
}

@keyframes kbp-pulse {
  50% { opacity: 0.45; }
}

.kbp-docs__empty,
.kbp-main__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--os-text-3, #9ca3af);
  text-align: center;
}

/* ---------- 通用空态零件（三处空态共用，避免各写一套） ---------- */
.kbp-empty__art {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin-bottom: 2px;
  border-radius: 16px;
  background: var(--os-bg-subtle, #fafafa);
  border: 1px solid var(--os-border-light, #f1f3f5);
  color: var(--os-text-3, #9ca3af);
}

.kbp-empty__title {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--os-text-2, #4b5563);
}

.kbp-empty__desc {
  max-width: 320px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

.kbp-empty__actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

.kbp-empty__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 14px;
  font-size: 13px;
  font-family: inherit;
  border-radius: 8px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text, #111827);
  cursor: pointer;
  transition: all 0.15s;

  &:hover:not(:disabled) {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }

  &.is-primary {
    background: var(--os-text, #111827);
    border-color: var(--os-text, #111827);
    color: #fff;

    &:hover:not(:disabled) {
      background: #000;
      border-color: #000;
      color: #fff;
    }
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.kbp-empty__formats {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 全页空态（一个知识库都没有） ---------- */
.kbp-blank {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: clamp(420px, calc(100vh - 260px), 720px);
}

.kbp-blank__box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 460px;
  padding: 44px 36px;
  text-align: center;
  border: 1px dashed var(--os-border, #e5e7eb);
  border-radius: 16px;
  background: var(--os-bg-subtle, #fafafa);
}

.kbp-blank__art {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 18px;
  background: #fff;
  border: 1px solid var(--os-border-light, #f1f3f5);
  color: var(--os-accent, #2563eb);

  /* 加载失败：换成警示色，别让"故障"看起来和"空"一模一样 */
  &.is-warn {
    color: #d97706;
    background: #fffbeb;
    border-color: #fde68a;
  }
}

.kbp-blank__title {
  margin: 2px 0 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.kbp-blank__desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text-3, #6b7280);
}

.kbp-blank__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  margin-top: 6px;
  padding: 0 18px;
  font-size: 13.5px;
  font-weight: 500;
  font-family: inherit;
  border: none;
  border-radius: 8px;
  background: var(--os-text, #111827);
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;

  &:hover:not(:disabled) {
    background: #000;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.kbp-blank__hint {
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 试试 AI 怎么找 ---------- */
.kbp-try {
  order: -1;
  position: relative;
  z-index: 20;
  margin: 0 0 10px;
  padding: 11px 14px;
  border-radius: 10px;
  background: var(--os-accent-50, #eff6ff);
  border: 1px solid var(--os-accent-100, #dbeafe);
}

.kbp-try__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.kbp-try__title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--os-text, #111827);
}

.kbp-try__hint {
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

.kbp-try__row {
  display: flex;
  gap: 10px;
}

.kbp-try__result {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  left: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: min(440px, 56vh);
  padding: 8px;
  overflow-y: auto;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.16);
}

.kbp-try__pager {
  position: sticky;
  bottom: 0;
  z-index: 1;
  display: flex;
  justify-content: flex-end;
  padding: 6px 4px 2px;
  background: #fff;
  border-top: 1px solid var(--os-border-light, #f1f3f5);
}

/* 低置信提示条：与结果并列，不遮住内容，也不当作错误红 */
.kbp-try__warn {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  font-size: 12px;
  line-height: 1.6;
  color: #92400e;

  :deep(svg) {
    flex: none;
    margin-top: 1px;
    color: #d97706;
  }
}

.kbp-try__file,
.kbp-try__hit {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 13px;
  transition: border-color 0.15s;

  &.is-best {
    border-color: var(--os-accent, #2563eb);
  }

  &:hover {
    border-color: var(--os-border, #e5e7eb);
  }
}

.kbp-try__snippet--hit {
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

.kbp-try__file-main {
  flex: 1;
  min-width: 0;
}

.kbp-try__file-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kbp-try__file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-try__kb {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--os-bg-subtle, #f3f4f6);
  color: var(--os-text-2, #6b7280);
}

/* 命中片段摘要：判断"是不是这份"的主要依据 */
.kbp-try__snippet {
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--os-text-2, #4b5563);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

/*
 * 关键词高亮（与知识库面板 `.kb-hit-body :deep(mark)` 同一套观感）
 *
 * `:deep()` 是必须的：`<mark>` 由 `v-html` 注入，不在本组件的 scoped 作用域里，
 * 不加 :deep 的话选择器根本匹配不到生成的元素。
 * 用暖黄而不是主题蓝：高亮是"标出一段文字"，不是链接/可点区域，别让人想点。
 */
.kbp-try__snippet :deep(mark),
.kbp-try__file-name :deep(mark) {
  background: #fff3c4;
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
}

.kbp-try__ops {
  display: flex;
  gap: 6px;
  flex: none;
}

.kbp-try__op {
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
  font-family: inherit;
  border-radius: 6px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: #fff;
  color: var(--os-text-2, #4b5563);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;

  &:hover {
    border-color: var(--os-accent, #2563eb);
    color: var(--os-accent, #2563eb);
  }
}

.kbp-try__rank {
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--os-bg-subtle, #f3f4f6);
  font-size: 11px;
  font-weight: 600;
  color: var(--os-text-3, #6b7280);

  .is-best & {
    background: var(--os-accent, #2563eb);
    color: #fff;
  }
}

.kbp-try__file-name {
  font-weight: 500;
  color: var(--os-text, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-try__badge {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--os-accent, #2563eb);
}

.kbp-try__empty {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--os-text-3, #6b7280);
}

.kbp-import__hint {
  margin: 0 0 10px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
}

.kbp-import__row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.kbp-import__label {
  flex: none;
  font-size: 13px;
  color: var(--os-text-2, #4b5563);
}

/* ---------- 单文档刨析 ---------- */
.kbp-anatomy {
  min-height: 420px;
}

.kbp-anatomy__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 8px;
  background: var(--os-surface-2, #f8fafc);
  color: var(--os-text-3, #6b7280);
  font-size: 12px;
}

.kbp-anatomy__stats b {
  color: var(--os-text-1, #111827);
  font-size: 15px;
}

.kbp-anatomy__grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(320px, 1.4fr) minmax(220px, 0.7fr);
  gap: 14px;
  min-height: 480px;
}

.kbp-anatomy__outline,
.kbp-anatomy__content,
.kbp-anatomy__assets {
  min-width: 0;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.kbp-anatomy__outline h4,
.kbp-anatomy__content h4,
.kbp-anatomy__assets h4 {
  margin: 0;
  padding: 10px 12px;
  border-bottom: 1px solid var(--os-border, #e5e7eb);
  font-size: 13px;
  color: var(--os-text-1, #111827);
}

.kbp-anatomy__assets h4 span {
  color: var(--os-text-3, #9ca3af);
  font-weight: 400;
}

.kbp-anatomy__outline-list {
  max-height: 540px;
  padding: 8px 0;
  overflow: auto;
}

.kbp-anatomy__question-groups {
  padding: 10px 12px;
  border-bottom: 1px solid var(--os-border, #e5e7eb);
  background: #f8fafc;
}

.kbp-anatomy__question-groups-label {
  margin-bottom: 6px;
  color: var(--os-text-3, #6b7280);
  font-size: 11px;
}

.kbp-anatomy__question-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 7px;
  border-radius: 4px;
  color: var(--os-text-2, #4b5563);
  font-size: 12.5px;
  cursor: pointer;
}

.kbp-anatomy__question-group:hover {
  background: #eff6ff;
  color: var(--os-primary, #2563eb);
}

.kbp-anatomy__question-group b {
  color: var(--os-primary, #2563eb);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.kbp-anatomy__outline-item {
  padding-top: 5px;
  padding-bottom: 5px;
  padding-right: 10px;
  border-left: 2px solid transparent;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--os-text-2, #4b5563);
  word-break: break-word;
}

.kbp-anatomy__outline-item:hover {
  border-left-color: var(--os-primary, #2563eb);
  background: var(--os-surface-2, #f8fafc);
}

.kbp-anatomy__content-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.kbp-anatomy__fullscreen {
  padding: 2px 7px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 4px;
  background: #fff;
  color: var(--os-primary, #2563eb);
  cursor: pointer;
  font-size: 11px;
}

.kbp-anatomy__fullscreen:hover {
  border-color: var(--os-primary, #2563eb);
  background: #eff6ff;
}

.kbp-anatomy-fullscreen__body {
  height: calc(100vh - 116px);
  padding: 24px max(24px, calc((100vw - 980px) / 2));
  overflow: auto;
  background: #fff;
  font-size: 15px;
  line-height: 1.8;
}

.kbp-anatomy-fullscreen__body .kbp-anatomy__inline-image {
  max-height: 75vh;
}

.kbp-anatomy-fullscreen__body .kbp-anatomy__rendered {
  font-size: 15px;
}

.kbp-anatomy__content-inner {
  max-height: 540px;
  padding: 12px;
  overflow: auto;
}

.kbp-anatomy__text {
  margin: 0 0 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text-2, #4b5563);
}

.kbp-anatomy__rendered {
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text-2, #4b5563);
}

.kbp-anatomy__rendered :deep(.latex-content) {
  font-size: inherit;
}

.kbp-anatomy__content-inner :deep(mark.kbp-search-mark),
.kbp-anatomy-fullscreen__body :deep(mark.kbp-search-mark) {
  padding: 0 2px;
  border-radius: 2px;
  background: #fff3c4;
  color: inherit;
}

.kbp-anatomy__inline-image {
  display: block;
  max-width: 100%;
  max-height: 320px;
  margin: 8px auto 12px;
  border-radius: 6px;
}

.kbp-anatomy__image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 8px;
  max-height: 540px;
  padding: 12px;
  overflow: auto;
}

.kbp-anatomy__image-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 4px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 6px;
}

.kbp-anatomy__image-card .el-image {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 4px;
  background: #f3f4f6;
}

.kbp-anatomy__image-card span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--os-text-3, #6b7280);
}

.kbp-anatomy__copy,
.kbp-image-wall__copy {
  padding: 3px 6px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 4px;
  background: #fff;
  color: var(--os-text-3, #6b7280);
  font-size: 11px;
  cursor: pointer;
}

.kbp-anatomy__copy:hover,
.kbp-image-wall__copy:hover {
  border-color: var(--os-primary, #2563eb);
  color: var(--os-primary, #2563eb);
}

.kbp-anatomy__empty {
  padding: 18px 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

/* ---------- 图片墙 ---------- */
.kbp-image-wall {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  max-height: 62vh;
  overflow: auto;
}

.kbp-image-wall__card {
  min-width: 0;
  padding: 5px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 7px;
  background: #fff;
}

.kbp-image-wall__card .el-image {
  width: 100%;
  aspect-ratio: 1.2;
  border-radius: 5px;
  background: #f3f4f6;
}

.kbp-image-wall__meta {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  padding: 5px 2px 1px;
  font-size: 11px;
  color: var(--os-text-3, #6b7280);
}

.kbp-image-wall__meta span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-image-wall__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.kbp-image-wall__copy {
  flex: 1;
  min-width: 56px;
  margin-top: 0;
}

.kbp-image-wall__used {
  flex: none;
  font-size: 10.5px;
  color: #16a34a;
}

.kbp-question-picker__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.kbp-question-picker__image {
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--os-text-3, #6b7280);
}

.kbp-question-picker__bank {
  width: 170px;
  flex: none;
}

.kbp-question-picker__bank-name {
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
}

.kbp-question-picker__text {
  font-size: 12.5px;
  color: var(--os-text-2, #4b5563);
}

.kbp-question-picker__hint {
  margin: 0 0 8px;
  font-size: 11.5px;
  color: var(--os-text-3, #9ca3af);
}

.kbp-report__stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.kbp-report__stats > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px;
  border-radius: 7px;
  background: var(--os-surface-2, #f8fafc);
}

.kbp-report__stats b {
  font-size: 20px;
  color: var(--os-text-1, #111827);
}

.kbp-report__stats span {
  font-size: 11px;
  color: var(--os-text-3, #6b7280);
}

.kbp-report__list {
  max-height: 360px;
  overflow: auto;
  border-top: 1px solid var(--os-border, #e5e7eb);
}

.kbp-report__row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 2px;
  border-bottom: 1px solid var(--os-border, #f3f4f6);
  font-size: 12.5px;
  color: var(--os-text-2, #4b5563);
}

.kbp-report__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  gap: 3px;
}

.kbp-report__name {
  overflow: hidden;
  color: var(--os-text-1, #111827);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-report__meta {
  color: var(--os-text-3, #9ca3af);
  font-size: 11.5px;
}

.kbp-report__changes {
  flex: none;
  color: var(--os-text-3, #6b7280);
  font-variant-numeric: tabular-nums;
}

.kbp-report__legacy {
  min-width: 48px;
  color: var(--os-text-3, #9ca3af);
  font-size: 11.5px;
  text-align: right;
}

.kbp-report-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin-left: 3px;
  padding: 0 4px;
  border-radius: 8px;
  background: #f59e0b;
  color: #fff;
  font-size: 10px;
}

/* ---------- 二次编辑 ---------- */
.kbp-editor__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  color: var(--os-text-3, #6b7280);
  font-size: 12px;
}

.kbp-editor__bar :deep(.el-tag) {
  flex: none;
}

.kbp-editor__bar .el-button {
  margin-left: auto;
}

.kbp-editor__rich :deep(.tiptap-editor) {
  min-height: 500px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 7px;
  background: #fff;
}

.kbp-editor__rich :deep(.editor-content) {
  min-height: 430px;
  max-height: 58vh;
  overflow: auto;
  padding: 14px 16px;
}

.kbp-editor__rich :deep(.tiptap-image) {
  max-width: 100%;
  max-height: 360px;
  border-radius: 4px;
}

.kbp-editor__preview {
  min-height: 460px;
  max-height: 60vh;
  padding: 14px 18px;
  overflow: auto;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 7px;
  background: #fff;
}

.kbp-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

/* ---------- 历史版本 ---------- */
.kbp-versions__hint {
  margin: 0 0 10px;
  color: var(--os-text-3, #6b7280);
  font-size: 12px;
  line-height: 1.6;
}

.kbp-versions__empty {
  padding: 26px 0;
  color: var(--os-text-3, #9ca3af);
  text-align: center;
  font-size: 13px;
}

.kbp-versions__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 12px;
  padding: 10px 0;
  border-top: 1px solid var(--os-border, #eef0f3);
}

.kbp-versions__row:first-of-type {
  border-top: 0;
}

.kbp-versions__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--os-text-3, #6b7280);
  font-size: 12px;
}

.kbp-versions__meta b {
  color: var(--os-text-1, #111827);
}

.kbp-versions__summary {
  grid-column: 1;
  overflow: hidden;
  color: var(--os-text-2, #4b5563);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kbp-versions__row .el-button {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
}

@media (max-width: 900px) {
  .kbp-anatomy__grid {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .kbp-anatomy__content-inner,
  .kbp-anatomy__image-grid {
    max-height: 360px;
  }
}

/* ---------- 过渡 ---------- */
.kbp-fade-enter-active,
.kbp-fade-leave-active {
  transition: all 0.2s;
}

.kbp-fade-enter-from,
.kbp-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ---------- 窄屏 ---------- */
@media (max-width: 900px) {
  /*
   * 堆叠布局下不能再套「两栏等高」那套最小高度：
   * 左栏在上、右栏在下，若整体还锁 clamp(420px…)，右栏会被推得很长，
   * 空态又在里面垂直居中 → 中间大片空。这里交还给自然高度。
   */
  .kbp-body {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .kbp-side {
    border-right: none;
    border-bottom: 1px solid var(--os-border, #e5e7eb);
  }

  .kbp-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }

  .kbp-side__list {
    max-height: 240px;
  }

  .kbp-blank {
    min-height: 320px;
  }

  .kbp-blank__box {
    padding: 32px 22px;
  }
}
</style>
