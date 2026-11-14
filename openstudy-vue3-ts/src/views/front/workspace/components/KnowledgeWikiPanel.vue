<template>
  <section class="kw-page" :class="{ 'kw-page--graph': view === 'map' }">
    <Teleport to="#workspace-wiki-search-dropdown">
      <div v-if="view === 'map' && graphSearchSuggestions.length" class="kw-graph-search-dropdown">
        <button v-for="item in graphSearchSuggestions" :key="item.pageId" type="button"
          class="kw-graph-search-item" @click="selectSearchSuggestion(item)">
          <span class="kw-graph-search-item__dot" :style="{ background: entityTypeMeta(item.kind || item.pageType).color }"></span>
          <span class="kw-graph-search-item__main">
            <b>{{ item.title }}</b>
            <em>{{ item.summary || '打开主题页查看内容' }}</em>
          </span>
          <span class="kw-graph-search-item__type">{{ entityTypeMeta(item.kind || item.pageType).label }}</span>
        </button>
      </div>
    </Teleport>
    <Teleport to="#workspace-wiki-toolbar">
      <div class="kw-context-actions">
        <div class="kw-switch">
          <button type="button" :class="{ 'is-active': view === 'pages' }" @click="view = 'pages'">主题页</button>
          <button type="button" :class="{ 'is-active': view === 'map' }" :disabled="!activeKbId" @click="switchMap()">知识图谱</button>
        </div>
        <el-dropdown trigger="click" :disabled="!activeKbId || buildActive" @command="onBuildCommand">
          <button type="button" class="kw-toolbar-btn is-primary" :disabled="!activeKbId || buildActive">
            <span v-if="buildActive" class="kw-toolbar-btn__spinner"></span>
            <span>{{ buildActive ? `更新中 ${buildJob.done}/${buildJob.total}` : pages.length ? '更新知识百科' : '生成知识百科' }}</span>
            <OsIcon name="chevron-down" :size="12" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="all">增量更新全部（跳过已更新）</el-dropdown-item>
              <el-dropdown-item command="document">只更新文档</el-dropdown-item>
              <el-dropdown-item command="image">只更新图片</el-dropdown-item>
              <el-dropdown-item command="bank">只更新题库</el-dropdown-item>
              <el-dropdown-item command="web">只更新网页</el-dropdown-item>
              <el-dropdown-item command="note">只更新笔记</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </Teleport>

    <div v-if="buildActive" class="kw-build-progress">
      <div class="kw-build-progress__top">
        <span>正在更新知识百科 {{ buildJob.done }}/{{ buildJob.total }}</span>
        <span v-if="buildJob.failed">失败 {{ buildJob.failed }}</span>
      </div>
      <div class="kw-build-progress__bar">
        <i :style="{ width: `${buildProgress}%` }"></i>
      </div>
      <p v-if="buildJob.currentTitle">正在整理：{{ buildJob.currentTitle }}</p>
      <p>切换页面不会中断；回到知识百科会自动恢复进度。</p>
    </div>

    <div v-if="loading" class="kw-loading" v-loading="true"></div>

    <template v-else-if="pages.length || (view === 'map' && allMapNodes.length)">
      <div v-if="view === 'pages'" class="kw-grid">
        <article
          v-for="page in filteredPages"
          :key="page.pageId"
          class="kw-card"
          tabindex="0"
          @click="openPage(page.pageId)"
          @keydown.enter="openPage(page.pageId)"
        >
          <div class="kw-card__top">
            <span class="kw-card__type">主题页</span>
            <span class="kw-card__status" :class="`is-${page.status}`">{{ statusLabel(page.status) }}</span>
          </div>
          <h3>{{ page.title }}</h3>
          <p>{{ page.summary || '还没有摘要，打开主题页查看整理内容。' }}</p>
          <div class="kw-card__meta">
            <span>{{ page.sourceCount || 0 }} 条来源</span>
            <span>{{ page.relatedCount || 0 }} 个关联</span>
            <span>{{ formatTime(page.updateTime) }}</span>
          </div>
        </article>
        <div v-if="!filteredPages.length" class="kw-filter-empty">
          没有匹配的主题页，换个关键词试试。
        </div>
      </div>

      <div v-else ref="mapCanvasRef" class="kw-map" :class="{ 'is-map-ready': mapReady, 'is-hovering': !!mapHoveredId, 'is-dragging': !!mapDraggingId, 'is-large-graph': mapNodes.length > 180 }"
        :style="{ '--kw-map-scale': mapView.scale }"
        @wheel.prevent="onMapWheel" @pointerdown="onMapDown"
        @pointermove="onMapMove" @pointerup="onMapUp" @pointerleave="onMapUp">
        <div class="kw-map-purpose">知识图谱：先看懂知识结构，再让系统帮你排下一步。</div>
        <button v-if="adviceAnimationActive" type="button" class="kw-map-stop-animation" @click.stop="stopAdviceAnimation">
          停止连线动画
        </button>
        <svg class="kw-map__svg" :viewBox="mapViewBox" preserveAspectRatio="xMidYMid meet" aria-label="知识图谱：知识主题节点">
          <defs>
            <marker id="kw-arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="10" markerHeight="7" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#9aa9c0" />
            </marker>
            <marker id="kw-arrow-hl" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="10" markerHeight="7" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#7e94bf" />
            </marker>
          </defs>
          <g :transform="`translate(${mapView.x} ${mapView.y}) scale(${mapView.scale})`">
            <g class="kw-map-base-edges">
              <line v-for="edge in mapEdges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
                :data-edge-source="edge.source" :data-edge-target="edge.target"
                class="kw-map-edge" :class="[`is-${edge.type}`, { 'is-cross': edge.cross, 'is-active': isMapEdgeActive(edge), 'is-dimmed': isMapEdgeDimmed(edge), 'is-current-route': isRouteEdge(edge), 'is-hidden': mapDraggingId && edge.source !== mapDraggingId && edge.target !== mapDraggingId }]"
                :marker-end="mapShowArrows ? (isMapEdgeActive(edge) ? 'url(#kw-arrow-hl)' : 'url(#kw-arrow)') : undefined">
                <title>{{ mapEdgeTitle(edge) }}</title>
              </line>
            </g>
            <line v-for="line in adviceVisibleLinePositions" :key="`advice-${line.key}`" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2"
              pathLength="1" class="kw-map-advice-ray" />
            <circle v-if="adviceActiveLinePosition" :key="`advice-dot-${adviceActiveLinePosition.key}`" r="3" class="kw-map-advice-dot">
              <animateMotion
                :path="`M ${adviceActiveLinePosition.x1} ${adviceActiveLinePosition.y1} L ${adviceActiveLinePosition.x2} ${adviceActiveLinePosition.y2}`"
                dur="1.5s"
                begin="0s"
                repeatCount="1"
                fill="freeze"
              />
            </circle>

            <g class="kw-map-base-nodes">
            <g v-for="node in mapNodes" :key="node.id" v-memo="[node, isMapSelected(node), isRouteNode(node), adviceLitPageIds.length]" class="kw-map-node" :data-node-id="String(node.id)"
              :class="{ 'is-selected': isMapSelected(node), 'is-dimmed': isMapNodeDimmed(node), 'is-bridge': bridgeNodeIds.has(String(node.id)), 'is-learned': Number(node.learning?.viewCount || 0) > 0, 'is-weak': Number(node.learning?.practiceCount || 0) > 0 && Number(node.learning?.accuracy || 0) < 60, 'is-route': isRouteNode(node), 'is-next-stop': isNextStopNode(node), 'is-advice-visited': adviceLitPageIds.includes(String(node.pageId)), 'is-advice-dimmed': adviceLitPageIds.length > 0 && !adviceLitPageIds.includes(String(node.pageId)) }"
              :transform="`translate(${node.x} ${node.y})`"
              @mouseenter="onMapNodeEnter(node)" @mouseleave="onMapNodeLeave(node)"
              @pointerdown.stop="onMapNodeDown($event, node)" @pointerup.stop="onMapNodeUp"
              @click.stop="onMapNodeClick(node)">
              <title>{{ node.title }}{{ node.learning ? ` · ${node.learning.label}` : '' }}</title>
              <!-- 透明命中圈：覆盖圆点、光环和文字之间的空隙，避免鼠标擦边反复 enter/leave。 -->
              <circle class="kw-map-node__hit" :r="node.r + 16" />
              <circle class="kw-map-node__halo" :r="node.r + 8" />
              <circle v-if="mapLearnMode" class="kw-map-node__learn-track" :r="node.r + 5" />
              <circle v-if="mapLearnMode && Number(node.learning?.masteryScore || 0) > 0" class="kw-map-node__learn-ring"
                :r="node.r + 5" pathLength="100" stroke-dasharray="100"
                :stroke-dashoffset="100 - Number(node.learning?.masteryScore || 0)"
                :stroke="learningColor(node.learning)" transform="rotate(-90)" />
              <circle v-if="isMapSelected(node)" class="kw-map-node__active" :r="node.r + 7" :stroke="node.color" />
              <circle class="kw-map-node__dot" :r="node.r + (isMapSelected(node) ? 3 : 0)" :fill="node.color" />
              <text v-if="showMapLabel(node)" class="kw-map-node__label" text-anchor="middle"
                :y="node.r + 14">{{ mapNodeLabel(node) }}</text>
            </g>
            </g>

            <!-- hover 高亮层：只渲染当前节点和少量邻居，避免给 300+ 个基础节点逐个打 class。 -->
            <g v-if="mapHoveredId" class="kw-map-hover-layer" pointer-events="none">
              <line v-for="edge in hoverActiveEdges" :key="`hover-edge-${edge.key}`" :x1="edge.x1" :y1="edge.y1"
                :x2="edge.x2" :y2="edge.y2" class="kw-map-hover-edge"
                :marker-end="mapShowArrows ? 'url(#kw-arrow-hl)' : undefined" />
              <g v-for="node in hoverNeighborNodes" :key="`hover-node-${node.id}`" class="kw-map-hover-node"
                :transform="`translate(${node.x} ${node.y})`">
                <circle class="kw-map-node__dot" :r="node.r + (node.id === mapHoveredId ? 3 : 0)" :fill="node.color" />
                <text v-if="hoverNeighborNodes.length <= 8 || node.id === mapHoveredId" class="kw-map-node__label"
                  text-anchor="middle" :y="node.r + 14">{{ mapNodeLabel(node) }}</text>
              </g>
            </g>
          </g>
        </svg>
        <KnowledgeGraphPanel
          v-model:collapsed="graphPanelCollapsed"
          :show-arrows="mapShowArrows"
          :performance-visible="showPerformanceMonitor"
          :learning-mode="learningMode"
          @toggle-arrows="toggleMapArrows"
          @reset-view="resetGraphView"
          @show-guide="showRouteGuide"
          @toggle-performance="togglePerformanceMonitor"
          @toggle-learning="learningMode = !learningMode"
        />
        <PerformanceMonitor
          v-if="showPerformanceMonitor"
          page="knowledge-graph"
          :kb-id="Number(activeKbId || 0)"
          :node-count="mapNodes.length"
          :edge-count="mapGraph.edges?.length || 0"
        />
        <div class="kw-graph-hint"><span>悬停/点击节点查看相关连线 · 点知识主题打开详情，来源类型与资料/网页/图片/题库/笔记都在详情里 · 规划建议入口在详情页</span></div>
      </div>
    </template>

    <div v-else class="kw-empty">
      <div class="kw-empty__art">◇</div>
      <h3>这个资料夹还没有知识百科</h3>
      <p>先生成知识图谱，再把图谱里的概念整理成可读主题页。不会补充资料里没有的内容。</p>
      <el-button class="kw-build-btn" type="primary" :loading="building || buildActive" :disabled="!activeKbId || buildActive" @click="build">
        {{ buildActive ? `更新中 ${buildJob.done}/${buildJob.total}` : '生成知识百科' }}
      </el-button>
    </div>

    <ResizableDrawer v-model="detailVisible" direction="rtl" storage-key="openstudy_wiki_detail_size"
      :default-width="620" :min="420" :max="1000" :modal="false" :modal-penetrable="true"
      :close-on-click-outside="true">
      <div class="kw-detail-shell">
      <div v-if="pageLoading" class="kw-detail-loading" v-loading="true"></div>
      <div v-else-if="activePage" class="kw-detail">
        <div class="kw-detail__mode-row">
          <div class="kw-detail__mode-tabs">
            <button type="button" :class="{ 'is-active': detailPanel === 'page' }" @click="detailPanel = 'page'">
              知识详情
            </button>
            <button type="button" :class="{ 'is-active': detailPanel === 'advice' }" @click="openAdviceForPage">
              规划建议
            </button>
          </div>
          <button type="button" class="kw-detail__close" title="关闭" @click="closeDetail">×</button>
        </div>

        <div v-show="detailPanel === 'page'" class="kw-detail__page-panel">
        <header class="kw-detail__head">
          <div>
            <h2>{{ activePage.title }}</h2>
            <div class="kw-detail__badges">
              <span class="kw-detail__type" :style="{ color: pageTypeMeta(activePage.pageType).color }">{{ pageTypeLabel(activePage.pageType) }}</span>
              <span>{{ activePage.sources?.length || 0 }} 条来源</span>
              <span>{{ activePage.linkStats?.outPageCount || 0 }} 个出链页面</span>
              <span>{{ activePage.linkStats?.inPageCount || 0 }} 个反链页面</span>
              <span>{{ activePage.version || 1 }} 版</span>
              <span v-if="activePage.status === 'stale'" class="is-stale">待更新</span>
              <span v-if="activePage.generatedBy === 'manual'" class="is-manual">手动编辑</span>
            </div>
          </div>
          <div class="kw-detail__head-actions">
            <el-button size="small" plain @click="openEditor">编辑</el-button>
            <el-button size="small" plain @click="openRevisions">历史版本</el-button>
          </div>
        </header>

        <div v-if="activePage.status === 'stale'" class="kw-detail__warning">
          资料已经更新，这一页的内容可能过期。请回到知识百科点击「更新知识百科」重新整理。
        </div>
        <LatexRenderer :content="activePage.summary" wiki-mode class="kw-detail__lead"
          @wiki-link-click="openPage" />

        <section v-for="(section, index) in activePage.sections || []" :key="`${index}-${section.heading}`" class="kw-detail__section">
          <h3>{{ section.heading }}</h3>
          <LatexRenderer :content="section.body" wiki-mode class="kw-detail__body"
            @wiki-link-click="openPage" />
        </section>

        <section class="kw-detail__block kw-link-block">
          <div class="kw-detail__block-head">
            <span>页面链接</span>
            <b>{{ activePage.linkStats?.outPageCount || 0 }} 页出链 · {{ activePage.linkStats?.inPageCount || 0 }} 页反链</b>
            <el-button size="small" text type="primary" @click="openLinkDialog">添加页面链接</el-button>
            <el-button size="small" text type="primary" :loading="linkRefreshing" @click="refreshLinks">刷新链接</el-button>
            <button type="button" class="kw-link-toggle" @click="linksExpanded = !linksExpanded">
              {{ linksExpanded ? '收起' : `展开（${(groupedOutLinks.length || 0) + (groupedInLinks.length || 0)}）` }}
            </button>
          </div>
          <div v-show="linksExpanded">
          <div v-if="groupedOutLinks.length" class="kw-link-group">
            <div class="kw-link-group__label">本页链接到</div>
            <div class="kw-link-list">
              <div v-for="item in groupedOutLinks" :key="`out-${item.pageId}-${item.anchorText}`"
                class="kw-link-item">
                <button type="button" class="kw-link-main" @click="openPage(item.pageId)">
                  <b>{{ item.title }}</b>
                  <span>“{{ item.anchorText }}”</span>
                  <em>{{ linkSectionsLabel(item) }}</em>
                </button>
                <button type="button" class="kw-link-remove" title="移除这条链接"
                  @click="removeLink(item)">×</button>
              </div>
            </div>
          </div>
          <div v-if="groupedInLinks.length" class="kw-link-group">
            <div class="kw-link-group__label">反向链接</div>
            <div class="kw-link-list">
              <button v-for="item in groupedInLinks" :key="`in-${item.pageId}-${item.anchorText}`"
                type="button" class="kw-link-main" @click="openPage(item.pageId)">
                <b>{{ item.title }}</b>
                <span>“{{ item.anchorText }}”</span>
                <em>{{ linkSectionsLabel(item) }}</em>
              </button>
            </div>
          </div>
          <div v-if="!groupedOutLinks.length && !groupedInLinks.length" class="kw-image-empty">
            正文里还没有页面链接。点击「添加页面链接」，或先在正文里写上目标主题名。
          </div>
          </div>
        </section>

        <section class="kw-detail__block">
          <div class="kw-detail__block-head">
            <span>画廊图片</span>
            <b>{{ activePage.images?.length || 0 }}</b>
            <el-button size="small" text type="primary" @click="openGalleryPicker">从画廊添加</el-button>
          </div>
          <div v-if="activePage.images?.length" class="kw-image-grid">
            <div v-for="image in activePage.images" :key="image.referenceId" class="kw-image-card">
              <el-image :src="imageUrl(image.url)" fit="cover" />
              <div class="kw-image-card__foot">
                <span :title="image.caption || image.fileName">{{ image.caption || image.fileName || '图片' }}</span>
                <button type="button" title="取消关联" @click="removeImage(image)">×</button>
              </div>
            </div>
          </div>
          <div v-else class="kw-image-empty">还没有关联画廊图片，可以从画廊选择。</div>
        </section>

        <section v-if="activePageGraphSources.length || activePage.sources?.length" class="kw-detail__block">
          <div class="kw-detail__block-head"><span>来源</span><b>主题节点关联到的实体</b></div>
          <div v-if="activePageGraphSources.length" class="kw-provenance-list">
            <div v-for="group in activePageGraphSources.filter((item) => item.kind !== 'document' || !activePage.sources?.length)" :key="group.kind" class="kw-provenance-row">
              <span class="kw-provenance-row__label"><i :style="{ background: group.color }"></i>{{ group.label }}</span>
              <span class="kw-provenance-row__titles">{{ group.titles.join('、') || '暂无名称' }}</span>
            </div>
          </div>
          <div v-if="activePage.sources?.length" class="kw-source-list">
            <button v-for="source in activePage.sources" :key="`${source.docId}-${source.chunkId}`" type="button"
              class="kw-source" @click="locateSource(source)">
              <span class="kw-source__type"><i class="is-document"></i>资料</span>
              <span class="kw-source__name">{{ source.docName }}</span>
              <span class="kw-source__index">第 {{ Number(source.chunkIndex || 0) + 1 }} 段</span>
              <span class="kw-source__quote">{{ source.quote }}</span>
            </button>
          </div>
        </section>

        <section v-if="activePage.practice?.questionIds?.length" class="kw-detail__block kw-practice-block">
          <div class="kw-detail__block-head">
            <span>相关题目</span>
            <b>{{ activePage.practice.questionCount || activePage.practice.questionIds.length }} 道同源题</b>
            <button type="button" class="kw-practice-toggle" @click="practiceExpanded = !practiceExpanded">
              {{ practiceExpanded ? '收起' : '展开' }}
            </button>
          </div>
          <div class="kw-practice-summary">
            {{ activePage.practice.bankName || '同源题库' }} · 可练 {{ activePage.practice.questionCount || activePage.practice.questionIds.length }} 题
          </div>
          <div v-show="practiceExpanded" class="kw-practice-list">
            <button v-for="item in pagePracticeQuestions" :key="item.questionId" type="button"
              class="kw-practice-item" @click="startPracticeFromPage(item.questionId)">
              <span class="kw-practice-item__index">#{{ item.questionId }}</span>
              <span class="kw-practice-item__text">{{ item.questionText || '未命名题目' }}</span>
              <em v-if="item.points?.length">{{ item.points[0].title }}</em>
            </button>
          </div>
          <div class="kw-practice-actions">
            <el-button size="small" type="primary" plain @click="startPracticeFromPage()">练本主题题</el-button>
          </div>
        </section>

        <section v-if="activePage.related?.length" class="kw-detail__block">
          <div class="kw-detail__block-head"><span>相关主题</span><b>{{ activePage.related.length }}</b></div>
          <div class="kw-related">
            <button v-for="item in activePage.related" :key="`${item.pageId}-${item.linkType}`" type="button"
              class="kw-related__item" @click="openPage(item.pageId)">
              <b>{{ item.title }}</b>
              <span>{{ linkTypeLabel(item.linkType) }}</span>
            </button>
          </div>
        </section>

        <footer class="kw-detail__foot">
          <span>基于 {{ activePage.sourceDocIds?.length || 0 }} 份资料生成 · {{ formatTime(activePage.updateTime) }}</span>
          <button v-if="activePage.sourceDocIds?.length" type="button" class="kw-detail__reupdate"
            :disabled="buildActive" @click="updateActivePageSource">
            重新更新这个来源
          </button>
        </footer>
        </div>
        <div v-show="detailPanel === 'advice'" class="kw-detail__advice">
          <KnowledgeAdviceHost
            ref="adviceHostRef"
            embedded
            :active-kb-id="activeKbId"
            :node-titles="adviceNodeTitles"
            @update="onAdviceUpdate"
            @focus-page="focusAdvicePage"
            @busy="adviceLoading = $event"
          />
        </div>
      </div>
      </div>
    </ResizableDrawer>

    <KnowledgeWikiEditor v-model="editorVisible" :page="activePage" :pages="pages" @saved="onPageSaved" />

    <el-dialog v-model="linkDialogVisible" title="添加页面链接" width="540px" append-to-body>
      <div class="kw-link-dialog">
        <p class="kw-link-dialog__hint">链接的锚文本必须已经出现在本页正文里；保存后会变成绿色下划线，点击就能跳到目标主题页。</p>
        <label class="kw-link-dialog__label">目标主题页</label>
        <el-select v-model="linkForm.targetPageId" filterable placeholder="选择一个主题页" style="width: 100%"
          @change="onLinkTargetChange">
          <el-option v-for="page in linkTargets" :key="page.pageId" :label="page.title" :value="page.pageId" />
        </el-select>
        <label class="kw-link-dialog__label">正文锚文本</label>
        <el-input v-model="linkForm.anchorText" maxlength="120" show-word-limit
          placeholder="例如：智能体" />
        <label class="kw-link-dialog__label">添加位置</label>
        <el-select v-model="linkForm.sectionIndex" style="width: 100%">
          <el-option label="摘要" :value="-1" />
          <el-option v-for="(section, index) in activePage?.sections || []" :key="index"
            :label="`第 ${index + 1} 节 · ${section.heading}`" :value="index" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="linkDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="linkSaving" :disabled="!linkForm.targetPageId || !linkForm.anchorText.trim()"
          @click="addLink">添加链接</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="revisionVisible" title="主题页历史版本" width="560px" append-to-body>
      <div v-if="revisions.length" class="kw-revisions">
        <div v-for="revision in revisions" :key="revision.revisionId" class="kw-revision">
          <div>
            <b>v{{ revision.version }}</b>
            <span>{{ revision.changeType === 'manual' ? '手动编辑' : revision.changeType === 'before_restore' ? '恢复前快照' : '生成' }}</span>
            <em>{{ revision.createTime }}</em>
          </div>
          <el-button size="small" plain @click="restoreRevision(revision)">恢复</el-button>
        </div>
      </div>
      <div v-else class="kw-image-empty">还没有历史版本。</div>
    </el-dialog>

    <el-dialog v-model="galleryPickerVisible" title="从画廊选择图片" width="760px" append-to-body>
      <div v-loading="galleryLoading" class="kw-gallery-picker">
        <button v-for="item in galleryItems" :key="item.assetKey" type="button" class="kw-gallery-pick"
          @click="attachImage(item)">
          <el-image :src="imageUrl(item.url)" fit="cover" />
          <span>{{ item.caption || item.fileName || item.assetKey }}</span>
        </button>
        <div v-if="!galleryLoading && !galleryItems.length" class="kw-image-empty">当前资料夹还没有可用的画廊图片。</div>
      </div>
    </el-dialog>

    <el-dialog v-model="routeGuideVisible" title="知识图谱怎么用" width="520px" append-to-body class="kw-guide-dialog">
      <div class="kw-guide-lead">知识图谱不是一张要背下来的图，而是帮你决定“下一步学什么”。</div>
      <div class="kw-guide-steps">
        <div class="kw-guide-step">
          <i>01</i>
          <div><b>先看节点</b><p>每个圆点是一个主题页。点击节点可以查看内容、来源和它连接的知识。</p></div>
        </div>
        <div class="kw-guide-step">
          <i>02</i>
          <div><b>生成规划建议</b><p>打开右侧「规划建议模式」，点一个节点作为起点，系统会沿着图谱关系生成可调整的规划建议。</p></div>
        </div>
        <div class="kw-guide-step">
          <i>03</i>
          <div><b>读完就练，计划会变</b><p>每页读完可以直接练同源题。练习后回到图谱，掌握度会更新，学习计划会按真实记录重算。</p></div>
        </div>
      </div>
      <div class="kw-guide-tip">点任意节点都可以在详情里“以此页为目标重新规划”；完整按天任务在「学习统计 → 学习计划」里。</div>
      <template #footer>
        <el-button type="primary" @click="routeGuideVisible = false">知道了</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="wikiUpdateVisible" title="按来源更新知识百科" width="540px" append-to-body>
      <p class="kw-update-hint">
        只更新选中的一个来源；已生成且未变化的主题页会跳过，不会重复调用模型。
      </p>
      <div v-loading="wikiUpdateLoading" class="kw-update-list">
        <button v-for="item in wikiUpdateOptions" :key="`${item.id}-${item.title}`" type="button"
          class="kw-update-item" :disabled="wikiUpdateSubmitting" @click="applyWikiUpdate(item)">
          <span class="kw-update-item__type">{{ { document: '文档', image: '图片', bank: '题库', web: '网页', note: '笔记' }[wikiUpdateType] }}</span>
          <span class="kw-update-item__main">
            <b>{{ item.title }}</b>
            <em>{{ item.subtitle || '更新这个来源对应的主题页' }}</em>
          </span>
          <OsIcon name="chevron-right" :size="14" />
        </button>
        <div v-if="!wikiUpdateLoading && !wikiUpdateOptions.length" class="kw-update-empty">
          这个资料夹暂时没有可更新的{{ { document: '文档', image: '图片', bank: '题库', web: '网页', note: '笔记' }[wikiUpdateType] }}来源。
        </div>
      </div>
      <template #footer>
        <el-button @click="wikiUpdateVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { ENTITY_TYPE_META, entityTypeMeta, normalizeEntityKind, pageTypeLabel, pageTypeMeta } from '../utils/knowledgeGraphMeta'
import { useWikiPanelFilters } from './useWikiPanelFilters'
import { useWikiPanelFormatters } from './useWikiPanelFormatters'
import { useWikiMapViewCache } from './wikiMapViewCache'
import { useWikiMapLayout } from './useWikiMapLayout'
import { useWikiMapDisplay } from './useWikiMapDisplay'
import { useWikiPlanState } from './useWikiPlanState'
import { useWikiMapViewControls } from './useWikiMapViewControls'
import { useWikiGraphDerived } from './useWikiGraphDerived'
import { useWikiLearningDisplay } from './useWikiLearningDisplay'
import { useWikiMapEdges } from './useWikiMapEdges'
import { useWikiMapNodes } from './useWikiMapNodes'
import { layoutTopicGraph } from './topicGraphLayout'
import { useWikiAdviceDisplay } from './useWikiAdviceDisplay'
import { useWikiLabelVisibility } from './useWikiLabelVisibility'
import {
  computeRepulsion,
  computeSpringForces,
  computeWheelZoom,
  integrateNodes
} from './wikiMapGeometry'
import { WIKI_VIEW_KEY, WIKI_LEARN_KEY, WIKI_GUIDE_KEY, WIKI_ROUTE_KEY, readWikiView, readWikiLearnMode, readRouteQuery } from './wikiPanelStorage'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import KnowledgeGraphPanel from './KnowledgeGraphPanel.vue'
import PerformanceMonitor from './PerformanceMonitor.vue'
import { readStudyPlanConfig } from '@/utils/studyPlanState'
import { getStudyMap } from '@/api/ai/studyPlan'
import { listKbNotes } from '@/api/ai/noteKbLink'
import KnowledgeAdviceHost from './KnowledgeAdviceHost.vue'
import { getQuestionKnowledgePoints } from '@/api/questionMain/questionMain'
import KnowledgeWikiEditor from './KnowledgeWikiEditor.vue'
import {
  addWikiPageLink,
  attachWikiImage,
  buildWikiIncremental,
  buildWikiSource,
  detachWikiImage,
  getLatestWikiBuildJob,
  getLearningRoute,
  getStudyPlan,
  getWikiBuildJob,
  getWikiPage,
  listGalleryAssets,
  listWikiPages,
  listWikiRevisions,
  recordWikiPageView,
  refreshWikiPageLinks,
  removeWikiPageLink,
  restoreWikiRevision
} from '@/api/ai/workspace'

const props = defineProps<{
  activeKbId?: number | null
  searchQuery?: string
  searchSubmitKey?: number
  initialPageId?: number | null
  filters?: Record<string, any>
  refreshKey?: number
}>()

const emit = defineEmits<{
  (e: 'stats', payload: { total: number }): void
  (e: 'locate', payload: { docId: number; chunkId?: number; chunkIndex?: number }): void
  (e: 'ask', prompt: string): void
  (e: 'search-selected', payload: { pageId: number }): void
  (e: 'open-source', payload: { kind: string; id: number; title?: string; doc?: any; assetKey?: string }): void
}>()

const mapTypeVisible = reactive<Record<string, boolean>>(
  Object.fromEntries(ENTITY_TYPE_META.map((item) => [item.type, true]))
)

const loading = ref(false)
const building = ref(false)
const buildJob = ref<any>(null)
const pages = ref<any[]>([])
const wikiUpdateVisible = ref(false)
const wikiUpdateType = ref<'document' | 'image' | 'bank' | 'web' | 'note'>('document')
const wikiUpdateOptions = ref<any[]>([])
const wikiUpdateLoading = ref(false)
const wikiUpdateSubmitting = ref(false)
const stats = reactive({ pageCount: 0, docCount: 0, staleCount: 0, linkCount: 0 })
const linkDialogVisible = ref(false)
const linkSaving = ref(false)
const linkRefreshing = ref(false)
const linkForm = reactive<{ targetPageId: number | null; anchorText: string; sectionIndex: number }>({
  targetPageId: null,
  anchorText: '',
  sectionIndex: -1
})
const router = useRouter()
const view = ref<'pages' | 'map'>(readWikiView())
const adviceHostRef = ref<any>(null)
const adviceLoading = ref(false)
const adviceTrace = ref<any>(null)
const adviceVisitedPageIds = ref<string[]>([])
const adviceLitPageIds = ref<string[]>([])
const detailVisible = ref(false)
const mapDetailOpening = ref(false)
const pageLoading = ref(false)
const activePage = ref<any>(null)
/** KNOWLEDGE PAGE 与规划建议面板在同一个右侧抽屉内切换。 */
const detailPanel = ref<'page' | 'advice'>('page')
/** 页面链接默认收起，避免长链接列表占满详情页。 */
const linksExpanded = ref(false)
const practiceExpanded = ref(false)
const pagePracticeQuestions = ref<any[]>([])
const {
  graphSourceTypeFilter,
  graphPageTypeFilter,
  graphLearningFilter,
  filteredPages,
  linkTargets,
  groupLinkItems,
  groupedOutLinks,
  groupedInLinks
} = useWikiPanelFilters({ props, pages, activePage })
const editorVisible = ref(false)
const revisionVisible = ref(false)
const revisions = ref<any[]>([])
const galleryPickerVisible = ref(false)
const galleryLoading = ref(false)
const galleryItems = ref<any[]>([])

const mapCanvasRef = ref<HTMLElement | null>(null)
const IMAGE_CLUSTER_ID = 'image:cluster'
// 大图数据不做深响应式：200+ 节点和上千条边若被 Vue 逐层代理，hover/筛选会明显卡顿。
// 只在整体替换时触发更新，节点局部变化用不可变替换（见 updateMapNodeLearning）。
const mapGraph = shallowRef<any>({ nodes: [], edges: [], groups: [] })
let skipNextMapGraphReset = false

/** 当前主题节点在完整图谱里的来源类型（资料/网页/图片/题库/笔记）。 */
const activePageGraphSources = computed(() => {
  const page = activePage.value
  if (!page) return []
  const pageId = Number(page.pageId || page.id || 0)
  if (!pageId) return []
  const nodes = mapGraph.value?.nodes || []
  const pageNode = nodes.find(
    (node: any) => Number(node.pageId) === pageId || String(node.id) === `page:${pageId}`
  )
  if (!pageNode) return []
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  const groups = new Map<
    string,
    { kind: string; label: string; color: string; count: number; titles: string[] }
  >()
  for (const edge of mapGraph.value?.edges || []) {
    const sourceId = String(edge.source || '')
    const targetId = String(edge.target || '')
    if (sourceId !== String(pageNode.id) && targetId !== String(pageNode.id)) continue
    const otherId = sourceId === String(pageNode.id) ? targetId : sourceId
    const other = byId.get(otherId)
    if (!other) continue
    const kind = normalizeEntityKind(other.kind || other.pageType)
    if (kind === 'topic') continue
    if (!groups.has(kind)) {
      const meta = entityTypeMeta(kind)
      groups.set(kind, { kind, label: meta.label, color: meta.color, count: 0, titles: [] })
    }
    const group = groups.get(kind)!
    group.count += 1
    const title = String(other.title || '').trim()
    if (title && !group.titles.includes(title) && group.titles.length < 8) group.titles.push(title)
  }
  return [...groups.values()]
})
const mapSize = reactive({ width: 1200, height: 760 })
const mapReady = ref(false)
const mapSwitching = ref(false)
const mapLayoutScale = computed(() => Math.min(1.8, Math.max(1, Math.min(mapSize.width / 1200, mapSize.height / 760))))
const mapViewBox = computed(() => `0 0 ${mapSize.width} ${mapSize.height}`)
const mapView = reactive({ x: 0, y: 0, scale: 1 })
// 镜头动画/滚轮会先写 DOM transform、后提交 mapView；拖拽坐标必须用这个“当前视觉基准”，
// 否则动画或缩放进行中拖拽会把屏幕位移按旧 scale 换算，松手后节点就会跑偏。
let mapVisualTransform = { x: 0, y: 0, scale: 1 }
watch(
  mapView,
  () => {
    mapVisualTransform = { x: mapView.x, y: mapView.y, scale: mapView.scale }
  },
  { deep: true }
)
const { mapViewCacheKey, readMapViewCache, saveMapViewCache } = useWikiMapViewCache({
  activeKbId: props.activeKbId,
  mapSize,
  mapGraph,
  mapView
})
const mapHoveredId = ref<string | null>(null)
const mapSelectedPageId = ref<number | null>(null)
const mapSelectedNodeId = ref<string | null>(null)
const mapImageExpanded = ref(false)
const searchSuppressed = ref(false)
const mapHideUnlinked = ref(false)
const mapShowArrows = ref(true)
const graphPanelCollapsed = ref(false)
const PERFORMANCE_MONITOR_KEY = 'openstudy.workspace.performanceMonitor'
const showPerformanceMonitor = ref(readPerformanceMonitorVisible())
function readPerformanceMonitorVisible() {
  try {
    return localStorage.getItem(PERFORMANCE_MONITOR_KEY) !== '0'
  } catch {
    return true
  }
}
function togglePerformanceMonitor() {
  showPerformanceMonitor.value = !showPerformanceMonitor.value
  try {
    localStorage.setItem(PERFORMANCE_MONITOR_KEY, showPerformanceMonitor.value ? '1' : '0')
  } catch {
    // 忽略存储失败
  }
}
const mapLearnMode = ref(true)
const learningMode = ref(false)
const mapLearningPath = ref<string[]>([])
const learningRoute = ref<any>(null)
const studyPlan = ref<any>(null)
const routeLoading = ref(false)
const routeStrategy = ref<'weakness' | 'foundation' | 'explore'>('weakness')
const routeTargetPageId = ref<number | null>(null)
const routeGuideVisible = ref(false)
const mapDraggingId = ref<string | null>(null)
const mapNodeOffsets = reactive<Record<string, { x: number; y: number }>>({})
const mapSimPositions = reactive<Record<string, { x: number; y: number }>>({})
let mapDrag: any = null
let mapNodeDrag: any = null
let suppressMapNodeClick = false
let mapAnimFrame = 0
let mapSimAlpha = 0
let mapSimNodes: any[] = []
let mapViewFrame = 0
let mapWheelRaf = 0
let mapWheelCommitTimer: ReturnType<typeof setTimeout> | null = null
let mapWheelPending: { x: number; y: number; scale: number } | null = null
let mapWheelRect: DOMRect | null = null
let mapZoomGroup: SVGGElement | null = null
let mapPanGroup: SVGGElement | null = null
let mapOpenTimer: ReturnType<typeof setTimeout> | null = null
let lastDetailPageId: number | null = null

const buildActive = computed(() => buildJob.value?.status === 'running')
const buildProgress = computed(() => {
  const total = Number(buildJob.value?.total || 0)
  const done = Number(buildJob.value?.done || 0)
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0
})

// 首层只画知识主题；资料/网页/图片/题库/笔记统一收进主题详情里的「来源」。
// sourceKinds 是从完整图谱的真实边反推出来的来源类型，供筛选使用。
const topicSourceKinds = computed(() => {
  const result = new Map<string, Set<string>>()
  const nodes = mapGraph.value?.nodes || []
  const topicIds = new Set(
    nodes
      .filter((node: any) => normalizeEntityKind(node.kind || node.pageType) === 'topic')
      .map((node: any) => String(node.id))
  )
  // 优先使用后端在截断前写入的来源类型，节点被 limit 截掉也不影响筛选。
  for (const node of nodes) {
    const kinds = node.detail?.sourceKinds
    if (Array.isArray(kinds) && kinds.length) {
      result.set(String(node.id), new Set(kinds.map(String)))
    }
  }
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  for (const edge of mapGraph.value?.edges || []) {
    const sourceId = String(edge.source || '')
    const targetId = String(edge.target || '')
    const sourceTopic = topicIds.has(sourceId)
    const targetTopic = topicIds.has(targetId)
    if (sourceTopic === targetTopic) continue
    const topicId = sourceTopic ? sourceId : targetId
    const sourceNode = byId.get(sourceTopic ? targetId : sourceId)
    if (!sourceNode) continue
    const kind = normalizeEntityKind(sourceNode.kind || sourceNode.pageType)
    if (kind === 'topic') continue
    if (!result.has(topicId)) result.set(topicId, new Set())
    result.get(topicId)!.add(kind)
  }
  return result
})
const allMapNodes = computed(() =>
  (mapGraph.value?.nodes || [])
    .filter((node: any) => normalizeEntityKind(node.kind || node.pageType) === 'topic')
    .map((node: any) => ({
      ...node,
      sourceKinds: [...(topicSourceKinds.value.get(String(node.id)) || [])]
    }))
)
// 图谱派生展示数据（类型统计/连通性/分组/桥接/搜索建议/学习理由，抽到同目录 composable）
const {
  mapConnectedNodeIds, graphSearchSuggestions,
  mapComponents, groupKeyByNode, isCrossSourceEdge, bridgeNodeIds, learningReason
} = useWikiGraphDerived({
  allMapNodes, mapGraph, props, searchSuppressed, view, learningRoute
})
const routeActive = computed(() => !!learningRoute.value?.stops?.length)

// 建议射线的节点标题 / 轨迹线（抽到同目录 composable；mapNodes 以惰性 getter 传入）
const { adviceNodeTitles, adviceTraceLines } = useWikiAdviceDisplay({
  adviceTrace,
  getMapNodes: () => mapNodes.value
})

// 射线逐条发射：一条线走完，才出现下一条线的新亮点。
const ADVICE_DOT_MS = 1500
const adviceVisibleLines = ref<any[]>([])
const adviceActiveLine = ref<any>(null)
const adviceAnimationActive = ref(false)
let adviceLineTimers: ReturnType<typeof setTimeout>[] = []
watch(adviceTrace, (trace) => {
  adviceLineTimers.forEach((timer) => clearTimeout(timer))
  adviceLineTimers = []
  adviceVisibleLines.value = []
  adviceActiveLine.value = null
  adviceAnimationActive.value = Boolean(trace?.steps?.length)
  adviceLitPageIds.value = mapSelectedPageId.value ? [String(mapSelectedPageId.value)] : []
  const lines = adviceTraceLines.value
  if (!trace?.steps?.length || !lines.length) {
    adviceAnimationActive.value = false
    return
  }
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduced) {
    adviceVisibleLines.value = lines
    adviceLitPageIds.value = Array.from(
      new Set(lines.flatMap((line: any) => [line.fromPageId, line.toPageId]).filter(Boolean))
    )
    adviceAnimationActive.value = false
    return
  }
  lines.forEach((line: any, index: number) => {
    adviceLineTimers.push(
      setTimeout(() => {
        adviceVisibleLines.value = lines.slice(0, index + 1)
        adviceActiveLine.value = line
        // 起点先亮；目标节点必须等亮点真正跑到终点后才亮。
        adviceLitPageIds.value = Array.from(
          new Set([...adviceLitPageIds.value, line.fromPageId].filter(Boolean))
        )
      }, 220 + index * ADVICE_DOT_MS)
    )
    adviceLineTimers.push(
      setTimeout(() => {
        adviceLitPageIds.value = Array.from(
          new Set([...adviceLitPageIds.value, line.toPageId].filter(Boolean))
        )
        if (adviceActiveLine.value?.key === line.key) adviceActiveLine.value = null
      }, 220 + (index + 1) * ADVICE_DOT_MS - 20)
    )
  })
})

function stopAdviceAnimation() {
  adviceLineTimers.forEach((timer) => clearTimeout(timer))
  adviceLineTimers = []
  adviceVisibleLines.value = []
  adviceActiveLine.value = null
  adviceLitPageIds.value = []
  adviceAnimationActive.value = false
  adviceTrace.value = null
}

onBeforeUnmount(() => {
  adviceLineTimers.forEach((timer) => clearTimeout(timer))
})

// 图谱节点布局：先沿用已有过滤/分组，再用主题关系做一次静态力导向布局。
const { mapNodes: baseMapNodes } = useWikiMapNodes({
  mapComponents, graphSourceTypeFilter, graphPageTypeFilter, graphLearningFilter,
  allMapNodes, routeActive, mapHideUnlinked, mapConnectedNodeIds,
  mapLayoutScale, mapImageExpanded, mapTypeVisible, mapSize, learningMode,
  mapNodeOffsets, mapSimPositions, IMAGE_CLUSTER_ID
})
const topicLayout = computed(() =>
  layoutTopicGraph(
    allMapNodes.value,
    mapGraph.value?.edges || [],
    mapSize.width,
    mapSize.height
  )
)
const mapNodes = computed(() => {
  const baseById = new Map(baseMapNodes.value.map((node: any) => [String(node.id), node]))
  return topicLayout.value
    .filter((node: any) => baseById.has(String(node.id)))
    .map((node: any) => {
      const base = baseById.get(String(node.id)) as any
      if (!base) return node
      // 布局只负责 x/y；半径、颜色、学习态和详情字段来自原 mapNodes。
      const merged = { ...node, ...base }
      const offset = mapNodeOffsets[String(node.id)]
      // offset 是松手后的绝对图谱坐标；明确覆盖布局坐标，避免布局重算把它抢回去。
      merged.x = offset ? Number(offset.x) : node.x
      merged.y = offset ? Number(offset.y) : node.y
      return merged
    })
})

// 学习模式/来源筛选后，顶栏计数与画布实际节点保持一致。
watch(() => mapNodes.value.length, (count) => emit('stats', { total: count }), { immediate: true })

/** 动画线坐标跟随当前节点位置实时重算，拖拽节点时不会留在原地。 */
function adviceLinePosition(line: any) {
  if (!line) return null
  const from = mapNodes.value.find((node: any) =>
    String(node.id) === String(line.fromId) ||
    String(node.pageId) === String(line.fromPageId)
  )
  const to = mapNodes.value.find((node: any) =>
    String(node.id) === String(line.toId) ||
    String(node.pageId) === String(line.toPageId)
  )
  if (!from || !to) return null
  return { ...line, x1: from.x, y1: from.y, x2: to.x, y2: to.y }
}
const adviceVisibleLinePositions = computed(() =>
  adviceVisibleLines.value.map(adviceLinePosition).filter(Boolean) as any[]
)
const adviceActiveLinePosition = computed(() => adviceLinePosition(adviceActiveLine.value))

watch(
  () => mapGraph.value,
  () => {
    // shallowRef 下 learning 回填也会替换 mapGraph；这类更新不能清掉用户拖拽偏移。
    if (skipNextMapGraphReset) {
      skipNextMapGraphReset = false
      return
    }
    resetMapNodeOffsets()
  },
  { deep: false }
)


const {
  mapEdgeTitle,
  learningLegend,
  learningColor,
  learningPriority,
  statusLabel,
  sectionLabel,
  linkSectionsLabel,
  linkTypeLabel,
  formatTime
} = useWikiPanelFormatters({ mapNodes })


const { syncMapSize, fitMapView, onMapResize } = useWikiMapLayout({
  mapCanvasRef,
  mapSize,
  mapNodes,
  mapView,
  mapLayoutScale,
  view,
  mapReady,
  saveMapViewCache
})

// 图谱连线（抽到同目录 composable；纯惰性 computed，不含任何交互或计时）
const { mapEdges } = useWikiMapEdges({
  mapHoveredId, mapSelectedNodeId, routeActive, detailVisible, detailOpening: mapDetailOpening,
  adviceAnimating: adviceAnimationActive,
  mapNodes, allMapNodes, mapImageExpanded, mapGraph, IMAGE_CLUSTER_ID, isCrossSourceEdge
})

// 图谱标签可见性（抽到同目录 composable；display helpers 以惰性 getter 传入，保持原声明顺序）
const { visibleLabelIds } = useWikiLabelVisibility({
  mapNodes, mapHoveredId, adviceLitPageIds, mapComponents, mapView, IMAGE_CLUSTER_ID,
  getDisplay: () => ({ isMapSelected, isRouteNode, mapNodeLabel })
})

// 学习态展示 computed（抽到同目录 composable；均为惰性纯展示，不含任何计时/轮询）
const {
  mapLearnSummary, learningRecommendations, routeStopsView, activeRouteStop,
  offRoutePage, nextLearningStep, learningPathItems, learningPathD
} = useWikiLearningDisplay({
  mapNodes, learningPriority, learningReason, learningRoute,
  routeActive, detailVisible, activePage, mapLearningPath
})

/** 清空「建议」相关的状态（轨迹 / 已访问页 / 已点亮的页） */
function resetAdviceState(): void {
  adviceTrace.value = null
  adviceVisitedPageIds.value = []
  adviceLitPageIds.value = []
}

function applyLearningRoute(data: any) {
  const plan = data?.plan || null
  if (plan) studyPlan.value = plan
  if (data?.hasRoute && Array.isArray(data.stops) && data.stops.length) {
    learningRoute.value = data
    mapLearningPath.value = data.stops.map((stop: any) => String(stop.pageId))
    if (data.strategy) routeStrategy.value = data.strategy
    routeTargetPageId.value = data.targetPageId ? Number(data.targetPageId) : null
  } else {
    learningRoute.value = null
    mapLearningPath.value = []
  }
}

// 学习计划快照读写（抽到同目录 composable）
const { persistPlanState, readPlanState } = useWikiPlanState({ props, routeStrategy })

/** 生成/重新生成学习计划；focusPageId 表示“以这一页为目标规划”。 */
async function generateRoute(focusPageId?: number | null, sinceMs?: number) {
  if (!props.activeKbId || routeLoading.value) return
  routeLoading.value = true
  try {
    const target = focusPageId ?? routeTargetPageId.value ?? undefined
    const savedConfig = readStudyPlanConfig(props.activeKbId)
    const res = await getStudyPlan(Number(props.activeKbId), {
      goal: routeStrategy.value,
      examDate: savedConfig?.examDate || undefined,
      focusPageId: target || undefined,
      horizonDays: savedConfig?.horizonDays || 7,
      dailyMinutes: savedConfig?.dailyMinutes || 40,
      restDays: savedConfig?.restDays || [],
      bankIds: savedConfig?.bankIds || [],
      sinceMs: sinceMs || savedConfig?.sinceMs
    })
    if (res.code === 200 && res.data?.route?.stops?.length) {
      const plan = res.data
      studyPlan.value = plan
      persistPlanState(plan)
      applyLearningRoute({
        ...plan.route,
        hasRoute: true,
        strategy: plan.route?.strategy || routeStrategy.value,
        targetPageId: plan.route?.targetPageId || null,
        plan
      })
    } else {
      // 兼容旧后端：新端点尚不可用时退回只读航线，不让用户看到空面板。
      const legacy = await getLearningRoute(Number(props.activeKbId), 3, routeStrategy.value, target || undefined)
      if (legacy.code !== 200) {
        ElMessage.error(legacy.msg || res.msg || '学习计划生成失败')
        return
      }
      if (!legacy.data?.hasRoute) {
        ElMessage.info(legacy.data?.reason || res.data?.route?.headline || '当前资料夹还没有可规划的主题页')
        exitRoute()
        return
      }
      applyLearningRoute(legacy.data)
    }
    try {
      sessionStorage.setItem(
        WIKI_ROUTE_KEY,
        JSON.stringify({ strategy: routeStrategy.value, targetPageId: routeTargetPageId.value })
      )
    } catch {
      // 计划仍可用，只是切页后不恢复
    }
    await nextTick()
    fitMapView()
  } catch (error: any) {
    ElMessage.error('学习计划生成失败：' + (error?.message || error))
  } finally {
    routeLoading.value = false
  }
}

/** 路径里点一个任务：有真实 target 才跳，没 target 的模型幻觉不接。 */
function onPlanTask(task: any) {
  const target = task?.target || {}
  if ((target.kind === 'bank' || target.kind === 'question') && target.bankId) {
    router.push({
      path: `/front/questionPractice/${target.bankId}/practice/sequential`,
      query: { bankName: target.bankName || '题库' }
    })
    return
  }
  if (target.pageId) {
    void openPage(Number(target.pageId))
  }
}

async function planToPage(pageId: number) {
  routeTargetPageId.value = Number(pageId)
  lastDetailPageId = null
  closeDetail()
  await generateRoute(Number(pageId))
}

/** 从当前 KNOWLEDGE PAGE 详情进入规划建议（不再使用图谱侧栏建议模式）。 */
function startPracticeFromPage(questionId?: number) {
  const practice = activePage.value?.practice
  if (!practice?.bankId || !practice?.questionIds?.length) return
  const ids = questionId ? [questionId] : practice.questionIds
  router.push({
    path: `/front/questionPractice/${practice.bankId}/practice/sequential`,
    query: {
      bankName: practice.bankName || '题库',
      from: 'wiki',
      pageId: String(activePage.value?.pageId || ''),
      questionIds: ids.join(',')
    }
  })
}

async function loadPagePracticeQuestions() {
  const ids = activePage.value?.practice?.questionIds || []
  if (!ids.length) {
    pagePracticeQuestions.value = []
    return
  }
  try {
    const res: any = await getQuestionKnowledgePoints(ids)
    pagePracticeQuestions.value = Array.isArray(res.data) ? res.data : []
  } catch {
    pagePracticeQuestions.value = []
  }
}

watch(
  () => activePage.value?.pageId,
  () => {
    practiceExpanded.value = false
    void loadPagePracticeQuestions()
  },
  { immediate: true }
)

function openAdviceForPage() {
  const pageId = Number(activePage.value?.pageId || activePage.value?.id || 0)
  if (!pageId) return
  detailPanel.value = 'advice'
  // 进入建议页只展示该节点的历史规划，生成必须由用户再次点击「生成建议」。
  nextTick(() => adviceHostRef.value?.showHistoryForPage?.(pageId))
}

function onAdviceUpdate(payload: any) {
  adviceTrace.value = payload?.trace || null
  adviceVisitedPageIds.value = (payload?.visitedPageIds || []).map(String)
}

function focusAdvicePage(pageId: number) {
  const node = mapNodes.value.find((item: any) => Number(item.pageId) === Number(pageId))
  detailVisible.value = false
  if (node) {
    selectMapNode(node, false)
  } else {
    mapSelectedPageId.value = Number(pageId)
  }
}

function exitRoute() {
  learningRoute.value = null
  studyPlan.value = null
  mapLearningPath.value = []
  routeTargetPageId.value = null
  try {
    sessionStorage.removeItem(WIKI_ROUTE_KEY)
    // 不删除共享的计划参数；「结束」只是退出当前路径预览。
  } catch {
    // 忽略 storage 不可用
  }
}

function showRouteGuide() {
  routeGuideVisible.value = true
}

function maybeShowRouteGuide() {
  try {
    if (localStorage.getItem(WIKI_GUIDE_KEY) !== '1') {
      routeGuideVisible.value = true
      localStorage.setItem(WIKI_GUIDE_KEY, '1')
    }
  } catch {
    // localStorage 不可用时只在本次打开说明
    routeGuideVisible.value = true
  }
}

async function maybeRestoreRoute() {
  if (learningRoute.value) return
  const state = readPlanState()
  const saved = readRouteQuery()
  if (!saved && !state) {
    maybeShowRouteGuide()
    return
  }
  routeStrategy.value = state?.strategy || saved?.strategy || 'weakness'
  routeTargetPageId.value = state?.targetPageId ?? saved?.targetPageId ?? null
  await generateRoute(routeTargetPageId.value, state?.sinceMs)
}

function toggleLearnMode() {
  mapLearnMode.value = !mapLearnMode.value
  try {
    localStorage.setItem(WIKI_LEARN_KEY, mapLearnMode.value ? '1' : '0')
  } catch {
    // localStorage 不可用时只影响持久化，不影响当前页面
  }
}

// 图谱节点/边的展示判定与标签格式化（抽到同目录 composable，模板调用名保持不变）
const {
  entitySetLabel, neighborIdsFor, mapFocusId, mapNeighborIds,
  onMapNodeEnter, onMapNodeLeave, isMapSelected, isMapNodeDimmed,
  isMapEdgeActive, isMapEdgeDimmed, isRouteNode, isRouteEdge,
  isNextStopNode, showMapLabel, mapNodeLabel, imageUrl
} = useWikiMapDisplay({
  mapHoveredId, mapSelectedNodeId, mapSelectedPageId, mapEdges, mapDraggingId,
  detailVisible, routeActive, learningRoute, activeRouteStop, visibleLabelIds,
  mapComponents, IMAGE_CLUSTER_ID
})

/** hover 只更新一个很小的覆盖层，不触碰 300+ 个基础节点。 */
const hoverNeighborNodes = computed(() => {
  if (!mapHoveredId.value) return []
  return mapNodes.value
    .filter((node: any) => mapNeighborIds.value.has(String(node.id)))
    .slice(0, 30)
})

const hoverActiveEdges = computed(() => {
  const focus = String(mapHoveredId.value || '')
  if (!focus) return []
  return mapEdges.value
    .filter((edge: any) => String(edge.source) === focus || String(edge.target) === focus)
    .slice(0, 80)
})

function animateMapViewTo(targetX: number, targetY: number, targetScale = mapView.scale, duration = 360) {
  cancelMapWheel(true)
  if (mapViewFrame) cancelAnimationFrame(mapViewFrame)
  const group = mapZoomGroup || (mapZoomGroup = mapCanvasRef.value?.querySelector('.kw-map__svg > g') || null)
  const from = { x: Number(mapView.x), y: Number(mapView.y), scale: Number(mapView.scale) }
  const to = { x: Number(targetX), y: Number(targetY), scale: Number(targetScale) }
  const start = performance.now()
  const tick = (now: number) => {
    const progress = Math.min(1, (now - start) / Math.max(1, duration))
    const eased = 1 - Math.pow(1 - progress, 3)
    const x = from.x + (to.x - from.x) * eased
    const y = from.y + (to.y - from.y) * eased
    const scale = from.scale + (to.scale - from.scale) * eased
    // 镜头动画期间直接写 DOM transform，不逐帧修改 200 个节点的响应式状态。
    setMapGroupTransform(group, x, y, scale)
    if (progress < 1) {
      mapViewFrame = requestAnimationFrame(tick)
    } else {
      mapViewFrame = 0
      mapView.x = to.x
      mapView.y = to.y
      mapView.scale = to.scale
      mapZoomGroup = null
      nextTick(() => clearMapGroupTransform(group))
    }
  }
  mapViewFrame = requestAnimationFrame(tick)
}

function selectMapNode(node: any, openDetail = true) {
  if (node.id === IMAGE_CLUSTER_ID) {
    mapImageExpanded.value = true
    return
  }
  stopMapAnimation()
  stopMapNodeDrag()
  mapSelectedPageId.value = Number(node.pageId)
  mapSelectedNodeId.value = String(node.id)
  if (openDetail) mapDetailOpening.value = true
  // 打开详情时不做 360ms 镜头动画：镜头、抽屉入场和页面加载同时跑
  // 会让点击后的第一帧卡顿。这里一次性把画布放到目标位置，抽屉立即打开。
  const targetScale = Math.max(0.9, Math.min(1.25, Number(mapView.scale) || 1))
  if (openDetail) {
    mapView.x = mapSize.width * 0.32 - Number(node.x) * targetScale
    mapView.y = mapSize.height * 0.5 - Number(node.y) * targetScale
    mapView.scale = targetScale
    // `clientToGraphPoint` 用同步快照算拖拽起点；不能等 Vue 的 deep watcher 下一拍。
    mapVisualTransform = { x: mapView.x, y: mapView.y, scale: mapView.scale }
    mapZoomGroup = null
    nextTick(() => {
      const group = mapCanvasRef.value?.querySelector('.kw-map__svg > g') as SVGGElement | null
      if (group) clearMapGroupTransform(group)
    })
  } else {
    animateMapViewTo(
      mapSize.width * 0.32 - Number(node.x) * targetScale,
      mapSize.height * 0.5 - Number(node.y) * targetScale,
      targetScale,
      360
    )
  }
  if (mapOpenTimer) clearTimeout(mapOpenTimer)
  mapOpenTimer = null
  if (!openDetail) return
  const detailClickAt = performance.now()
  const pageId = Number(node.pageId)
  if (!pageId) {
    mapDetailOpening.value = false
    const kind = normalizeEntityKind(node.kind)
    if (kind === 'image' && node.ref?.assetKey) {
      emit('open-source', Object.freeze({
        kind: 'image',
        id: 0,
        assetKey: String(node.ref.assetKey),
        title: node.title,
        doc: node
      }))
      return
    }
    const sourceId = Number(node.ref?.docId || node.ref?.noteId || node.ref?.bankId || node.ref?.pageId || 0)
    if (sourceId) {
      emit('open-source', Object.freeze({ kind, id: sourceId, title: node.title, doc: node }))
    }
    return
  }
  mapOpenTimer = setTimeout(() => {
    mapOpenTimer = null
    markPerformance('graph-detail-open', {
      durationMs: Math.round(performance.now() - detailClickAt)
    })
    void openPage(pageId)
  }, 0)
}

function onMapNodeClick(node: any) {
  if (suppressMapNodeClick || mapNodeDrag?.moved) {
    suppressMapNodeClick = false
    mapNodeDrag = null
    return
  }
  // 同一节点再次点击：关闭详情、取消尚未触发的打开定时器、停止建议动画。
  // 不能只看 detailVisible：第一次点击后有 260ms 的延迟打开窗口，第二次点击也要能取消。
  const samePage = Number(node.pageId) > 0 && Number(mapSelectedPageId.value) === Number(node.pageId)
  const sameNode = String(mapSelectedNodeId.value || '') === String(node.id)
  if ((samePage || sameNode) && mapSelectedNodeId.value) {
    stopAdviceAnimation()
    closeDetail()
    return
  }
  selectMapNode(node)
}

function onRouteStopSelect(pageId: number) {
  const node = mapNodes.value.find((item: any) => Number(item.pageId) === Number(pageId))
  if (node) selectMapNode(node)
}

function startNextRouteStop() {
  const stop = activeRouteStop.value
  if (!stop) return
  const planTask = (studyPlan.value?.days || [])
    .flatMap((day: any) => day.tasks || [])
    .find((item: any) => Number(item.pageId) === Number(stop.pageId) && item.status !== 'done')
  if (planTask) {
    onPlanTask(planTask)
    return
  }
  const task = stop.task || {}
  if (task.type === 'practice' && task.bankId) {
    router.push({
      path: `/front/questionPractice/${task.bankId}/practice/sequential`,
      query: { bankName: task.bankName || '题库' }
    })
    return
  }
  if (task.type === 'ask-agent') {
    emit(
      'ask',
      `请基于知识百科主题页《${stop.title}》（pageId=${stop.pageId}，kbId=${props.activeKbId}）生成 5 道练习题，并在每题后标出对应的主题页小节和原文来源。`
    )
    return
  }
  if (stop.node) selectMapNode(stop.node)
}

function clientToGraphPoint(clientX: number, clientY: number) {
  const svg = mapCanvasRef.value?.querySelector('.kw-map__svg') as SVGSVGElement | null
  const rect = svg?.getBoundingClientRect() || mapCanvasRef.value?.getBoundingClientRect()
  if (!rect) return null
  const scale = Number(mapVisualTransform.scale) || 1
  return {
    x: (clientX - rect.left - Number(mapVisualTransform.x)) / scale,
    y: (clientY - rect.top - Number(mapVisualTransform.y)) / scale
  }
}

function onMapNodeDown(event: PointerEvent, node: any) {
  // 详情抽屉是 non-modal / 可穿透的：打开抽屉后仍允许拖动图谱节点。
  if (event.button !== 0) return
  event.preventDefault()
  try {
    // 让 pointermove/up 始终发到当前节点，避免拖动时被 hover 覆盖层或文字打断。
    ;(event.currentTarget as any)?.setPointerCapture?.(event.pointerId)
  } catch {
    // 不支持 pointer capture 的浏览器退化为 window pointermove 监听。
  }
  stopMapAnimation()
  suppressMapNodeClick = false
  mapDraggingId.value = String(node.id)
  // 拖拽开始时固定高亮当前节点，整段拖拽期间只保留它的邻接高亮，不跟随指针变化。
  mapHoveredId.value = String(node.id)
  const nodeEl = mapCanvasRef.value?.querySelector(`[data-node-id="${String(node.id)}"]`) as SVGGElement | null
  const relatedEdges = Array.from(
    mapCanvasRef.value?.querySelectorAll(`[data-edge-source="${String(node.id)}"], [data-edge-target="${String(node.id)}"]`) || []
  ) as SVGLineElement[]
  mapNodeDrag = {
    node,
    nodeId: String(node.id),
    nodeEl,
    relatedEdges,
    positions: new Map(mapNodes.value.map((item: any) => [String(item.id), item])),
    startX: event.clientX,
    startY: event.clientY,
    // 拖拽期间镜头不会移动，缓存当前缩放即可把屏幕位移精确换算成图谱位移。
    scale: Number(mapVisualTransform.scale) || 1,
    origX: Number(node.x),
    origY: Number(node.y),
    x: Number(node.x),
    y: Number(node.y),
    r: Number(node.r || 5),
    moved: false,
    raf: 0
  }
  window.addEventListener('pointermove', onMapNodeMove)
  window.addEventListener('pointerup', onMapNodeUp)
}

function renderDraggedNode() {
  if (!mapNodeDrag) return
  const { nodeEl, relatedEdges, positions, nodeId, x, y, r } = mapNodeDrag
  nodeEl?.setAttribute('transform', `translate(${x} ${y})`)
  for (const line of relatedEdges) {
    const sourceId = line.getAttribute('data-edge-source') || ''
    const targetId = line.getAttribute('data-edge-target') || ''
    const source = sourceId === nodeId ? { x, y, r } : positions.get(sourceId)
    const target = targetId === nodeId ? { x, y, r } : positions.get(targetId)
    if (!source || !target) continue
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distance = Math.hypot(dx, dy) || 1
    const ux = dx / distance
    const uy = dy / distance
    line.setAttribute('x1', String(source.x + ux * (Number(source.r || 5) + 5)))
    line.setAttribute('y1', String(source.y + uy * (Number(source.r || 5) + 5)))
    line.setAttribute('x2', String(target.x - ux * (Number(target.r || 5) + 7)))
    line.setAttribute('y2', String(target.y - uy * (Number(target.r || 5) + 7)))
  }
}

function onMapNodeMove(event: PointerEvent) {
  if (!mapNodeDrag) return
  // 只使用拖拽开始时缓存的缩放和屏幕位移，避免每个 pointermove 读 SVG rect，
  // 也避免相机快照与起点快照不一致造成“拖到 B 点却落在 B+10”。
  const scale = Number(mapNodeDrag.scale) || 1
  const dx = (event.clientX - mapNodeDrag.startX) / scale
  const dy = (event.clientY - mapNodeDrag.startY) / scale
  if (Math.abs(dx) + Math.abs(dy) > 4) mapNodeDrag.moved = true
  // 不再限制在固定 1000×640 内：允许拖到任意方向，拖出视图后画布自动扩展，
  // 实体集轮廓会跟随节点形成新的边界。
  mapNodeDrag.x = Math.max(-4000, Math.min(4000, mapNodeDrag.origX + dx))
  mapNodeDrag.y = Math.max(-4000, Math.min(4000, mapNodeDrag.origY + dy))
  // 拖拽过程中只写 DOM，不触发 Vue 的整图 computed 重算；松手后再落一次状态。
  if (!mapNodeDrag.raf) {
    mapNodeDrag.raf = requestAnimationFrame(() => {
      if (!mapNodeDrag) return
      mapNodeDrag.raf = 0
      renderDraggedNode()
    })
  }
}

function onMapNodeUp() {
  if (!mapNodeDrag) return
  const state = mapNodeDrag
  mapNodeDrag = null
  mapDraggingId.value = null
  window.removeEventListener('pointermove', onMapNodeMove)
  window.removeEventListener('pointerup', onMapNodeUp)
  if (state.raf) cancelAnimationFrame(state.raf)
  if (state.moved) {
    // 拖拽结束后不再保留 hover 覆盖层，避免鼠标仍在节点上时又出现一层高亮。
    mapHoveredId.value = null
    mapNodeOffsets[state.nodeId] = { x: state.x, y: state.y }
    // 拖拽结束后不再根据节点位置改动 mapView/mapSize：
    // 那会让整张画布在松手瞬间平移/缩放，产生“拖到 B 点却落到 B+10”的错觉。
    // 节点超出当前 viewBox 时由下一次“适配视图”统一处理。
    // 拖拽结束后浏览器仍会补发一次 click；暂时压掉，避免误打开详情。
    suppressMapNodeClick = true
    window.setTimeout(() => { suppressMapNodeClick = false }, 80)
  }
}

function stopMapNodeDrag() {
  if (mapNodeDrag?.raf) cancelAnimationFrame(mapNodeDrag.raf)
  mapNodeDrag = null
  mapDraggingId.value = null
  mapHoveredId.value = null
  suppressMapNodeClick = false
  window.removeEventListener('pointermove', onMapNodeMove)
  window.removeEventListener('pointerup', onMapNodeUp)
}

function stopMapAnimation() {
  if (mapAnimFrame) {
    cancelAnimationFrame(mapAnimFrame)
    mapAnimFrame = 0
  }
  mapSimAlpha = 0
  mapSimNodes = []
}

const MAP_SIMULATION_NODE_LIMIT = 80

function startMapAnimation() {
  stopMapAnimation()
  if (view.value !== 'map' || detailVisible.value || !mapNodes.value.length) return
  // 主题图已经由 topicGraphLayout 做过一次静态力导向布局；
  // 不再每帧跑自动力导向，避免几百个主题时拖拽/缩放掉帧，也避免覆盖计算结果。
  if (mapComponents.value.components.length >= 1) {
    mapSimAlpha = 0
    mapSimNodes = []
    return
  }
  // 大图禁用初始力导向：几百个节点时 O(n²) 模拟会持续触发重绘，
  // 静态布局已经足够可读，优先保证拖拽/缩放的帧率。
  if (mapNodes.value.length > MAP_SIMULATION_NODE_LIMIT) {
    mapSimAlpha = 0
    mapSimNodes = []
    return
  }
  mapSimNodes = mapNodes.value.map((node: any) => ({
    id: String(node.id),
    x: Number(node.x),
    y: Number(node.y),
    vx: Math.sin(Number(node.id) * 1.37) * 0.45,
    vy: Math.cos(Number(node.id) * 1.91) * 0.45,
    degree: Number(node.degree || 0)
  }))
  const byId = new Map(mapSimNodes.map((node) => [node.id, node]))
  mapSimAlpha = 1
  // 与 WeKnora 相同的快慢节奏：初始 alpha=1，逐帧衰减；前半段移动快，后半段慢慢停稳。
  const tick = () => {
    if (detailVisible.value || view.value !== 'map') {
      stopMapAnimation()
      return
    }
    mapSimAlpha *= 0.985
    if (mapSimAlpha < 0.02) {
      mapAnimFrame = 0
      return
    }
    computeRepulsion(mapSimNodes, mapSimAlpha)
    computeSpringForces(mapEdges.value, byId, mapSimAlpha)
    integrateNodes(mapSimNodes, mapSimPositions)
    mapAnimFrame = requestAnimationFrame(tick)
  }
  mapAnimFrame = requestAnimationFrame(tick)
}


async function reload() {
  loading.value = true
  try {
    const res = await listWikiPages({ kbId: props.activeKbId || undefined })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识百科加载失败')
      return
    }
    pages.value = res.data?.pages || []
    Object.assign(stats, res.data?.stats || {})
    emit('stats', { total: pages.value.length })
    if (view.value === 'map') {
      // 刷新后仍停留在知识图谱：有旧图时保留当前视角，只更新数据；
      // 只有第一次进入图谱才做首次 fit。
      await switchMap(Boolean(mapGraph.value.nodes?.length) && mapReady.value)
    } else if (!pages.value.length) {
      view.value = 'pages'
    }
  } catch (error: any) {
    ElMessage.error('知识百科加载失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

let buildTimer: ReturnType<typeof setInterval> | null = null
let buildPollFailures = 0

function stopBuildPolling() {
  if (buildTimer) {
    clearInterval(buildTimer)
    buildTimer = null
  }
}

function startBuildPolling(jobId: number) {
  stopBuildPolling()
  buildPollFailures = 0
  buildTimer = setInterval(async () => {
    try {
      const res = await getWikiBuildJob(jobId)
      if (res.code !== 200 || !res.data) return
      buildPollFailures = 0
      buildJob.value = res.data
      if (res.data.status !== 'running') {
        stopBuildPolling()
        await reload()
        if (res.data.status === 'failed') {
          ElMessage.error(res.data.error || '知识百科生成失败')
        } else if (Number(res.data.failed || 0)) {
          ElMessage.warning(`已整理 ${res.data.done || 0} 个主题，${res.data.failed} 个生成失败`)
        } else {
          ElMessage.success(`已整理 ${res.data.done || 0} 个主题页`)
        }
      }
    } catch (error: any) {
      // 后端重启/断网时不能无限显示更新中：连续 3 次轮询失败就结束。
      buildPollFailures += 1
      console.warn('[wiki] build job poll failed', error)
      if (buildPollFailures >= 3) {
        stopBuildPolling()
        buildJob.value = {
          ...(buildJob.value || {}),
          status: 'failed',
          error: '知识百科更新任务连接中断，请重新发起'
        }
        ElMessage.error('知识百科更新任务连接中断，请重新发起')
      }
    }
  }, 1500)
}

async function resumeBuildJob() {
  try {
    const res = await getLatestWikiBuildJob(props.activeKbId || undefined)
    const job = res.code === 200 ? res.data : null
    if (job?.status === 'running') {
      buildJob.value = job
      startBuildPolling(job.jobId)
    }
  } catch {
    // 恢复失败不影响知识百科本身
  }
}

function onBuildCommand(command: string) {
  if (command === 'all') {
    void build()
    return
  }
  if (['document', 'image', 'bank', 'web', 'note'].includes(command)) {
    void openWikiUpdate(command as typeof wikiUpdateType.value)
  }
}

async function updateActivePageSource() {
  if (!props.activeKbId || !activePage.value?.sourceDocIds?.length || buildActive.value) return
  const sourceId = Number(activePage.value.sourceDocIds[0])
  if (!sourceId) return
  wikiUpdateSubmitting.value = true
  try {
    const res: any = await buildWikiSource({
      kbId: Number(props.activeKbId),
      sourceType: 'document',
      sourceId,
      limit: 30
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '重新更新失败')
      return
    }
    if (res.data?.jobId) {
      buildJob.value = res.data
      ElMessage.info(res.msg || '已开始重新更新这个来源')
      startBuildPolling(res.data.jobId)
    } else {
      await reload()
      ElMessage.success(res.msg || '这个来源已更新')
    }
  } catch (error: any) {
    ElMessage.error('重新更新失败：' + (error?.message || error))
  } finally {
    wikiUpdateSubmitting.value = false
  }
}

async function openWikiUpdate(type: typeof wikiUpdateType.value) {
  wikiUpdateType.value = type
  wikiUpdateVisible.value = true
  wikiUpdateLoading.value = true
  wikiUpdateOptions.value = []
  try {
    if (type === 'note') {
      const res: any = await listKbNotes(Number(props.activeKbId || 0))
      if (res.code !== 200) throw new Error(res.msg || '读取笔记来源失败')
      wikiUpdateOptions.value = (res.data?.linked || []).map((note: any) => ({
        id: Number(note.noteId || note.id || 0),
        title: String(note.title || '未命名笔记'),
        subtitle: String(note.summary || ''),
        node: note
      })).filter((item: any) => item.id > 0)
      return
    }
    const res: any = await getStudyMap({
      kbId: Number(props.activeKbId || 0),
      sourceTypes: [type],
      limit: 300
    })
    if (res.code !== 200) throw new Error(res.msg || '读取来源失败')
    wikiUpdateOptions.value = (res.data?.nodes || [])
      .filter((node: any) => String(node.kind) === type)
      .map((node: any) => ({
        id: Number(node.ref?.assetId || node.ref?.docId || node.ref?.bankId || 0),
        title: String(node.title || '未命名来源'),
        subtitle: String(node.subtitle || ''),
        node
      }))
      .filter((item: any) => item.id > 0)
  } catch (error: any) {
    ElMessage.error('读取可更新来源失败：' + (error?.message || error))
  } finally {
    wikiUpdateLoading.value = false
  }
}

async function applyWikiUpdate(item: any) {
  if (!props.activeKbId || !item?.id || wikiUpdateSubmitting.value) return
  wikiUpdateSubmitting.value = true
  try {
    const res: any = await buildWikiSource({
      kbId: Number(props.activeKbId),
      sourceType: wikiUpdateType.value,
      sourceId: Number(item.id),
      limit: 120
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '按来源更新失败')
      return
    }
    wikiUpdateVisible.value = false
    if (res.data?.jobId) {
      buildJob.value = res.data
      ElMessage.info(res.msg || '已开始增量更新')
      startBuildPolling(res.data.jobId)
    } else {
      ElMessage.success(res.msg || '已加入更新队列')
    }
  } catch (error: any) {
    ElMessage.error('按来源更新失败：' + (error?.message || error))
  } finally {
    wikiUpdateSubmitting.value = false
  }
}

async function build() {
  if (!props.activeKbId || building.value || buildActive.value) return
  building.value = true
  buildPollFailures = 0
  try {
    const res = await buildWikiIncremental({
      kbId: Number(props.activeKbId),
      limit: 30
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识百科生成失败')
      return
    }
    const data = res.data || {}
    if (data.skipped) {
      ElMessage.success(res.msg || '没有需要更新的来源')
      return
    }
    if (data.jobId) {
      buildJob.value = data
      if (data.status === 'running') {
        ElMessage.info(res.msg || '已开始更新知识百科，切换页面不会中断')
        startBuildPolling(data.jobId)
      } else {
        await reload()
      }
      return
    }
    // 兼容旧后端：没有 jobId 时按原同步结果处理
    const errors = Array.isArray(data.errors) ? data.errors.length : 0
    if (errors) ElMessage.warning(`已完成 ${data.pages || 0} 个主题，${errors} 个生成失败`)
    else ElMessage.success(`已整理 ${data.pages || 0} 个主题页`)
    await reload()
  } catch (error: any) {
    ElMessage.error('知识百科生成失败：' + (error?.message || error))
  } finally {
    building.value = false
  }
}

// 图谱视图开关与重置（抽到同目录 composable）
const {
  resetMapNodeOffsets, toggleMapArrows, resetGraphView
} = useWikiMapViewControls({
  mapNodeOffsets, mapSimPositions, mapLearningPath, mapTypeVisible,
  mapHideUnlinked, mapShowArrows, mapImageExpanded,
  stopMapAnimation, startMapAnimation, syncMapSize, fitMapView
})

async function switchMap(preserveView = false) {
  if (!Number(props.activeKbId)) return
  // 防止 onMounted 的 reload 和用户点击同时触发两套加载/两次 fit。
  if (mapSwitching.value) return
  mapSwitching.value = true
  view.value = 'map'
  if (!preserveView) {
    mapReady.value = false
    mapImageExpanded.value = false
    resetMapNodeOffsets()
    mapView.x = 0
    mapView.y = 0
    mapView.scale = 1
  }
  try {
    const res: any = await getStudyMap({
      kbId: Number(props.activeKbId),
      sourceTypes: ['wiki', 'bank', 'document', 'web', 'note', 'image'],
      // 后端 query.limit 上限为 500；保留足够额度给题库/资料等来源节点，
      // 避免只取 300 时来源节点被截断、来源筛选误判为空。
      limit: 500
    })
    if (res.code !== 200) {
      view.value = 'pages'
      return
    }
    const raw = res.data || {}
    mapGraph.value = {
      nodes: (raw.nodes || []).map((node: any) => ({
        ...node,
        id: String(node.id),
        kind: normalizeEntityKind(node.kind),
        pageId: Number(node.ref?.pageId || 0),
        pageType: String(node.detail?.pageType || node.kind || 'topic'),
        title: node.title || node.subtitle || '未命名',
        summary: String(node.detail?.summary || node.subtitle || ''),
        degree: Number(node.metrics?.degree || 0),
        docIds: node.ref?.docId ? [Number(node.ref.docId)] : (node.detail?.docIds || []),
        sourceType: node.source || node.kind,
        sourceId: node.ref?.docId || node.ref?.noteId || node.ref?.bankId || node.ref?.pageId || 0,
        aliases: node.detail?.aliases || []
      })),
      edges: (raw.edges || []).map((edge: any) => ({
        ...edge,
        id: String(edge.id || ''),
        source: String(edge.source),
        target: String(edge.target),
        type: edge.kind || edge.type || 'related'
      })),
      groups: raw.groups || []
    }
    await nextTick()
    if (!preserveView) {
      // 等两帧让右侧面板/画布尺寸稳定后再 fit，并在 ready 前隐藏 SVG，
      // 避免首屏先以 scale=1 渲染、随后又自动缩放的闪动。
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      })
      syncMapSize()
      const cachedView = readMapViewCache()
      if (cachedView) {
        mapView.x = Number(cachedView.x)
        mapView.y = Number(cachedView.y)
        mapView.scale = Number(cachedView.scale)
      } else {
        fitMapView()
      }
    }
    mapReady.value = true
    startMapAnimation()
  } catch {
    // 图谱失败时保持主题页入口，不影响阅读。
    view.value = 'pages'
  } finally {
    mapSwitching.value = false
  }
}

function closeDetail() {
  if (mapOpenTimer) {
    clearTimeout(mapOpenTimer)
    mapOpenTimer = null
  }
  detailPanel.value = 'page'
  linksExpanded.value = false
  mapDetailOpening.value = false
  stopAdviceAnimation()
  detailVisible.value = false
  mapSelectedPageId.value = null
  mapSelectedNodeId.value = null
  mapHoveredId.value = null
}

watch(detailVisible, (visible) => {
  if (visible) return
  const viewedPageId = lastDetailPageId
  lastDetailPageId = null
  mapSelectedPageId.value = null
  mapSelectedNodeId.value = null
  mapHoveredId.value = null
  if (view.value === 'map') nextTick(startMapAnimation)
  if (
    routeActive.value &&
    viewedPageId &&
    (learningRoute.value?.stops || []).some((stop: any) => Number(stop.pageId) === Number(viewedPageId))
  ) {
    void generateRoute(routeTargetPageId.value)
  }
})

function updateMapNodeLearning(pageId: number, learning: any) {
  const nodes = mapGraph.value?.nodes || []
  if (nodes.some((item: any) => Number(item.pageId) === Number(pageId))) {
    // mapGraph 是 shallowRef：用不可变替换节点数组，既更新节点也不让整张图变深响应式。
    skipNextMapGraphReset = true
    mapGraph.value = {
      ...mapGraph.value,
      nodes: nodes.map((item: any) =>
        Number(item.pageId) === Number(pageId) ? { ...item, learning } : item
      )
    }
  }

  const stops = learningRoute.value?.stops || []
  const stop = stops.find((item: any) => Number(item.pageId) === Number(pageId))
  if (!stop) return
  stop.learning = learning
  const views = Number(learning?.viewCount || 0)
  if (views === 0) {
    stop.task = { type: 'read', label: '读主题页', pageId: Number(pageId) }
  } else if (Number(stop.practice?.bankId || 0) > 0) {
    const count = Number(stop.practice?.questionCount || 0)
    stop.task = {
      type: 'practice',
      label: count ? `去练 ${count} 题` : '去练同源题',
      pageId: Number(pageId),
      bankId: Number(stop.practice.bankId),
      bankName: stop.practice.bankName || '题库',
      questionCount: count
    }
  } else if (String(learning?.level || '') === 'mastered') {
    stop.task = { type: 'review', label: '快速复习', pageId: Number(pageId) }
  } else {
    stop.task = { type: 'ask-agent', label: '生成练习', pageId: Number(pageId) }
  }

  const practices = Number(learning?.practiceCount || 0)
  const accuracy = Number(learning?.accuracy || 0)
  if (views === 0) {
    stop.reason = `还没读过 · 连接 ${Number(node?.degree || 0)} 个主题`
  } else if (practices === 0) {
    stop.reason = '已读但还没练过 · 用同源题检验'
  } else if (accuracy < 60) {
    stop.reason = `正确率 ${accuracy}% · 建议回看后再练一轮`
  } else if (accuracy < 80) {
    stop.reason = `正确率 ${accuracy}% · 再练一轮`
  } else if (String(learning?.level || '') === 'mastered') {
    stop.reason = '已掌握 · 可快速复习'
  }

  const openIndex = stops.findIndex(
    (item: any) => String(item.learning?.level || '') !== 'mastered' && Number(item.learning?.practiceCount || 0) === 0
  )
  stops.forEach((item: any, index: number) => {
    if (openIndex < 0) item.status = 'review'
    else if (index < openIndex) item.status = 'done'
    else if (index === openIndex) item.status = 'current'
    else item.status = 'next'
  })
}

async function openPage(pageId: number) {
  const openedAt = performance.now()
  mapSelectedPageId.value = Number(pageId)
  lastDetailPageId = Number(pageId)
  mapDetailOpening.value = true
  detailPanel.value = 'page'
  linksExpanded.value = false
  detailVisible.value = true
  pageLoading.value = true
  activePage.value = null
  try {
    const res = await getWikiPage(pageId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '主题页加载失败')
      closeDetail()
      return
    }
    activePage.value = res.data
    // 阅读记录不阻塞正文展示；成功后再把学习态回填到当前页和图谱节点。
    void recordWikiPageView(pageId).then((viewRes) => {
      if (viewRes.code !== 200 || !viewRes.data?.learning) return
      if (Number(activePage.value?.pageId) === Number(pageId)) {
        activePage.value.learning = viewRes.data.learning
      }
      updateMapNodeLearning(Number(pageId), viewRes.data.learning)
    }).catch(() => {
      // 阅读统计失败不影响阅读本身（例如离线/接口暂时不可用）
    })
  } catch (error: any) {
    ElMessage.error('主题页加载失败：' + (error?.message || error))
    closeDetail()
  } finally {
    pageLoading.value = false
    mapDetailOpening.value = false
    markPerformance('graph-detail-loaded', {
      durationMs: Math.round(performance.now() - openedAt)
    })
  }
}

function locateSource(source: any) {
  if (!source?.docId) return
  emit('locate', {
    docId: Number(source.docId),
    chunkId: Number(source.chunkId) || undefined,
    chunkIndex: Number(source.chunkIndex) || undefined
  })
  closeDetail()
}

function openEditor() {
  if (!activePage.value) return
  editorVisible.value = true
}

async function onPageSaved(page: any) {
  if (page?.pageId) activePage.value = page
  await reload()
}

function openLinkDialog() {
  linkForm.targetPageId = null
  linkForm.anchorText = ''
  linkForm.sectionIndex = activePage.value?.sections?.length ? 0 : -1
  linkDialogVisible.value = true
}

function onLinkTargetChange(value: number) {
  const target = linkTargets.value.find((page: any) => Number(page.pageId) === Number(value))
  if (target && !linkForm.anchorText.trim()) linkForm.anchorText = String(target.title || '')
}

async function addLink() {
  if (!activePage.value || !linkForm.targetPageId || !linkForm.anchorText.trim()) return
  linkSaving.value = true
  try {
    const res = await addWikiPageLink(activePage.value.pageId, {
      targetPageId: Number(linkForm.targetPageId),
      anchorText: linkForm.anchorText.trim(),
      sectionIndex: linkForm.sectionIndex
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '添加页面链接失败')
      return
    }
    activePage.value = res.data
    linkDialogVisible.value = false
    await reload()
    ElMessage.success('页面链接已添加')
  } catch (error: any) {
    ElMessage.error('添加页面链接失败：' + (error?.message || error))
  } finally {
    linkSaving.value = false
  }
}

async function removeLink(item: any) {
  if (!activePage.value) return
  try {
    await ElMessageBox.confirm(
      `移除「${item.title}」这条页面链接${Array.isArray(item.sectionIndexes) && item.sectionIndexes.length > 1 ? `（共 ${item.sectionIndexes.length} 处正文）` : ''}？正文会保留锚文本，只去掉跳转。`,
      '移除页面链接',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' }
    )
    const sectionIndexes = Array.isArray(item.sectionIndexes) && item.sectionIndexes.length
      ? item.sectionIndexes
      : [Number(item.sectionIndex)]
    let latest: any = null
    for (const sectionIndex of sectionIndexes) {
      const res = await removeWikiPageLink(activePage.value.pageId, {
        targetPageId: Number(item.pageId),
        anchorText: item.anchorText,
        sectionIndex: Number(sectionIndex)
      })
      if (res.code !== 200) {
        ElMessage.error(res.msg || '移除页面链接失败')
        return
      }
      latest = res.data
    }
    if (latest) activePage.value = latest
    await reload()
    ElMessage.success('页面链接已移除')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('移除页面链接失败：' + (error?.message || error))
  }
}

async function refreshLinks() {
  if (!activePage.value) return
  linkRefreshing.value = true
  try {
    const res = await refreshWikiPageLinks(activePage.value.pageId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '刷新页面链接失败')
      return
    }
    activePage.value = res.data
    await reload()
    ElMessage.success(`页面链接已刷新，新增 ${res.data?.refreshStats?.links ?? 0} 条`)
  } catch (error: any) {
    ElMessage.error('刷新页面链接失败：' + (error?.message || error))
  } finally {
    linkRefreshing.value = false
  }
}

async function openRevisions() {
  if (!activePage.value) return
  revisionVisible.value = true
  try {
    const res = await listWikiRevisions(activePage.value.pageId)
    revisions.value = res.code === 200 ? (res.data || []) : []
  } catch {
    revisions.value = []
  }
}

async function restoreRevision(revision: any) {
  if (!activePage.value) return
  try {
    const res = await restoreWikiRevision(activePage.value.pageId, revision.revisionId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '恢复失败')
      return
    }
    activePage.value = res.data
    revisionVisible.value = false
    await reload()
    ElMessage.success('已恢复历史版本')
  } catch (error: any) {
    ElMessage.error('恢复失败：' + (error?.message || error))
  }
}

async function openGalleryPicker() {
  galleryPickerVisible.value = true
  galleryLoading.value = true
  try {
    const res = await listGalleryAssets({
      scope: 'current',
      kbId: props.activeKbId || undefined,
      limit: 200
    })
    galleryItems.value = res.code === 200 ? (res.data?.items || []) : []
  } catch {
    galleryItems.value = []
  } finally {
    galleryLoading.value = false
  }
}

async function attachImage(item: any) {
  if (!activePage.value || !item?.assetKey) return
  try {
    const res = await attachWikiImage(activePage.value.pageId, { assetKey: item.assetKey })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '关联图片失败')
      return
    }
    await refreshActivePage()
    galleryPickerVisible.value = false
    ElMessage.success('图片已关联到主题页')
  } catch (error: any) {
    ElMessage.error('关联图片失败：' + (error?.message || error))
  }
}

async function removeImage(image: any) {
  if (!activePage.value || !image?.referenceId) return
  try {
    const res = await detachWikiImage(activePage.value.pageId, image.referenceId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '取消关联失败')
      return
    }
    await refreshActivePage()
  } catch (error: any) {
    ElMessage.error('取消关联失败：' + (error?.message || error))
  }
}

async function refreshActivePage() {
  if (!activePage.value?.pageId) return
  const res = await getWikiPage(activePage.value.pageId)
  if (res.code === 200) activePage.value = res.data
}

function askPage(kind: 'ask' | 'practice' = 'ask') {
  if (!activePage.value) return
  const title = activePage.value.title
  const pageId = activePage.value.pageId
  const kbId = activePage.value.kbId
  const pageRef = `知识百科主题页《${title}》（pageId=${pageId}，kbId=${kbId}）`
  const prompt = kind === 'practice'
    ? `请基于${pageRef}生成 5 道练习题，并在每题后标出对应的主题页小节和原文来源。`
    : `请基于${pageRef}回答我，并在回答里标出引用的主题页和原文来源。`
  emit('ask', prompt)
  closeDetail()
}

function goPractice() {
  const practice = activePage.value?.practice
  if (!practice?.bankId) return
  closeDetail()
  router.push({
    path: `/front/questionPractice/${practice.bankId}/practice/sequential`,
    query: { bankName: practice.bankName || '题库' }
  })
}

function setMapGroupTransform(g: SVGGElement | null, x: number, y: number, scale: number) {
  mapVisualTransform = { x, y, scale }
  if (!g) return
  // CSS transform 走合成层，连续滚轮/拖拽时不必重算 SVG transform 属性。
  g.style.transformOrigin = '0 0'
  g.style.transform = `translate(${x}px, ${y}px) scale(${scale})`
}

function clearMapGroupTransform(g: SVGGElement | null) {
  g?.style.removeProperty('transform')
  mapVisualTransform = { x: mapView.x, y: mapView.y, scale: mapView.scale }
}

function renderMapPan() {
  if (!mapDrag) return
  const g = mapPanGroup || (mapPanGroup = mapCanvasRef.value?.querySelector('.kw-map__svg > g') || null)
  setMapGroupTransform(g, mapDrag.nextX, mapDrag.nextY, mapView.scale)
  mapDrag.raf = 0
}

function renderMapZoom() {
  if (!mapWheelPending) {
    mapWheelRaf = 0
    return
  }
  const g = mapZoomGroup || (mapZoomGroup = mapCanvasRef.value?.querySelector('.kw-map__svg > g') || null)
  setMapGroupTransform(g, mapWheelPending.x, mapWheelPending.y, mapWheelPending.scale)
  mapWheelRaf = 0
}

function commitMapZoom() {
  if (!mapWheelPending) return
  const group = mapZoomGroup
  mapView.x = mapWheelPending.x
  mapView.y = mapWheelPending.y
  mapView.scale = mapWheelPending.scale
  mapWheelPending = null
  mapWheelRect = null
  mapZoomGroup = null
  mapWheelCommitTimer = null
  mapCanvasRef.value?.classList.remove('is-zooming')
  markPerformance('graph-wheel-end', { scale: mapView.scale })
  // 等 Vue 把 mapView 写回 SVG transform 后再移除内联样式，避免一帧闪烁。
  nextTick(() => clearMapGroupTransform(group))
}

function cancelMapWheel(commit = false) {
  if (mapWheelRaf) {
    cancelAnimationFrame(mapWheelRaf)
    mapWheelRaf = 0
  }
  if (mapWheelCommitTimer) {
    clearTimeout(mapWheelCommitTimer)
    mapWheelCommitTimer = null
  }
  if (commit) commitMapZoom()
  else {
    const group = mapZoomGroup
    mapWheelPending = null
    mapWheelRect = null
    mapZoomGroup = null
    mapCanvasRef.value?.classList.remove('is-zooming')
    nextTick(() => clearMapGroupTransform(group))
  }
}

function markPerformance(action: string, detail: Record<string, any> = {}) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('openstudy:performance', { detail: { action, ...detail } }))
}

function onMapWheel(event: WheelEvent) {
  // 缩放时停止初始力导向动画，避免每一帧同时改响应式节点位置造成卡顿。
  if (mapAnimFrame) stopMapAnimation()
  if (!mapWheelPending) markPerformance('graph-wheel-start', { scale: mapView.scale })
  // 滚轮期间隐藏文字标签：200+ 节点时文字重绘是连续滚动最明显的瓶颈。
  mapCanvasRef.value?.classList.add('is-zooming')
  // 连续滚轮共用同一个 rect，避免每个 wheel 事件都触发布局计算。
  const rect = mapWheelRect || (mapWheelRect = mapCanvasRef.value?.getBoundingClientRect() || null)
  if (!rect) return
  const px = event.clientX - rect.left
  const py = event.clientY - rect.top
  const current = mapWheelPending || { x: mapView.x, y: mapView.y, scale: mapView.scale }
  mapWheelPending = computeWheelZoom(current, px, py, event.deltaY)
  // 滚轮期间只直接改 SVG transform，不触发几百个节点/边的 Vue 重渲染。
  if (!mapWheelRaf) mapWheelRaf = requestAnimationFrame(renderMapZoom)
  if (mapWheelCommitTimer) clearTimeout(mapWheelCommitTimer)
  // 留出更大的连续滚动窗口：停下后才提交响应式 mapView，避免 140ms 就整图重绘。
  mapWheelCommitTimer = setTimeout(commitMapZoom, 320)
}

function onMapDown(event: PointerEvent) {
  if (event.button !== 0) return
  stopMapAnimation()
  cancelMapWheel(true)
  mapPanGroup = null
  markPerformance('graph-pan-start')
  if (mapViewFrame) {
    cancelAnimationFrame(mapViewFrame)
    mapViewFrame = 0
  }
  mapDrag = {
    x: event.clientX,
    y: event.clientY,
    vx: mapView.x,
    vy: mapView.y,
    nextX: mapView.x,
    nextY: mapView.y,
    moved: false,
    closeDetailOnClick: detailVisible.value,
    raf: 0
  }
}

function onMapMove(event: PointerEvent) {
  if (!mapDrag) return
  const dx = event.clientX - mapDrag.x
  const dy = event.clientY - mapDrag.y
  if (Math.abs(dx) + Math.abs(dy) > 4) mapDrag.moved = true
  mapDrag.nextX = mapDrag.vx + dx
  mapDrag.nextY = mapDrag.vy + dy
  // 拖动期间只改 SVG <g> 的 transform，不写 Vue 响应式 mapView，
  // 避免每个 pointermove 都重算几百个节点/边，保住帧率。
  if (!mapDrag.raf) mapDrag.raf = requestAnimationFrame(renderMapPan)
}

function onMapUp() {
  const state = mapDrag
  if (!state) return
  if (state.raf) cancelAnimationFrame(state.raf)
  const group = mapPanGroup
  mapPanGroup = null
  mapDrag = null
  if (state.moved) {
    mapView.x = state.nextX
    mapView.y = state.nextY
  } else if (state.closeDetailOnClick && detailVisible.value) {
    // 抽屉打开时仍允许拖动图谱；只有“按下后没移动”的空白点击才关闭抽屉。
    closeDetail()
  }
  if (state.moved) markPerformance('graph-pan-end', { moved: true })
  nextTick(() => clearMapGroupTransform(group))
}

let mapSearchTimer: ReturnType<typeof setTimeout> | null = null

function focusMapSearch(force = false) {
  if (view.value !== 'map') return
  const query = String(props.searchQuery || '').trim().toLowerCase()
  if (!query) return
  const nodes = allMapNodes.value
  const exact = nodes.find((node: any) => String(node.title || '').trim().toLowerCase() === query)
  const target = exact || (force ? graphSearchSuggestions.value[0] : null)
  if (!target) return
  // 搜索命中的节点可能被类型筛选隐藏；先恢复它的类型再选中。
  mapTypeVisible[normalizeEntityKind(target.kind || target.pageType)] = true
  resetMapNodeOffsets()
  nextTick(() => {
    const current = mapNodes.value.find((node: any) => String(node.id) === String(target.id))
    if (current) selectMapNode(current)
  })
}

function selectSearchSuggestion(item: any) {
  searchSuppressed.value = true
  if (Number(item.pageId)) emit('search-selected', { pageId: Number(item.pageId) })
  mapTypeVisible[normalizeEntityKind(item.kind || item.pageType)] = true
  resetMapNodeOffsets()
  nextTick(() => {
    const current = mapNodes.value.find((node: any) => String(node.id) === String(item.id))
    if (current) selectMapNode(current)
  })
}

watch(() => props.searchQuery, () => {
  searchSuppressed.value = false
  if (mapSearchTimer) clearTimeout(mapSearchTimer)
  mapSearchTimer = setTimeout(focusMapSearch, 280)
})

watch(() => props.searchSubmitKey, () => {
  focusMapSearch(true)
})

watch(() => props.refreshKey, async () => {
  if (view.value === 'map') await switchMap()
  else await reload()
})

watch(view, (value) => {
  try {
    localStorage.setItem(WIKI_VIEW_KEY, value)
  } catch {
    // 忽略 localStorage 不可用
  }
})

watch(() => props.activeKbId, async (kbId) => {
  stopBuildPolling()
  stopMapNodeDrag()
  resetMapNodeOffsets()
  exitRoute()
  buildJob.value = null
  await reload()
  if (view.value === 'map' && kbId && !mapGraph.value.nodes?.length) {
    await switchMap()
  }
  await resumeBuildJob()
})
async function openInitialPage() {
  const pageId = Number(props.initialPageId || 0)
  if (!pageId) return
  await nextTick()
  void openPage(pageId)
}

watch(() => props.initialPageId, () => { void openInitialPage() })

onMounted(async () => {
  window.addEventListener('resize', onMapResize)
  await reload()
  await resumeBuildJob()
  await openInitialPage()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onMapResize)
  stopBuildPolling()
  stopMapNodeDrag()
  stopMapAnimation()
  cancelMapWheel()
  if (mapSearchTimer) clearTimeout(mapSearchTimer)
  if (mapViewFrame) cancelAnimationFrame(mapViewFrame)
  if (mapOpenTimer) clearTimeout(mapOpenTimer)
})
</script>

<style scoped src="./KnowledgeWikiPanel.style1.css"></style>












