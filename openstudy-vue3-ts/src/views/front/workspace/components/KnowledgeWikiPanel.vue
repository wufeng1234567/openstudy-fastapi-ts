<template>
  <section class="kw-page" :class="{ 'kw-page--graph': view === 'map' }">
    <Teleport to="#workspace-wiki-search-dropdown">
      <div v-if="view === 'map' && graphSearchSuggestions.length" class="kw-graph-search-dropdown">
        <button v-for="item in graphSearchSuggestions" :key="item.pageId" type="button"
          class="kw-graph-search-item" @click="selectSearchSuggestion(item)">
          <span class="kw-graph-search-item__dot" :style="{ background: pageTypeMeta(item.pageType).color }"></span>
          <span class="kw-graph-search-item__main">
            <b>{{ item.title }}</b>
            <em>{{ item.summary || '打开主题页查看内容' }}</em>
          </span>
          <span class="kw-graph-search-item__type">{{ pageTypeMeta(item.pageType).label }}</span>
        </button>
      </div>
    </Teleport>
    <Teleport to="#workspace-wiki-toolbar">
      <div class="kw-context-actions">
        <div class="kw-switch">
          <button type="button" :class="{ 'is-active': view === 'pages' }" @click="view = 'pages'">主题页</button>
          <button type="button" :class="{ 'is-active': view === 'map' }" :disabled="!pages.length" @click="switchMap">知识图谱</button>
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

    <template v-else-if="pages.length">
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

      <div v-else ref="mapCanvasRef" class="kw-map" :class="{ 'is-advice-focus': adviceMode && !!mapSelectedPageId }"
        @wheel.prevent="onMapWheel" @pointerdown="onMapDown"
        @pointermove="onMapMove" @pointerup="onMapUp" @pointerleave="onMapUp">
        <div class="kw-map-purpose">知识图谱：先看懂知识结构，再让系统帮你排下一步。</div>
        <svg class="kw-map__svg" viewBox="0 0 1000 640" aria-label="知识图谱：每个主题页一个节点">
          <defs>
            <marker id="kw-arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#aeb5c0" />
            </marker>
            <marker id="kw-arrow-hl" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#7e94bf" />
            </marker>
          </defs>
          <g :transform="`translate(${mapView.x} ${mapView.y}) scale(${mapView.scale})`">
            <path v-for="hull in mapHulls" :key="hull.key" :d="hull.path" class="kw-map-hull"
              :class="{ 'is-hovered': mapHoveredId && hull.ids.includes(String(mapHoveredId)) }" />
            <line v-for="edge in mapEdges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              :data-edge-source="edge.source" :data-edge-target="edge.target"
              class="kw-map-edge" :class="[`is-${edge.type}`, { 'is-active': isMapEdgeActive(edge), 'is-dimmed': isMapEdgeDimmed(edge), 'is-current-route': isRouteEdge(edge), 'is-hidden': mapDraggingId && edge.source !== mapDraggingId && edge.target !== mapDraggingId }]"
              :marker-end="mapShowArrows ? (isMapEdgeActive(edge) ? 'url(#kw-arrow-hl)' : 'url(#kw-arrow)') : undefined" />
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
              :class="{ 'is-selected': isMapSelected(node), 'is-hovered': mapHoveredId === String(node.id), 'is-dimmed': isMapNodeDimmed(node), 'is-learned': Number(node.learning?.viewCount || 0) > 0, 'is-weak': Number(node.learning?.practiceCount || 0) > 0 && Number(node.learning?.accuracy || 0) < 60, 'is-route': isRouteNode(node), 'is-next-stop': isNextStopNode(node), 'is-advice-visited': adviceLitPageIds.includes(String(node.pageId)), 'is-advice-dimmed': adviceMode && adviceLitPageIds.length > 0 && !adviceLitPageIds.includes(String(node.pageId)) }"
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
              <text v-if="showMapLabel(node)" class="kw-map-node__label" text-anchor="middle" :y="node.r + 14">{{ node.title }}</text>
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
              <button v-for="item in pageTypeLegend" :key="item.type" type="button" class="kw-graph-type"
                :class="{ 'is-disabled': mapTypeVisible[item.type] === false }"
                @click="toggleMapType(item.type)">
                <i :style="{ background: item.color }"></i>
                <span>{{ item.label }}</span>
                <em>{{ mapTypeCounts[item.type] || 0 }}</em>
              </button>
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
        <div v-if="!adviceMode" class="kw-graph-hint"><span>点节点查看主题页 · 右侧开启规划建议模式后可生成建议</span></div>
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

        <div v-if="activePage.learning" class="kw-detail__learning">
          <div class="kw-detail__learning-head">
            <span>学习状态</span>
            <b :class="`is-${activePage.learning.level}`">{{ activePage.learning.label }}</b>
          </div>
          <div class="kw-detail__learning-bar">
            <i :class="`is-${activePage.learning.level}`" :style="{ width: `${activePage.learning.masteryScore}%` }"></i>
          </div>
          <div class="kw-detail__learning-meta">
            <span>读过 {{ activePage.learning.viewCount }} 次</span>
            <span>练过 {{ activePage.learning.practiceCount }} 题</span>
            <span v-if="activePage.learning.practiceCount">正确率 {{ activePage.learning.accuracy }}%</span>
          </div>
        </div>

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
          基于 {{ activePage.sourceDocIds?.length || 0 }} 份资料生成 · {{ formatTime(activePage.updateTime) }}
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
          <span class="kw-update-item__type">{{ { document: '文档', image: '图片', bank: '题库', web: '网页' }[wikiUpdateType] }}</span>
          <span class="kw-update-item__main">
            <b>{{ item.title }}</b>
            <em>{{ item.subtitle || '更新这个来源对应的主题页' }}</em>
          </span>
          <OsIcon name="chevron-right" :size="14" />
        </button>
        <div v-if="!wikiUpdateLoading && !wikiUpdateOptions.length" class="kw-update-empty">
          这个资料夹暂时没有可更新的{{ { document: '文档', image: '图片', bank: '题库', web: '网页' }[wikiUpdateType] }}来源。
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
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import { readStudyPlanConfig, saveStudyPlanConfig } from '@/utils/studyPlanState'
import { getStudyMap } from '@/api/ai/studyPlan'
import KnowledgeAdviceHost from './KnowledgeAdviceHost.vue'
import KnowledgeWikiEditor from './KnowledgeWikiEditor.vue'
import {
  addWikiPageLink,
  attachWikiImage,
  buildWikiPages,
  buildWikiSource,
  detachWikiImage,
  getLatestWikiBuildJob,
  getLearningRoute,
  getStudyPlan,
  getWikiBuildJob,
  getWikiGraph,
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
}>()

const emit = defineEmits<{
  (e: 'stats', payload: { total: number }): void
  (e: 'locate', payload: { docId: number; chunkId?: number; chunkIndex?: number }): void
  (e: 'ask', prompt: string): void
  (e: 'search-selected', payload: { pageId: number }): void
}>()

const PAGE_TYPE_META = [
  { type: 'summary', label: '摘要', color: '#3B7CFF' },
  { type: 'entity', label: '实体', color: '#2F9E8F' },
  { type: 'concept', label: '概念', color: '#F08A24' },
  { type: 'synthesis', label: '综合', color: '#2D8CF0' },
  { type: 'comparison', label: '对比', color: '#D95757' },
  { type: 'overview', label: '总览', color: '#8A94A6' }
]
const mapTypeVisible = reactive<Record<string, boolean>>(
  Object.fromEntries(PAGE_TYPE_META.map((item) => [item.type, true]))
)

const loading = ref(false)
const building = ref(false)
const buildJob = ref<any>(null)
const pages = ref<any[]>([])
const wikiUpdateVisible = ref(false)
const wikiUpdateType = ref<'document' | 'image' | 'bank' | 'web'>('document')
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
const WIKI_VIEW_KEY = 'openstudy.workspace.wikiView'
const WIKI_LEARN_KEY = 'openstudy.workspace.wikiLearnMode'
const WIKI_GUIDE_KEY = 'openstudy.workspace.routeGuideSeen'
const WIKI_ROUTE_KEY = 'openstudy.workspace.routeQuery'
function readWikiView(): 'pages' | 'map' {
  try {
    return localStorage.getItem(WIKI_VIEW_KEY) === 'map' ? 'map' : 'pages'
  } catch {
    return 'pages'
  }
}
function readWikiLearnMode(): boolean {
  try {
    return localStorage.getItem(WIKI_LEARN_KEY) !== '0'
  } catch {
    return true
  }
}
function readRouteQuery(): { strategy: 'weakness' | 'foundation' | 'explore'; targetPageId: number | null } | null {
  try {
    const raw = sessionStorage.getItem(WIKI_ROUTE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw)
    const strategy = ['weakness', 'foundation', 'explore'].includes(value?.strategy)
      ? value.strategy
      : 'weakness'
    return {
      strategy,
      targetPageId: Number(value?.targetPageId) || null
    }
  } catch {
    return null
  }
}
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
const editorVisible = ref(false)
const revisionVisible = ref(false)
const revisions = ref<any[]>([])
const galleryPickerVisible = ref(false)
const galleryLoading = ref(false)
const galleryItems = ref<any[]>([])

const mapCanvasRef = ref<HTMLElement | null>(null)
const mapGraph = ref<any>({ nodes: [], edges: [] })
const mapView = reactive({ x: 0, y: 0, scale: 1 })
const mapHoveredId = ref<string | null>(null)
const mapSelectedPageId = ref<number | null>(null)
const searchSuppressed = ref(false)
const mapHideUnlinked = ref(false)
const mapShowArrows = ref(true)
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

const filteredPages = computed(() => {
  const query = String(props.searchQuery || '').trim().toLowerCase()
  if (!query) return pages.value
  return pages.value.filter((page: any) =>
    `${page.title || ''} ${page.summary || ''}`.toLowerCase().includes(query)
  )
})

const linkTargets = computed(() =>
  pages.value.filter((page: any) => Number(page.pageId) !== Number(activePage.value?.pageId))
)

/** 同一目标页 + 同一锚文本的多次正文出现合并成一行，避免摘要/各小节重复刷屏。 */
function groupLinkItems(items: any[] = []) {
  const grouped = new Map<string, any>()
  for (const item of items) {
    const key = `${item.pageId}:${item.anchorText || ''}`
    let entry = grouped.get(key)
    if (!entry) {
      entry = { ...item, sectionIndexes: [] as number[] }
      grouped.set(key, entry)
    }
    const sectionIndex = Number(item.sectionIndex)
    if (!entry.sectionIndexes.includes(sectionIndex)) entry.sectionIndexes.push(sectionIndex)
  }
  return Array.from(grouped.values())
    .map((item) => ({
      ...item,
      sectionIndexes: [...item.sectionIndexes].sort((a: number, b: number) => a - b)
    }))
    .sort((a, b) => String(a.title || '').localeCompare(String(b.title || '')))
}

const groupedOutLinks = computed(() => groupLinkItems(activePage.value?.outLinks || []))
const groupedInLinks = computed(() => groupLinkItems(activePage.value?.inLinks || []))

const buildActive = computed(() => buildJob.value?.status === 'running')
const buildProgress = computed(() => {
  const total = Number(buildJob.value?.total || 0)
  const done = Number(buildJob.value?.done || 0)
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0
})

const pageTypeLegend = computed(() =>
  PAGE_TYPE_META.filter((item) => item.type !== 'overview')
)

const allMapNodes = computed(() => mapGraph.value?.nodes || [])
const mapTypeCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const node of allMapNodes.value) {
    const type = normalizePageType(node.pageType)
    counts[type] = (counts[type] || 0) + 1
  }
  return counts
})
const unlinkedCount = computed(() =>
  allMapNodes.value.filter((node: any) => Number(node.degree || 0) === 0).length
)
const routeActive = computed(() => !!learningRoute.value?.stops?.length)

const graphSearchSuggestions = computed(() => {
  const query = String(props.searchQuery || '').trim().toLowerCase()
  if (searchSuppressed.value || !query || view.value !== 'map') return []
  return allMapNodes.value
    .filter((node: any) => {
      const haystack = `${node.title || ''} ${node.summary || ''} ${(node.aliases || []).join(' ')}`.toLowerCase()
      return haystack.includes(query)
    })
    .sort((a: any, b: any) => {
      const at = String(a.title || '').toLowerCase()
      const bt = String(b.title || '').toLowerCase()
      return Number(bt === query) - Number(at === query) || at.localeCompare(bt)
    })
    .slice(0, 8)
})

function normalizePageType(value?: string) {
  const type = String(value || '').trim()
  if (type === 'topic' || !type) return 'concept'
  return type
}

function pageTypeMeta(value?: string) {
  const type = normalizePageType(value)
  return PAGE_TYPE_META.find((item) => item.type === type) || PAGE_TYPE_META[2]
}

function pageTypeLabel(value?: string) {
  return pageTypeMeta(value).label
}

const mapComponents = computed(() => {
  const nodes = allMapNodes.value
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  // 以资料（文档）为聚类边界：同一份资料的主题页放在同一个灰色包裹区，
  // 跨资料页面链接仍然作为边绘制，但不把两块灰色区域粘成一团。
  const grouped = new Map<string, string[]>()
  for (const node of nodes) {
    const rawDocs = Array.isArray(node.docIds) ? node.docIds : []
    const primaryDoc = rawDocs.length ? String(rawDocs[0]) : '__none__'
    if (!grouped.has(primaryDoc)) grouped.set(primaryDoc, [])
    grouped.get(primaryDoc)!.push(String(node.id))
  }
  const components = [...grouped.values()].sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]))
  return { components, byId }
})

const adviceNodeTitles = computed(() => {
  const result: Record<string, string> = {}
  for (const node of mapNodes.value || []) result[String(node.pageId)] = String(node.title || '')
  return result
})

const adviceTraceLines = computed(() => {
  const steps = adviceTrace.value?.steps || []
  const position = new Map(mapNodes.value.map((node: any) => [String(node.pageId), node]))
  return steps
    .map((step: any, index: number) => {
      const fromId = String(step.from || '').replace(/^topic:/, '')
      const toId = String(step.to || '').replace(/^topic:/, '')
      const from = position.get(fromId)
      const to = position.get(toId)
      if (!from || !to) return null
      return {
        key: `${fromId}-${toId}-${index}`,
        fromPageId: fromId,
        toPageId: toId,
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
  const visibleIds = new Set(
    allMapNodes.value
      .filter((node: any) => routeActive.value || mapTypeVisible[normalizePageType(node.pageType)] !== false)
      .filter((node: any) => routeActive.value || !mapHideUnlinked.value || Number(node.degree || 0) > 0)
      .map((node: any) => String(node.id))
  )
  const visibleComponents = components
    .map((component) => component.filter((id) => visibleIds.has(id)))
    .filter((component) => component.length)
  const centerSets: Record<number, { x: number; y: number }[]> = {
    1: [{ x: 500, y: 320 }],
    2: [{ x: 340, y: 300 }, { x: 760, y: 485 }],
    3: [{ x: 250, y: 210 }, { x: 750, y: 210 }, { x: 500, y: 525 }],
    4: [{ x: 260, y: 210 }, { x: 740, y: 210 }, { x: 260, y: 510 }, { x: 740, y: 510 }]
  }
  const centers = centerSets[visibleComponents.length] || visibleComponents.map((_, index) => ({
    x: 220 + (index % 3) * 280,
    y: 180 + Math.floor(index / 3) * 250
  }))
  const result: any[] = []
  visibleComponents.forEach((component, componentIndex) => {
    const members = component.map((id) => byId.get(id)).filter(Boolean) as any[]
    const hub = [...members].sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0))[0]
    const center = centers[componentIndex] || centers[centers.length - 1]
    const radius = Math.min(160, 54 + Math.sqrt(members.length) * 20)
    const orbit = members.filter((node) => node !== hub)
    const hubOnCenter = members.length > 1
    let orbitIndex = 0
    for (const node of members) {
      const degree = Number(node.degree || 0)
      const pageType = normalizePageType(node.pageType)
      let x = center.x
      let y = center.y
      if (members.length > 1 && !(hubOnCenter && node === hub)) {
        const count = orbit.length
        const angle = -Math.PI / 2 + (Math.PI * 2 * orbitIndex) / Math.max(1, count)
        const jitter = Math.sin((Number(node.id) || orbitIndex + 1) * 12.9898) * 0.16
        x = center.x + Math.cos(angle + jitter) * radius
        y = center.y + Math.sin(angle + jitter) * radius
        orbitIndex += 1
      }
      const offset = mapNodeOffsets[String(node.id)]
      const simulated = mapSimPositions[String(node.id)]
      result.push({
        ...node,
        pageType,
        x: offset?.x ?? simulated?.x ?? x,
        y: offset?.y ?? simulated?.y ?? y,
        // 与 WeKnora 的 graphNodeRadius 同一条公式：叶子小、枢纽大。
        r: Math.max(5, Math.min(20, 4 + Math.sqrt(Math.max(0, degree)) * 1.8)),
        color: pageTypeMeta(pageType).color
      })
    }
  })
  return result
})

const mapEdges = computed(() => {
  const positions = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  return (mapGraph.value?.edges || [])
    .map((edge: any) => {
      const source = positions.get(String(edge.source))
      const target = positions.get(String(edge.target))
      if (!source || !target) return null
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.hypot(dx, dy) || 1
      const ux = dx / distance
      const uy = dy / distance
      const startPad = Number(source.r || 5) + 5
      const endPad = Number(target.r || 5) + 7
      return {
        key: `${edge.source}-${edge.target}-${edge.type}`,
        source: String(edge.source),
        target: String(edge.target),
        x1: source.x + ux * startPad,
        y1: source.y + uy * startPad,
        x2: target.x - ux * endPad,
        y2: target.y - uy * endPad,
        type: edge.type || 'related'
      }
    })
    .filter(Boolean)
})

const learningLegend = [
  { level: 'unread', label: '未学', color: '#cbd3df' },
  { level: 'reading', label: '已读', color: '#5b8def' },
  { level: 'practicing', label: '练习中', color: '#f0a13a' },
  { level: 'mastered', label: '已掌握', color: '#2f9e8f' }
]

function learningColor(learning: any) {
  return learningLegend.find((item) => item.level === learning?.level)?.color || '#cbd3df'
}

function learningPriority(node: any) {
  const learning = node?.learning || {}
  const accuracy = Number(learning.accuracy || 0)
  const degree = Number(node?.degree || 0)
  if (!Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
    return 100 + degree * 2
  }
  if (Number(learning.practiceCount || 0) && accuracy < 60) {
    return 140 + (60 - accuracy)
  }
  if (Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
    return 70 + degree
  }
  if (Number(learning.practiceCount || 0) && accuracy < 80) return 60
  if (learning.level === 'mastered') return 10
  return 20
}

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

/** 计划快照只存“可重建状态 + 当前视图”，不把前端勾选当完成态。 */
function persistPlanState(plan: any) {
  if (!plan) return
  saveStudyPlanConfig({
    kbId: Number(props.activeKbId || 0),
    goal: plan.intent?.goal || routeStrategy.value,
    examDate: plan.intent?.examDate || '',
    horizonDays: Number(plan.window?.horizonDays || 7),
    dailyMinutes: Number(plan.window?.dailyMinutes || 40),
    restDays: Array.isArray(plan.window?.restDays) ? plan.window.restDays : [],
    bankIds: Array.isArray(plan.intent?.bankIds) ? plan.intent.bankIds : [],
    sinceMs: Number(plan.window?.sinceMs || 0),
    planId: String(plan.planId || '')
  })
}

function readPlanState(): any | null {
  return readStudyPlanConfig(props.activeKbId)
}

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

function neighborIdsFor(id: string | null) {
  const result = new Set<string>()
  if (!id) return result
  result.add(id)
  for (const edge of mapEdges.value) {
    if (edge.source === id) result.add(edge.target)
    if (edge.target === id) result.add(edge.source)
  }
  return result
}

const mapSelectedNodeId = computed(() => {
  const selected = mapNodes.value.find((node: any) => Number(node.pageId) === Number(mapSelectedPageId.value))
  return selected ? String(selected.id) : null
})
const mapFocusId = computed(() => mapHoveredId.value || mapSelectedNodeId.value)
const mapNeighborIds = computed(() => neighborIdsFor(mapFocusId.value))

function onMapNodeEnter(node: any) {
  // 拖拽期间冻结悬停态：指针扫过其他节点时不能反复切换高亮/灰化。
  if (mapDraggingId.value || detailVisible.value) return
  mapHoveredId.value = String(node.id)
}

function onMapNodeLeave(node: any) {
  if (mapDraggingId.value || detailVisible.value) return
  if (mapHoveredId.value === String(node.id)) mapHoveredId.value = null
}

function isMapSelected(node: any) {
  return Number(node.pageId) === Number(mapSelectedPageId.value)
}

function isMapNodeDimmed(node: any) {
  if (routeActive.value && !isRouteNode(node)) return true
  if (isMapSelected(node)) return false
  return !!mapFocusId.value && !mapNeighborIds.value.has(String(node.id))
}

function isMapEdgeActive(edge: any) {
  return !!mapFocusId.value && (edge.source === mapFocusId.value || edge.target === mapFocusId.value)
}

function isMapEdgeDimmed(edge: any) {
  if (routeActive.value) {
    const routeIds = new Set((learningRoute.value?.stops || []).map((stop: any) => String(stop.pageId)))
    return !(routeIds.has(edge.source) && routeIds.has(edge.target))
  }
  return !!mapFocusId.value && !isMapEdgeActive(edge)
}

function showMapLabel(node: any) {
  return (
    isMapSelected(node) ||
    isRouteNode(node) ||
    adviceLitPageIds.value.includes(String(node.pageId)) ||
    mapHoveredId.value === String(node.id) ||
    mapView.scale >= 1.05 ||
    Number(node.degree || 0) >= 5
  )
}

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
  stopMapAnimation()
  stopMapNodeDrag()
  mapSelectedPageId.value = Number(node.pageId)
  // 把选中节点移到画布左侧中央，右侧留给详情抽屉。
  // 用 rAF 做镜头移动，而不是瞬移；节点选中环和周围灰化同时生效。
  const targetScale = Math.max(0.9, Math.min(1.25, Number(mapView.scale) || 1))
  animateMapViewTo(
    330 - Number(node.x) * targetScale,
    320 - Number(node.y) * targetScale,
    targetScale,
    360
  )
  if (mapOpenTimer) clearTimeout(mapOpenTimer)
  mapOpenTimer = null
  if (!openDetail) return
  const pageId = Number(node.pageId)
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
    if (Number(mapSelectedPageId.value) === pageId) {
      mapSelectedPageId.value = null
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
    adviceHostRef.value?.generateForPage?.(pageId)
    return
  }
  selectMapNode(node)
}

function isRouteNode(node: any) {
  return (learningRoute.value?.stops || []).some(
    (stop: any) => Number(stop.pageId) === Number(node?.pageId)
  )
}

function isRouteEdge(edge: any) {
  const routeIds = new Set((learningRoute.value?.stops || []).map((stop: any) => String(stop.pageId)))
  return routeIds.has(edge.source) && routeIds.has(edge.target)
}

function isNextStopNode(node: any) {
  return activeRouteStop.value
    ? Number(activeRouteStop.value.pageId) === Number(node?.pageId)
    : false
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
  mapNodeDrag.x = Math.max(30, Math.min(970, mapNodeDrag.origX + dx))
  mapNodeDrag.y = Math.max(30, Math.min(610, mapNodeDrag.origY + dy))
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

function startMapAnimation() {
  stopMapAnimation()
  if (view.value !== 'map' || detailVisible.value || !mapNodes.value.length) return
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

function clusterOutline(points: any[]) {
  if (!points.length) return ''
  const samples = 20
  const expanded = points.flatMap((p) => {
    const radius = Number(p.r || 0) + 20
    return Array.from({ length: samples }, (_, i) => ({
      x: p.x + Math.cos((i * 2 * Math.PI) / samples) * radius,
      y: p.y + Math.sin((i * 2 * Math.PI) / samples) * radius
    }))
  }).sort((a, b) => a.x - b.x || a.y - b.y)
  const unique = expanded.filter((p, i) => !i || p.x !== expanded[i - 1].x || p.y !== expanded[i - 1].y)
  const cross = (o: any, a: any, b: any) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
  const half = (list: any[]) => {
    const hull: any[] = []
    for (const point of list) {
      while (hull.length > 1 && cross(hull[hull.length - 2], hull[hull.length - 1], point) <= 0) hull.pop()
      hull.push(point)
    }
    hull.pop()
    return hull
  }
  const hull = [...half(unique), ...half([...unique].reverse())]
  if (!hull.length) return ''
  const at = (i: number) => hull[(i + hull.length) % hull.length]
  const fmt = (p: any) => `${Math.round(p.x * 10) / 10},${Math.round(p.y * 10) / 10}`
  const tangent = (from: any, to: any, length: number) => {
    const dx = to.x - from.x
    const dy = to.y - from.y
    const norm = Math.hypot(dx, dy) || 1
    return { x: (dx / norm) * length, y: (dy / norm) * length }
  }
  const path = [`M${fmt(hull[0])}`]
  hull.forEach((p, i) => {
    const next = at(i + 1)
    const reach = Math.hypot(next.x - p.x, next.y - p.y) * 0.36
    const out = tangent(at(i - 1), next, reach)
    const into = tangent(p, at(i + 2), reach)
    path.push(`C${fmt({ x: p.x + out.x, y: p.y + out.y })} ${fmt({ x: next.x - into.x, y: next.y - into.y })} ${fmt(next)}`)
  })
  return path.join(' ') + ' Z'
}

const mapHulls = computed(() => {
  const nodes = mapNodes.value
  if (!nodes.length) return []
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  const visibleIds = new Set(byId.keys())
  const hulls: any[] = []
  for (const component of mapComponents.value.components) {
    const ids = component.filter((id) => visibleIds.has(id))
    if (ids.length < 2) continue
    const points = ids.map((id) => byId.get(id)).filter(Boolean)
    hulls.push({ key: ids[0], ids, path: clusterOutline(points) })
  }
  return hulls
})

function statusLabel(status: string) {
  if (status === 'stale') return '待更新'
  if (status === 'failed') return '生成失败'
  if (status === 'draft') return '整理中'
  return '已整理'
}

function sectionLabel(index: number) {
  return Number(index) < 0 ? '摘要' : `第 ${Number(index) + 1} 节`
}

function linkSectionsLabel(item: any) {
  const indexes = Array.isArray(item?.sectionIndexes) && item.sectionIndexes.length
    ? item.sectionIndexes
    : [item?.sectionIndex]
  const labels = indexes.map((index: number) => sectionLabel(index))
  if (labels.length <= 2) return labels.join('、')
  return `${labels.slice(0, 2).join('、')} 等 ${labels.length} 节`
}

function linkTypeLabel(type: string) {
  if (type === 'prerequisite') return '先学'
  if (type === 'contrast') return '对比'
  if (type === 'part_of') return '结构'
  return '相关'
}

function formatTime(value?: string) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
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
    if (!pages.value.length) {
      view.value = 'pages'
    } else if (view.value === 'map') {
      // 刷新后仍停留在知识图谱：页面数据回来后再拉一次图数据。
      await switchMap()
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
  if (['document', 'image', 'bank', 'web'].includes(command)) {
    void openWikiUpdate(command as typeof wikiUpdateType.value)
  }
}

async function openWikiUpdate(type: typeof wikiUpdateType.value) {
  wikiUpdateType.value = type
  wikiUpdateVisible.value = true
  wikiUpdateLoading.value = true
  wikiUpdateOptions.value = []
  try {
    const res: any = await getStudyMap({
      kbId: Number(props.activeKbId || 0),
      sourceTypes: [type],
      limit: 120
    })
    if (res.code !== 200) throw new Error(res.msg || '读取来源失败')
    wikiUpdateOptions.value = (res.data?.nodes || [])
      .filter((node: any) => String(node.kind) === type)
      .map((node: any) => ({
        id: Number(node.ref?.docId || node.ref?.bankId || 0),
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
    const res = await buildWikiPages({
      kbId: Number(props.activeKbId),
      // 默认只补未完成/stale 页面；已有 ready 页面不重复生成。
      force: false,
      limit: 30
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识百科生成失败')
      return
    }
    const data = res.data || {}
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

function resetMapNodeOffsets() {
  Object.keys(mapNodeOffsets).forEach((key) => delete mapNodeOffsets[key])
  Object.keys(mapSimPositions).forEach((key) => delete mapSimPositions[key])
  mapLearningPath.value = []
  stopMapAnimation()
}

function toggleMapType(type: string) {
  mapTypeVisible[type] = mapTypeVisible[type] === false
  resetMapNodeOffsets()
  nextTick(startMapAnimation)
}

function toggleHideUnlinked() {
  mapHideUnlinked.value = !mapHideUnlinked.value
  resetMapNodeOffsets()
  nextTick(startMapAnimation)
}

function toggleMapArrows() {
  mapShowArrows.value = !mapShowArrows.value
}

function fitMapView() {
  const nodes = mapNodes.value
  if (!nodes.length) {
    mapView.x = 0
    mapView.y = 0
    mapView.scale = 1
    return
  }
  const xs = nodes.map((node: any) => Number(node.x))
  const ys = nodes.map((node: any) => Number(node.y))
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const padding = 90
  const scale = Math.min(
    1.4,
    Math.max(
      0.4,
      Math.min(
        (1000 - padding * 2) / Math.max(120, maxX - minX + 100),
        (640 - padding * 2) / Math.max(120, maxY - minY + 100)
      )
    )
  )
  mapView.scale = scale
  mapView.x = 500 - ((minX + maxX) / 2) * scale
  mapView.y = 320 - ((minY + maxY) / 2) * scale
}

async function switchMap() {
  if (!pages.value.length || !Number(props.activeKbId)) return
  view.value = 'map'
  resetMapNodeOffsets()
  mapView.x = -70
  mapView.y = 0
  mapView.scale = 1
  try {
    const graphRes = await getWikiGraph(Number(props.activeKbId))
    if (graphRes.code === 200) {
      mapGraph.value = graphRes.data || { nodes: [], edges: [] }
      await nextTick()
      fitMapView()
      if (String(props.searchQuery || '').trim()) focusMapSearch()
      startMapAnimation()
    }
  } catch {
    // 地图失败时保持主题页入口，不影响阅读。
    view.value = 'pages'
  }
}

function closeDetail() {
  if (mapOpenTimer) {
    clearTimeout(mapOpenTimer)
    mapOpenTimer = null
  }
  detailVisible.value = false
  mapSelectedPageId.value = null
  mapHoveredId.value = null
}

watch(detailVisible, (visible) => {
  if (visible) return
  const viewedPageId = lastDetailPageId
  lastDetailPageId = null
  mapSelectedPageId.value = null
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

function imageUrl(url: string) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : '/' + value)
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
  mapTypeVisible[normalizePageType(target.pageType)] = true
  resetMapNodeOffsets()
  nextTick(() => {
    const current = mapNodes.value.find((node: any) => Number(node.pageId) === Number(target.pageId))
    if (current) selectMapNode(current)
  })
}

function selectSearchSuggestion(item: any) {
  searchSuppressed.value = true
  emit('search-selected', { pageId: Number(item.pageId) })
  mapTypeVisible[normalizePageType(item.pageType)] = true
  resetMapNodeOffsets()
  nextTick(() => {
    const current = mapNodes.value.find((node: any) => Number(node.pageId) === Number(item.pageId))
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
  await reload()
  await resumeBuildJob()
  await openInitialPage()
})
onBeforeUnmount(() => {
  stopBuildPolling()
  stopMapNodeDrag()
  stopMapAnimation()
  cancelMapWheel()
  if (mapSearchTimer) clearTimeout(mapSearchTimer)
  if (mapViewFrame) cancelAnimationFrame(mapViewFrame)
  if (mapOpenTimer) clearTimeout(mapOpenTimer)
})
</script>

<style scoped>
.kw-page { display: flex; flex-direction: column; gap: 14px; padding: 2px 2px 12px; }
.kw-context-actions { display: flex; align-items: center; gap: 6px; }
.kw-graph-search-dropdown { position: absolute; z-index: 30; top: 42px; left: 0; right: 0; overflow: hidden; padding: 6px; border: 1px solid #e4eaf3; border-radius: 10px; background: #fff; box-shadow: 0 12px 30px rgba(28, 45, 75, .14); }
.kw-graph-search-item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 7px 8px; border: 0; border-radius: 7px; background: transparent; color: #4b5563; cursor: pointer; font: inherit; text-align: left; }
.kw-graph-search-item:hover { background: #f3f7ff; }
.kw-graph-search-item__dot { width: 9px; height: 9px; flex: none; border-radius: 50%; }
.kw-graph-search-item__main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
.kw-graph-search-item__main b { overflow: hidden; color: #253247; font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.kw-graph-search-item__main em { overflow: hidden; color: #9aa1af; font-size: 9px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }
.kw-graph-search-item__type { flex: none; color: #a0a6b2; font-size: 9px; }
.kw-toolbar-btn {
  display: inline-flex; align-items: center; gap: 4px; height: 30px; padding: 0 11px;
  border: 1px solid #e5eaf2; border-radius: 7px; color: #5f6b7d; background: #fff;
  cursor: pointer; font: inherit; font-size: 11px; white-space: nowrap;
  transition: border-color .15s ease, color .15s ease, background .15s ease;
}
.kw-toolbar-btn:hover { border-color: #c7d8f1; color: #2f5fce; background: #f8faff; }
.kw-toolbar-btn:disabled { opacity: .5; cursor: not-allowed; }
.kw-toolbar-btn.is-primary { border-color: #c9d9f8; color: #2f5fce; background: #f4f7ff; }
.kw-toolbar-btn__glyph { font-size: 15px; line-height: 1; }
.kw-toolbar-btn__spinner {
  width: 10px; height: 10px; border: 1.5px solid currentColor; border-right-color: transparent;
  border-radius: 50%; animation: kw-spin .8s linear infinite;
}
@keyframes kw-spin { to { transform: rotate(360deg); } }
.kw-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 2px 2px 12px; border-bottom: 1px solid #edf0f5; }
.kw-kicker { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: 0.12em; }
.kw-head h2 { margin: 5px 0 4px; color: #1f2937; font-size: 22px; font-weight: 700; }
.kw-head p { margin: 0; color: #8a91a0; font-size: 12px; }
.kw-stats { display: flex; align-items: center; gap: 5px; margin-top: 7px; color: #9aa1af; font-size: 10px; }
.kw-stats b { color: #2f5fce; font-weight: 600; }
.kw-head__actions { display: flex; flex: none; align-items: center; gap: 8px; }
.kw-switch { display: inline-flex; padding: 2px; border: 1px solid #e6ebf4; border-radius: 8px; background: #f8fafc; }
.kw-switch button { padding: 5px 10px; border: 0; border-radius: 6px; color: #7d8596; background: transparent; cursor: pointer; font-size: 11px; }
.kw-switch button.is-active { color: #2f5fce; background: #fff; box-shadow: 0 1px 4px rgba(47, 95, 206, 0.1); font-weight: 600; }
.kw-switch button:disabled { opacity: 0.45; cursor: not-allowed; }
.kw-build-btn { border-color: rgba(47, 95, 206, 0.28); color: #2f5fce; background: #f5f8ff; }
.kw-build-progress {
  padding: 9px 12px;
  border: 1px solid #e2e9fb;
  border-radius: 8px;
  background: #f8faff;
}
.kw-build-progress__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #2f5fce;
  font-size: 11px;
  font-weight: 600;
}
.kw-build-progress__top span:last-child { color: #d97706; font-weight: 400; }
.kw-build-progress__bar {
  height: 5px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: 99px;
  background: #e7edfb;
}
.kw-build-progress__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #6f8df2, #2f5fce);
  transition: width .35s ease;
}
.kw-build-progress p { margin: 6px 0 0; color: #9aa1af; font-size: 10px; }
.kw-loading { min-height: 420px; }
.kw-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.kw-card { display: flex; min-height: 160px; flex-direction: column; padding: 15px 16px 13px; border: 1px solid #e7ebf3; border-radius: 13px; background: #fff; cursor: pointer; transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease; }
.kw-card:hover { border-color: #cbd9f2; box-shadow: 0 8px 24px rgba(47, 95, 206, 0.08); transform: translateY(-1px); }
.kw-card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.kw-card__type { color: #2f5fce; font-size: 10px; font-weight: 600; }
.kw-card__status { color: #9aa1af; font-size: 9px; }
.kw-card__status.is-stale { color: #c47a55; }
.kw-card__status.is-failed { color: #c05c7e; }
.kw-card h3 { margin: 11px 0 7px; color: #253247; font-size: 16px; font-weight: 700; line-height: 1.4; }
.kw-card p { display: -webkit-box; overflow: hidden; flex: 1; margin: 0; color: #697386; font-size: 11px; line-height: 1.7; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.kw-card__meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; color: #a0a6b2; font-size: 9.5px; }
.kw-filter-empty { grid-column: 1 / -1; padding: 60px 0; color: #9aa1af; text-align: center; font-size: 12px; }
.kw-page--graph { height: calc(100vh - 138px); min-height: 0; gap: 0; padding: 0; overflow: hidden; }
.kw-map { position: relative; min-height: 590px; overflow: hidden; border: 1px solid #e6ebf4; border-radius: 13px; background: radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.1) 1px, transparent 0), #fbfcfe; background-size: 20px 20px; cursor: grab; touch-action: none; user-select: none; }
.kw-page--graph .kw-map { flex: 1; min-height: 0; height: 100%; border: 0; border-radius: 0; background: radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.1) 1px, transparent 0), #fbfcfe; background-size: 20px 20px; }
.kw-map.is-route-mode { background: radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.1) 1px, transparent 0), #fbfcfe; background-size: 20px 20px; }
.kw-map:active { cursor: grabbing; }
.kw-map__svg { width: 100%; height: 590px; }
.kw-page--graph .kw-map__svg { height: 100%; }
.kw-map-purpose { position: absolute; z-index: 7; top: 14px; left: 16px; padding: 6px 9px; border: 1px solid rgba(15, 23, 42, 0.05); border-radius: 6px; color: #7d8596; background: rgba(255, 255, 255, 0.86); font-size: 11px; pointer-events: none; }
.kw-map-hull { fill: #f1f3f7; fill-opacity: 0.72; stroke: #e5e8ef; stroke-width: 1; vector-effect: non-scaling-stroke; transition: fill 0.2s ease, stroke 0.2s ease; }
.kw-map-hull.is-hovered { fill: #ebeef5; stroke: #dce2ed; }
.kw-map-edge { stroke: #c7d0e0; stroke-width: 0.8; opacity: 0.42; vector-effect: non-scaling-stroke; transition: stroke 0.2s, stroke-width 0.2s, stroke-opacity 0.2s; }
.kw-map-edge.is-part_of { stroke: #c7d0e0; }
.kw-map-edge.is-prerequisite { stroke: #73a6dd; stroke-dasharray: 4 4; }
.kw-map-edge.is-contrast { stroke: #d38e7d; stroke-dasharray: 3 5; }
.kw-map-edge.is-related { stroke: #c7d0e0; }
.kw-map-edge.is-mention { stroke: #77bfae; }
.kw-map-edge.is-active { stroke: #7e94bf; stroke-width: 1.5; opacity: 0.85; }
.kw-map.is-route-mode .kw-map-edge { opacity: 0.36; }
.kw-map.is-route-mode .kw-map-edge.is-current-route { stroke: #7e94bf; opacity: 0.82; }
.kw-map-edge.is-dimmed { opacity: 0.08; }
.kw-map-edge.is-hidden { display: none; }
.kw-map-advice-ray { stroke: #2f5fce; stroke-width: 2; opacity: .78; pointer-events: none; stroke-dasharray: 1; stroke-dashoffset: 1; animation: kw-advice-draw .58s ease-out forwards; filter: drop-shadow(0 0 3px rgba(47, 95, 206, .35)); }
.kw-map-advice-dot { fill: #2f5fce; pointer-events: none; filter: drop-shadow(0 0 5px rgba(47, 95, 206, .8)); }
.kw-map-advice-dot circle { pointer-events: none; }
.kw-map.is-advice-focus .kw-map-edge,
.kw-map.is-advice-focus .kw-map-learning-path { display: none; }
.kw-map.is-advice-focus .kw-map-hull { opacity: .18; }
.kw-map.is-advice-focus .kw-map-node:not(.is-selected):not(.is-advice-visited) { opacity: .18; }
.kw-map.is-advice-focus .kw-map-node.is-advice-visited { opacity: 1; }
@keyframes kw-advice-draw { to { stroke-dashoffset: 0; } }
.kw-map-node { cursor: grab; transition: opacity 0.18s ease; }
.kw-map-node.is-advice-dimmed { opacity: .24; }
.kw-map-node.is-advice-visited .kw-map-node__dot { stroke: #2f5fce; stroke-width: 2.8; filter: drop-shadow(0 0 5px rgba(47, 95, 206, .55)); }
.kw-map-node:active { cursor: grabbing; }
.kw-map-node.is-dimmed { opacity: 0.2; }
.kw-map.is-route-mode .kw-map-node.is-dimmed { opacity: 0.42; }
.kw-map-node.is-selected { opacity: 1 !important; }
.kw-map-node.is-selected .kw-map-node__dot { stroke: #253247; stroke-width: 2.5; }
.kw-map-node.is-selected .kw-map-node__label,
.kw-map-node.is-advice-visited .kw-map-node__label { fill: #1f2937; font-size: 12px; font-weight: 700; }
.kw-map-node__halo { fill: rgba(255, 255, 255, 0.86); }
.kw-map.is-route-mode .kw-map-node.is-route .kw-map-node__halo { fill: #f4f8ff; }
.kw-map-node__learn-track { fill: none; stroke: #e5eaf2; stroke-width: 1.8; pointer-events: none; }
.kw-map-node__learn-ring { fill: none; stroke-width: 2.4; stroke-linecap: round; pointer-events: none; transition: stroke-dashoffset .35s ease, stroke .2s ease; }
.kw-map-node.is-weak .kw-map-node__halo { fill: #fff8f5; }
.kw-map-node.is-weak .kw-map-node__learn-ring { filter: drop-shadow(0 0 2px rgba(224, 122, 95, .28)); }
.kw-map-node__dot { stroke: #fff; stroke-width: 1.5; transition: r 0.2s ease, stroke-width 0.2s ease, opacity 0.2s ease; }
.kw-map.is-route-mode .kw-map-node.is-route .kw-map-node__dot { stroke: #2f5fce; stroke-width: 2.2; }
.kw-map-node.is-next-stop .kw-map-node__halo { fill: #edf3fe; }
.kw-map-node__active { fill: none; stroke-width: 2; pointer-events: none; transform-box: fill-box; transform-origin: center; animation: kw-node-pulse 1.5s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite; }
.kw-map-learning-path { fill: none; stroke: #2f5fce; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; opacity: .8; pointer-events: none; }
.kw-map-learning-path.is-fallback { stroke: #c7d0e0; stroke-width: 1.5; stroke-dasharray: 5 4; opacity: .75; }
.kw-map-node__label { fill: #4b5563; font-size: 11px; pointer-events: none; paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round; }
.kw-map.is-route-mode .kw-map-node.is-route .kw-map-node__label { fill: #1f3f8f; font-weight: 700; }
.kw-map-node.is-hovered .kw-map-node__dot { stroke: #253247; stroke-width: 2.5; }
.kw-map-node.is-hovered .kw-map-node__label { fill: #1f2937; font-weight: 600; }
@keyframes kw-node-pulse {
  0% { opacity: 0.8; transform: scale(1); }
  100% { opacity: 0; transform: scale(1.6); }
}
.kw-graph-panel { position: absolute; z-index: 8; top: 12px; right: 12px; display: flex; width: min(200px, calc(100vw - 32px)); max-height: calc(100% - 24px); flex-direction: column; gap: 5px; overflow-y: auto; padding: 8px 9px; border: 1px solid rgba(15, 23, 42, 0.08); border-radius: 9px; background: rgba(255, 255, 255, 0.94); box-shadow: 0 8px 22px rgba(29, 43, 70, 0.1); backdrop-filter: blur(10px); }
.kw-graph-mode-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 3px 2px 6px; color: #5f6b7d; font-size: 11px; font-weight: 600; }
.kw-mode-switch { position: relative; width: 30px; height: 17px; flex: none; padding: 0; border: 0; border-radius: 99px; background: #dfe5ee; cursor: pointer; transition: background .18s ease; }
.kw-mode-switch i { position: absolute; top: 2px; left: 2px; width: 13px; height: 13px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(20, 34, 60, .18); transition: left .18s ease; }
.kw-mode-switch.is-on { background: #2f5fce; }
.kw-mode-switch.is-on i { left: 15px; }
.kw-advice-mode-tip { margin: 1px 0 2px; color: #7d8596; font-size: 11px; line-height: 1.55; }

.kw-graph-panel__legend { display: flex; flex-direction: column; gap: 4px; }
.kw-graph-type { display: flex; align-items: center; gap: 4px; width: 100%; padding: 0 1px; border: 0; color: #5f6b7d; background: transparent; cursor: pointer; font: inherit; font-size: 9.5px; line-height: 1.35; text-align: left; transition: opacity .15s ease, color .15s ease; }
.kw-graph-type:hover { color: #253247; }
.kw-graph-type.is-disabled { opacity: .35; text-decoration: line-through; }
.kw-graph-type i { width: 7px; height: 7px; flex: none; border-radius: 50%; }
.kw-graph-type em { margin-left: auto; color: #a0a6b2; font-size: 8px; font-style: normal; }
.kw-graph-panel__divider { height: 1px; margin: 0 -9px; background: #edf0f5; }
.kw-graph-panel__actions { display: flex; flex-direction: column; gap: 1px; }
.kw-graph-action { display: flex; align-items: center; gap: 4px; width: 100%; padding: 3px 1px; border: 0; color: #6b7280; background: transparent; cursor: pointer; font: inherit; font-size: 9.5px; line-height: 1.35; text-align: left; transition: color .15s ease; }
.kw-graph-action:hover, .kw-graph-action.is-active { color: #2f5fce; }
.kw-route-action { color: #2f5fce; font-weight: 600; }
.kw-graph-action:disabled { opacity: .35; cursor: not-allowed; }
.kw-graph-panel__overview { display: flex; flex-direction: column; gap: 2px; color: #9aa1af; font-size: 8.5px; line-height: 1.35; }
.kw-graph-panel__overview span { display: inline-flex; align-items: center; gap: 3px; }
.kw-graph-panel__overview b { color: #253247; font-size: 10.5px; font-weight: 600; }
.kw-graph-panel__overview em { color: #a0a6b2; font-style: normal; }
.kw-route-generate { display: flex; align-items: center; gap: 7px; width: 100%; padding: 7px; border: 1px solid #c9d9f8; border-radius: 8px; background: linear-gradient(135deg, #f5f8ff, #eef4ff); color: #2f5fce; cursor: pointer; font: inherit; text-align: left; transition: border-color .15s ease, background .15s ease; }
.kw-route-generate:hover { border-color: #a9c3f2; background: #edf4ff; }
.kw-route-generate:disabled { opacity: .6; cursor: wait; }
.kw-route-generate__icon { display: inline-flex; width: 25px; height: 25px; flex: none; align-items: center; justify-content: center; border-radius: 7px; background: #e3edff; }
.kw-route-generate__text { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.kw-route-generate__text b { color: #2f5fce; font-size: 11.5px; font-weight: 700; }
.kw-route-generate__text em { color: #8b95a7; font-size: 11px; font-style: normal; line-height: 1.4; }
.kw-learn-next { display: flex; align-items: center; gap: 4px; width: 100%; margin-top: 3px; padding: 4px 6px; border: 1px solid #e0e8f8; border-radius: 6px; background: #f7f9ff; color: #2f5fce; cursor: pointer; font: inherit; font-size: 9px; text-align: left; }
.kw-learn-next span { flex: none; color: #8a91a0; }
.kw-learn-next b { overflow: hidden; flex: 1; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.kw-learn-next:hover { border-color: #c7d8f1; background: #eef4ff; }
.kw-learn-legend { display: flex; flex-wrap: wrap; gap: 3px 8px; margin-top: 3px; color: #9aa1af; font-size: 8px; }
.kw-learn-legend span { display: inline-flex; align-items: center; gap: 3px; }
.kw-learn-legend i { width: 6px; height: 6px; border-radius: 50%; }
.kw-graph-hint { position: absolute; z-index: 7; left: 16px; bottom: 14px; padding: 5px 9px; border: 1px solid rgba(15, 23, 42, 0.05); border-radius: 6px; color: #9aa1af; background: rgba(255, 255, 255, 0.82); font-size: 11px; pointer-events: none; }
.kw-graph-hint.is-route { right: 16px; left: auto; font-size: 11px; }
.kw-learning-path-card { position: absolute; z-index: 9; left: 16px; bottom: 14px; display: flex; width: 242px; flex-direction: column; gap: 3px; padding: 8px 9px; border: 1px solid #dbe5fb; border-radius: 9px; background: rgba(255, 255, 255, 0.95); box-shadow: 0 10px 24px rgba(47, 95, 206, 0.14); backdrop-filter: blur(10px); }
.kw-learning-path-card__head { display: flex; align-items: center; justify-content: space-between; padding-bottom: 3px; border-bottom: 1px solid #edf1fa; color: #2f5fce; font-size: 9.5px; font-weight: 600; }
.kw-learning-path-card__head span { display: inline-flex; align-items: center; gap: 3px; }
.kw-learning-path-card__head button { padding: 0 2px; border: 0; color: #9aa1af; background: transparent; cursor: pointer; font-size: 15px; line-height: 1; }
.kw-learning-path-step { display: flex; align-items: center; gap: 5px; width: 100%; padding: 3px 1px; border: 0; background: transparent; color: #5f6b7d; cursor: pointer; font: inherit; font-size: 9.5px; text-align: left; }
.kw-learning-path-step:hover { color: #2f5fce; }
.kw-learning-path-step i { display: inline-flex; width: 15px; height: 15px; flex: none; align-items: center; justify-content: center; border-radius: 50%; color: #2f5fce; background: #edf3ff; font-size: 8px; font-style: normal; font-weight: 600; }
.kw-learning-path-step span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-learning-path-step em { flex: none; margin-left: auto; color: #a0a6b2; font-size: 8px; font-style: normal; }
.kw-empty { display: flex; min-height: 520px; flex-direction: column; align-items: center; justify-content: center; border: 1px dashed #dfe6f2; border-radius: 13px; background: #fcfdff; text-align: center; }
.kw-empty__art { display: flex; width: 56px; height: 56px; align-items: center; justify-content: center; margin-bottom: 10px; border-radius: 16px; color: #2f5fce; background: #eef4ff; font-size: 28px; }
.kw-empty h3 { margin: 0 0 6px; color: #374151; font-size: 16px; }
.kw-empty p { max-width: 420px; margin: 0 0 16px; color: #9aa1af; font-size: 11px; line-height: 1.7; }
.kw-detail-shell { height: 100%; overflow-y: auto; padding: 24px 30px 40px; }
.kw-detail { display: flex; min-height: 100%; flex-direction: column; gap: 18px; }
.kw-detail__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 14px; border-bottom: 1px solid #edf0f5; }
.kw-detail__head h2 { margin: 6px 0 7px; color: #1f2937; font-size: 25px; line-height: 1.3; }
.kw-detail__badges { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; color: #9aa1af; font-size: 10px; }
.kw-detail__type { padding: 3px 7px; border-radius: 5px; color: #2f5fce; background: #eef4ff; font-weight: 600; }
.kw-detail__badges .is-stale { color: #c47a55; }
.kw-detail__badges .is-manual { color: #2f9e8f; }
.kw-detail__head-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.kw-detail__close { flex: none; padding: 0 4px; border: 0; color: #9aa1af; background: transparent; cursor: pointer; font-size: 24px; line-height: 1; }
.kw-detail__warning { padding: 9px 11px; border: 1px solid #f0d9cc; border-radius: 8px; color: #a96545; background: #fff8f3; font-size: 11px; line-height: 1.6; }
.kw-detail__learning { display: flex; flex-direction: column; gap: 5px; padding: 9px 11px; border: 1px solid #e7ebf3; border-radius: 8px; background: #fbfcfe; }
.kw-detail__learning-head { display: flex; align-items: center; justify-content: space-between; color: #6b7280; font-size: 10px; font-weight: 600; }
.kw-detail__learning-head b { font-weight: 600; }
.kw-detail__learning-head b.is-unread { color: #9aa1af; }
.kw-detail__learning-head b.is-reading { color: #5b8def; }
.kw-detail__learning-head b.is-practicing { color: #f0a13a; }
.kw-detail__learning-head b.is-mastered { color: #2f9e8f; }
.kw-detail__learning-bar { height: 4px; overflow: hidden; border-radius: 99px; background: #e9eef7; }
.kw-detail__learning-bar i { display: block; height: 100%; border-radius: inherit; background: #5b8def; transition: width .35s ease; }
.kw-detail__learning-bar i.is-practicing { background: #f0a13a; }
.kw-detail__learning-bar i.is-mastered { background: #2f9e8f; }
.kw-detail__learning-meta { display: flex; flex-wrap: wrap; gap: 10px; color: #9aa1af; font-size: 9.5px; }
.kw-detail__route-action { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border: 1px dashed #dbe5f8; border-radius: 8px; background: #fbfcff; color: #8a91a0; font-size: 11px; }
.kw-detail__route-action button { flex: none; padding: 0; border: 0; color: #2f5fce; background: transparent; cursor: pointer; font: inherit; font-size: 11px; font-weight: 600; }
.kw-detail__route-action button:hover { text-decoration: underline; }
.kw-detail__lead { margin: 0; padding: 14px 16px; border-left: 3px solid #5f87e6; border-radius: 0 8px 8px 0; color: #4b5563; background: #f7f9ff; font-size: 13px; line-height: 1.8; }
.kw-detail__section h3 { margin: 0 0 7px; color: #253247; font-size: 15px; font-weight: 700; }
.kw-detail__body { color: #4b5563; font-size: 13px; line-height: 1.85; }
.kw-detail__body :deep(.latex-content) { font-size: 13px; line-height: 1.85; }
.kw-detail__block { padding-top: 13px; border-top: 1px solid #edf0f5; }
.kw-detail__block-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; color: #6b7280; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; }
.kw-detail__block-head b { color: #2f5fce; font-weight: 600; }
.kw-source { display: grid; width: 100%; grid-template-columns: auto auto 1fr; align-items: center; gap: 9px; margin-bottom: 6px; padding: 8px 9px; border: 1px solid #eef1f6; border-radius: 8px; background: #fbfcfe; color: #697386; cursor: pointer; font-size: 10.5px; text-align: left; }
.kw-source:hover { border-color: #d9e1f4; background: #f5f7fc; }
.kw-source__name { overflow: hidden; color: #4b5563; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.kw-source__index { color: #9aa1af; white-space: nowrap; }
.kw-source__quote { overflow: hidden; color: #9aa1af; text-overflow: ellipsis; white-space: nowrap; }
.kw-link-block .kw-detail__block-head { gap: 8px; }
.kw-link-block .kw-detail__block-head > span:first-child { margin-right: auto; }
.kw-link-group { margin-top: 9px; }
.kw-link-group__label { margin-bottom: 5px; color: #9aa1af; font-size: 9.5px; font-weight: 600; }
.kw-link-list { display: flex; flex-direction: column; gap: 5px; }
.kw-link-item { display: flex; align-items: center; gap: 5px; }
.kw-link-main { display: flex; min-width: 0; flex: 1; align-items: center; gap: 7px; padding: 7px 9px; border: 1px solid #e7f2ee; border-radius: 8px; background: #fbfefd; color: #4b5563; cursor: pointer; font-size: 10.5px; text-align: left; }
.kw-link-main:hover { border-color: #b9dfd5; background: #f1fbf8; }
.kw-link-main b { overflow: hidden; max-width: 42%; color: #256e5d; text-overflow: ellipsis; white-space: nowrap; }
.kw-link-main span { overflow: hidden; color: #7d8596; text-overflow: ellipsis; white-space: nowrap; }
.kw-link-main em { flex: none; margin-left: auto; color: #a0a6b2; font-style: normal; font-size: 9px; }
.kw-link-remove { flex: none; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px; color: #b26a7f; background: transparent; cursor: pointer; font-size: 16px; line-height: 1; }
.kw-link-remove:hover { background: #fff1f5; }
.kw-link-dialog { display: flex; flex-direction: column; gap: 7px; }
.kw-link-dialog__hint { margin: 0 0 3px; padding: 8px 10px; border-radius: 7px; color: #6b7280; background: #f6fbf9; font-size: 11px; line-height: 1.65; }
.kw-link-dialog__label { margin-top: 4px; color: #4b5563; font-size: 11px; font-weight: 600; }
.kw-related { display: flex; flex-wrap: wrap; gap: 7px; }
.kw-related__item { display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px; border: 1px solid #e6ebf4; border-radius: 8px; background: #fff; color: #4b5563; cursor: pointer; font-size: 11px; }
.kw-related__item:hover { border-color: #cbd9f2; background: #f7f9ff; }
.kw-related__item span { color: #9aa1af; font-size: 9px; }
.kw-detail__foot { padding-top: 5px; color: #a0a6b2; font-size: 10px; }
.kw-image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.kw-image-card { overflow: hidden; border: 1px solid #e8edf5; border-radius: 8px; background: #fbfcfe; }
.kw-image-card :deep(.el-image) { display: block; width: 100%; height: 110px; }
.kw-image-card__foot { display: flex; align-items: center; gap: 5px; padding: 5px 7px; color: #697386; font-size: 10px; }
.kw-image-card__foot span { overflow: hidden; flex: 1; text-overflow: ellipsis; white-space: nowrap; }
.kw-image-card__foot button { border: 0; color: #c05c7e; background: transparent; cursor: pointer; font-size: 16px; line-height: 1; }
.kw-image-empty { padding: 12px; border: 1px dashed #e4eaf3; border-radius: 7px; color: #a0a6b2; font-size: 10.5px; text-align: center; }
.kw-gallery-picker { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; max-height: 55vh; overflow-y: auto; }
.kw-gallery-pick { display: flex; min-width: 0; flex-direction: column; gap: 5px; padding: 6px; border: 1px solid #e8edf5; border-radius: 8px; background: #fff; color: #697386; cursor: pointer; font-size: 10px; text-align: left; }
.kw-gallery-pick:hover { border-color: #cbd9f2; }
.kw-gallery-pick :deep(.el-image) { width: 100%; height: 95px; border-radius: 5px; }
.kw-gallery-pick span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-revisions { display: flex; flex-direction: column; gap: 7px; }
.kw-revision { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border: 1px solid #eef1f6; border-radius: 7px; background: #fbfcfe; }
.kw-revision > div { display: flex; align-items: center; gap: 8px; color: #697386; font-size: 11px; }
.kw-revision b { color: #2f5fce; }
.kw-revision em { color: #a0a6b2; font-style: normal; font-size: 10px; }
.kw-detail-loading { height: 500px; }
.kw-guide-lead { margin-bottom: 12px; padding: 9px 11px; border-radius: 8px; color: #4b5563; background: #f7f9ff; font-size: 11px; line-height: 1.6; }
.kw-guide-steps { display: flex; flex-direction: column; gap: 9px; }
.kw-guide-step { display: flex; align-items: flex-start; gap: 9px; }
.kw-guide-step > i { display: inline-flex; width: 24px; height: 24px; flex: none; align-items: center; justify-content: center; border-radius: 50%; color: #2f5fce; background: #edf3ff; font-size: 9px; font-style: normal; font-weight: 700; }
.kw-guide-step b { color: #253247; font-size: 12px; font-weight: 600; }
.kw-guide-step p { margin: 3px 0 0; color: #7d8596; font-size: 11px; line-height: 1.6; }
.kw-guide-tip { margin-top: 13px; padding: 8px 10px; border: 1px dashed #dbe5f8; border-radius: 8px; color: #7d8596; background: #fbfcff; font-size: 11px; line-height: 1.6; }
.kw-update-hint { margin: 0 0 10px; color: #7d8596; font-size: 12px; line-height: 1.6; }
.kw-update-list { display: flex; max-height: 360px; flex-direction: column; gap: 8px; overflow-y: auto; }
.kw-update-item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 10px 11px; border: 1px solid #e8edf5; border-radius: 8px; background: #fff; color: #4b5563; cursor: pointer; text-align: left; }
.kw-update-item:hover { border-color: #c9d8f5; background: #f8faff; }
.kw-update-item__type { flex: none; padding: 2px 6px; border-radius: 5px; background: #eef4ff; color: #2f5fce; font-size: 10px; }
.kw-update-item__main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }
.kw-update-item__main b { overflow: hidden; color: #253247; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.kw-update-item__main em { overflow: hidden; color: #9aa3b2; font-size: 10.5px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }
.kw-update-empty { padding: 24px 0; color: #9aa3b2; font-size: 12px; text-align: center; }
@media (max-width: 900px) { .kw-head { flex-direction: column; align-items: flex-start; gap: 10px; } .kw-head__actions { flex-wrap: wrap; } .kw-map, .kw-map__svg { min-height: 460px; height: 460px; } .kw-detail-drawer { width: 92vw !important; } }
</style>











