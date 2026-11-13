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

    <template v-else-if="pages.length || (view === 'map' && mapGraph.nodes.length)">
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

      <div v-else ref="mapCanvasRef" class="kw-map" :class="{ 'is-advice-focus': adviceMode && !!mapSelectedPageId, 'is-map-ready': mapReady }"
        @wheel.prevent="onMapWheel" @pointerdown="onMapDown"
        @pointermove="onMapMove" @pointerup="onMapUp" @pointerleave="onMapUp">
        <div class="kw-map-purpose">知识图谱：先看懂知识结构，再让系统帮你排下一步。</div>
        <svg class="kw-map__svg" :viewBox="mapViewBox" preserveAspectRatio="xMidYMid meet" aria-label="知识图谱：知识主题与六类来源实体集">
          <defs>
            <marker id="kw-arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="10" markerHeight="7" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#9aa9c0" />
            </marker>
            <marker id="kw-arrow-hl" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="10" markerHeight="7" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#7e94bf" />
            </marker>
          </defs>
          <g :transform="`translate(${mapView.x} ${mapView.y}) scale(${mapView.scale})`">
            <path v-for="hull in mapHulls" :key="hull.key" :d="hull.path" class="kw-map-hull"
              :class="{ 'is-hovered': mapHoveredId && hull.ids.includes(String(mapHoveredId)) }" />
            <text v-for="hull in mapHulls" v-show="mapShowEntitySetLabels" :key="`label-${hull.key}`" :x="hull.labelX" :y="hull.labelY"
              class="kw-map-hull-label">{{ hull.label }}</text>
            <line v-for="edge in mapEdges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              :data-edge-source="edge.source" :data-edge-target="edge.target"
              class="kw-map-edge" :class="[`is-${edge.type}`, { 'is-cross': edge.cross, 'is-active': isMapEdgeActive(edge), 'is-dimmed': isMapEdgeDimmed(edge), 'is-current-route': isRouteEdge(edge), 'is-hidden': mapDraggingId && edge.source !== mapDraggingId && edge.target !== mapDraggingId }]"
              :marker-end="mapShowArrows ? (isMapEdgeActive(edge) ? 'url(#kw-arrow-hl)' : 'url(#kw-arrow)') : undefined">
              <title>{{ mapEdgeTitle(edge) }}</title>
            </line>
            <line v-for="line in adviceVisibleLines" :key="`advice-${line.key}`" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2"
              pathLength="1" class="kw-map-advice-ray" />
            <circle v-if="adviceActiveLine" :key="`advice-dot-${adviceActiveLine.key}`" r="3" class="kw-map-advice-dot">
              <animateMotion
                :path="`M ${adviceActiveLine.x1} ${adviceActiveLine.y1} L ${adviceActiveLine.x2} ${adviceActiveLine.y2}`"
                dur="1.5s"
                begin="0s"
                repeatCount="1"
                fill="freeze"
              />
            </circle>

            <g v-for="node in mapNodes" :key="node.id" class="kw-map-node" :data-node-id="String(node.id)"
              :class="{ 'is-selected': isMapSelected(node), 'is-hovered': mapHoveredId === String(node.id), 'is-dimmed': isMapNodeDimmed(node), 'is-bridge': bridgeNodeIds.has(String(node.id)), 'is-learned': Number(node.learning?.viewCount || 0) > 0, 'is-weak': Number(node.learning?.practiceCount || 0) > 0 && Number(node.learning?.accuracy || 0) < 60, 'is-route': isRouteNode(node), 'is-next-stop': isNextStopNode(node), 'is-advice-visited': adviceLitPageIds.includes(String(node.pageId)), 'is-advice-dimmed': adviceMode && adviceLitPageIds.length > 0 && !adviceLitPageIds.includes(String(node.pageId)) }"
              :transform="`translate(${node.x} ${node.y})`"
              @mouseenter="onMapNodeEnter(node)" @mouseleave="onMapNodeLeave(node)"
              @pointerdown.stop="onMapNodeDown($event, node)" @pointerup.stop="onMapNodeUp"
              @click.stop="onMapNodeClick(node)">
              <title>{{ node.title }}{{ node.learning ? ` · ${node.learning.label}` : '' }}</title>
              <circle class="kw-map-node__halo" :r="node.r + 8" />
              <circle v-if="mapLearnMode" class="kw-map-node__learn-track" :r="node.r + 5" />
              <circle v-if="mapLearnMode && Number(node.learning?.masteryScore || 0) > 0" class="kw-map-node__learn-ring"
                :r="node.r + 5" pathLength="100" stroke-dasharray="100"
                :stroke-dashoffset="100 - Number(node.learning?.masteryScore || 0)"
                :stroke="learningColor(node.learning)" transform="rotate(-90)" />
              <circle v-if="isMapSelected(node)" class="kw-map-node__active" :r="node.r + 7" :stroke="node.color" />
              <circle class="kw-map-node__dot" :r="node.r + (isMapSelected(node) || mapHoveredId === String(node.id) ? 3 : 0)" :fill="node.color" />
              <text v-if="showMapLabel(node)" class="kw-map-node__label" text-anchor="middle"
                :y="node.r + 14" :style="{ fontSize: `${11 / Math.max(0.8, mapView.scale)}px` }">{{ mapNodeLabel(node) }}</text>
            </g>
          </g>
        </svg>
        <aside class="kw-graph-panel" @pointerdown.stop>
          <div class="kw-graph-mode-row">
            <span>规划建议模式</span>
            <button type="button" class="kw-mode-switch" :class="{ 'is-on': adviceMode }" :aria-pressed="adviceMode"
              @click="toggleAdviceMode">
              <i></i>
            </button>
          </div>
          <template v-if="!adviceMode">
            <div class="kw-graph-panel__legend">
              <button v-for="item in activeLegend" :key="item.type" type="button" class="kw-graph-type"
                :class="{ 'is-disabled': mapTypeVisible[item.type] === false }"
                @click="toggleMapType(item.type)">
                <i :style="{ background: item.color }"></i>
                <span>{{ item.label }}</span>
                <em>{{ mapTypeCounts[item.type] || 0 }}</em>
              </button>
            </div>
            <div class="kw-graph-panel__divider"></div>
            <div class="kw-graph-relations">
              <div class="kw-graph-relations__title">连线方向：源 → 目标</div>
              <div><i class="is-doc-image"></i><span>文档 → 图片 · 包含图片</span></div>
              <div><i class="is-image-knowledge"></i><span>图片 → 知识主题 · 图片知识点</span></div>
              <div><i class="is-topic-doc"></i><span>知识主题 → 资料 · 文档/图片知识点</span></div>
              <div><i class="is-bank-topic"></i><span>知识主题 → 题库 · 题源关系</span></div>
            </div>
            <div class="kw-graph-panel__divider"></div>
            <div class="kw-graph-panel__actions">
              <button type="button" class="kw-graph-action" :class="{ 'is-active': mapHideUnlinked }"
                :disabled="!unlinkedCount" @click="toggleHideUnlinked">
                <OsIcon name="eye-off" :size="14" />
                <span>隐藏无关联页面（{{ unlinkedCount }}）</span>
              </button>
              <button type="button" class="kw-graph-action" :class="{ 'is-active': !mapShowArrows }" @click="toggleMapArrows">
                <OsIcon name="check" :size="14" />
                <span>{{ mapShowArrows ? '隐藏箭头' : '显示箭头' }}</span>
              </button>
              <button type="button" class="kw-graph-action" :class="{ 'is-active': !mapShowEntitySetLabels }"
                @click="mapShowEntitySetLabels = !mapShowEntitySetLabels">
                <OsIcon name="eye-off" :size="14" />
                <span>{{ mapShowEntitySetLabels ? '隐藏实体集名称' : '显示实体集名称' }}</span>
              </button>
              <button v-if="mapTypeCounts.image > 8" type="button" class="kw-graph-action"
                :class="{ 'is-active': mapImageExpanded }" @click="mapImageExpanded = !mapImageExpanded">
                <OsIcon name="layout-grid" :size="14" />
                <span>{{ mapImageExpanded ? '收起图片节点' : `展开图片节点（${mapTypeCounts.image}）` }}</span>
              </button>
              <button type="button" class="kw-graph-action" @click="resetGraphView">
                <OsIcon name="refresh" :size="14" />
                <span>适配视图</span>
              </button>
              <button type="button" class="kw-graph-action" @click="showRouteGuide">
                <OsIcon name="circle-help" :size="14" />
                <span>使用说明</span>
              </button>
            </div>
          </template>
          <template v-else>
            <p class="kw-advice-mode-tip">点一个节点作为起点，生成可反复调整的规划建议；不会打开知识百科抽屉。</p>
            <button type="button" class="kw-graph-action kw-route-action" :disabled="adviceLoading" @click="generateAdvice">
              <OsIcon name="sparkles" :size="14" />
              <span>{{ adviceLoading ? '正在生成…' : '生成规划建议' }}</span>
            </button>
          </template>
        </aside>
        <div v-if="!adviceMode" class="kw-graph-hint"><span>悬停/点击节点查看相关连线 · 点知识主题查看主题页，点来源节点查看资料/题库/笔记 · 右侧可开启规划建议</span></div>
      </div>
      <KnowledgeAdviceHost
        ref="adviceHostRef"
        :active-kb-id="activeKbId"
        :node-titles="adviceNodeTitles"
        @update="onAdviceUpdate"
        @focus-page="focusAdvicePage"
        @busy="adviceLoading = $event"
      />
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
        <header class="kw-detail__head">
          <div>
            <div class="kw-kicker">KNOWLEDGE PAGE</div>
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
            <el-button v-if="activePage.practice?.bankId" size="small" plain @click="goPractice">
              去练 {{ activePage.practice.questionCount }} 题
            </el-button>
            <el-button v-else size="small" plain @click="askPage('practice')">生成练习</el-button>
            <el-button size="small" type="primary" plain @click="askPage()">问 AI 这一页</el-button>
            <button type="button" class="kw-detail__close" @click="closeDetail">×</button>
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
          </div>
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

        <section v-if="activePage.sources?.length" class="kw-detail__block">
          <div class="kw-detail__block-head"><span>来源</span><b>{{ activePage.sourceDocIds?.length || 0 }} 份资料 · {{ activePage.sources.length }} 个片段</b></div>
          <button v-for="source in activePage.sources" :key="`${source.docId}-${source.chunkId}`" type="button"
            class="kw-source" @click="locateSource(source)">
            <span class="kw-source__name">{{ source.docName }}</span>
            <span class="kw-source__index">第 {{ Number(source.chunkIndex || 0) + 1 }} 段</span>
            <span class="kw-source__quote">{{ source.quote }}</span>
          </button>
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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ENTITY_TYPE_META, entityTypeMeta, normalizeEntityKind, normalizePageType, pageTypeLabel } from '../utils/knowledgeGraphMeta'
import { clusterOutline } from '../utils/knowledgeGraphGeometry'
import { useWikiPanelFilters } from './useWikiPanelFilters'
import { useWikiPanelFormatters } from './useWikiPanelFormatters'
import { useWikiMapViewCache } from './wikiMapViewCache'
import { useWikiMapLayout } from './useWikiMapLayout'
import { useWikiMapDisplay } from './useWikiMapDisplay'
import { useWikiPlanState } from './useWikiPlanState'
import { useWikiMapViewControls } from './useWikiMapViewControls'
import { WIKI_VIEW_KEY, WIKI_LEARN_KEY, WIKI_GUIDE_KEY, WIKI_ROUTE_KEY, readWikiView, readWikiLearnMode, readRouteQuery } from './wikiPanelStorage'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import { readStudyPlanConfig } from '@/utils/studyPlanState'
import { getStudyMap } from '@/api/ai/studyPlan'
import { listKbNotes } from '@/api/ai/noteKbLink'
import KnowledgeAdviceHost from './KnowledgeAdviceHost.vue'
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
const adviceMode = ref(false)
const adviceHostRef = ref<any>(null)
const adviceLoading = ref(false)
const adviceTrace = ref<any>(null)
const adviceVisitedPageIds = ref<string[]>([])
const adviceLitPageIds = ref<string[]>([])
const detailVisible = ref(false)
const pageLoading = ref(false)
const activePage = ref<any>(null)
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
const mapGraph = ref<any>({ nodes: [], edges: [], groups: [] })
const mapSize = reactive({ width: 1200, height: 760 })
const mapReady = ref(false)
const mapSwitching = ref(false)
const mapLayoutScale = computed(() => Math.min(1.8, Math.max(1, Math.min(mapSize.width / 1200, mapSize.height / 760))))
const mapViewBox = computed(() => `0 0 ${mapSize.width} ${mapSize.height}`)
const mapView = reactive({ x: 0, y: 0, scale: 1 })
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
const mapShowEntitySetLabels = ref(true)
const mapLearnMode = ref(true)
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
let mapOpenTimer: ReturnType<typeof setTimeout> | null = null
let lastDetailPageId: number | null = null

const buildActive = computed(() => buildJob.value?.status === 'running')
const buildProgress = computed(() => {
  const total = Number(buildJob.value?.total || 0)
  const done = Number(buildJob.value?.done || 0)
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0
})

const activeLegend = computed(() => ENTITY_TYPE_META)

const allMapNodes = computed(() => mapGraph.value?.nodes || [])
const mapTypeCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const node of allMapNodes.value) {
    const kind = normalizeEntityKind(node.kind || node.pageType)
    counts[kind] = (counts[kind] || 0) + 1
  }
  return counts
})
const mapConnectedNodeIds = computed(() => {
  const ids = new Set(allMapNodes.value.map((node: any) => String(node.id)))
  const connected = new Set<string>()
  for (const edge of mapGraph.value?.edges || []) {
    const source = String(edge.source || '')
    const target = String(edge.target || '')
    if (ids.has(source) && ids.has(target)) {
      connected.add(source)
      connected.add(target)
    }
  }
  return connected
})
const unlinkedCount = computed(() =>
  allMapNodes.value.filter((node: any) => !mapConnectedNodeIds.value.has(String(node.id))).length
)
const routeActive = computed(() => !!learningRoute.value?.stops?.length)

const graphSearchSuggestions = computed(() => {
  const query = String(props.searchQuery || '').trim().toLowerCase()
  if (searchSuppressed.value || !query || view.value !== 'map') return []
  return allMapNodes.value
    .filter((node: any) => {
      const detail = node.detail || {}
      const haystack = [
        node.title,
        node.summary,
        detail.summary,
        node.subtitle,
        ...(node.aliases || []),
        ...(detail.aliases || [])
      ].join(' ').toLowerCase()
      return haystack.includes(query)
    })
    .sort((a: any, b: any) => {
      const at = String(a.title || '').toLowerCase()
      const bt = String(b.title || '').toLowerCase()
      return Number(bt === query) - Number(at === query) || at.localeCompare(bt)
    })
    .slice(0, 8)
})

const mapComponents = computed(() => {
  const nodes = allMapNodes.value
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  const groups = Array.isArray(mapGraph.value?.groups) ? mapGraph.value.groups : []
  if (groups.length) {
    return {
      components: groups
        .map((group: any) => ({
          key: String(group.id || group.kind),
          kind: normalizeEntityKind(group.kind),
          label: String(group.title || entityTypeMeta(group.kind).label),
          ids: (group.nodeIds || []).map(String).filter((id: string) => byId.has(id))
        }))
        .filter((group: any) => group.ids.length),
      byId
    }
  }
  const grouped = new Map<string, string[]>()
  for (const node of nodes) {
    const kind = normalizeEntityKind(node.kind || node.pageType)
    if (!grouped.has(kind)) grouped.set(kind, [])
    grouped.get(kind)!.push(String(node.id))
  }
  return {
    components: [...grouped.entries()].map(([kind, ids]) => ({
      key: kind,
      kind,
      label: entityTypeMeta(kind).label,
      ids
    })),
    byId
  }
})

const groupKeyByNode = computed(() => {
  const result = new Map<string, string>()
  for (const component of mapComponents.value.components) {
    for (const id of component.ids) result.set(String(id), component.key)
  }
  return result
})

function isCrossSourceEdge(edge: any) {
  if (String(edge.type || '') === 'document_image') return false
  const source = allMapNodes.value.find((node: any) => String(node.id) === String(edge.source))
  const target = allMapNodes.value.find((node: any) => String(node.id) === String(edge.target))
  if (!source || !target) return false
  if (normalizeEntityKind(source.kind) === 'topic' || normalizeEntityKind(target.kind) === 'topic') return false
  return groupKeyByNode.value.get(String(edge.source)) !== groupKeyByNode.value.get(String(edge.target))
}

const bridgeNodeIds = computed(() => {
  const result = new Set<string>()
  for (const edge of mapGraph.value?.edges || []) {
    if (!isCrossSourceEdge(edge)) continue
    result.add(String(edge.source))
    result.add(String(edge.target))
  }
  return result
})

const adviceNodeTitles = computed(() => {
  const result: Record<string, string> = {}
  for (const node of mapNodes.value || []) {
    result[String(node.id)] = String(node.title || '')
    if (Number(node.pageId)) result[String(node.pageId)] = String(node.title || '')
  }
  return result
})

const adviceTraceLines = computed(() => {
  const steps = adviceTrace.value?.steps || []
  const position = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  return steps
    .map((step: any, index: number) => {
      const rawFromId = String(step.from || '')
      const rawToId = String(step.to || '')
      const from = position.get(rawFromId) || position.get(`topic:${rawFromId}`)
      const to = position.get(rawToId) || position.get(`topic:${rawToId}`)
      if (!from || !to) return null
      return {
        key: `${rawFromId}-${rawToId}-${index}`,
        fromPageId: String(from.pageId || from.id),
        toPageId: String(to.pageId || to.id),
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y
      }
    })
    .filter(Boolean) as any[]
})

// 射线逐条发射：一条线走完，才出现下一条线的新亮点。
const ADVICE_DOT_MS = 1500
const adviceVisibleLines = ref<any[]>([])
const adviceActiveLine = ref<any>(null)
let adviceLineTimers: ReturnType<typeof setTimeout>[] = []
watch(adviceTrace, (trace) => {
  adviceLineTimers.forEach((timer) => clearTimeout(timer))
  adviceLineTimers = []
  adviceVisibleLines.value = []
  adviceActiveLine.value = null
  adviceLitPageIds.value = mapSelectedPageId.value ? [String(mapSelectedPageId.value)] : []
  const lines = adviceTraceLines.value
  if (!trace?.steps?.length || !lines.length) return
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduced) {
    adviceVisibleLines.value = lines
    adviceLitPageIds.value = Array.from(
      new Set(lines.flatMap((line: any) => [line.fromPageId, line.toPageId]).filter(Boolean))
    )
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

onBeforeUnmount(() => {
  adviceLineTimers.forEach((timer) => clearTimeout(timer))
})

const mapNodes = computed(() => {
  const { components, byId } = mapComponents.value
  const sourceTypes = graphSourceTypeFilter.value
  const pageTypes = graphPageTypeFilter.value
  const learningLevels = graphLearningFilter.value
  const visibleIds = new Set(
    allMapNodes.value
      .filter((node: any) => routeActive.value || mapTypeVisible[normalizeEntityKind(node.kind || node.pageType)] !== false)
      .filter((node: any) => !sourceTypes.length || sourceTypes.includes(normalizeEntityKind(node.kind || node.pageType)))
      .filter((node: any) => {
        if (!pageTypes.length || normalizeEntityKind(node.kind) !== 'topic') return true
        return pageTypes.includes(normalizePageType(node.pageType))
      })
      .filter((node: any) => {
        if (!learningLevels.length || normalizeEntityKind(node.kind) !== 'topic') return true
        return learningLevels.includes(String(node.detail?.learning?.level || node.learning?.level || 'unread'))
      })
      .filter((node: any) => routeActive.value || !mapHideUnlinked.value || mapConnectedNodeIds.value.has(String(node.id)))
      .map((node: any) => String(node.id))
  )
  const visibleComponents = components
    .map((component) => ({ ...component, ids: component.ids.filter((id: string) => visibleIds.has(id)) }))
    .filter((component) => component.ids.length)
  const width = Number(mapSize.width || 1200)
  const height = Number(mapSize.height || 760)
  const layoutScale = Number(mapLayoutScale.value || 1)
  // 右侧实体集面板按分辨率占 220–320px；节点布局只使用左侧可用区域，避免来源组被面板盖住。
  const panelReserve = Math.min(320, Math.max(220, width * 0.12))
  const usableWidth = Math.max(640, width - panelReserve)
  const topicSpacingX = Math.round(60 * layoutScale)
  const topicSpacingY = Math.round(58 * layoutScale)
  const kindCenters: Record<string, { x: number; y: number }> = {
    topic: { x: usableWidth * 0.52, y: height * 0.5 },
    document: { x: usableWidth * 0.10, y: height * 0.64 },
    bank: { x: usableWidth * 0.90, y: height * 0.64 },
    web: { x: usableWidth * 0.10, y: height * 0.15 },
    note: { x: usableWidth * 0.52, y: height * 0.94 },
    image: { x: usableWidth * 0.90, y: height * 0.15 }
  }
  const nodePadding = 28 * Math.min(1.35, layoutScale)
  // 组间留白是硬间隔，不用“看起来差不多”；窗口小也至少保留 48px。
  const groupGap = Math.max(96, 120 * layoutScale)
  const groupLayouts = visibleComponents.map((component, componentIndex) => {
    const collapseImages = component.kind === 'image' && !mapImageExpanded.value && component.ids.length > 8
    const members = collapseImages
      ? [{
          id: IMAGE_CLUSTER_ID,
          kind: 'image',
          title: `图片资产（${component.ids.length}）`,
          subtitle: '点击展开图片节点',
          pageId: 0,
          pageType: 'image',
          degree: component.ids.length,
          sourceType: 'image',
          sourceId: 0,
          color: entityTypeMeta('image').color
        }]
      : component.ids.map((id: string) => byId.get(id)).filter(Boolean) as any[]
    const hub = [...members].sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0))[0]
    const fallbackCenter = {
      x: 80 + ((componentIndex % 3) + 0.5) * Math.max(1, (usableWidth - 160) / 3),
      y: 80 + (Math.floor(componentIndex / 3) + 0.5) * Math.max(1, (height - 160) / Math.max(1, Math.ceil(visibleComponents.length / 3)))
    }
    const center = { ...(kindCenters[component.kind] || fallbackCenter) }
    const topicCols = component.kind === 'topic'
      ? Math.max(4, Math.ceil(Math.sqrt(members.length * 0.75)))
      : 0
    const topicRows = topicCols ? Math.ceil(members.length / topicCols) : 0
    const sourceCols = component.kind !== 'topic' && members.length > 6
      ? Math.ceil(Math.sqrt(members.length))
      : 0
    const sourceRows = sourceCols ? Math.ceil(members.length / sourceCols) : 0
    const orbitRadius = (component.kind === 'topic'
      ? Math.min(260, 72 + Math.sqrt(members.length) * 24)
      : Math.min(170, 62 + Math.sqrt(members.length) * 22)) * Math.min(1.45, layoutScale)
    const maxNodeRadius = component.kind === 'topic' ? 14 : 16
    let halfWidth = maxNodeRadius + nodePadding
    let halfHeight = maxNodeRadius + nodePadding
    if (component.kind === 'topic' && topicCols) {
      halfWidth = ((topicCols - 1) / 2) * topicSpacingX + maxNodeRadius + nodePadding
      halfHeight = ((topicRows - 1) / 2) * topicSpacingY + maxNodeRadius + nodePadding
    } else if (sourceCols) {
      const sourceSpacing = 40 * layoutScale
      halfWidth = ((sourceCols - 1) / 2) * sourceSpacing + maxNodeRadius + nodePadding
      halfHeight = ((sourceRows - 1) / 2) * sourceSpacing + maxNodeRadius + nodePadding
    } else if (members.length > 1) {
      halfWidth = orbitRadius + maxNodeRadius + nodePadding
      halfHeight = halfWidth
    }
    return {
      component,
      members,
      hub,
      center,
      topicCols,
      topicRows,
      sourceCols,
      sourceRows,
      orbitRadius,
      radius: Math.max(halfWidth, halfHeight)
    }
  })
  // 如果当前窗口宽度不足以容纳最大的两组，就扩展虚拟画布；再由 fitMapView 统一缩放。
  // 这样宁可整体缩小一点，也不会把组强行压到互相重叠。
  let maxPairRadius = 0
  for (let i = 0; i < groupLayouts.length; i += 1) {
    for (let j = i + 1; j < groupLayouts.length; j += 1) {
      maxPairRadius = Math.max(maxPairRadius, groupLayouts[i]!.radius + groupLayouts[j]!.radius)
    }
  }
  const layoutWidth = Math.max(
    usableWidth,
    Math.ceil(maxPairRadius * 2 + groupGap + 36)
  )
  if (layoutWidth > usableWidth) {
    const ratio = layoutWidth / usableWidth
    groupLayouts.forEach((layout) => {
      layout.center.x = Math.round(layout.center.x * ratio)
    })
  }
  // 组间分离：把每个实体集当成有半径的圆，用简单迭代把重叠的组推开。
  // 这是实际几何计算，不再依赖某一组固定坐标，窗口变大/变小时组与组之间始终保留 gap。
  for (let pass = 0; pass < 90; pass += 1) {
    for (let i = 0; i < groupLayouts.length; i += 1) {
      const a = groupLayouts[i]!
      for (let j = i + 1; j < groupLayouts.length; j += 1) {
        const b = groupLayouts[j]!
        let dx = b.center.x - a.center.x
        let dy = b.center.y - a.center.y
        let distance = Math.hypot(dx, dy)
        const minimum = a.radius + b.radius + groupGap
        if (distance >= minimum) continue
        if (distance < 0.01) {
          dx = 1
          dy = 0
          distance = 1
        }
        const push = (minimum - distance) / 2
        const ux = dx / distance
        const uy = dy / distance
        a.center.x -= ux * push
        a.center.y -= uy * push
        b.center.x += ux * push
        b.center.y += uy * push
      }
    }
    for (const layout of groupLayouts) {
      layout.center.x = Math.min(
        Math.max(layout.radius + 18, layoutWidth - layout.radius - 18),
        Math.max(layout.radius + 18, layout.center.x)
      )
      layout.center.y = Math.min(
        Math.max(layout.radius + 18, height - layout.radius - 18),
        Math.max(layout.radius + 18, layout.center.y)
      )
    }
  }
  const result: any[] = []
  groupLayouts.forEach((layout) => {
    const { component, members, hub, center, topicCols, topicRows, sourceCols, sourceRows, orbitRadius } = layout
    const orbit = members.filter((node) => node !== hub)
    const hubOnCenter = members.length > 1
    let orbitIndex = 0
    for (let memberIndex = 0; memberIndex < members.length; memberIndex += 1) {
      const node = members[memberIndex]
      const degree = Number(node.degree || 0)
      let x = center.x
      let y = center.y
      if (component.kind === 'topic' && topicCols) {
        const col = memberIndex % topicCols
        const row = Math.floor(memberIndex / topicCols)
        x = center.x + (col - (topicCols - 1) / 2) * topicSpacingX
        y = center.y + (row - (topicRows - 1) / 2) * topicSpacingY
      } else if (sourceCols) {
        const col = memberIndex % sourceCols
        const row = Math.floor(memberIndex / sourceCols)
        const sourceSpacing = 40 * layoutScale
        x = center.x + (col - (sourceCols - 1) / 2) * sourceSpacing
        y = center.y + (row - (sourceRows - 1) / 2) * sourceSpacing
      } else if (members.length > 1 && !(hubOnCenter && node === hub)) {
        const count = orbit.length
        const angle = -Math.PI / 2 + (Math.PI * 2 * orbitIndex) / Math.max(1, count)
        const jitter = Math.sin((Number(node.id) || orbitIndex + 1) * 12.9898) * 0.16
        x = center.x + Math.cos(angle + jitter) * orbitRadius
        y = center.y + Math.sin(angle + jitter) * orbitRadius
        orbitIndex += 1
      }
      const offset = mapNodeOffsets[String(node.id)]
      // 多实体集使用稳定的分区布局，禁止复用单组阶段产生的旧力导向坐标。
      // 否则首次渲染和二次刷新时序不同，会把几组节点一起吸到旧坐标里。
      const simulated = mapComponents.value.components.length < 2
        ? mapSimPositions[String(node.id)]
        : undefined
      const kind = normalizeEntityKind(node.kind || node.pageType)
      const offsetX = Number(offset?.x)
      const offsetY = Number(offset?.y)
      const simulatedX = Number(simulated?.x)
      const simulatedY = Number(simulated?.y)
      const resolvedX = Number.isFinite(offsetX) ? offsetX : Number.isFinite(simulatedX) ? simulatedX : x
      const resolvedY = Number.isFinite(offsetY) ? offsetY : Number.isFinite(simulatedY) ? simulatedY : y
      result.push({
        ...node,
        kind,
        pageType: normalizePageType(node.pageType),
        x: resolvedX,
        y: resolvedY,
        r: Math.max(kind === 'topic' ? 5 : 9, Math.min(kind === 'topic' ? 14 : 16, 4 + Math.sqrt(Math.max(0, degree)) * 1.35)) * Math.min(1.35, layoutScale),
        color: entityTypeMeta(kind).color
      })
    }
  })
  return result
})

watch(
  () => mapGraph.value,
  () => resetMapNodeOffsets(),
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

const mapEdges = computed(() => {
  // 首屏不画线：只有悬停/选中某个节点，或处于学习路线时才显示相关连线。
  // 这样 100+ 节点的资料夹不会一进来就因为几百条 SVG 线卡住。
  const focusId = mapHoveredId.value || mapSelectedNodeId.value
  if (!focusId && !routeActive.value) return []
  const positions = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  const imageIds = new Set(
    allMapNodes.value
      .filter((node: any) => normalizeEntityKind(node.kind) === 'image')
      .map((node: any) => String(node.id))
  )
  const collapseImages = !mapImageExpanded.value && imageIds.size > 8
  const endpoint = (id: any) => collapseImages && imageIds.has(String(id)) ? IMAGE_CLUSTER_ID : String(id)
  const edges = (mapGraph.value?.edges || [])
    .map((edge: any) => {
      const sourceId = endpoint(edge.source)
      const targetId = endpoint(edge.target)
      if (sourceId === targetId) return null
      const source = positions.get(sourceId)
      const target = positions.get(targetId)
      if (!source || !target) return null
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.hypot(dx, dy) || 1
      const ux = dx / distance
      const uy = dy / distance
      const startPad = Number(source.r || 5) + 5
      const endPad = Number(target.r || 5) + 7
      return {
        key: `${sourceId}-${targetId}-${edge.type}`,
        source: sourceId,
        target: targetId,
        x1: source.x + ux * startPad,
        y1: source.y + uy * startPad,
        x2: target.x - ux * endPad,
        y2: target.y - uy * endPad,
        type: edge.type || 'related',
        label: edge.label || edge.type || '关系',
        cross: isCrossSourceEdge(edge)
      }
    })
    .filter(Boolean) as any[]
  const unique = new Map<string, any>()
  for (const edge of edges) {
    if (!unique.has(edge.key)) unique.set(edge.key, edge)
  }
  const visible = [...unique.values()]
  if (focusId) {
    return visible.filter((edge: any) => edge.source === focusId || edge.target === focusId)
  }
  return visible
})

const visibleLabelIds = computed(() => {
  const result = new Set<string>()
  const candidates = [...mapNodes.value]
    .filter((node: any) => {
      const kind = normalizeEntityKind(node.kind)
      if (node.id === IMAGE_CLUSTER_ID) return true
      if (isMapSelected(node) || isRouteNode(node) || mapHoveredId.value === String(node.id)) return true
      if (adviceLitPageIds.value.includes(String(node.pageId))) return true
      if (kind !== 'topic') {
        const component = mapComponents.value.components.find((item) => item.ids.includes(String(node.id)))
        return !(component?.kind === 'image' && component.ids.length > 8)
      }
      return mapView.scale >= 1.25 || Number(node.degree || 0) >= 12
    })
    .sort((a: any, b: any) => {
      const priority = (node: any) => {
        if (isMapSelected(node) || mapHoveredId.value === String(node.id)) return 0
        if (normalizeEntityKind(node.kind) !== 'topic') return 1
        return 2
      }
      return priority(a) - priority(b) || Number(b.degree || 0) - Number(a.degree || 0)
    })
  const occupied: Array<{ left: number; right: number; top: number; bottom: number }> = []
  for (const node of candidates) {
    const title = mapNodeLabel(node)
    if (!title) continue
    const screenX = Number(node.x) * Number(mapView.scale) + Number(mapView.x)
    const screenY = Number(node.y) * Number(mapView.scale) + Number(mapView.y) + Number(node.r) + 14
    const width = Math.max(34, title.length * 11)
    const box = { left: screenX - width / 2, right: screenX + width / 2, top: screenY - 12, bottom: screenY + 4 }
    const overlaps = occupied.some((item) => !(box.right < item.left || box.left > item.right || box.bottom < item.top || box.top > item.bottom))
    if (overlaps) continue
    occupied.push(box)
    result.add(String(node.id))
  }
  return result
})

function learningReason(node: any) {
  const routeStop = (learningRoute.value?.stops || []).find(
    (stop: any) => Number(stop.pageId) === Number(node?.pageId ?? node?.id)
  )
  if (routeStop?.reason) return routeStop.reason
  const learning = node?.learning || {}
  const accuracy = Number(learning.accuracy || 0)
  if (!Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
    return `还没读过 · 连接 ${Number(node?.degree || 0)} 个主题`
  }
  if (Number(learning.practiceCount || 0) && accuracy < 60) {
    return `练习正确率 ${accuracy}% · 建议回看`
  }
  if (Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
    return '已读但还没练过'
  }
  if (Number(learning.practiceCount || 0) && accuracy < 80) {
    return `正确率 ${accuracy}% · 再练一轮`
  }
  if (learning.level === 'mastered') return '已掌握 · 可快速复习'
  return '按图谱连接继续探索'
}

const mapLearnSummary = computed(() => {
  const nodes = mapNodes.value
  const read = nodes.filter((node: any) => Number(node.learning?.viewCount || 0) > 0).length
  const practiced = nodes.filter((node: any) => Number(node.learning?.practiceCount || 0) > 0).length
  const mastered = nodes.filter((node: any) => node.learning?.level === 'mastered').length
  const weak = nodes.filter((node: any) => {
    const learning = node.learning || {}
    return Number(learning.practiceCount || 0) > 0 && Number(learning.accuracy || 0) < 60
  }).length
  return {
    total: nodes.length,
    read,
    practiced,
    mastered,
    weak,
    coverage: nodes.length ? Math.round((read / nodes.length) * 100) : 0
  }
})

const learningRecommendations = computed(() =>
  [...mapNodes.value]
    .map((node: any) => ({ node, score: learningPriority(node), reason: learningReason(node) }))
    .sort((a, b) => b.score - a.score || Number(b.node.degree || 0) - Number(a.node.degree || 0))
    .slice(0, 3)
)

const routeStopsView = computed(() => {
  const byId = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  return (learningRoute.value?.stops || [])
    .map((stop: any) => {
      const node = byId.get(String(stop.pageId))
      return node ? { ...stop, node } : null
    })
    .filter(Boolean) as any[]
})

const activeRouteStop = computed(() =>
  routeStopsView.value.find((stop: any) => stop.status === 'current') ||
  routeStopsView.value.find((stop: any) => stop.learning?.level !== 'mastered') ||
  routeStopsView.value[0] ||
  null
)

const offRoutePage = computed(() => {
  if (!routeActive.value || !detailVisible.value || !activePage.value) return null
  const pageId = Number(activePage.value.pageId)
  const inRoute = (learningRoute.value?.stops || []).some(
    (stop: any) => Number(stop.pageId) === pageId
  )
  return inRoute ? null : activePage.value
})

const nextLearningStep = computed(() => {
  const routeStop = activeRouteStop.value
  if (routeStop?.node) return { node: routeStop.node, reason: routeStop.reason }
  return learningRecommendations.value[0] || null
})

const learningPathItems = computed(() => {
  if (routeStopsView.value.length) {
    return routeStopsView.value.map((stop: any) => ({ node: stop.node, reason: stop.reason }))
  }
  const byId = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  return mapLearningPath.value
    .map((id) => {
      const node = byId.get(id)
      return node ? { node, reason: learningReason(node) } : null
    })
    .filter(Boolean) as Array<{ node: any; reason: string }>
})

const learningPathD = computed(() => {
  const items = learningPathItems.value
  if (items.length < 2) return ''
  const edges = learningRoute.value?.edges || []
  const routeEdgeSet = new Set(
    edges.map((edge: any) => `${String(edge.source)}|${String(edge.target)}`)
  )
  const segments: string[] = []
  for (let index = 1; index < items.length; index += 1) {
    const previous = items[index - 1].node
    const current = items[index].node
    const forward = `${String(previous.id)}|${String(current.id)}`
    const backward = `${String(current.id)}|${String(previous.id)}`
    // 只画图谱里真实存在的相邻边；没有边就不画，绝不把启发式顺序伪装成前置关系。
    if (!routeEdgeSet.has(forward) && !routeEdgeSet.has(backward)) continue
    segments.push(`M${Number(previous.x)} ${Number(previous.y)} L${Number(current.x)} ${Number(current.y)}`)
  }
  return segments.join(' ')
})

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

function toggleAdviceMode() {
  adviceMode.value = !adviceMode.value
  if (adviceMode.value) {
    view.value = 'map'
    detailVisible.value = false
  } else {
    adviceTrace.value = null
    adviceVisitedPageIds.value = []
    adviceLitPageIds.value = []
  }
}

function generateAdvice() {
  if (!adviceMode.value) {
    adviceMode.value = true
    view.value = 'map'
  }
  if (mapSelectedPageId.value) {
    nextTick(() => adviceHostRef.value?.generateForPage?.(Number(mapSelectedPageId.value)))
  } else {
    nextTick(() => adviceHostRef.value?.open?.())
  }
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

/** 旧入口：不再跳学习计划页，直接在当前知识图谱里开启建议模式。 */
function openStudyPlan() {
  adviceMode.value = true
  view.value = 'map'
  detailVisible.value = false
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

function animateMapViewTo(targetX: number, targetY: number, targetScale = mapView.scale, duration = 360) {
  cancelMapWheel(true)
  if (mapViewFrame) cancelAnimationFrame(mapViewFrame)
  const from = { x: Number(mapView.x), y: Number(mapView.y), scale: Number(mapView.scale) }
  const to = { x: Number(targetX), y: Number(targetY), scale: Number(targetScale) }
  const start = performance.now()
  const tick = (now: number) => {
    const progress = Math.min(1, (now - start) / Math.max(1, duration))
    const eased = 1 - Math.pow(1 - progress, 3)
    mapView.x = from.x + (to.x - from.x) * eased
    mapView.y = from.y + (to.y - from.y) * eased
    mapView.scale = from.scale + (to.scale - from.scale) * eased
    if (progress < 1) {
      mapViewFrame = requestAnimationFrame(tick)
    } else {
      mapViewFrame = 0
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
  // 把选中节点移到画布左侧中央，右侧留给详情抽屉。
  // 用 rAF 做镜头移动，而不是瞬移；节点选中环和周围灰化同时生效。
  const targetScale = Math.max(0.9, Math.min(1.25, Number(mapView.scale) || 1))
  animateMapViewTo(
    mapSize.width * 0.32 - Number(node.x) * targetScale,
    mapSize.height * 0.5 - Number(node.y) * targetScale,
    targetScale,
    360
  )
  if (mapOpenTimer) clearTimeout(mapOpenTimer)
  mapOpenTimer = null
  if (!openDetail) return
  const pageId = Number(node.pageId)
  if (!pageId) {
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
    openPage(pageId)
  }, 260)
}

function onMapNodeClick(node: any) {
  if (suppressMapNodeClick || mapNodeDrag?.moved) {
    suppressMapNodeClick = false
    mapNodeDrag = null
    return
  }
  if (adviceMode.value) {
    const pageId = Number(node.pageId)
    // 再次点击同一个节点 = 取消选中，恢复图谱原状。
    if (mapSelectedNodeId.value === String(node.id) || (pageId > 0 && Number(mapSelectedPageId.value) === pageId)) {
      mapSelectedPageId.value = null
      mapSelectedNodeId.value = null
      detailVisible.value = false
      adviceHostRef.value?.clear?.()
      adviceTrace.value = null
      adviceVisitedPageIds.value = []
      adviceLitPageIds.value = []
      return
    }
    // 建议模式只选中节点并把它移到视野中央，不打开知识百科详情抽屉。
    detailVisible.value = false
    selectMapNode(node, false)
    adviceHostRef.value?.generateForNode?.(node)
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

function onMapNodeDown(event: PointerEvent, node: any) {
  if (event.button !== 0 || detailVisible.value) return
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
  if (detailVisible.value) {
    stopMapNodeDrag()
    return
  }
  const dx = (event.clientX - mapNodeDrag.startX) / mapView.scale
  const dy = (event.clientY - mapNodeDrag.startY) / mapView.scale
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
    mapNodeOffsets[state.nodeId] = { x: state.x, y: state.y }
    // 拖出当前画布时扩展世界尺寸，保证节点与实体集轮廓不会被 viewBox 裁成直线。
    const margin = 180
    if (state.x > mapSize.width - margin) mapSize.width = Math.ceil(state.x + margin)
    if (state.y > mapSize.height - margin) mapSize.height = Math.ceil(state.y + margin)
    if (state.x < margin) {
      const shift = margin - state.x
      mapSize.width = Math.ceil(mapSize.width + shift)
      Object.keys(mapNodeOffsets).forEach((key) => {
        mapNodeOffsets[key] = { x: mapNodeOffsets[key].x + shift, y: mapNodeOffsets[key].y }
      })
      mapView.x += shift
    }
    if (state.y < margin) {
      const shift = margin - state.y
      mapSize.height = Math.ceil(mapSize.height + shift)
      Object.keys(mapNodeOffsets).forEach((key) => {
        mapNodeOffsets[key] = { x: mapNodeOffsets[key].x, y: mapNodeOffsets[key].y + shift }
      })
      mapView.y += shift
    }
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
  // 六类实体集使用预先计算的稳定分区布局；初始力导向会让不同实体集互相挤压，
  // 第一屏看起来像“几个图叠在一起”，因此分组图不再启动自动力导向。
  if (mapComponents.value.components.length >= 2) {
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
    for (let i = 0; i < mapSimNodes.length; i++) {
      const a = mapSimNodes[i]!
      for (let j = i + 1; j < mapSimNodes.length; j++) {
        const b = mapSimNodes[j]!
        const dx = b.x - a.x
        const dy = b.y - a.y
        const distance = Math.hypot(dx, dy) || 1
        const force = (12000 * mapSimAlpha) / Math.max(distance * distance, 100)
        const fx = (dx / distance) * force
        const fy = (dy / distance) * force
        a.vx -= fx
        a.vy -= fy
        b.vx += fx
        b.vy += fy
      }
    }
    for (const edge of mapEdges.value) {
      const source = byId.get(edge.source)
      const target = byId.get(edge.target)
      if (!source || !target) continue
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.hypot(dx, dy) || 1
      const degree = Math.max(1, Math.sqrt(Math.max(1, (source.degree || 0) + (target.degree || 0))))
      const force = ((distance - 140) * 0.003 * mapSimAlpha) / degree
      const fx = (dx / distance) * force
      const fy = (dy / distance) * force
      source.vx += fx
      source.vy += fy
      target.vx -= fx
      target.vy -= fy
    }
    for (const node of mapSimNodes) {
      node.vx *= 0.6
      node.vy *= 0.6
      const speed = Math.hypot(node.vx, node.vy)
      if (speed > 20) {
        node.vx *= 20 / speed
        node.vy *= 20 / speed
      }
      node.x = Math.max(40, Math.min(960, node.x + node.vx))
      node.y = Math.max(40, Math.min(600, node.y + node.vy))
      mapSimPositions[node.id] = { x: node.x, y: node.y }
    }
    mapAnimFrame = requestAnimationFrame(tick)
  }
  mapAnimFrame = requestAnimationFrame(tick)
}


const mapHulls = computed(() => {
  const nodes = mapNodes.value
  if (!nodes.length) return []
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  const visibleIds = new Set(byId.keys())
  const hulls: any[] = []
  for (const component of mapComponents.value.components) {
    const ids = component.ids.filter((id: string) => visibleIds.has(id))
    if (!ids.length) continue
    const points = ids.map((id: string) => byId.get(id)).filter(Boolean)
    if (!points.length) continue
    const minX = Math.min(...points.map((point: any) => Number(point.x || 0)))
    const minY = Math.min(...points.map((point: any) => Number(point.y || 0)))
    hulls.push({
      key: component.key,
      ids,
      label: component.label,
      labelX: minX - 6,
      labelY: minY - 24,
      path: clusterOutline(points, 18 * Math.min(1.35, mapLayoutScale.value))
    })
  }
  return hulls
})

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
  resetMapNodeOffsets, toggleMapType, toggleHideUnlinked, toggleMapArrows, resetGraphView
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
      limit: 300
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
  const node = (mapGraph.value?.nodes || []).find((item: any) => Number(item.pageId) === Number(pageId))
  if (node) node.learning = learning

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
  mapSelectedPageId.value = Number(pageId)
  lastDetailPageId = Number(pageId)
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

function renderMapPan() {
  if (!mapDrag) return
  const g = mapCanvasRef.value?.querySelector('.kw-map__svg > g')
  if (g) {
    g.setAttribute(
      'transform',
      `translate(${mapDrag.nextX} ${mapDrag.nextY}) scale(${mapView.scale})`
    )
  }
  mapDrag.raf = 0
}

function renderMapZoom() {
  if (!mapWheelPending) {
    mapWheelRaf = 0
    return
  }
  const g = mapCanvasRef.value?.querySelector('.kw-map__svg > g')
  if (g) {
    g.setAttribute(
      'transform',
      `translate(${mapWheelPending.x} ${mapWheelPending.y}) scale(${mapWheelPending.scale})`
    )
  }
  mapWheelRaf = 0
}

function commitMapZoom() {
  if (!mapWheelPending) return
  mapView.x = mapWheelPending.x
  mapView.y = mapWheelPending.y
  mapView.scale = mapWheelPending.scale
  mapWheelPending = null
  mapWheelCommitTimer = null
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
  else mapWheelPending = null
}

function onMapWheel(event: WheelEvent) {
  // 缩放时停止初始力导向动画，避免每一帧同时改响应式节点位置造成卡顿。
  if (mapAnimFrame) stopMapAnimation()
  const rect = mapCanvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const px = event.clientX - rect.left
  const py = event.clientY - rect.top
  const current = mapWheelPending || { x: mapView.x, y: mapView.y, scale: mapView.scale }
  const old = current.scale
  const next = Math.max(0.35, Math.min(3, old * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
  const wx = (px - current.x) / old
  const wy = (py - current.y) / old
  mapWheelPending = { x: px - wx * next, y: py - wy * next, scale: next }
  // 滚轮期间只直接改 SVG transform，不触发几百个节点/边的 Vue 重渲染。
  if (!mapWheelRaf) mapWheelRaf = requestAnimationFrame(renderMapZoom)
  if (mapWheelCommitTimer) clearTimeout(mapWheelCommitTimer)
  mapWheelCommitTimer = setTimeout(commitMapZoom, 140)
}

function onMapDown(event: PointerEvent) {
  if (event.button !== 0) return
  stopMapAnimation()
  cancelMapWheel(true)
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
  mapDrag = null
  if (state.moved) {
    mapView.x = state.nextX
    mapView.y = state.nextY
  } else if (state.closeDetailOnClick && detailVisible.value) {
    // 抽屉打开时仍允许拖动图谱；只有“按下后没移动”的空白点击才关闭抽屉。
    closeDetail()
  }
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












