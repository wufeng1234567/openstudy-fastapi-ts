<!--
  front.vue — 前台应用外壳（App Shell）
  ============================================================================
  形态对齐 DSH Web：**左侧竖向导航 + 右侧内容区**，不再有顶部横向菜单、
  不再有"首页轮播"这种与智能体无关的落地页。

  三层结构：
    ① Sidebar   —— 品牌 / 新建对话 / 模块导航 / 底部账号区（可折叠、移动端抽屉）
    ② Topbar    —— 当前页标题 + 消息入口（52px，一条发丝分割线，不抢内容）
    ③ Content   —— 路由出口；普通页面自行滚动，智能体 / 笔记编辑器走"满高"模式

  与旧版的差异（都是刻意的）：
    · 删掉顶部 header / nav / footer —— 导航全部进竖栏，页脚不再占高度；
    · 删掉 `agent-mode` 那套「100vh - 68px」魔法高度 —— 顶栏高度现在由
      `--os-topbar-h` 统一声明，内容区用 flex 自然分配，不再手算；
    · 智能体页不再套一层圆角边框卡片（它就是主内容，不该像弹窗）。
-->
<template>
  <div class="os-app" :class="{ 'is-mobile-open': mobileOpen }">
    <!-- ==================== ① 侧边栏 ==================== -->
    <div class="os-sidebar-host">
      <FrontSidebar
        :collapsed="collapsed"
        :unread-count="unreadCount"
        @toggle="toggleSidebar"
        @navigate="mobileOpen = false"
      />
    </div>

    <!-- 移动端抽屉遮罩 -->
    <div v-if="mobileOpen" class="os-backdrop" @click="mobileOpen = false" />

    <!-- ==================== ② 主区 ==================== -->
    <div class="os-main">
      <header class="os-topbar">
        <div class="os-topbar__left">
          <!--
            只在移动端出现：桌面端收起侧栏后，展开入口在**最左侧图标栏**里（见 FrontSidebar），
            内容区不再放第二个展开按钮（用户明确要求：收起后按钮不要出现在路由显示区域）。
          -->
          <button
            v-if="isMobile"
            type="button"
            class="os-icon-btn"
            title="打开导航"
            @click="onTopbarMenu"
          >
            <OsIcon name="panel-left" :size="17" />
          </button>
          <h1 class="os-topbar__title">{{ pageTitle }}</h1>
        </div>

        <div class="os-topbar__right">
          <button
            type="button"
            class="os-icon-btn os-bell"
            title="消息中心"
            @click="goMessages"
          >
            <OsIcon name="bell" :size="17" />
            <i v-if="unreadCount > 0" class="os-bell__dot" />
          </button>

          <!--
            「新对话」按钮已删除（2026-10-17）：会话列表与「新建对话」都在侧栏，
            顶栏在其它 tab 页再放一个 +新对话 属于重复入口，没有必要。

            账号区从侧栏底部搬到这里（右上角）：
              · 头像 + 昵称 + 角色，点开是下拉；
              · 下拉里**不再有「消息中心」** —— 消息入口只保留顶栏这个铃铛（外层唯一的那个），
                避免同一个人在一个屏幕里看到两个消息入口；
              · 其余（个人中心 / 后台管理 / 退出登录）保持不变。
          -->
          <el-dropdown
            v-if="isLogin"
            trigger="click"
            placement="bottom-end"
            popper-class="os-user-pop"
          >
            <button type="button" class="os-user" :title="displayName">
              <UserAvatar :src="userStore.avatar" :name="displayName" :size="26" />
              <span class="os-user__meta">
                <span class="os-user__name">{{ displayName }}</span>
                <span class="os-user__role">{{ roleLabel }}</span>
              </span>
              <OsIcon name="chevron-down" :size="13" class="os-user__caret" />
              <i v-if="unreadCount > 0" class="os-user__dot" />
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="goProfile">
                  <OsIcon name="user" :size="15" class="dd-ico" />个人中心
                </el-dropdown-item>
                <el-dropdown-item v-if="isAdmin" @click="goAdmin">
                  <OsIcon name="settings" :size="15" class="dd-ico" />后台管理
                </el-dropdown-item>
                <el-dropdown-item divided @click="doLogout">
                  <OsIcon name="log-out" :size="15" class="dd-ico" />退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 未登录 / 游客：登录、注册入口也在右上角（身份相关操作集中一处） -->
          <template v-else>
            <button type="button" class="os-topbar__link" @click="goLogin">登录</button>
            <button type="button" class="os-topbar__signup" @click="goRegister">注册</button>
          </template>
        </div>
      </header>

      <!--
        内容区：两种模式
          · flush —— 页面自己管滚动与高度（智能体对话 / 笔记编辑器）
          · 默认  —— 由这里滚动，页面各自负责内边距
        keep-alive 仍由 tagsViewStore 的 cachedViews 控制（与旧版一致）。
      -->
      <main class="os-content" :class="{ 'is-flush': isFlushPage }">
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedViews">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
    </div>

    <!-- 全局悬浮 AI 助手：智能体页本身就是对话页，不再叠一个悬浮球 -->
    <AiAssistant v-if="isLogin && !isGuest && !isAgentPage" />

    <!--
      全局设置抽屉
      ------------------------------------------------------------------
      用户 2026-10-18：「设置面板和智能会话目前是绑定在一起的…设置按钮应该作为
      一个全局设置对象处理，在哪里点击就在那个页面展开。」

      所以它挂在**外壳**上（不是挂在对话页里）：
        · 任何页面点侧栏「设置」都在**当前页**就地展开，不再被拽去对话页；
        · 侧栏只发一个信号（`agentUi.requestSettings()`），不做 router.push；
        · 与对话页彻底解耦，也就不会再出现"keep-alive 反复激活导致两个抽屉"。
    -->
    <GlobalSettings v-if="isLogin && !isGuest" />
  </div>
</template>

<script setup lang="ts">
/**
 * 前台外壳逻辑
 * =============
 * 只保留四件事：
 *   1. 侧栏折叠状态（持久化到 localStorage）+ 移动端抽屉开关；
 *   2. 未读消息数（路由变化时刷新，供侧栏红点 / 顶栏圆点使用）；
 *   3. keep-alive 页面缓存的注册（沿用 tagsView 机制，不动业务页）；
 *   4. 登录态 / 游客态判断与页面级布局模式（flush）。
 * 具体的导航项、跳转、账号菜单都在 FrontSidebar 里，避免外壳越堆越厚。
 */
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import useTagsViewStore from '@/store/modules/tagsView'
import { ensureLogin } from '@/utils/loginGuard'
import { checkRole } from '@/utils/permission'
import { ElMessageBox } from 'element-plus'
import { listAllNotice } from '@/api/system/notice'
import { getNotificationUnreadCount } from '@/api/notification/notification'
import { isSystemNotice, isUserNoticeFor } from '@/utils/notice'
import { getToken } from '@/utils/auth'
import FrontSidebar from '@/components/FrontSidebar/index.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import UserAvatar from '@/components/UserAvatar/index.vue'
import AiAssistant from '@/components/AiAssistant/index.vue'
import GlobalSettings from '@/components/GlobalSettings/index.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const tagsViewStore = useTagsViewStore()

// ==================== 布局状态 ====================
const COLLAPSE_KEY = 'os_sidebar_collapsed'

const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')
const mobileOpen = ref(false)
const isMobile = ref(false)

let media: MediaQueryList | null = null
const syncMobile = (e: MediaQueryListEvent | MediaQueryList) => {
  isMobile.value = e.matches
  // 从移动端切回桌面：抽屉状态复位，避免遮罩残留
  if (!e.matches) mobileOpen.value = false
}

onMounted(() => {
  media = window.matchMedia('(max-width: 900px)')
  syncMobile(media)
  media.addEventListener('change', syncMobile)
  window.addEventListener('keydown', onGlobalKeydown)

  // 刷新页面后 Pinia 里可能还没有用户信息（游客判断依赖它）
  if (getToken() && !userStore.name) {
    userStore.getInfo().catch(() => {})
  }
  fetchUnread()
})

onBeforeUnmount(() => {
  media?.removeEventListener('change', syncMobile)
  window.removeEventListener('keydown', onGlobalKeydown)
})

/**
 * 侧栏收起/展开快捷键：Ctrl + Alt + B（与 DSH 的侧边栏开关同一组合）
 * 在输入框里打字时不拦截，避免和浏览器/输入法的组合键打架。
 */
function onGlobalKeydown(e: KeyboardEvent) {
  if (!e.ctrlKey || !e.altKey || e.key.toLowerCase() !== 'b') return
  const el = e.target as HTMLElement | null
  const tag = el?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || el?.isContentEditable) return
  e.preventDefault()
  toggleSidebar()
}

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
}

function onTopbarMenu() {
  if (isMobile.value) mobileOpen.value = true
  else toggleSidebar()
}

/** 移动端点导航后自动收起抽屉 */
watch(
  () => route.path,
  () => {
    mobileOpen.value = false
  }
)

// ==================== 未读消息 ====================
const unreadCount = ref(0)

provide('refreshBadge', (type: string, count: number) => {
  if (type === 'sys') unreadCount.value = count
})

async function fetchUnread() {
  if (!getToken() || userStore.isGuest) {
    unreadCount.value = 0
    return
  }
  try {
    const res = await listAllNotice()
    const all = res.data || []
    const myId = userStore.id
    unreadCount.value = all.filter(
      (n) => !n.read && (isSystemNotice(n) || isUserNoticeFor(n, myId))
    ).length
  } catch (e) {
    /* 静默：红点失败不影响页面 */
  }
  try {
    const notifyRes = await getNotificationUnreadCount()
    unreadCount.value = (unreadCount.value || 0) + (notifyRes.data || 0)
  } catch (e) {
    /* 未登录 / 失败忽略 */
  }
}

watch(() => route.path, fetchUnread)

// ==================== 用户态 / 页面模式 ====================
const isLogin = computed(() => !!userStore.token)
const isGuest = computed(() => userStore.isGuest)

const isAgentPage = computed(() => route.path.startsWith('/front/agent'))
const isNotesEditorPage = computed(() => route.path === '/front/notes/editor')
const isMessagesPage = computed(() => route.path.startsWith('/front/messages'))

/** 满高页面：自己管滚动，外壳不套 padding */
const isFlushPage = computed(
  () => isAgentPage.value || isNotesEditorPage.value || isMessagesPage.value
)

/**
 * 顶栏标题 = **模块名**，不是叶子页面名。
 * 理由：业务页自己都有二级标题（"我的题库 共 9 个" / "系统通知"…），
 * 顶栏再显示一遍叶子标题就是重复；这里统一显示模块名，形成"模块 → 页面"的层级。
 */
const SECTION_TITLES: Array<[string, string]> = [
  ['/front/agent', '智能对话'],
  ['/front/questionPractice', '题库练习'],
  ['/front/myQuestion', '我的学习'],
  ['/front/notes', '学习分享'],
  ['/front/english', '英语学习'],
  ['/front/studio', '题库搭建'],
  ['/front/tools', '实用工具箱'],
  ['/front/messages', '消息中心'],
  ['/front/profile', '个人中心']
]

const pageTitle = computed(() => {
  const hit = SECTION_TITLES.find(([prefix]) => route.path.startsWith(prefix))
  if (hit) return hit[1]
  return (route.meta?.title as string) || 'OpenStudy'
})

// ==================== 动作 ====================
async function goMessages() {
  if (!(await ensureLogin('查看消息中心'))) return
  router.push('/front/messages')
}

/* ---- 账号区（右上角）---- */
const isAdmin = computed(() => checkRole(['admin']))
const displayName = computed(() => userStore.nickName || userStore.name || '用户')
const roleLabel = computed(() => {
  if (userStore.isGuest) return '游客模式'
  if (isAdmin.value) return '管理员'
  return '学习者'
})

function goProfile() {
  router.push('/front/profile')
}

function goAdmin() {
  router.push('/index/home')
}

function goLogin() {
  router.push({ path: '/login', query: { redirect: route.fullPath } })
}

function goRegister() {
  router.push({ path: '/register', query: { redirect: route.fullPath } })
}

async function doLogout() {
  try {
    await ElMessageBox.confirm(
      userStore.isGuest ? '确定退出游客模式吗？' : '确定退出登录吗？',
      '提示',
      { confirmButtonText: '退出', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  await userStore.logOut()
  router.push('/front/agent/chat')
}

// ==================== keep-alive 缓存注册 ====================
/**
 * 与旧版一致：把聚合页 / 编辑器等"父级容器"手动注册进缓存表。
 * 缓存名必须与对应组件的 defineOptions({ name }) 完全一致。
 */
watch(
  () => route.path,
  () => {
    const { name, meta, path, fullPath, query } = route

    if (name && !meta.hidden && name !== 'login' && name !== 'register') {
      tagsViewStore.addView({ name, path, fullPath, meta, query })
    }

    const register = (cacheName: string, cachePath: string, title: string) => {
      if (!tagsViewStore.cachedViews.includes(cacheName)) {
        tagsViewStore.addView({ name: cacheName, path: cachePath, fullPath: cachePath, meta: { title } })
      }
    }

    if (path.startsWith('/front/myQuestion')) register('FrontMyQuestion', '/front/myQuestion', '我的学习')
    if (path.startsWith('/front/studio')) register('FrontStudio', '/front/studio', '题库搭建')
    if (path.startsWith('/front/notes/editor')) register('FrontNotesEditor', path, '笔记编辑')
    else if (path.startsWith('/front/notes')) register('FrontNotes', '/front/notes', '学习分享')
    if (path.startsWith('/front/agent')) register('FrontAgent', '/front/agent', '智能体')
    if (path.startsWith('/front/messages')) register('FrontMessages', '/front/messages', '消息中心')
    if (path.startsWith('/front/questionPractice')) {
      register('FrontQuestionPractice', '/front/questionPractice', '题库练习')
    }
    if (path.startsWith('/front/english')) register('FrontEnglish', '/front/english', '英语学习')
    if (path.startsWith('/front/tools')) register('FrontTools', '/front/tools', '实用工具')
  },
  { immediate: true }
)

const cachedViews = computed(() => tagsViewStore.cachedViews)
</script>

<style scoped lang="scss">
/* ==================== 应用外壳 ==================== */
.os-app {
  display: flex;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  border-radius: 0;
  background: var(--os-bg);
  color: var(--os-text);
}

/* 侧栏与主区必须"严丝合缝"：不留外边距、不留圆角，交接处只用一条 1px 发丝线 */
.os-sidebar-host {
  flex: none;
  height: 100%;
  z-index: 30;
  margin: 0;
  border-radius: 0;
  border-right: 1px solid var(--os-border-soft);
  box-sizing: border-box;
}

.os-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  margin: 0;
  border-radius: 0;
  background: var(--os-bg);
}

/* ==================== 顶栏 ==================== */
.os-topbar {
  flex: none;
  height: var(--os-topbar-h);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
  padding: 0 16px 0 20px;
  border-radius: 0;
  border-bottom: 1px solid var(--os-border-soft);
  background: #fff;
  box-sizing: border-box;
}

.os-topbar__left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.os-topbar__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--os-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.os-topbar__right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.os-bell {
  position: relative;
}

.os-bell__dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--os-accent);
  box-shadow: 0 0 0 2px #fff;
}

/* ==================== 右上角账号区 ====================
   从侧栏底部搬过来的（用户 2026-10-17）。顶栏只有 52px 高，
   所以这里做成「小头像 + 两行文字（名字 / 角色）」的紧凑形态，
   hover 给一层浅底，点开是下拉。 */
.os-user {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 8px 0 5px;
  border: none;
  border-radius: var(--os-radius-sm);
  background: transparent;
  color: var(--os-text);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out);

  &:hover {
    background: var(--os-bg-hover);
  }
}

.os-user__meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  max-width: 130px;
  line-height: 1.2;
}

.os-user__name {
  font-size: 13px;
  font-weight: 500;
  color: var(--os-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.os-user__role {
  font-size: 11px;
  color: var(--os-text-4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.os-user__caret {
  flex: none;
  color: var(--os-text-4);
}

.os-user__dot {
  position: absolute;
  top: 6px;
  left: 24px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--os-accent);
  box-shadow: 0 0 0 2px #fff;
}

/* 未登录：登录 / 注册 */
.os-topbar__link,
.os-topbar__signup {
  height: 30px;
  padding: 0 12px;
  border-radius: var(--os-radius-sm);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
}

.os-topbar__link {
  border: 1px solid var(--os-border);
  background: #fff;
  color: var(--os-text);

  &:hover {
    background: var(--dsw-static-neutral-bluish-75);
  }
}

.os-topbar__signup {
  border: 1px solid var(--os-primary);
  background: var(--os-primary);
  color: #fff;

  &:hover {
    background: var(--os-primary-hover);
  }
}

/* 顶栏账号下拉：popper 在 body 上，样式不能 scoped */

/* ==================== 内容区 ==================== */
.os-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--os-bg);
  border-radius: 0;

  &.is-flush {
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
}

/*
 * 页面根节点不允许再自带圆角/外边距：
 * 曾经出现过"内容区是一张悬浮圆角卡片"的写法，卡片四角会把侧栏底色露出来，
 * 在侧栏与内容之间形成一道弧形空隙。外壳已经负责分栏与留白，页面根节点保持方正、贴边。
 */
.os-content > * {
  border-radius: 0;
  margin-top: 0;
  margin-bottom: 0;
}

/* ==================== 移动端 ==================== */
.os-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(15, 17, 21, 0.32);
  backdrop-filter: blur(2px);
}

@media (max-width: 900px) {
  .os-sidebar-host {
    position: fixed;
    top: 0;
    left: 0;
    height: 100%;
    z-index: 50;
    transform: translateX(-100%);
    transition: transform var(--ds-duration-base) var(--ds-ease-in-out);
    box-shadow: 12px 0 32px rgba(0, 0, 0, 0.12);
  }

  /* 抽屉态宽度固定：拖拽出来的内联宽度（桌面端记忆值）在移动端不适用 */
  .os-sidebar-host :deep(.os-sidebar) {
    width: min(86vw, 320px) !important;
  }

  .os-sidebar-host :deep(.sb-resize-handle) {
    display: none;
  }

  .is-mobile-open .os-sidebar-host {
    transform: translateX(0);
  }

  .os-topbar {
    padding: 0 12px;
  }
}
</style>

<style lang="scss">
/* 顶栏账号下拉：popper 挂在 body 上，必须放在非 scoped 样式里 */
.os-user-pop {
  min-width: 160px;

  .dd-ico {
    margin-right: 8px;
    color: var(--os-text-3);
  }
}
</style>
