<!--
  FrontSidebar —— 前台竖向导航侧栏（对齐 DSH Web 的三段结构）
  ============================================================================
  DSH 的侧栏是这么分段的（用户 2026-10-17 要求照此重构）：

    ①  品牌行         —— logo + 产品名 + 收起按钮
    ②  功能入口       —— 新建对话 + 题库练习 / 我的学习 / 学习分享 / 题库搭建
    ③  对话列表       —— 「智能对话」标题 + 搜索 + 历史会话（可滚动）
    ④  底部           —— 设置 + 账号

  与之前版本的差别（都是用户明确要求的）：
    · **不再用分割线**分隔模块，改用留白与分组小标题（DSH 的做法）；
    · 「智能对话」不再是一个导航项，而是**第三段的标题**，下面直接列会话；
    · 会话搜索从输入框工具栏移到侧栏（那里才是"找历史对话"的入口）；
    · 底部去掉「© 2026 OpenStudy」；
    · 展开 280（可拖拽 220–420）/ 收起 64，收起态只在最左图标列留展开按钮。

  滚动优化：
    · 只有**会话列表**滚动（`min-height: 0` + `overflow-y: auto`），
      品牌 / 功能入口 / 底部始终可见；
    · 会话数多时不会把底部账号区顶出视口；
    · 侧栏自身 `overflow: hidden`，避免出现两层滚动条。
-->
<template>
  <aside
    ref="rootRef"
    class="os-sidebar"
    :class="{ 'is-collapsed': collapsed, 'is-resizing': resizing }"
    :style="collapsed ? undefined : { width: width + 'px' }"
  >
    <!-- 拖拽手柄：贴在侧栏右边缘（只展开态可用） -->
    <div
      v-if="!collapsed"
      class="sb-resize-handle"
      title="拖动调整侧栏宽度"
      @mousedown.stop="startResize"
    />

    <!-- ==================== ① 品牌行 ==================== -->
    <div class="sb-head">
      <template v-if="!collapsed">
        <button class="sb-brand" type="button" title="回到智能对话" @click="goEntry">
          <OsLogo :size="26" />
          <span class="sb-name">OpenStudy</span>
        </button>

        <el-tooltip placement="right" popper-class="os-tip-pop" :show-after="400" :offset="10">
          <template #content>
            <span class="os-tip">
              <span class="os-tip__label">收起侧边栏</span>
              <kbd class="os-tip__kbd">Ctrl + Alt + B</kbd>
            </span>
          </template>
          <button class="sb-toggle" type="button" aria-label="收起侧边栏" @click="$emit('toggle')">
            <OsIcon name="panel-left-close" :size="17" />
          </button>
        </el-tooltip>
      </template>

      <el-tooltip v-else placement="right" popper-class="os-tip-pop" :show-after="250" :offset="10">
        <template #content>
          <span class="os-tip">
            <span class="os-tip__label">展开侧边栏</span>
            <kbd class="os-tip__kbd">Ctrl + Alt + B</kbd>
          </span>
        </template>
        <button class="sb-toggle sb-rail-toggle" type="button" aria-label="展开侧边栏" @click="$emit('toggle')">
          <OsIcon name="panel-left" :size="18" />
        </button>
      </el-tooltip>
    </div>

    <!-- ==================== ② 新建对话 + 功能入口 ==================== -->
    <button class="sb-new" type="button" :title="collapsed ? '新建对话' : ''" @click="startNewChat">
      <OsIcon name="plus" :size="17" />
      <span v-if="!collapsed" class="sb-new__label">新建对话</span>
    </button>

    <!--
      ==================== 中段：功能区 + 会话列表 ====================
      ⚠️ 两段放在**同一个滚动容器**里（用户 2026-10-17 报的 bug）。

      原来的结构是「功能区自己滚 + 会话区自己滚」，结果是：展开「我的学习」后
      功能区被压到 307px、只能滚 96px，下面的「学习分享 / 题库搭建」被挡住，
      用户必须先滚一下才知道下面还有东西 —— 而且两段各有一条滚动条，很吵。

      现在的结构：品牌行固定 → 中段整体滚动 → 底部设置固定。
      菜单展开多长都能滚到，会话列表也跟着这条滚动条走，观感更接近 DSH。
    -->
    <div class="sb-scroll">
      <nav class="sb-features" aria-label="功能导航">
        <div v-for="item in featureItems" :key="item.key" class="sb-group">
          <div class="sb-row">
            <button
              type="button"
              class="sb-item"
              :class="{ 'is-active': isActive(item) }"
              :title="collapsed ? item.label : ''"
              @click="onFeatureClick(item)"
            >
              <span class="sb-ico"><OsIcon :name="item.icon" :size="18" /></span>
              <span v-if="!collapsed" class="sb-label">{{ item.label }}</span>
              <span v-if="collapsed && isActive(item)" class="sb-pip" />
            </button>
            <button
              v-if="item.children && !collapsed"
              type="button"
              class="sb-caret"
              :class="{ 'is-open': openGroups[item.key] }"
              :title="openGroups[item.key] ? '收起子项' : '展开子项'"
              @click="toggleGroup(item.key)"
            >
              <OsIcon name="chevron-right" :size="14" />
            </button>
          </div>

          <div v-if="item.children && !collapsed && openGroups[item.key]" class="sb-children">
            <button
              v-for="child in item.children"
              :key="child.to"
              type="button"
              class="sb-child"
              :class="{ 'is-active': isChildActive(child) }"
              @click="onChildClick(item, child)"
            >
              {{ child.label }}
            </button>
          </div>
        </div>
      </nav>

      <!-- ==================== ③ 智能对话（会话列表） ==================== -->
      <!--
        这一段是 DSH 侧栏的主体：标题行 + 搜索 + 会话列表。
        - 与功能区共享同一条滚动条（见外面 `.sb-scroll` 的说明）；
        - 搜索按钮切换输入框，避免常驻占一行高度；
        - 收起态整段隐藏（图标列放不下会话标题）。
      -->
      <section v-if="!collapsed" class="sb-conv">
      <div class="sb-conv__head">
        <span class="sb-conv__title">智能对话</span>
        <el-tooltip placement="top" popper-class="os-tip-pop" :show-after="300" :offset="8">
          <template #content>
            <span class="os-tip"><span class="os-tip__label">搜索历史会话</span></span>
          </template>
          <button
            type="button"
            class="sb-conv__icon"
            :class="{ 'is-on': searchOpen }"
            aria-label="搜索历史会话"
            @click="toggleSearch"
          >
            <OsIcon name="search" :size="15" />
          </button>
        </el-tooltip>
      </div>

      <div v-if="searchOpen" class="sb-conv__search">
        <el-input
          ref="searchRef"
          v-model="sessionStore.keyword"
          size="small"
          clearable
          placeholder="搜索会话标题"
          @keydown.esc="closeSearch"
        >
          <template #prefix><OsIcon name="search" :size="14" /></template>
        </el-input>
      </div>

      <div class="sb-conv__list" v-loading="sessionStore.loading">
        <button
          v-for="s in sessionStore.filtered"
          :key="s.sessionId"
          type="button"
          class="sb-conv__item"
          :class="{ 'is-active': isSessionActive(s) }"
          :title="plainTitle(sessionStore.title(s))"
          @click="openSession(s)"
        >
          <!--
            会话标题去掉 LaTeX 记号（2026-10-27 修）

            ⚠️ 实测问题：会话标题取自用户第一句话，
               用户问「求极限 $\lim_{x\to 0}\frac{\sin x}{x}$」时
               侧栏显示成 `把这道题排成好看的 Word：求极限 $\lim_{x\to`，
               **一屏反斜杠**。用户原话：「不要有任何数学代码给用户看到」。

            ⚠️ 这里**刻意不渲染公式**（与聊天正文不同）：
               侧栏宽度只有 ~200px，一个分式 KaTeX 就能撑破布局或压掉时间戳。
               标题是"用来认出这是哪次对话"的，纯文字足够。
               所以做法是**剥掉 LaTeX 记号只留可读文字**。
          -->
          <span class="sb-conv__name">{{ plainTitle(sessionStore.title(s)) }}</span>
          <span class="sb-conv__meta">{{ formatSessionTime(s.updatedAt) }}</span>
          <!-- 删除只在 hover / 当前项出现，避免每条都挂一个叉 -->
          <span
            class="sb-conv__del"
            title="删除会话"
            @click.stop="removeSession(s)"
          >
            <OsIcon name="trash" :size="13" />
          </span>
        </button>

        <p v-if="!sessionStore.loading && !sessionStore.sessions.length" class="sb-conv__empty">
          还没有对话，发一条试试
        </p>
        <p
          v-else-if="!sessionStore.loading && !sessionStore.filtered.length"
          class="sb-conv__empty"
        >
          没有匹配「{{ sessionStore.keyword.trim() }}」的会话
        </p>
      </div>
    </section>

      <!-- 收起态：给一个「回到对话」的图标，避免会话列表完全不可达 -->
      <div v-else class="sb-rail-conv">
        <el-tooltip placement="right" popper-class="os-tip-pop" :show-after="250" :offset="10">
          <template #content>
            <span class="os-tip"><span class="os-tip__label">回到智能对话</span></span>
          </template>
          <button
            type="button"
            class="sb-item"
            :class="{ 'is-active': isAgentPage }"
            aria-label="回到智能对话"
            @click="goEntry"
          >
            <span class="sb-ico"><OsIcon name="bot" :size="18" /></span>
          </button>
        </el-tooltip>
      </div>
    </div>
    <!-- /中段滚动容器 -->

    <!--
      ==================== ④ 底部：只有设置 ====================
      用户 2026-10-17：
        · 「设置」用齿轮图标、固定在**最底部**；
        · 账号区（头像 / 用户名 / 下拉）整体移到**右上角顶栏** —— 那里才是身份与
          消息、退出这些"全局操作"该待的地方，侧栏底部只留一个功能入口更干净。
    -->
    <div class="sb-foot">
      <button
        type="button"
        class="sb-item sb-item--settings"
        :title="collapsed ? '设置' : ''"
        @click="openSettings"
      >
        <span class="sb-ico"><OsIcon name="settings" :size="18" /></span>
        <span v-if="!collapsed" class="sb-label">设置</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import useAgentUiStore from '@/store/modules/agentUi'
import useAgentSessionStore, { formatSessionTime } from '@/store/modules/agentSession'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { ensureLogin } from '@/utils/loginGuard'
import OsIcon from '@/components/OsIcon/index.vue'
import OsLogo from '@/components/OsLogo/index.vue'

defineOptions({ name: 'FrontSidebar' })

/**
 * 会话标题去 LaTeX 记号（2026-10-27 加）
 *
 * ⚠️ 实测问题：会话标题是用户第一句话的前缀。
 *    用户问「把这道题排成好看的 Word：求极限 $\lim_{x\to 0}\frac{\sin x}{x}$」时，
 *    侧栏显示成 `把这道题排成好看的 Word：求极限 $\lim_{x\to` —— 一屏反斜杠。
 *    用户原话：「不要有任何数学代码给用户看到」。
 *
 * 处理策略（与聊天正文不同，**刻意不渲染公式**）：
 *   侧栏宽约 200px，一个分式 KaTeX 就能撑破布局或压掉时间戳。
 *   标题的用途是"认出这是哪次对话"，纯文字足够。
 *   所以**剥掉记号、只留可读文字**：
 *
 *     `$\lim_{x\to 0}\frac{\sin x}{x}$`  →  `lim x→0`
 *
 * ⚠️ 只做展示，不改存储的标题 —— 用户回到对话里仍能看到完整原文。
 */
function plainTitle(raw: string): string {
  if (!raw) return ''
  return raw
    // 块级/行内定界符先去掉
    .replace(/\$\$?/g, '')
    .replace(/\\[()[\]]/g, '')
    // 常见数学命令 → 可读写法（顺序重要：长的先匹配）
    .replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '$1/$2')
    .replace(/\\sqrt\s*\{([^{}]*)\}/g, '√$1')
    .replace(/\\lim\b/g, 'lim')
    .replace(/\\(sin|cos|tan|log|ln|exp|max|min|int|sum)\b/g, '$1')
    .replace(/\\to\b/g, '→')
    .replace(/\\times\b/g, '×')
    .replace(/\\cdot\b/g, '·')
    .replace(/\\(le|leq)\b/g, '≤')
    .replace(/\\(ge|geq)\b/g, '≥')
    .replace(/\\infty\b/g, '∞')
    .replace(/\\[a-zA-Z]{2,15}/g, '')   // 其余命令直接去掉
    .replace(/[\^_]\{?([^{}]*)\}?/g, '$1')  // 上下标只留内容
    .replace(/[{}\\]/g, '')             // 残余结构符号
    .replace(/\s+/g, ' ')
    .trim()
}

const props = defineProps<{
  collapsed: boolean
  unreadCount?: number
}>()

const emit = defineEmits<{ (e: 'toggle'): void; (e: 'navigate'): void }>()

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const agentUiStore = useAgentUiStore()
const sessionStore = useAgentSessionStore()
const cacheStore = useFrontPageCacheStore()

/* ==================== 拖拽调宽（复用 ResizableDrawer 的手感） ==================== */
const WIDTH_KEY = 'os_sidebar_width'
const MIN_W = 220
const MAX_W = 420

const clampWidth = (n: number) => Math.max(MIN_W, Math.min(MAX_W, n))

const readStoredWidth = (): number => {
  const n = Number(localStorage.getItem(WIDTH_KEY))
  return Number.isFinite(n) && n >= MIN_W ? clampWidth(n) : 280
}

const rootRef = ref<HTMLElement | null>(null)
const width = ref(readStoredWidth())
const resizing = ref(false)

let startX = 0
let startWidth = 0
let nextWidth = width.value
let raf = 0

function startResize(e: MouseEvent) {
  e.preventDefault()
  resizing.value = true
  startX = e.clientX
  startWidth = width.value
  nextWidth = width.value
  document.addEventListener('mousemove', onResize, { passive: false })
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResize(e: MouseEvent) {
  if (!resizing.value) return
  e.preventDefault()
  nextWidth = clampWidth(startWidth + (e.clientX - startX))
  if (raf) return
  // rAF 节流 + 直接写 DOM：拖拽期间不进 Vue 渲染管线（消息多时也不掉帧）
  raf = requestAnimationFrame(() => {
    raf = 0
    if (rootRef.value) rootRef.value.style.width = nextWidth + 'px'
  })
}

function stopResize() {
  if (!resizing.value) return
  resizing.value = false
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
  width.value = nextWidth
  localStorage.setItem(WIDTH_KEY, String(nextWidth))
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
})

/* ==================== 功能导航（第二段） ==================== */
interface NavChild {
  label: string
  to: string
  cacheKey?: string
}

interface NavItem {
  key: string
  label: string
  icon: string
  to: string
  match: string
  cacheKey: string
  requiresLogin?: boolean
  children?: NavChild[]
}

/**
 * 第二段的功能入口：题库练习 / 我的学习 / 学习分享 / 题库搭建。
 *
 * 「智能对话」已从导航项里拿掉 —— 它是第三段的标题，会话列表本身就是入口。
 * ⚠️ 「英语学习」「实用工具」本系统暂时不需要，导航项以注释形式保留在下方。
 */
const featureItems: NavItem[] = [
  {
    key: 'practice',
    label: '题库练习',
    icon: 'book-open',
    to: '/front/questionPractice',
    match: '/front/questionPractice',
    cacheKey: 'questionPractice'
  },
  {
    key: 'study',
    label: '我的学习',
    icon: 'graduation-cap',
    to: '/front/myQuestion/myBank',
    match: '/front/myQuestion',
    cacheKey: 'myQuestion',
    requiresLogin: true,
    children: [
      /*
       * 「我的题库」改名为「题库管理」（用户 2026-10-18）：
       * 这一页现在同时管「我的题库」和「题库收藏」两个分组，
       * 叫「管理」比叫「我的题库」更贴切，也不会和分组名撞车。
       *
       * 「题库收藏」这一项**已移除**（用户：「我的学习目录下多余的题库收藏模块可以去掉了」）——
       * 收藏已经合并进「题库管理」的第二个分组，再放一个侧栏入口就是重复导航。
       *
       * 「我的分享」也**已移除**（用户 2026-10-19：「我的分享页面的重构，给他作为一个子路由，
       * 转移到题库管理内部去」）—— 它是「题库管理」的第三个分组。
       */
      { label: '题库管理', to: '/front/myQuestion/myBank', cacheKey: 'myBank' },
      /*
       * 下面三项都指向同一个「题目管理」页（用户 2026-10-18 要求像题库那样合并）：
       * 用 `?tab=` 决定进页面时停在哪个分组。三个入口保留是因为用户习惯从
       * 「我的错题」「我的斩题」直接进，只是落地页变成了带分组切换的统一页面。
       */
      /*
       * 「题目管理」一个入口管三组：题目收藏 / 我的错题 / 我的斩题。
       *
       * 「我的错题」「我的斩题」两个独立入口**已移除**（用户 2026-10-18：
       * 「把多余的我的错题、我的斩题去掉」）——它们指向的是同一个页面，
       * 只是 `?tab=` 不同，放在侧栏里等于同一个功能出现三次。
       * 需要到某个分组，进「题目管理」后点顶部 tab 即可。
       */
      { label: '题目管理', to: '/front/myQuestion/questions?tab=favorite', cacheKey: 'questions' },
      /*
       * 「我的笔记」改名为「笔记管理」并合并了「收藏的笔记」（用户 2026-10-18）。
       * 旧的两个独立入口（我的笔记 / 收藏的笔记）合成一个 ——
       * 收藏是笔记管理的第二个分组，不该在侧栏再占一行。
       */
      { label: '笔记管理', to: '/front/myQuestion/noteManage?tab=own', cacheKey: 'noteManage' },
      { label: '学习统计', to: '/front/myQuestion/myStats', cacheKey: 'myStats' }
    ]
  },
  {
    key: 'notes',
    label: '学习分享',
    icon: 'pen-line',
    to: '/front/notes/list',
    match: '/front/notes',
    cacheKey: 'notes'
  },
  {
    key: 'studio',
    label: '题库搭建',
    icon: 'folder-plus',
    to: '/front/studio/create?type=public',
    match: '/front/studio',
    cacheKey: 'studio',
    requiresLogin: true
  },
  /*
   * 「知识库」（2026-10-22 由「我的空间」改名并升级）
   * ------------------------------------------------------
   * 产品定位：用户所有资料的**统一管理处**。每个知识库是一个「资料夹」，
   * 里面装若干文档；默认库用来接「随手传的资料」，不用先想放哪。
   *
   * 为什么改名：
   *   原来这里叫「我的空间」，而对话页抽屉里又叫「知识库」——
   *   两者其实是同一套数据（`rag_knowledge_base`，空间就是 `is_workspace=1` 的库），
   *   用户会看到「我的空间」同时出现在侧栏和知识库列表里，分不清该往哪传。
   *   现在合并成一个概念、一个入口：**知识库**。
   *
   * 为什么放在「题库搭建」下面而不是「我的学习」里：
   *   「我的学习」是**已经沉淀成学习成果**的东西（题库、笔记、错题）；
   *   知识库是**原始资料**，是它们的上游。放在一起会让用户分不清
   *   「我上传的资料」和「我做出来的题」。
   */
  {
    key: 'workspace',
    label: '知识库',
    icon: 'folder',
    to: '/front/workspace',
    match: '/front/workspace',
    cacheKey: 'workspace',
    requiresLogin: true
  },
  /*
   * 「英语学习」（2026-10-23 重新开放）
   * --------------------------------
   * 之前因为「系统只做题库」被注释隐藏。现在按用户要求放出来 ——
   * 只聚焦题库确实单调，英语是第二个真实的练习场景。
   *
   * 放出来之前已经把这条链路上的**真实 bug 修完**（不是只把注释解开）：
   *   · 词书接口打的是不存在的 `/front/list` 路由，被 catch_all 兜成空列表；
   *   · 前端读 `book.id / word.english / word.chinese`，后端给的是
   *     `bookId / word / translation` —— 点卡片会跳到 `/undefined`；
   *   · 还有个 `isMastered` 概念，后端表里压根没有这一列。
   * 详见各页面顶部的说明。
   *
   * ⚠️ 2026-10-26 下线「首页」（用户：「英语学习的首页直接去掉」）。
   *
   *    原来这里是 5 项，第一项是「首页」——一张四宫格入口卡片。
   *    但它和左侧二级菜单**完全重复**：下面四项就是那四张卡片，
   *    用户点进来还要在"菜单"和"卡片"之间做同一个选择，多一层跳转。
   *
   *    去掉后点击「英语学习」直接落在「拍照识词」，二级菜单只剩四项，
   *    与其它模块（我的学习 / 题库练习）的层级习惯一致。
   *    `home/index.vue` 文件保留但不再被菜单引用（路由也已重定向，见 router）。
   */
  {
    key: 'english',
    label: '英语学习',
    icon: 'languages',
    to: '/front/english/ocr',
    match: '/front/english',
    cacheKey: 'english',
    requiresLogin: true,
    children: [
      { label: '拍照识词', to: '/front/english/ocr', cacheKey: 'ocr' },
      { label: '我的词库', to: '/front/english/vocabulary', cacheKey: 'vocabulary' },
      { label: '单词听写', to: '/front/english/listening', cacheKey: 'listening' },
      { label: '阅读练习', to: '/front/english/reading', cacheKey: 'reading' }
      /*
       * 「学习统计」入口已移除（2026-10-26）
       * ---------------------------------
       * 用户：「两个页面的学习统计有点多余了，想办法融合起来」。
       *
       * 英语统计已经并进「我的学习 › 学习统计」的第二个 tab，
       * 侧边栏再留一个同名项就是重复导航 —— 和之前处理
       * 「我的错题 / 我的斩题」「题库收藏」是同一个判断：
       * 同一个功能不该在侧栏出现两次。
       *
       * 路由 `/front/english/statistics` 仍然保留（见 router/index.ts），
       * 从别的页面直接跳过去仍能打开，只是不再有侧栏入口。
       */
    ]
  }
  /*
   * 「实用工具」本系统暂时不需要，隐藏（路由与页面都还在，解开注释即可恢复）：
   *
   * { key: 'tools', label: '实用工具', icon: 'wrench', to: '/front/tools/home',
   *   match: '/front/tools', cacheKey: 'tools', children: [...] },
   */
]

/* ==================== 二级展开状态 ==================== */
const openGroups = reactive<Record<string, boolean>>({})

const activeKey = computed(() => featureItems.find((n) => isActive(n))?.key || '')

watch(
  activeKey,
  (key) => {
    if (key) openGroups[key] = true
  },
  { immediate: true }
)

function toggleGroup(key: string) {
  openGroups[key] = !openGroups[key]
}

function isActive(item: NavItem) {
  return route.path === item.match || route.path.startsWith(item.match + '/')
}

function isChildActive(child: NavChild) {
  const path = child.to.split('?')[0]
  if (route.path === path) return true
  return route.path.startsWith(path + '/')
}

const isAgentPage = computed(() => route.path.startsWith('/front/agent'))

/**
 * 侧栏某条会话是否该高亮
 * ================================
 * 用户 2026-10-19：「点了 A 会话后离开对话页去刷题，A 会话依旧处于被选中状态」。
 *
 * `currentSessionId` 记的是「上次打开过哪个会话」，它是**持久化**的（刷新要恢复），
 * 用户离开对话页并不会清掉它。所以光比对 id 会让这条会话在任何页面都亮着，
 * 看起来像"当前正在这里的会话"，实际上你人已经在题库页了。
 *
 * 高亮表达的是「你现在在哪儿」，因此必须同时满足：
 *   · 就在对话页（`isAgentPage`，与收起态那个「回到对话」图标同口径）
 *   · 且这条正是当前会话
 *
 * ⚠️ 不要用 `currentSessionId = ''` 来表示"离开对话页" —— 那会把持久化位置也一起
 *    抹掉，刷新/切回来就无法恢复上次的会话了（bug 反复的根源就在这两件事被混为一谈）。
 */
function isSessionActive(s: any) {
  return isAgentPage.value && s?.sessionId === sessionStore.currentSessionId
}

/* ==================== 导航动作 ==================== */
function onFeatureClick(item: NavItem) {
  if (item.children && !props.collapsed) {
    toggleGroup(item.key)
    return
  }
  navigate(item.to, item.requiresLogin)
}

function onChildClick(item: NavItem, child: NavChild) {
  if (child.cacheKey) cacheStore.setLastVisited(item.key, child.cacheKey)
  navigate(child.to, item.requiresLogin)
}

async function navigate(to: string, requiresLogin?: boolean) {
  if (requiresLogin && !(await ensureLogin('使用该功能'))) return
  if (route.fullPath !== to) router.push(to)
  emitNavigate()
}

function emitNavigate() {
  emit('navigate')
}

function goEntry() {
  router.push('/front/agent/chat')
  emitNavigate()
}

/** 新建对话：清掉当前会话 + 让对话页重置 */
async function startNewChat() {
  if (!(await ensureLogin('使用智能对话'))) return
  agentUiStore.requestNewChat()
  if (route.path !== '/front/agent/chat') router.push('/front/agent/chat')
  emitNavigate()
}

/**
 * 打开设置抽屉
 * ------------
 * 用户 2026-10-18：「设置面板和智能会话绑定在一起…我在题库练习页面点设置，
 * 它会自动跳到智能会话页面，这不合理。设置按钮应该作为全局设置对象，
 * **在哪里点击就在那个页面展开**。」
 *
 * 所以这里**不再 router.push**。设置抽屉已经提升为全局组件
 * （`components/GlobalSettings`，挂在外壳 `layout/front.vue` 上），
 * 侧栏只负责发一个信号，它在当前页面就地展开。
 *
 * ⚠️ 同时删掉了 `emitNavigate()`：那是"点了导航项就收起移动端侧栏"用的，
 *    现在点设置不跳页面，再收侧栏会让抽屉莫名其妙跟着收起。
 */
async function openSettings() {
  if (!(await ensureLogin('修改设置'))) return
  agentUiStore.requestSettings()
}

/* ==================== 会话列表 ==================== */
const searchOpen = ref(false)
const searchRef = ref<any>(null)

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) {
    nextTick(() => searchRef.value?.focus?.())
  } else {
    sessionStore.keyword = ''
  }
}

function closeSearch() {
  searchOpen.value = false
  sessionStore.keyword = ''
}

async function openSession(s: any) {
  if (!s?.sessionId) return
  if (!(await ensureLogin('继续对话'))) return
  // 当前会话：只是回到对话页，不重新加载
  if (s.sessionId === sessionStore.currentSessionId && isAgentPage.value) return
  sessionStore.selectSession(s.sessionId)
  if (route.path !== '/front/agent/chat') router.push('/front/agent/chat')
  emitNavigate()
}

async function removeSession(s: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${plainTitle(sessionStore.title(s))}」吗？`, '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    await sessionStore.removeSession(s.sessionId)
  } catch {
    // 删除失败：交给 chat.vue 的全局错误提示，这里不重复弹
  }
}

/**
 * 会话列表加载
 * ------------
 * ⚠️ 不能在 setup 顶层直接调：那时 `userStore.id` 往往还是空（getInfo 刚发出），
 *    `loadSessions` 里 `if (!userId) return` 会直接吞掉，于是侧栏永远显示"还没有对话"。
 *    所以这里 watch 用户 id，拿到就加载一次（id 变了也重新加载）。
 */
watch(
  () => userStore.id,
  (id) => {
    if (id && !sessionStore.sessions.length) sessionStore.loadSessions()
  },
  { immediate: true }
)

/* ==================== 提示 ====================
 * 账号区（头像 / 用户名 / 下拉：个人中心、后台管理、退出登录）已整体移到右上角顶栏
 * （见 `layout/front.vue`）。侧栏底部只留「设置」，所以这里不再有 goProfile/goAdmin/logout。
 * 未登录时的「登录 / 注册」入口也一并交给顶栏 —— 身份相关的操作集中在一处。
 */
</script>

<style scoped lang="scss">
.os-sidebar {
  position: relative;
  width: var(--os-sidebar-w);
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 6px 12px;
  box-sizing: border-box;
  border-radius: 0;
  background: var(--os-bg-sidebar);
  color: var(--os-text);
  font-size: 14px;
  overflow: hidden;
  transition: width var(--ds-duration-base) var(--ds-ease-in-out),
    padding var(--ds-duration-base) var(--ds-ease-in-out);

  &.is-resizing {
    transition: none;
  }

  &.is-collapsed {
    width: var(--os-sidebar-w-collapsed);
    padding: 6px 10px;
  }
}

/* 右边缘拖拽手柄：8px 命中区 + hover 才显形的细线 */
.sb-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 8px;
  z-index: 20;
  cursor: col-resize;
  background: transparent;

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    right: 2px;
    width: 3px;
    height: 32px;
    transform: translateY(-50%);
    border-radius: 2px;
    background: transparent;
    transition: background 0.15s;
  }

  &:hover::after {
    background: var(--dsw-static-neutral-bluish-300);
  }
}

/* ==================== ① 品牌 ==================== */
.sb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 60px;
  padding: 8px 0 8px 4px;
  margin-bottom: 4px;
  flex-shrink: 0;

  .is-collapsed & {
    height: 44px;
    padding: 0;
    justify-content: center;
    margin-bottom: 10px;
  }
}

.sb-brand {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  height: 34px;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  overflow: hidden;
}

/* 品牌标由 `OsLogo` 组件渲染（与 favicon 同一套几何），这里不再自己画 */

.sb-name {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--os-text);
  white-space: nowrap;
}

.sb-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex: none;
  padding: 0;
  border: none;
  border-radius: var(--os-radius-sm);
  background: transparent;
  color: var(--os-text-3);
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-text);
  }
}

.sb-rail-toggle {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  color: var(--os-text-2);
}

/* ==================== ② 新建对话 ==================== */
.sb-new {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  height: 38px;
  margin: 0 0 10px;
  padding: 0 12px;
  box-sizing: border-box;
  flex-shrink: 0;
  border: 0.5px solid var(--os-border-strong);
  border-radius: var(--os-radius);
  background: #fff;
  color: var(--os-text);
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--dsw-static-neutral-bluish-75);
  }

  .is-collapsed & {
    width: 38px;
    padding: 0;
    border-color: transparent;
    background: transparent;

    &:hover {
      background: var(--os-bg-hover);
    }
  }
}

.sb-new__label {
  white-space: nowrap;
}

/* ==================== ② 功能入口 ==================== */
/*
 * 中段滚动容器（功能区 + 会话列表）
 *
 * 只有这一条滚动条：菜单展开多长都能滚到，会话列表也在这条线上。
 * `min-height: 0` 是关键 —— 没有它，flex 子项的最小内容高度会让容器撑破父级
 * （这正是"展开我的学习后各段被挤压"的机制）。
 */
.sb-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-thumb {
    border-width: 2px;
  }
}

/* 功能入口区：自然高度，滚动交给外层 `.sb-scroll` */
.sb-features {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: none;
}

.sb-group {
  display: flex;
  flex-direction: column;
}

.sb-row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.sb-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 1;
  min-width: 0;
  height: 36px;
  padding: 0 9px;
  border: none;
  border-radius: var(--os-radius);
  background: transparent;
  color: var(--os-text-2);
  font-size: 14px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-text);
  }

  &.is-active {
    background: var(--dsw-specific-sidebar-nav-item-active);
    color: var(--os-text);
    font-weight: 500;
  }

  .is-collapsed & {
    flex: none;
    width: 40px;
    height: 40px;
    padding: 0;
    justify-content: center;
  }
}

.sb-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  color: inherit;
  opacity: 0.9;

  .is-active > & {
    opacity: 1;
    color: var(--os-text);
  }
}

.sb-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sb-pip {
  position: absolute;
  left: 3px;
  top: 50%;
  width: 3px;
  height: 14px;
  margin-top: -7px;
  border-radius: 2px;
  background: var(--os-accent);
}

.sb-caret {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: var(--os-radius-sm);
  background: transparent;
  color: var(--os-text-4);
  cursor: pointer;
  transition: transform var(--ds-duration-fast) var(--ds-ease-in-out),
    background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-text-2);
  }

  &.is-open {
    transform: rotate(90deg);
  }
}

/* 二级：细竖线 + 缩进 */
.sb-children {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: 2px 0 4px 27px;
  padding-left: 10px;
  border-left: 1px solid var(--os-border-soft);
}

.sb-child {
  display: flex;
  align-items: center;
  height: 30px;
  padding: 0 9px;
  border: none;
  border-radius: var(--os-radius-sm);
  background: transparent;
  color: var(--os-text-3);
  font-size: 13px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-text);
  }

  &.is-active {
    background: var(--os-bg-active);
    color: var(--os-text);
    font-weight: 500;
  }
}

/* ==================== ③ 智能对话（会话列表） ==================== */
/*
 * 关键点：这一段 `flex: 1; min-height: 0`，内部列表 `overflow-y: auto`。
 * 只有列表滚动，品牌 / 功能入口 / 底部始终固定可见。
 */
/*
 * 会话区：跟着外层 `.sb-scroll` 一起滚，自己不再滚动。
 * （两层滚动条会互相打架：内层滚到顶继续滚时，外层才动，手感很怪。）
 */
.sb-conv {
  flex: none;
  display: flex;
  flex-direction: column;
  /* 与上面的功能入口用留白分隔（不用分割线，DSH 的做法） */
  margin-top: 16px;
  padding-bottom: 4px;
}

.sb-conv__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  height: 26px;
  padding: 0 4px 0 9px;
  flex-shrink: 0;
}

.sb-conv__title {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--os-text-4);
  user-select: none;
}

.sb-conv__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--os-text-4);
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover,
  &.is-on {
    background: var(--os-bg-hover);
    color: var(--os-text-2);
  }
}

.sb-conv__search {
  flex-shrink: 0;
  padding: 2px 2px 6px;
}

/* 会话列表：不再自己滚动（统一由外层 `.sb-scroll` 滚），只是纵向排列 */
.sb-conv__list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 2px 2px 4px;
}

.sb-conv__item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 7px 24px 7px 9px;
  box-sizing: border-box;
  border: none;
  border-radius: var(--os-radius-sm);
  background: transparent;
  color: var(--os-text-2);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-text);
  }

  &.is-active {
    background: var(--os-bg-active);
    color: var(--os-text);
    font-weight: 500;
  }

  &:hover .sb-conv__del,
  &.is-active .sb-conv__del {
    opacity: 1;
  }
}

.sb-conv__name {
  font-size: 13px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sb-conv__meta {
  font-size: 11px;
  line-height: 1.3;
  color: var(--os-text-4);
  font-weight: 400;
}

.sb-conv__del {
  position: absolute;
  top: 50%;
  right: 4px;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 5px;
  color: var(--os-text-4);
  opacity: 0;
  transition: opacity var(--ds-duration-fast) var(--ds-ease-in-out),
    background-color var(--ds-duration-fast) var(--ds-ease-in-out),
    color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-danger);
  }
}

.sb-conv__empty {
  margin: 10px 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--os-text-4);
  word-break: break-word;
}

/* 收起态：只有一枚「回到对话」的图标 */
.sb-rail-conv {
  display: flex;
  flex-direction: column;
  margin-top: 10px;
}

/* ==================== ④ 底部 ==================== */
.sb-foot {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 8px;
  margin-top: 6px;

  .is-collapsed & {
    align-items: center;
  }
}
</style>
