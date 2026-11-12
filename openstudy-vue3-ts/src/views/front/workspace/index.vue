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
  <div class="kb-page" :class="{ 'kb-page--wiki': viewMode === 'wiki' }">
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
    <WorkspaceChrome
      ref="workspaceChromeRef"
      :can-teleport="canTeleport"
      :view-mode="viewMode"
      :active-kb-name="activeKb?.name"
      :tabs="workspaceTabs"
      :count-label="workspaceCountLabel"
      :search="workspaceSearch"
      :search-placeholder="workspaceSearchPlaceholder"
      :filter-open="workspaceFilterOpen"
      :filter-active="workspaceFilterActive"
      :filter-title="workspaceFilterTitle"
      :filter-groups="workspaceFilterGroups"
      :filter-form="workspaceFilters"
      :filter-default="workspaceFilterDefault"
      @update:view-mode="viewMode = $event"
      @update:search="workspaceSearch = $event"
      @update:filter-open="workspaceFilterOpen = $event"
      @update:filter-active="workspaceFilterActive = $event"
      @toggle-filter="toggleWorkspaceFilter"
      @enter="onWorkspaceSearchEnter"
      @filter-change="handleWorkspaceFilterChange"
      @reset-filters="handleWorkspaceFilterReset"
      @receive="receiveDialogVisible = true"
    />

    <!-- 智能整理：即使关闭预览弹窗，后台进度也要可见、可再次打开 -->
    <WorkspaceTaskBars
      :organize-task="organizeTask"
      :reprocess-task="reprocessTask"
      :reprocess-elapsed="reprocessElapsed"
      @open-organize="organizeVisible = true"
    />

    <WorkspaceCascade
      :is-cascade-mode="isCascadeMode"
      :loading="cascadeLoading"
      :search="workspaceSearch"
      :result="cascadeResults"
      :highlight-query="highlightQuery"
      @open-folder="openCascadeFolder"
      @open-document="openCascadeDocument"
    />

    <!--
      ⚠️ 一个知识库都没有时**不渲染两栏区**（v-if）。
         否则会出现「左边：还没有知识库 / 右边：左边选一个知识库」这种
         两块空面板互相指路的尴尬画面 —— 那是典型的"没设计过空态"。
         这种情况下直接用下面那张整页引导替代。
         注意：默认库是自动创建的，所以这个分支实际上只在接口返回异常时出现，
         但兜底必须画对。
    -->
    <div v-if="viewMode === 'list' && !isCascadeMode && (loading || (kbs.length && !loadFailed))" class="kbp-body">
      <!-- ============ 左：知识库列表 ============ -->
      <WorkspaceSidebar
        :loading="loading"
        :creating="creating"
        :filtered-kbs="filteredKbs"
        :active-kb-id="activeKbId"
        :folder-keyword="folderKeyword"
        :kb-menu="kbMenu"
        @create="promptCreate"
        @select="selectKb"
        @open-menu="openKbMenu"
        @command="handleKbCommand"
        @update:folder-keyword="folderKeyword = $event"
      />

      <!-- ============ 右：当前库的文档 ============ -->
      <WorkspaceFilePanel
        :active-kb="activeKb"
        :loading="loading"
        :busy="busy"
        :uploading="uploading"
        :importing="importing"
        :bank-importing="bankImporting"
        :note-importing="noteImporting"
        :upload-tip="uploadTip"
        :selected-doc-count="selectedDocCount"
        :selected-doc-ids="selectedDocIds"
        :organize-report="organizeReport"
        :linked-banks="linkedBanks"
        :linked-notes="linkedNotes"
        :docs-loading="docsLoading"
        :visible-files="visibleFiles"
        :jump-target-doc-id="jumpTargetDocId"
        :doc-tag-type="docTagType"
        :workspace-search="workspaceSearch"
        @open-share="openShare"
        @remove-selected="removeSelectedDocs"
        @open-organize-report="openOrganizeReport"
        @upload-command="onUploadCommand"
        @drop="onDrop"
        @open-bank-knowledge="openBankKnowledge"
        @remove-linked-bank="removeLinkedBank"
        @unlink-linked-note="unlinkLinkedNote"
        @toggle-doc="toggleDocSelected"
        @show-anatomy="showAnatomy"
        @toggle-searchable="toggleDocSearchable"
        @open-clinic="openClinic"
        @start-organize="startOrganize"
        @doc-more="handleDocMore"
        @pick="onPick"
      />
    </div>

    <!-- 完整书架视图 -->
    <section v-else-if="viewMode === 'shelf' && !isCascadeMode && (loading || (kbs.length && !loadFailed))" class="kbp-shelf-page">
      <div class="kbp-shelf-page__head">
        <div>
          <h2>{{ activeKb?.name || '我的资料' }}</h2>
          <p>{{ visibleFiles.length }} 份资料 · 点击卡片看刨析</p>
        </div>
        <el-button size="small" @click="viewMode = 'list'">返回资料夹</el-button>
      </div>
      <div v-if="visibleFiles.length" class="kbp-shelf-grid">
        <button v-for="doc in visibleFiles" :key="doc.docId" type="button" class="kbp-shelf-card"
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
        <p class="kbp-empty__title">{{ workspaceSearch ? '没有匹配的资料' : '书架还是空的' }}</p>
        <span class="kbp-empty__desc">{{ workspaceSearch ? '换个关键词，或清空搜索再看全部资料。' : '上传课件、真题或笔记后，这里会按资料显示成书架卡片。' }}</span>
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
      v-model:search-query="workspaceSearch"
      :filters="workspaceFilters"
      :focus-asset-key="galleryFocusAssetKey"
      @stats="onGalleryStats"
      @use-image="onGalleryUseImage"
      @locate="onGalleryLocate"
      @back="viewMode = 'list'"
    />

    <!-- 0.5.x 知识百科：主题页是前台内容 -->
    <KnowledgeWikiPanel
      v-else-if="viewMode === 'wiki' && (loading || (kbs.length && !loadFailed))"
      :active-kb-id="activeKbId"
      :search-query="workspaceSearch"
      :search-submit-key="wikiSearchSubmitKey"
      :initial-page-id="wikiInitialPageId"
      :filters="workspaceFilters"
      :refresh-key="wikiRefreshKey"
      @stats="onMapStats"
      @locate="onGraphLocate"
      @ask="onWikiAsk"
      @search-selected="onWikiSearchSelected"
      @open-source="onWikiOpenSource"
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
    <el-dialog v-model="anatomyVisible" :title="`原文阅读 · ${anatomyDocName}`" width="1100px" append-to-body
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

    <!-- 统一入口：资料体检 / 原文阅读 / 智能报告共用一套工作台 -->
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

    <WorkspaceTextWebDialogs
      :text-import-visible="textImportVisible"
      :text-import-content="textImportContent"
      :text-import-file-name="textImportFileName"
      :importing="importing"
      :web-import-visible="webImportVisible"
      :web-import-query="webImportQuery"
      :web-import-note="webImportNote"
      :web-searching="webSearching"
      :web-importing="webImporting"
      :web-results="webResults"
      :web-import-is-url="webImportIsUrl"
      @update:text-import-visible="textImportVisible = $event"
      @update:text-import-content="textImportContent = $event"
      @update:text-import-file-name="textImportFileName = $event"
      @update:web-import-visible="webImportVisible = $event"
      @update:web-import-query="webImportQuery = $event"
      @update:web-import-note="webImportNote = $event"
      @reset-text="resetTextImport"
      @reset-web="resetWebImport"
      @submit-text="submitTextImport"
      @submit-web="submitWebImport"
      @import-web="importWebResult"
    />

    <WorkspaceBankDialogs
      v-model:bank-import-visible="bankImportVisible"
      v-model:bank-import-keyword="bankImportKeyword"
      v-model:bank-knowledge-visible="bankKnowledgeVisible"
      v-model:selected-bank-entity-name="selectedBankEntityName"
      v-model:question-jump-visible="questionJumpVisible"
      :filtered-bank-import-banks="filteredBankImportBanks"
      :bank-import-loading="bankImportLoading"
      :bank-import-loading-id="bankImportLoadingId"
      :bank-knowledge="bankKnowledge"
      :bank-knowledge-loading="bankKnowledgeLoading"
      :bank-knowledge-title="bankKnowledgeTitle"
      :filtered-bank-knowledge-questions="filteredBankKnowledgeQuestions"
      :question-jump-data="questionJumpData"
      :question-jump-loading="questionJumpLoading"
      :format-question-options="formatQuestionOptions"
      :api="{
        refreshBankImportList,
        importQuestionBank,
        selectBankKnowledgeEntity,
        openBankQuestion,
        goBankPractice
      }"
    />

    <NoteImportDialog
      v-model="noteImportVisible"
      :kb-id="Number(activeKb?.kbId || 0)"
      @imported="onNoteImported"
      @busy="noteImporting = $event"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import OsIcon from '@/components/OsIcon/index.vue'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import { getWorkspaceOverview, uploadToWorkspace, searchWorkspace, listWorkspaceStandaloneImages, getAssetUsageSummary, recordAssetUsage, previewWorkspaceOrganize, getWorkspaceOrganizePlan, getWorkspaceOrganizeRecord, listWorkspaceOrganizePlans, applyWorkspaceOrganize, deleteWorkspaceOrganizeRecord, rollbackWorkspacePlan, setDocumentSearchable, createContentReference } from '@/api/ai/workspace'
import OrganizeDiffDialog from './components/OrganizeDiffDialog.vue'
import DocumentClinicDialog from './components/DocumentClinicDialog.vue'
import GalleryPanel from './components/GalleryPanel.vue'
import KnowledgeWikiPanel from './components/KnowledgeWikiPanel.vue'
import WorkspaceSidebar from './components/WorkspaceSidebar.vue'
import WorkspaceFilePanel from './components/WorkspaceFilePanel.vue'
import WorkspaceChrome from './components/WorkspaceChrome.vue'
import WorkspaceCascade from './components/WorkspaceCascade.vue'
import WorkspaceTextWebDialogs from './components/WorkspaceTextWebDialogs.vue'
import WorkspaceBankDialogs from './components/WorkspaceBankDialogs.vue'
import WorkspaceTaskBars from './components/WorkspaceTaskBars.vue'
import VersionHistoryDialog from './components/VersionHistoryDialog.vue'
import ShareKnowledgeDialog from './components/ShareKnowledgeDialog.vue'
import ReceiveKnowledgeDialog from './components/ReceiveKnowledgeDialog.vue'
import NoteImportDialog from './components/NoteImportDialog.vue'
import { listQuestionMain, getQuestionMain, updateQuestionMain } from '@/api/questionMain/questionMain'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { listKbQuestionBanks, linkKbQuestionBank, unlinkKbQuestionBank, getKbQuestionBankKnowledge } from '@/api/ai/questionBankLink'
import { listKbNotes, unlinkKbNote } from '@/api/ai/noteKbLink'
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
  importDocumentUrl,
  reprocessDocument,
  searchPublicWeb,
  updateKnowledgeBase,
  uploadDocument
} from '@/api/ai/rag'
import { Plus } from '@element-plus/icons-vue'
import { Download, Search, Share } from '@element-plus/icons-vue'
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/legacy'
import {
  ensureMarkdownImageFiles,
  missingMarkdownImageFiles,
  pickMissingImagesFromDirectory
} from '@/utils/markdownUpload'
import {
  delay,
  facetText,
  readWorkspaceView,
  reprocessPercent
} from './helpers'
import { createTurndownService, htmlToEditorMarkdown, markdownToEditorHtml } from './editorMarkdown'
import { computeOrganizeReport, countOrganizePlans, planStatusText, planStatusType } from './organizeHelpers'
import { useImageInsertion } from './useImageInsertion'
import { useWorkspaceNavigation } from './useWorkspaceNavigation'
import { useWorkspaceFilters } from './useWorkspaceFilters'
import { useWorkspaceCascade } from './useWorkspaceCascade'

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

/** 从学习计划点“打开完整主题页”时，用 ?pageId= 直接打开对应主题页。 */
const wikiInitialPageId = computed(() => Number(route.query.pageId || 0) || null)

/** 左侧资料夹搜索：只过滤展示，不影响当前选中的库。 */
const filteredKbs = computed(() => {
  const keyword = (folderKeyword.value || workspaceSearch.value).trim().toLowerCase()
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

const {
  organizeReportVisible,
  organizePlansLoading,
  organizePlans,
  organizeVisible,
  organizeMode,
  organizeStatus,
  organizeStage,
  organizeProgress,
  organizeElapsed,
  organizeError,
  organizeApplied,
  organizeRecordView,
  organizePlanId,
  organizeChanges,
  organizeSuggestions,
  organizeDocTarget,
  organizeTask,
  deepOrganizeOptions,
  organizeReport,
  refreshOrganizePlans,
  openOrganizeReport,
  deleteOrganizeRecord,
  organizePlanCount,
  openOrganizePlan,
  startOrganize,
  stopOrganizeClock,
  beginOrganize,
  pollOrganizePlan,
  applyOrganizePreview,
  freshOrganizeDoc,
  rerunOrganize,
  recheckOrganize,
  rollbackOrganizePreview
} = useWorkspaceOrganize({
  activeKb,
  load,
  uploadTip,
  runReindex,
  showHealth
})

/* 富文本编辑：Tiptap HTML ↔ Markdown，保留原有图片标记 */
const viewMode = ref<'list' | 'shelf' | 'gallery' | 'wiki'>(
  readWorkspaceView(typeof route.query.view === 'string' ? route.query.view : '', WORKSPACE_VIEW_KEY)
)
const canTeleport = ref(false)
const workspaceSearch = ref('')
const galleryFocusAssetKey = ref('')
const workspaceFilterOpen = ref(false)
const workspaceFilterActive = ref(false)
const workspaceFilterRef = ref<any>(null)
const workspaceChromeRef = ref<any>(null)
const workspaceFilters = reactive<Record<string, any>>({})
const galleryStats = reactive({ total: 0 })
const mapStats = reactive({ total: 0 })
const wikiSearchSubmitKey = ref(0)
const wikiRefreshKey = ref(0)
const workspaceTabs = [
  { key: 'list' as const, label: '资料夹', icon: 'folder' },
  { key: 'shelf' as const, label: '书架', icon: 'book-open' },
  { key: 'gallery' as const, label: '画廊', icon: 'layout-grid' },
  { key: 'wiki' as const, label: '知识百科', icon: 'book-open' }
]
const {
  workspaceSearchPlaceholder,
  workspaceCountLabel,
  workspaceFilterTitle,
  workspaceFilterDefault,
  workspaceFilterGroups,
  visibleFiles
} = useWorkspaceFilters({
  viewMode,
  activeKb,
  workspaceSearch,
  workspaceFilters,
  stats,
  galleryStats,
  mapStats
})

const {
  isCascadeMode,
  cascadeLoading,
  cascadeResults,
  resetCascade,
  runCascade,
  scheduleCascade,
  openCascadeFolder,
  openCascadeDocument
} = useWorkspaceCascade({
  viewMode,
  workspaceSearch,
  activeKbId,
  showAnatomy
})

function toggleWorkspaceFilter() {
  workspaceChromeRef.value?.toggleCollapse?.()
}

function handleWorkspaceFilterChange(value: Record<string, any>) {
  Object.keys(workspaceFilters).forEach((key) => delete workspaceFilters[key])
  Object.assign(workspaceFilters, value || {})
}

function handleWorkspaceFilterReset() {
  Object.keys(workspaceFilters).forEach((key) => delete workspaceFilters[key])
  workspaceFilterActive.value = false
}

watch(workspaceSearch, scheduleCascade)
watch(viewMode, (mode) => {
  workspaceSearch.value = ''
  workspaceFilterOpen.value = false
  workspaceFilterActive.value = false
  Object.keys(workspaceFilters).forEach((key) => delete workspaceFilters[key])
  resetCascade()
  try {
    localStorage.setItem(WORKSPACE_VIEW_KEY, mode)
  } catch {
    // 忽略存储失败
  }
  const nextQuery = { ...route.query }
  if (mode === 'list') delete nextQuery.view
  else nextQuery.view = mode
  if (String(route.query.view || '') !== String(nextQuery.view || '')) {
    router.replace({ query: nextQuery }).catch(() => {})
  }
})
watch(() => route.query.view, (value) => {
  if (typeof value !== 'string') return
  if ((WORKSPACE_VIEWS as readonly string[]).includes(value) && value !== viewMode.value) {
    viewMode.value = value as 'list' | 'shelf' | 'gallery' | 'wiki'
  }
})
watch(activeKbId, (kbId) => {
  try {
    if (kbId) localStorage.setItem(WORKSPACE_KB_KEY, String(kbId))
    else localStorage.removeItem(WORKSPACE_KB_KEY)
  } catch {
    // 忽略存储失败
  }
  if (kbId) {
    void loadLinkedBanks()
    void loadLinkedNotes()
  } else {
    linkedBanks.value = []
    linkedNotes.value = []
  }
})
const standaloneImages = ref<any[]>([])
const assetUsage = ref<Record<string, number>>({})

const {
  questionPickerVisible,
  questionPickerLoading,
  questionPickerImage,
  questionKeyword,
  questionBankFilter,
  questionBanks,
  questionRows,
  questionTotal,
  questionPage,
  questionInsertingId,
  notePickerVisible,
  notePickerLoading,
  notePickerImage,
  noteKeyword,
  noteRows,
  noteTotal,
  notePage,
  noteInsertingId,
  openQuestionPicker,
  loadQuestionBanks,
  loadQuestionPicker,
  insertImageIntoQuestion,
  openNotePicker,
  loadNotePicker,
  insertImageIntoNote
} = useImageInsertion({
  userId: () => userStore.id,
  onUsageChanged: () => loadAssetUsage()
})

const {
  findDocRecord,
  onGalleryUseImage,
  onGalleryLocate,
  onMapOpenDoc,
  onGraphLocate,
  onWikiAsk,
  onGalleryStats,
  onMapStats,
  onWorkspaceSearchEnter,
  onWikiSearchSelected
} = useWorkspaceNavigation({
  kbs,
  activeKb,
  openQuestionPicker,
  openNotePicker,
  showAnatomy,
  showHealth,
  router,
  galleryStats,
  mapStats,
  viewMode,
  workspaceSearch,
  wikiSearchSubmitKey
})

function onWikiOpenSource(payload: { kind: string; id: number; title?: string; assetKey?: string }) {
  const kind = String(payload?.kind || '')
  const id = Number(payload?.id || 0)
  if (kind === 'image') {
    galleryFocusAssetKey.value = String(payload?.assetKey || '')
    viewMode.value = 'gallery'
    return
  }
  if (!id) return
  if (kind === 'document' || kind === 'web') {
    const doc = findDocRecord(id)
    if (doc) showAnatomy(doc)
    else ElMessage.warning('没有找到这份资料，可能已经被移动或删除')
    return
  }
  if (kind === 'bank') {
    const bank = linkedBanks.value.find((item: any) => Number(item.bankId || item.id) === id)
    openBankKnowledge(bank || { bankId: id, bankName: payload.title || '题库' })
    return
  }
  if (kind === 'note') {
    router.push(`/front/notes/detail/${id}`)
    return
  }
  if (kind === 'image') {
    viewMode.value = 'gallery'
    return
  }
}

const {
  tryQuery,
  tryPanelRef,
  trying,
  tried,
  tryHits,
  tryPage,
  tryPageHits,
  tryReason,
  lowConfidence,
  trySearchedQuery,
  clearTryResults,
  onTryInput,
  doTry,
  openHit,
  highlight,
  highlightQuery,
  cleanMathForSnippet,
  buildHitSnippet,
  docTagType
} = useWorkspaceTrySearch({ activeKb, showAnatomy })

/* 分块 */

/* ===================== 单文档刨析 ===================== */
/** 共享刨析查看器：打开、切文档、高亮定位都由组件内部处理 */
const clinicRef = ref<InstanceType<typeof DocumentClinicDialog> | null>(null)
const {
  anatomyVisible,
  anatomyLoading,
  anatomyFullscreen,
  anatomyDocName,
  anatomyContent,
  anatomyHighlight,
  anatomyTargetChunkId,
  anatomyTargetChunkIndex,
  anatomyTargetChunkCount,
  anatomyTargetText,
  anatomyScrollTargetOffset,
  anatomyExcludedRanges,
  anatomyImageMap,
  anatomyTree,
  anatomyOutlineReason,
  anatomyStats,
  anatomyImageUrl,
  copyImageMarkdown,
  anatomyImages,
  anatomyOutlineItems,
  anatomyQuestionGroups,
  scrollAnatomyToOffset,
  onAnatomyImageLoad,
  jumpToQuestionGroup,
  isAnatomyExcluded,
  blankExcludedText,
  anatomySegments
} = useWorkspaceAnatomy()

const {
  editorVisible,
  editorLoading,
  editorSaving,
  editorDoc,
  editorContent,
  editorHtml,
  editorImageMap,
  editorPreview,
  versionsVisible,
  editorMarkdown,
  openEditor,
  exportDoc,
  exportCurrent,
  openMicroCourse
} = useWorkspaceEditor({ anatomyImageUrl })

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

const {
  importing,
  textImportVisible,
  textImportContent,
  textImportFileName,
  webImportVisible,
  webImportQuery,
  webImportNote,
  webSearching,
  webImporting,
  webResults,
  webImportIsUrl,
  bankImportVisible,
  bankImportLoading,
  bankImporting,
  bankImportKeyword,
  bankImportAvailable,
  linkedBanks,
  bankImportLoadingId,
  noteImportVisible,
  noteImporting,
  linkedNotes,
  bankKnowledgeVisible,
  bankKnowledgeLoading,
  bankKnowledgeTitle,
  bankKnowledge,
  bankKnowledgeBankId,
  questionJumpVisible,
  questionJumpLoading,
  questionJumpData,
  selectedBankEntityName,
  selectedBankEntity,
  filteredBankKnowledgeQuestions,
  filteredBankImportBanks,
  openTextImport,
  resetTextImport,
  submitTextImport,
  openWebImport,
  resetWebImport,
  submitWebImport,
  runWebSearch,
  importWebResult,
  importWebUrl,
  loadLinkedBanks,
  loadLinkedNotes,
  openNoteImport,
  onNoteImported,
  unlinkLinkedNote,
  refreshBankImportList,
  openBankImport,
  importQuestionBank,
  selectBankKnowledgeEntity,
  formatQuestionOptions,
  openBankQuestion,
  goBankPractice,
  openBankKnowledge,
  removeLinkedBank
} = useWorkspaceImports({
  activeKb,
  busy,
  load,
  wikiRefreshKey
})

/* ===================== 加载 ===================== */

async function load(keepActive = true) {
  loading.value = true
  loadFailed.value = false
  try {
    const res: any = await getWorkspaceOverview()
    if (res.code === 200 && res.data) {
      kbs.value = res.data.knowledgeBases || []
      Object.assign(stats, res.data.stats || {})

      // 从聊天跳转过来时优先打开指定资料夹；否则保持当前选中的库。
      // 刷新页面时用 localStorage 恢复上次刷新的资料夹，避免知识百科直接退回默认库。
      const requestedKbId = Number(route.query.kbId || 0)
      let savedKbId = 0
      try {
        savedKbId = Number(localStorage.getItem(WORKSPACE_KB_KEY) || 0)
      } catch {
        savedKbId = 0
      }
      if (requestedKbId && kbs.value.some((k) => Number(k.kbId) === requestedKbId)) {
        activeKbId.value = requestedKbId
      } else if (!keepActive || !kbs.value.some((k) => k.kbId === activeKbId.value)) {
        const fallbackKbId = savedKbId && kbs.value.some((k) => Number(k.kbId) === savedKbId)
          ? savedKbId
          : res.data.defaultKbId || kbs.value[0]?.kbId || null
        activeKbId.value = fallbackKbId
      }
      // 文档被删/换库后，清掉已经不存在的批量选择
      const aliveIds = new Set(
        ((kbs.value.find((k: any) => k.kbId === activeKbId.value)?.files || []) as any[]).map((d: any) => Number(d.docId))
      )
      selectedDocIds.value = selectedDocIds.value.filter((id) => aliveIds.has(id))
      await applyJumpQuery()
      await Promise.all([loadLinkedBanks(), loadLinkedNotes()])
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

const {
  openShare,
  openKbMenu,
  closeKbMenu,
  openDocShare,
  handleKbCommand,
  promptCreate,
  promptRename,
  removeKb,
  toggleDisabled,
  toggleDocSearchable
} = useWorkspaceKbActions({
  activeKbId,
  creating,
  kbMenu,
  shareKbId,
  shareDialogVisible,
  docShareDialogVisible,
  shareDoc,
  load
})

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

/* ===================== 文档上传 ===================== */

const {
  onPick,
  onUploadCommand,
  onFilesPicked,
  onDrop,
  toggleDocSelected,
  removeSelectedDocs,
  removeDoc
} = useWorkspaceUpload({
  activeKb,
  fileInputRef,
  busy,
  dragOver,
  uploading,
  uploadTip,
  selectedDocIds,
  load,
  openTextImport,
  openWebImport,
  openBankImport,
  openNoteImport
})

function stopReprocessClock() {
  if (reprocessTimer) {
    clearInterval(reprocessTimer)
    reprocessTimer = null
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
async function runReindex(doc: any, statusText: string): Promise<{ ok: boolean; message: string; chunkCount?: number }> {
  reprocessTask.active = true
  reprocessTask.docId = doc.docId
  reprocessTask.fileName = doc.fileName
  reprocessTask.statusText = statusText
  reprocessTask.percent = 10
  reprocessTask.error = ''
  reprocessElapsed.value = 0
  stopReprocessClock()
  reprocessTimer = setInterval(() => { reprocessElapsed.value += 1 }, 1000)
  await load()
  const result = await pollReprocess(doc.docId)
  reprocessTask.active = false
  stopReprocessClock()
  await load()
  return result
}

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

function showSmartReport(doc: any) {
  if (!doc?.docId) return
  clinicRef.value?.open(doc, 'report')
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
    ElMessage.error('读取资料原文失败：' + (e?.message || e))
  } finally {
    anatomyLoading.value = false
    await nextTick()
    applyAnatomyHighlight()
  }
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

<style lang="scss" src="./index.scss"></style>
