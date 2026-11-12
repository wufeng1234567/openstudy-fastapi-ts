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
    <Teleport v-if="canTeleport" to="#os-workspace-nav">
      <div class="kbp-workspace-nav">
        <div class="kbp-nav-row">
          <nav class="kbp-crumbs" aria-label="当前位置">
            <button type="button" class="kbp-crumbs__root" @click="viewMode = 'list'">我的资料</button>
            <span class="kbp-crumbs__sep">/</span>
            <span class="kbp-crumbs__current">{{ activeKb?.name || '全部资料' }}</span>
          </nav>

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
      </div>
    </Teleport>

    <!-- 第二层：当前视图的全局计数 + 全局搜索；不再重复堆统计信息 -->
    <div class="kbp-context-bar">
      <div class="kbp-context-count">{{ workspaceCountLabel }}</div>
      <div class="kbp-context-tools">
        <div class="kbp-search-wrap">
          <SearchFilterInput
            v-model="workspaceSearch"
            class="kbp-global-search"
            :placeholder="workspaceSearchPlaceholder"
            :show-filter="true"
            :filter-open="workspaceFilterOpen"
            :filter-active="workspaceFilterActive"
            @toggle-filter="toggleWorkspaceFilter"
            @enter="onWorkspaceSearchEnter"
          >
            <template #dropdown>
              <div v-if="viewMode === 'wiki'" id="workspace-wiki-search-dropdown"></div>
            </template>
          </SearchFilterInput>
          <CommonFilterSidebar
            ref="workspaceFilterRef"
            :key="viewMode"
            :title="workspaceFilterTitle"
            hide-trigger
            :filter-groups="workspaceFilterGroups"
            :filter-form="workspaceFilters"
            :default-filter="workspaceFilterDefault"
            :default-collapsed="true"
            :style="{ '--filter-top': '38px', '--filter-left': '0px' }"
            @filter-change="handleWorkspaceFilterChange"
            @reset-filters="handleWorkspaceFilterReset"
            @collapse-change="workspaceFilterOpen = $event"
            @active-change="workspaceFilterActive = $event"
          />
        </div>
        <div v-if="viewMode === 'gallery'" id="workspace-gallery-describe" class="kbp-gallery-describe-slot"></div>
        <div v-if="viewMode === 'wiki'" id="workspace-wiki-toolbar" class="kbp-wiki-toolbar"></div>
        <el-button v-if="viewMode !== 'wiki'" size="small" text class="kbp-receive-share" @click="receiveDialogVisible = true">
          <el-icon><Download /></el-icon>
          获取资料分享
        </el-button>
      </div>
    </div>

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

    <!-- 跨资料夹级联搜索：资料夹名命中与内部文档名/备注/正文命中同时呈现 -->
    <section v-if="isCascadeMode" class="kbp-cascade" v-loading="cascadeLoading">
      <header class="kbp-cascade__head">
        <div>
          <div class="kbp-cascade__kicker">级联搜索 · 资料夹 + 内部文档</div>
          <h2>“{{ workspaceSearch }}”的搜索结果</h2>
        </div>
        <div class="kbp-cascade__summary">
          {{ cascadeResults.totalFolders }} 个资料夹 · {{ cascadeResults.totalDocs }} 份资料命中
        </div>
      </header>

      <div v-if="cascadeResults.folders?.length" class="kbp-cascade__folders">
        <article v-for="folder in cascadeResults.folders" :key="folder.kbId" class="kbp-cascade-folder">
          <button type="button" class="kbp-cascade-folder__head" @click="openCascadeFolder(folder)">
            <span class="kbp-cascade-folder__icon"><OsIcon name="folder" :size="17" /></span>
            <span class="kbp-cascade-folder__main">
              <span class="kbp-cascade-folder__name" v-html="highlightQuery(folder.name, cascadeResults.query)"></span>
              <span v-if="folder.matchedByName" class="kbp-cascade-folder__tag">资料夹名称命中</span>
            </span>
            <span class="kbp-cascade-folder__meta">
              {{ folder.docCount }} 份资料
              <template v-if="folder.matchedDocCount">· {{ folder.matchedDocCount }} 份文档命中</template>
            </span>
            <OsIcon name="chevron-right" :size="15" />
          </button>

          <div v-if="folder.documents?.length" class="kbp-cascade-docs">
            <button
              v-for="doc in folder.documents"
              :key="doc.docId"
              type="button"
              class="kbp-cascade-doc"
              @click="openCascadeDocument(doc)"
            >
              <span class="kbp-cascade-doc__icon"><OsIcon name="file-text" :size="15" /></span>
              <span class="kbp-cascade-doc__main">
                <span class="kbp-cascade-doc__top">
                  <b v-html="highlightQuery(doc.fileName, cascadeResults.query)"></b>
                  <span v-for="field in doc.matchedBy" :key="field" class="kbp-cascade-doc__hit">{{ field }}命中</span>
                </span>
                <span v-if="doc.snippet" class="kbp-cascade-doc__snippet" v-html="highlightQuery(doc.snippet, cascadeResults.query)"></span>
                <span v-else-if="doc.note" class="kbp-cascade-doc__snippet">{{ doc.note }}</span>
              </span>
              <span class="kbp-cascade-doc__meta">{{ doc.sizeText }} · {{ doc.createTime }}</span>
            </button>
          </div>
          <div v-else class="kbp-cascade-folder__hint">资料夹名称命中，内部暂无文档正文命中。</div>
        </article>
      </div>

      <div v-else-if="!cascadeLoading" class="kbp-cascade__empty">
        <div class="kbp-empty__art"><OsIcon name="search" :size="28" /></div>
        <h3>没有找到“{{ workspaceSearch }}”</h3>
        <p>可以换个关键词，资料夹名称和文档正文会一起搜索。</p>
      </div>
    </section>

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

    <!-- 从网页导入：一个输入框同时支持「粘贴网址」和「关键词搜索」 -->
    <el-dialog v-model="webImportVisible" title="从网页导入" width="680px" append-to-body @closed="resetWebImport">
      <div class="kbp-web">
        <p class="kbp-web__hint">
          粘贴一个公开网页链接直接导入；或输入关键词，让系统搜索后由你挑选。
        </p>
        <div class="kbp-web__search">
          <el-input
            v-model="webImportQuery"
            clearable
            placeholder="粘贴网址，或输入关键词搜索网页"
            @keyup.enter="submitWebImport"
          />
          <el-button type="primary" :loading="webSearching || webImporting" @click="submitWebImport">
            {{ webImportIsUrl ? '导入网址' : '搜索网页' }}
          </el-button>
        </div>
        <div v-if="webImportQuery.trim() && !webImportIsUrl && !webResults.length && !webSearching" class="kbp-web__empty">
          还没有搜索结果。输入关键词后点「搜索网页」。
        </div>
        <div v-if="webResults.length" class="kbp-web__results">
          <div v-for="item in webResults" :key="item.url" class="kbp-web__item">
            <div class="kbp-web__main">
              <a class="kbp-web__title" :href="item.url" target="_blank" rel="noopener noreferrer">
                [{{ item.index }}] {{ item.title }}
              </a>
              <div class="kbp-web__meta">
                <span>{{ item.siteName }}</span>
                <span v-if="item.date">· {{ item.date }}</span>
              </div>
              <p>{{ item.snippet || item.summary }}</p>
            </div>
            <el-button size="small" plain :loading="webImporting" @click="importWebResult(item)">导入</el-button>
          </div>
        </div>
        <div class="kbp-web__note">
          <span class="kbp-import__label">备注（可选）</span>
          <el-input v-model="webImportNote" maxlength="200" placeholder="例如：这节课要用的参考资料" />
        </div>
        <p class="kbp-web__foot">
          导入后会走和上传文件相同的分块、向量化、知识百科与知识图谱流程，智能体可以直接检索。
        </p>
      </div>
      <template #footer>
        <el-button @click="webImportVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 从题库导入：只做资料夹与题库的逻辑关联，不复制题目 -->
    <el-dialog v-model="bankImportVisible" title="从题库导入" width="700px" append-to-body>
      <div class="kbp-bank">
        <p class="kbp-bank__hint">
          把已有题库关联到当前资料夹。题库不会复制到资料夹里，只建立逻辑连接；关联后知识图谱会读取题库中的知识点与题目关系。
        </p>
        <div class="kbp-bank__bar">
          <el-input v-model="bankImportKeyword" clearable placeholder="搜索题库名称或科目" />
          <el-button size="small" plain :loading="bankImportLoading" @click="refreshBankImportList">刷新</el-button>
        </div>
        <div v-loading="bankImportLoading" class="kbp-bank__list">
          <article v-for="bank in filteredBankImportBanks" :key="bank.bankId || bank.id" class="kbp-bank__item">
            <div class="kbp-bank__main">
              <div class="kbp-bank__title-row">
                <b>{{ bank.bankName || bank.name || '未命名题库' }}</b>
                <el-tag v-if="bank.linked" size="small" type="success" effect="plain">已关联</el-tag>
              </div>
              <span class="kbp-bank__meta">
                {{ bank.subject || '未设置科目' }} · {{ bank.questionCount || bank.totalQuestions || 0 }} 道题
              </span>
              <p v-if="bank.description" class="kbp-bank__desc">{{ bank.description }}</p>
            </div>
            <el-button
              size="small"
              :type="bank.linked ? 'success' : 'primary'"
              plain
              :loading="bankImportLoadingId === (bank.bankId || bank.id)"
              :disabled="bank.linked"
              @click="importQuestionBank(bank)"
            >
              {{ bank.linked ? '已关联' : '关联到资料夹' }}
            </el-button>
          </article>
          <div v-if="!bankImportLoading && !filteredBankImportBanks.length" class="kbp-bank__empty">
            没有找到可关联的题库。先去「题库搭建」创建或导入题库。
          </div>
        </div>
        <p class="kbp-bank__foot">
          关联后题库仍归题库模块管理；知识图谱只读取其中的知识点、题目关系和薄弱题信息，不会复制题干。
        </p>
      </div>
      <template #footer>
        <el-button @click="bankImportVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <NoteImportDialog
      v-model="noteImportVisible"
      :kb-id="Number(activeKb?.kbId || 0)"
      @imported="onNoteImported"
      @busy="noteImporting = $event"
    />

    <el-dialog v-model="bankKnowledgeVisible" :title="`题库知识点 · ${bankKnowledgeTitle}`" width="720px" append-to-body>
      <div v-loading="bankKnowledgeLoading" class="kbp-bank-knowledge">
        <p v-if="bankKnowledge.summary" class="kbp-bank-knowledge__summary">{{ bankKnowledge.summary }}</p>
        <section class="kbp-bank-knowledge__section">
          <h4>知识点</h4>
          <div v-if="bankKnowledge.entities?.length" class="kbp-bank-knowledge__chips">
            <button type="button" class="kbp-bank-knowledge__chip"
              :class="{ 'is-active': !selectedBankEntityName }" @click="selectedBankEntityName = ''">
              全部
            </button>
            <button v-for="entity in bankKnowledge.entities" :key="entity.name" type="button"
              class="kbp-bank-knowledge__chip" :class="{ 'is-active': selectedBankEntityName === entity.name }"
              @click="selectBankKnowledgeEntity(entity.name)">
              {{ entity.name }}<em v-if="entity.type"> · {{ entity.type }}</em>
              <span v-if="entity.questionIds?.length">{{ entity.questionIds.length }} 题</span>
            </button>
          </div>
          <p v-else class="kbp-bank-knowledge__empty">还没有抽取到知识点，关联后会在后台自动抽取。</p>
          <div v-if="bankKnowledge.relations?.length" class="kbp-bank-knowledge__relations">
            <span v-for="rel in bankKnowledge.relations" :key="`${rel.source}-${rel.target}-${rel.type}`">
              {{ rel.source }} → {{ rel.target }}<em>（{{ rel.type }}）</em>
            </span>
          </div>
        </section>
        <section class="kbp-bank-knowledge__section">
          <h4>
            对应题目
            <span v-if="selectedBankEntityName">「{{ selectedBankEntityName }}」{{ filteredBankKnowledgeQuestions.length }} 道</span>
            <span v-else>示例 {{ filteredBankKnowledgeQuestions.length }} 道</span>
          </h4>
          <div v-if="filteredBankKnowledgeQuestions.length" class="kbp-bank-knowledge__questions">
            <article v-for="question in filteredBankKnowledgeQuestions" :key="question.id"
              class="kbp-bank-knowledge__question" @click="openBankQuestion(question)">
              <b>#{{ question.id }}</b>
              <p>{{ question.text }}</p>
              <em v-if="question.analysis">解析：{{ question.analysis }}</em>
              <span class="kbp-bank-knowledge__jump">查看题目 →</span>
            </article>
          </div>
          <p v-else class="kbp-bank-knowledge__empty">
            {{ selectedBankEntityName ? '这个知识点暂未匹配到可展示的题目。' : '暂无题目样例。' }}
          </p>
        </section>
      </div>
      <template #footer>
        <el-button @click="bankKnowledgeVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="questionJumpVisible" title="题目详情" width="720px" append-to-body>
      <div v-loading="questionJumpLoading" class="kbp-question-jump">
        <template v-if="questionJumpData">
          <div class="kbp-question-jump__meta">
            <el-tag size="small" type="info" effect="plain">题目 #{{ questionJumpData.id }}</el-tag>
            <el-tag v-if="questionJumpData.questionType" size="small" effect="plain">题型 {{ questionJumpData.questionType }}</el-tag>
          </div>
          <LatexRenderer class="kbp-question-jump__stem" :content="questionJumpData.questionText || questionJumpData.content || ''" />
          <div v-if="questionJumpData.options" class="kbp-question-jump__options">
            <pre>{{ formatQuestionOptions(questionJumpData.options) }}</pre>
          </div>
          <div v-if="questionJumpData.answer" class="kbp-question-jump__answer">
            <b>答案</b>
            <LatexRenderer :content="questionJumpData.answer" />
          </div>
          <div v-if="questionJumpData.analysis" class="kbp-question-jump__answer">
            <b>解析</b>
            <LatexRenderer :content="questionJumpData.analysis" />
          </div>
        </template>
        <p v-else-if="!questionJumpLoading" class="kbp-bank-knowledge__empty">题目详情加载失败。</p>
      </div>
      <template #footer>
        <el-button @click="goBankPractice">去题库练习</el-button>
        <el-button @click="questionJumpVisible = false">关闭</el-button>
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
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import { getWorkspaceOverview, uploadToWorkspace, searchWorkspace, listWorkspaceStandaloneImages, getAssetUsageSummary, recordAssetUsage, previewWorkspaceOrganize, getWorkspaceOrganizePlan, getWorkspaceOrganizeRecord, listWorkspaceOrganizePlans, applyWorkspaceOrganize, deleteWorkspaceOrganizeRecord, rollbackWorkspacePlan, setDocumentSearchable, createContentReference } from '@/api/ai/workspace'
import OrganizeDiffDialog from './components/OrganizeDiffDialog.vue'
import DocumentClinicDialog from './components/DocumentClinicDialog.vue'
import GalleryPanel from './components/GalleryPanel.vue'
import KnowledgeWikiPanel from './components/KnowledgeWikiPanel.vue'
import WorkspaceSidebar from './components/WorkspaceSidebar.vue'
import WorkspaceFilePanel from './components/WorkspaceFilePanel.vue'
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
const turndownService = createTurndownService()

const editorMarkdown = computed(() => htmlToEditorMarkdown(turndownService, editorHtml.value))
const WORKSPACE_VIEW_KEY = 'openstudy.workspace.viewMode'
const WORKSPACE_KB_KEY = 'openstudy.workspace.activeKbId'
const WORKSPACE_VIEWS = ['list', 'shelf', 'gallery', 'wiki'] as const

const viewMode = ref<'list' | 'shelf' | 'gallery' | 'wiki'>(
  readWorkspaceView(typeof route.query.view === 'string' ? route.query.view : '', WORKSPACE_VIEW_KEY)
)
const canTeleport = ref(false)
const workspaceSearch = ref('')
const galleryFocusAssetKey = ref('')
const workspaceFilterOpen = ref(false)
const workspaceFilterActive = ref(false)
const workspaceFilterRef = ref<any>(null)
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
  workspaceFilterRef.value?.toggleCollapse?.()
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
const organizeReport = computed(() => computeOrganizeReport(organizePlans.value))

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
/* 在线网页导入：一个输入框同时支持「粘贴网址」与「关键词搜索」 */
const webImportVisible = ref(false)
const webImportQuery = ref('')
const webImportNote = ref('')
const webSearching = ref(false)
const webImporting = ref(false)
const webResults = ref<Array<Record<string, any>>>([])
const webImportIsUrl = computed(() => /^https?:\/\/\S+/i.test(webImportQuery.value.trim()))

/* 从题库导入：题库本身不复制，只建立资料夹 ↔ 题库引用 */
const bankImportVisible = ref(false)
const bankImportLoading = ref(false)
const bankImporting = ref(false)
const bankImportKeyword = ref('')
const bankImportAvailable = ref<any[]>([])
const linkedBanks = ref<any[]>([])
const bankImportLoadingId = ref(0)
const noteImportVisible = ref(false)
const noteImporting = ref(false)
const linkedNotes = ref<any[]>([])
const bankKnowledgeVisible = ref(false)
const bankKnowledgeLoading = ref(false)
const bankKnowledgeTitle = ref('')
const bankKnowledge = ref<any>({ summary: '', entities: [], relations: [], questions: [] })
const bankKnowledgeBankId = ref(0)
const questionJumpVisible = ref(false)
const questionJumpLoading = ref(false)
const questionJumpData = ref<any>(null)
const selectedBankEntityName = ref('')
const selectedBankEntity = computed(() =>
  (bankKnowledge.value.entities || []).find((entity: any) => String(entity.name) === selectedBankEntityName.value)
)
const filteredBankKnowledgeQuestions = computed(() => {
  const questions = bankKnowledge.value.questions || []
  if (!selectedBankEntityName.value) return questions.slice(0, 20)
  const ids = new Set((selectedBankEntity.value?.questionIds || []).map(Number))
  return questions.filter((question: any) => ids.has(Number(question.id)))
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
  return countOrganizePlans(organizePlans.value, status)
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
    editorHtml.value = markdownToEditorHtml(editorContent.value, editorImageMap.value, anatomyImageUrl)
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
  else if (command === 'url') openWebImport()
  else if (command === 'bank') openBankImport()
  else if (command === 'note') openNoteImport()
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
      const images = Array.isArray(res.data?.images)
        ? res.data.images
        : (res.data?.assetKey ? [res.data] : [])
      const failed = Array.isArray(res.data?.failed) ? res.data.failed : []
      ok = documents.length + images.length
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
      const imageCount = images.length
      const documentCount = ok - imageCount
      if (documentCount) {
        ElMessage.success(`已上传 ${documentCount} 份资料${fail ? `，${fail} 份失败` : ''}，正在后台解析并建立索引`)
      }
      if (imageCount) {
        ElMessage.success(`已上传 ${imageCount} 张独立图片，正在生成图片名称和描述`)
      }
      uploadTip.value = '上传完成：资料正在解析、提取图片/公式并建立索引；独立图片已加入画廊并生成名称/描述。'
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

/* ===================== 从网页导入 ===================== */

function openWebImport() {
  if (busy.value) {
    ElMessage.warning('有导入正在进行，等它跑完')
    return
  }
  webImportQuery.value = ''
  webImportNote.value = ''
  webResults.value = []
  webImportVisible.value = true
}

function resetWebImport() {
  webImportQuery.value = ''
  webImportNote.value = ''
  webResults.value = []
  webSearching.value = false
  webImporting.value = false
}

async function submitWebImport() {
  if (webImportIsUrl.value) {
    await importWebUrl(webImportQuery.value.trim())
    return
  }
  await runWebSearch()
}

async function runWebSearch() {
  const query = webImportQuery.value.trim()
  if (!query) {
    ElMessage.warning('先输入关键词')
    return
  }
  if (webSearching.value) return
  webSearching.value = true
  webResults.value = []
  try {
    const res: any = await searchPublicWeb(query, 6)
    if (res.code === 200) {
      webResults.value = Array.isArray(res.data?.results) ? res.data.results : []
      if (!webResults.value.length) ElMessage.warning('没有搜索到公开网页结果，换个关键词试试')
    } else {
      ElMessage.error(res.msg || '网页搜索失败')
    }
  } catch (e: any) {
    ElMessage.error('网页搜索失败：' + (e?.message || e))
  } finally {
    webSearching.value = false
  }
}

async function importWebResult(item: Record<string, any>) {
  const url = String(item?.url || '').trim()
  if (!url) return
  await importWebUrl(url)
}

async function importWebUrl(url: string) {
  const kb = activeKb.value
  if (!kb) return
  if (!/^https?:\/\/\S+/i.test(url)) {
    ElMessage.warning('请提供 http:// 或 https:// 开头的公开网页链接')
    return
  }
  if (webImporting.value) return
  webImporting.value = true
  try {
    const res: any = await importDocumentUrl(kb.kbId, url, webImportNote.value.trim() || undefined)
    if (res.code === 200) {
      ElMessage.success(res.msg || '网页已导入，后台正在分块')
      webImportVisible.value = false
      await load()
      setTimeout(() => load(), 4000)
    } else {
      ElMessage.error(res.msg || '网页导入失败')
    }
  } catch (e: any) {
    ElMessage.error('网页导入失败：' + (e?.message || e))
  } finally {
    webImporting.value = false
  }
}

/* ===================== 从题库导入（逻辑关联） ===================== */

const filteredBankImportBanks = computed(() => {
  const q = bankImportKeyword.value.trim().toLowerCase()
  if (!q) return bankImportAvailable.value
  return bankImportAvailable.value.filter((bank: any) => {
    const text = `${bank.bankName || bank.name || ''} ${bank.subject || ''}`.toLowerCase()
    return text.includes(q)
  })
})

async function loadLinkedBanks() {
  const kb = activeKb.value
  if (!kb || !Number(kb.kbId)) {
    linkedBanks.value = []
    return
  }
  try {
    const res: any = await listKbQuestionBanks(Number(kb.kbId))
    if (res.code === 200) linkedBanks.value = res.data?.linked || []
  } catch {
    linkedBanks.value = []
  }
}

async function loadLinkedNotes() {
  const kb = activeKb.value
  if (!kb || !Number(kb.kbId)) {
    linkedNotes.value = []
    return
  }
  try {
    const res: any = await listKbNotes(Number(kb.kbId))
    if (res.code === 200) linkedNotes.value = res.data?.linked || []
  } catch {
    linkedNotes.value = []
  }
}

function openNoteImport() {
  if (!activeKb.value || !Number(activeKb.value.kbId)) return
  noteImportVisible.value = true
}

function onNoteImported() {
  noteImporting.value = false
  void loadLinkedNotes()
  wikiRefreshKey.value += 1
}

async function unlinkLinkedNote(note: any) {
  const kb = activeKb.value
  const noteId = Number(note?.noteId || note?.id || 0)
  if (!kb || !noteId) return
  try {
    await ElMessageBox.confirm(`确定取消关联笔记「${note.title || '未命名笔记'}」吗？`, '取消关联', {
      confirmButtonText: '取消关联',
      cancelButtonText: '保留',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res: any = await unlinkKbNote(Number(kb.kbId), noteId)
    if (res.code === 200) {
      ElMessage.success('已取消关联')
      await loadLinkedNotes()
    } else {
      ElMessage.error(res.msg || '取消关联失败')
    }
  } catch (error: any) {
    ElMessage.error('取消关联失败：' + (error?.message || error))
  }
}

async function refreshBankImportList() {
  const kb = activeKb.value
  if (!kb || !Number(kb.kbId)) return
  bankImportLoading.value = true
  try {
    const res: any = await listKbQuestionBanks(Number(kb.kbId))
    if (res.code === 200) {
      linkedBanks.value = res.data?.linked || []
      bankImportAvailable.value = res.data?.available || []
    } else {
      ElMessage.error(res.msg || '读取题库失败')
    }
  } catch (e: any) {
    ElMessage.error('读取题库失败：' + (e?.message || e))
  } finally {
    bankImportLoading.value = false
  }
}

async function openBankImport() {
  if (!activeKb.value) return
  bankImportKeyword.value = ''
  bankImportVisible.value = true
  await refreshBankImportList()
}

async function importQuestionBank(bank: any) {
  const kb = activeKb.value
  const bankId = Number(bank?.bankId || bank?.id || 0)
  if (!kb || !bankId || bank?.linked || bankImporting.value) return
  bankImporting.value = true
  bankImportLoadingId.value = bankId
  try {
    const res: any = await linkKbQuestionBank(Number(kb.kbId), bankId)
    if (res.code === 200) {
      ElMessage.success(`已关联题库「${bank.bankName || bank.name || ''}」，知识图谱会自动提取其中的知识点`)
      await refreshBankImportList()
    } else {
      ElMessage.error(res.msg || '关联题库失败')
    }
  } catch (e: any) {
    ElMessage.error('关联题库失败：' + (e?.message || e))
  } finally {
    bankImporting.value = false
    bankImportLoadingId.value = 0
  }
}

function selectBankKnowledgeEntity(name: string) {
  selectedBankEntityName.value = selectedBankEntityName.value === name ? '' : name
}

function formatQuestionOptions(value: any) {
  if (!value) return ''
  if (Array.isArray(value)) {
    return value.map((item: any, index: number) => `${String.fromCharCode(65 + index)}. ${item?.label ?? item?.content ?? item}`).join('\n')
  }
  if (typeof value === 'object') {
    return Object.entries(value).map(([key, item]: any) => `${key}. ${item?.label ?? item?.content ?? item}`).join('\n')
  }
  return String(value)
}

async function openBankQuestion(question: any) {
  const questionId = Number(question?.id || 0)
  if (!questionId || questionJumpLoading.value) return
  questionJumpData.value = null
  questionJumpVisible.value = true
  questionJumpLoading.value = true
  try {
    const res: any = await getQuestionMain(questionId)
    if (res.code === 200) questionJumpData.value = res.data || null
    else ElMessage.error(res.msg || '题目详情加载失败')
  } catch (e: any) {
    ElMessage.error('题目详情加载失败：' + (e?.message || e))
  } finally {
    questionJumpLoading.value = false
  }
}

function goBankPractice() {
  if (bankKnowledgeBankId.value) {
    router.push(`/front/questionPractice/${bankKnowledgeBankId.value}?from=bankKnowledge`)
  }
}

async function openBankKnowledge(bank: any) {
  const kb = activeKb.value
  const bankId = Number(bank?.bankId || bank?.id || 0)
  if (!kb || !bankId || bankKnowledgeLoading.value) return
  bankKnowledgeTitle.value = String(bank.bankName || bank.name || '题库知识点')
  bankKnowledgeBankId.value = bankId
  bankKnowledge.value = { summary: '', entities: [], relations: [], questions: [] }
  selectedBankEntityName.value = ''
  bankKnowledgeVisible.value = true
  bankKnowledgeLoading.value = true
  try {
    const res: any = await getKbQuestionBankKnowledge(Number(kb.kbId), bankId)
    if (res.code === 200) bankKnowledge.value = res.data || { entities: [], relations: [], questions: [] }
    else ElMessage.error(res.msg || '读取题库知识点失败')
  } catch (e: any) {
    ElMessage.error('读取题库知识点失败：' + (e?.message || e))
  } finally {
    bankKnowledgeLoading.value = false
  }
}

async function removeLinkedBank(bank: any) {
  const kb = activeKb.value
  const bankId = Number(bank?.bankId || bank?.id || 0)
  if (!kb || !bankId) return
  try {
    const res: any = await unlinkKbQuestionBank(Number(kb.kbId), bankId)
    if (res.code === 200) {
      ElMessage.success('已取消关联')
      await refreshBankImportList()
    }
  } catch (e: any) {
    ElMessage.error('取消关联失败：' + (e?.message || e))
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

function highlightQuery(content: string, query: string): string {
  const escaped = String(content || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const term = String(query || '').trim()
  if (!term) return escaped
  const pattern = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
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

<style lang="scss" src="./index.scss"></style>
