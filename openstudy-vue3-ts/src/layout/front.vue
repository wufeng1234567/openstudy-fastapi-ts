<!--
  front.vue — 前台全局布局组件
  ============================
  这是所有前台页面的"骨架"，负责：
  1. 顶部导航栏（Logo、导航菜单、消息铃铛、用户下拉菜单）
  2. 中间内容区（通过 router-view + keep-alive 实现页面缓存）
  3. 底部页脚
  4. 全局悬浮 AI 助手
-->
<template>
    <!--
      最外层容器通过 CSS class 控制特殊场景：
      - hide-footer：消息中心、笔记编辑器页面隐藏底部页脚
      - notes-editor-mode：笔记编辑器全屏模式，去掉内边距
    -->
    <div class="front-layout" :class="{ 'hide-footer': hideFooter, 'notes-editor-mode': isNotesEditorPage }">

        <!-- ==================== 顶部导航栏 ==================== -->
        <header class="front-header">
            <div class="header-container">

                <!-- Logo：点击回到首页 -->
                <div class="logo" @click="$router.push('/front/index')">
                    <h1>📚 OpenStudy</h1>
                </div>

                <!-- 导航菜单 -->
                <nav class="nav-menu">
                    <!-- 简单页面用 router-link 直接跳转 -->
                    <router-link to="/front/index">首页</router-link>
                    <router-link to="/front/questionPractice">题库练习</router-link>

                    <!--
                      复杂模块用 <a> + goToModule() 跳转：
                      实现"记住上次访问的子页面"功能，
                      比如用户上次在"我的学习 > 错题本"，下次点击直接回到错题本
                    -->
                    <a @click.prevent="goToModule('myQuestion', 'myBank')"
                        :class="{ 'router-link-active': isModuleActive('myQuestion') }">
                        我的学习
                    </a>
                    <a @click.prevent="goToStudio"
                        :class="{ 'router-link-active': isModuleActive('studio') }">
                        题库搭建
                    </a>
                    <a @click.prevent="goToModule('notes', 'list')"
                        :class="{ 'router-link-active': isModuleActive('notes') }">
                        学习分享
                    </a>
                </nav>

                <!-- 右侧用户区域 -->
                <div class="user-area">
                    <!--
                      消息铃铛：登录后显示，带未读数红点
                      - el-badge 的 :hidden 属性在 unreadCount === 0 时自动隐藏红点
                      - 点击跳转到消息中心页面
                    -->
                    <el-badge v-if="isLogin && !isGuest" :value="unreadCount" :hidden="unreadCount === 0" class="bell-badge">
                        <el-button class="bell-btn" :icon="Bell" circle @click="goMessages" />
                    </el-badge>

                    <!-- 未登录：显示登录/注册按钮 -->
                    <template v-if="!isLogin">
                        <el-button text @click="$router.push('/login')">登录</el-button>
                        <el-button type="primary" @click="$router.push('/register')">注册</el-button>
                    </template>

                    <!-- 游客：只读身份，操作时提示登录 -->
                    <el-dropdown v-else-if="isGuest">
                        <span class="user-name">
                            <UserAvatar :src="userStore.avatar" :name="userStore.nickName || userStore.name" :size="32" />
                            游客 <el-icon>
                                <ArrowDown />
                            </el-icon>
                        </span>
                        <template #dropdown>
                            <el-dropdown-item @click="goLogin">
                                <el-icon>
                                    <User />
                                </el-icon>登录
                            </el-dropdown-item>
                            <el-dropdown-item @click="goRegister">
                                <el-icon>
                                    <Plus />
                                </el-icon>注册
                            </el-dropdown-item>
                        </template>
                    </el-dropdown>

                    <!-- 普通用户/管理员：显示用户下拉菜单 -->
                    <el-dropdown v-else>
                        <span class="user-name">
                            <UserAvatar :src="userStore.avatar" :name="userStore.nickName || userStore.name" :size="32" />
                            {{ userStore.nickName || userStore.name || '用户' }} <el-icon>
                                <ArrowDown />
                            </el-icon>
                        </span>
                        <template #dropdown>
                            <el-dropdown-item @click="$router.push('/front/profile')">
                                <el-icon>
                                    <User />
                                </el-icon>个人中心
                            </el-dropdown-item>
                            <!-- 仅管理员可见：切换到后台管理 -->
                            <el-dropdown-item v-if="isAdmin" @click="goAdmin">
                                <el-icon>
                                    <Switch />
                                </el-icon>切换到后台
                            </el-dropdown-item>
                            <el-dropdown-item divided @click="logout">
                                <el-icon>
                                    <Back />
                                </el-icon>退出登录
                            </el-dropdown-item>
                        </template>
                    </el-dropdown>
                </div>
            </div>
        </header>

        <!-- ==================== 主内容区 ==================== -->
        <!--
          keep-alive 实现页面缓存：
          - :include="cachedViews" 只缓存指定的页面组件（需要组件 name 匹配）
          - 切换路由时，已缓存的组件不会销毁，保持滚动位置等状态
          - tagsViewStore 统一管理哪些页面需要缓存
        -->
        <main class="front-main">
            <router-view v-slot="{ Component }">
                <keep-alive :include="cachedViews">
                    <component :is="Component" />
                </keep-alive>
            </router-view>
        </main>

        <!-- ==================== 底部页脚 ==================== -->
        <footer class="front-footer">
            <p>© 2026 OpenStudy 开源学习平台. All rights reserved.</p>
        </footer>

        <!-- 全局悬浮 AI 助手（纯 LLM 聊天，无 Agent）；游客只读，不展示 -->
        <AiAssistant v-if="isLogin && !isGuest" />
    </div>
</template>

<script setup lang="ts">
/**
 * 前台布局核心逻辑
 * =================
 * 主要职责：
 * 1. 未读消息轮询 — 路由切换时自动刷新铃铛红点
 * 2. 页面缓存管理 — 通过 tagsViewStore 控制 keep-alive 缓存哪些页面
 * 3. 模块跳转记忆 — goToModule() 记住用户上次访问的子页面
 * 4. 用户状态管理 — 登录态判断、角色判断、退出登录
 */
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { ArrowDown, Switch, User, Back, Bell, Plus } from '@element-plus/icons-vue'
import { provide } from 'vue'
import useUserStore from '@/store/modules/user'
import useTagsViewStore from '@/store/modules/tagsView'
import { checkRole } from "@/utils/permission"
import { ensureLogin } from '@/utils/loginGuard'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { listAllNotice } from '@/api/system/notice'
import { getNotificationUnreadCount } from '@/api/notification/notification'
import { isSystemNotice, isUserNoticeFor } from '@/utils/notice'
import { getToken } from '@/utils/auth'
import UserAvatar from '@/components/UserAvatar/index.vue'
import AiAssistant from '@/components/AiAssistant/index.vue'

const cacheStore = useFrontPageCacheStore()
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const tagsViewStore = useTagsViewStore()

// keep-alive 缓存列表（computed 响应式）
const cachedViews = computed(() => tagsViewStore.cachedViews)

// ==================== 未读消息红点 ====================
const unreadCount = ref(0)

// 提供 refreshBadge 函数给子组件
provide('refreshBadge', (type: string, count: number) => {
    if (type === 'sys') {
        unreadCount.value = count
    }
})

/**
 * 获取未读消息数
 * 调用后端 listAllNotice 接口获取所有通知，
 * 过滤出 isRead === false 的通知数量作为红点数字
 */
const fetchUnread = async () => {
    // 未登录 / 游客：不展示消息铃铛，也不轮询未读
    if (!getToken() || userStore.isGuest) {
        unreadCount.value = 0
        return
    }
    try {
        const res = await listAllNotice()
        const all = res.data || []
        const myId = userStore.id
        // 后端返回的是 read 字段（true=已读，false=未读）
        // 只统计系统公告 + 发给当前用户的用户通知（评论 / 回复 / @我），
        // 避免把发给别人的用户通知也算进红点
        const unreadCountValue = all.filter(n => !n.read && (isSystemNotice(n) || isUserNoticeFor(n, myId))).length
        unreadCount.value = unreadCountValue
    } catch (e) {
        // 获取失败静默处理，不影响页面使用
    }

    // 叠加「分享通知」等定向通知的未读数
    try {
        const notifyRes = await getNotificationUnreadCount()
        unreadCount.value = (unreadCount.value || 0) + (notifyRes.data || 0)
    } catch (e) {
        // 未登录 / 失败时忽略
    }
}

// ==================== 生命周期 ====================
onMounted(async () => {
    // 如果有 token 但没有用户信息（如刷新页面），先恢复用户信息，游客判断才可靠
    if (getToken() && !userStore.name) {
        await userStore.getInfo().catch(() => { })
    }
    // 页面加载时拉取未读消息数（游客跳过）
    fetchUnread()
})

// 路由切换时刷新未读消息数（实现"准实时"红点更新，无需 WebSocket）
watch(() => route.path, () => {
    fetchUnread()
})

// ==================== 导航菜单相关 ====================

/**
 * 判断当前路由是否属于某个模块（用于菜单高亮）
 * 例如：当前路径是 /front/myQuestion/myBank → 'myQuestion' 模块高亮
 */
const isModuleActive = (moduleKey) => {
    return route.path.startsWith(`/front/${moduleKey}`)
}

/**
 * 跳转到模块的子页面（带记忆功能）
 * @param moduleKey  模块标识，如 'myQuestion'
 * @param defaultPath 默认子页面，如 'myBank'
 *
 * 工作原理：
 * 1. 如果用户已在该模块内 → 不做任何跳转（避免重复渲染）
 * 2. 从 Pinia 缓存中读取上次访问的子页面路径
 * 3. 如果没有缓存记录，使用 defaultPath 作为默认值
 *
 * 示例：用户上次访问了 /front/myQuestion/wrongBook
 *       下次点击"我的学习"直接回到错题本，而不是默认的 myBank
 */
const goToModule = async (moduleKey, defaultPath) => {
    if (isModuleActive(moduleKey)) return
    // 「我的学习」是个人数据，游客先提示登录；「学习分享」是公开浏览，可直接进入
    if (moduleKey === 'myQuestion' && !(await ensureLogin('查看我的学习'))) return
    const lastVisited = cacheStore.getLastVisited(moduleKey, defaultPath)
    router.push(`/front/${moduleKey}/${lastVisited}`)
}

/**
 * 跳转到题库搭建模块（直接进入创建题库页面）
 */
const goToStudio = async () => {
    if (isModuleActive('studio')) return
    if (!(await ensureLogin('创建题库'))) return
    router.push('/front/studio/create?type=public')
}

// ==================== 页面缓存管理 ====================
/**
 * 监听路由变化，自动将页面注册到 keep-alive 缓存列表
 * 这样用户在模块间切换时，已访问的页面不会重新加载
 *
 * 注意：每个缓存的 name 必须和对应组件的 defineOptions({ name: 'xxx' }) 一致
 */
watch(() => route.path, () => {
    const { name, meta, path, fullPath, query } = route

    // 通用：将非隐藏页面加入 tagsView（顶部标签栏）
    if (name && !meta.hidden && name !== 'login' && name !== 'register') {
        tagsViewStore.addView({ name, path, fullPath, meta, query })
    }

    // 以下为各模块的聚合页缓存注册
    // 聚合页 = 包含子路由的父页面（如"我的学习"包含题库列表、错题本等子页面）

    // 我的学习聚合页缓存
    if (path.startsWith('/front/myQuestion') && !tagsViewStore.cachedViews.includes('FrontMyQuestion')) {
        tagsViewStore.addView({
            name: 'FrontMyQuestion',
            path: '/front/myQuestion',
            fullPath: '/front/myQuestion',
            meta: { title: '我的学习' }
        })
    }

    // 题库搭建聚合页缓存
    if (path.startsWith('/front/studio') && !tagsViewStore.cachedViews.includes('FrontStudio')) {
        tagsViewStore.addView({
            name: 'FrontStudio',
            path: '/front/studio',
            fullPath: '/front/studio',
            meta: { title: '题库搭建' }
        })
    }

    // 学习分享聚合页缓存
    if (path.startsWith('/front/notes') && !tagsViewStore.cachedViews.includes('FrontNotes')) {
        tagsViewStore.addView({
            name: 'FrontNotes',
            path: '/front/notes',
            fullPath: '/front/notes',
            meta: { title: '学习分享' }
        })
    }

    // 笔记编辑器缓存（编辑器需要保持输入状态，不能被销毁重建）
    if (path.startsWith('/front/notes/editor') && !tagsViewStore.cachedViews.includes('FrontNotesEditor')) {
        tagsViewStore.addView({
            name: 'FrontNotesEditor',
            path: path,
            fullPath: path,
            meta: { title: '笔记编辑' }
        })
    }

    // 消息中心缓存
    if (path.startsWith('/front/messages') && !tagsViewStore.cachedViews.includes('FrontMessages')) {
        tagsViewStore.addView({
            name: 'FrontMessages',
            path: '/front/messages',
            fullPath: '/front/messages',
            meta: { title: '消息中心' }
        })
    }

    // 题库练习聚合页缓存
    if (path.startsWith('/front/questionPractice') && !tagsViewStore.cachedViews.includes('FrontQuestionPractice')) {
        tagsViewStore.addView({
            name: 'FrontQuestionPractice',
            path: '/front/questionPractice',
            fullPath: '/front/questionPractice',
            meta: { title: '题库练习' }
        })
    }
}, { immediate: true })

// ==================== 计算属性 ====================

/** 是否已登录（通过 token 判断） */
const isLogin = computed(() => !!userStore.token)

/** 是否为游客只读账号 */
const isGuest = computed(() => userStore.isGuest)

/** 是否为管理员（用于显示"切换到后台"菜单项） */
const isAdmin = computed(() => checkRole(['admin']))

/** 是否为消息中心页面（隐藏底部页脚，给消息列表更多空间） */
const isMessagesPage = computed(() => route.path.startsWith('/front/messages'))

/** 是否为笔记编辑器页面（全屏模式，隐藏页脚） */
const isNotesEditorPage = computed(() => route.path === '/front/notes/editor')

/** 是否隐藏底部页脚 */
const hideFooter = computed(() => isMessagesPage.value || isNotesEditorPage.value)

// ==================== 用户操作 ====================

/** 消息中心需要登录；游客点击时先提示 */
async function goMessages() {
    if (!(await ensureLogin('查看消息中心'))) return
    router.push('/front/messages')
}

/** 游客切换为正式登录：保留游客态直接去登录页，登录成功后 token 会被新账号覆盖 */
function goLogin() {
    const redirect = route.fullPath || '/front/index'
    router.push({ path: '/login', query: { redirect } })
}

/** 游客切换到注册页：保留游客态，注册成功后由注册流程接管 */
function goRegister() {
    const redirect = route.fullPath || '/front/index'
    router.push({ path: '/register', query: { redirect } })
}

/** 管理员切换到后台管理页面 */
function goAdmin() {
    router.push('/index/home')
}

/** 退出登录：弹出确认框 → 调用 store 登出 → 跳转首页 */
function logout() {
    const tip = isGuest.value ? '确定退出游客模式吗？' : '确定注销并退出系统吗？'
    ElMessageBox.confirm(tip, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
    }).then(async () => {
        await userStore.logOut()
        router.push('/front/index')
    }).catch(() => { })
}
</script>

<!-- ==================== 样式部分 ==================== -->
<style scoped lang="scss">
/*
 * 设计系统颜色变量
 * 项目统一使用灰色系配色，避免花哨的颜色
 */
:root {
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-900: #111827;
}

.front-layout {
    min-height: 100vh;
    display: flex;
    flex-direction: column;

    /* ========== 顶部导航栏 ========== */
    .front-header {
        background: rgba(255, 255, 255, 0.95);
        /* 半透明白色背景 */
        backdrop-filter: blur(12px);
        /* 毛玻璃效果 */
        -webkit-backdrop-filter: blur(12px);
        border-bottom: 1px solid #e5e7eb;
        padding: 0 32px;
        height: 68px;
        display: flex;
        align-items: center;
        position: sticky;
        /* 滚动时固定在顶部 */
        top: 0;
        z-index: 100;

        .header-container {
            max-width: 1280px;
            width: 100%;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            /* Logo | 导航 | 用户 三栏分布 */

            /* Logo 样式 */
            .logo {
                cursor: pointer;
                padding: 8px 12px;
                border-radius: 10px;
                transition: all 0.2s ease-in-out;

                &:hover {
                    background: #f5f7fa;
                }

                h1 {
                    margin: 0;
                    font-size: 22px;
                    font-weight: 600;
                    color: #1f2937;
                    letter-spacing: -0.5px;
                }
            }

            /* 导航菜单样式 */
            .nav-menu {
                display: flex;
                gap: 8px;

                a {
                    color: #6b7280;
                    text-decoration: none;
                    font-size: 15px;
                    font-weight: 500;
                    padding: 8px 16px;
                    border-radius: 8px;
                    transition: all 0.2s ease-in-out;
                    position: relative;
                    cursor: pointer;

                    &:hover {
                        color: #374151;
                        background: #f5f7fa;
                    }

                    /* 当前激活的菜单项高亮 */
                    &.router-link-active {
                        color: #1f2937;
                        background: #f3f4f6;
                        font-weight: 600;
                    }
                }
            }

            /* 右侧用户区域 */
            .user-area {
                display: flex;
                align-items: center;
                gap: 12px;

                /* 消息铃铛红点样式 */
                .bell-badge {
                    :deep(.el-badge__content) {
                        font-size: 11px;
                        height: 16px;
                        line-height: 16px;
                        padding: 0 4px;
                        border: none;
                    }

                    .bell-btn {
                        width: 34px;
                        height: 34px;
                        font-size: 18px;
                        color: #6b7280;
                        background: transparent;
                        border: none;
                        transition: all 0.2s ease-in-out;

                        &:hover {
                            color: #374151;
                            background: #f5f7fa;
                        }
                    }
                }

                /* 用户名下拉触发区域 */
                .user-name {
                    cursor: pointer;
                    color: #6b7280;
                    font-weight: 500;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    padding: 8px 14px;
                    border-radius: 8px;
                    transition: all 0.2s ease-in-out;
                    outline: none;

                    &:hover {
                        background: #f5f7fa;
                        color: #374151;
                    }

                    &:focus {
                        outline: none;
                    }

                    &:focus-visible {
                        outline: none;
                    }
                }
            }
        }
    }

    /* ========== 主内容区 ========== */
    .front-main {
        flex: 1;
        /* 撑满剩余空间，将页脚推到底部 */
        width: 100%;
        margin: 12px 0;
        padding: 0 16px;
    }

    /* ========== 底部页脚 ========== */
    .front-footer {
        background: white;
        padding: 16px;
        text-align: center;
        color: #6b7280;
        margin-top: auto;
        /* 始终贴底 */
        border-top: 1px solid #e5e7eb;
        font-size: 13px;

        /* hide-footer 模式下隐藏页脚 */
        .hide-footer & {
            display: none;
        }
    }
}

/* 消息中心/笔记编辑器页面：隐藏页脚 */
.front-layout.hide-footer {
    .front-footer {
        display: none;
    }
}

/* 笔记编辑器全屏模式：去掉内边距，让编辑器占满屏幕 */
.front-layout.notes-editor-mode {
    .front-main {
        margin: 0;
        padding: 0;
        max-width: 100%;
        height: calc(100vh - 68px);
        overflow: hidden;
    }
}

/* ========== 响应式适配 ========== */
/* 中等屏幕（平板横屏） */
@media (max-width: 1200px) {
    .front-layout {
        .front-header {
            padding: 0 24px;

            .header-container {
                .nav-menu {
                    gap: 6px;

                    a {
                        padding: 6px 12px;
                        font-size: 14px;
                    }
                }

                .logo h1 {
                    font-size: 20px;
                }
            }
        }

        .front-main {
            padding: 0 24px;
        }
    }
}

/* 较小屏幕（平板竖屏） */
@media (max-width: 1024px) {
    .front-layout {
        .front-header {
            padding: 0 16px;
            height: 60px;

            .header-container {
                .nav-menu {
                    gap: 4px;

                    a {
                        padding: 6px 10px;
                        font-size: 14px;
                    }
                }

                .logo h1 {
                    font-size: 18px;
                }
            }
        }

        .front-main {
            padding: 0 16px;
            margin: 12px auto;
        }

        .front-footer {
            padding: 24px 16px;
        }
    }
}

/* 移动端 */
@media (max-width: 768px) {
    .front-layout {
        .front-header {
            padding: 0 12px;
            height: 56px;

            .header-container {
                .nav-menu {
                    gap: 2px;

                    a {
                        padding: 6px 8px;
                        font-size: 13px;
                    }
                }

                .logo {
                    padding: 6px 8px;

                    h1 {
                        font-size: 16px;
                    }
                }
            }
        }

        .front-main {
            padding: 0 12px;
            margin: 16px auto;
        }

        .front-footer {
            padding: 20px 12px;
            font-size: 12px;
        }
    }
}

/* 下拉菜单图标间距 */
.el-dropdown-menu .el-icon {
    margin-right: 8px;
}
</style>

<!-- ==================== 全局样式（非 scoped） ==================== -->
<!--
  以下样式不加 scoped，用于覆盖 Element Plus 组件的默认样式
  确保下拉菜单、对话框等弹出层也能使用项目统一的设计风格
-->
<style lang="scss">
/* 用户区域按钮统一白底灰边风格 */
.front-layout .user-area .el-button {
    border-radius: 8px;
    font-weight: 500;
    padding: 6px 14px;
    transition: all 0.2s ease-in-out;
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #374151;

    &:hover {
        border-color: #d1d5db;
        color: #111827;
        background: #fff;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
    }

    &:active {
        box-shadow: none;
    }
}

/* 注册按钮（主要按钮）样式 */
.front-layout .user-area .el-button--primary {
    background: #fff;
    border-color: #d1d5db;
    color: #111827;

    &:hover {
        background: #fff;
        border-color: #9ca3af;
        color: #111827;
    }
}

/* 下拉菜单项样式 */
.el-dropdown-menu__item {
    border-radius: 6px;
    margin: 2px 6px;
    padding: 8px 12px;
    transition: all 0.2s ease-in-out;

    &:hover {
        background: #f3f4f6;
        color: #111827;
    }
}

/* 全局 Tag 标签样式覆盖 */
.el-tag--info {
    background: #f3f4f6;
    border-color: #e5e7eb;
    color: #6b7280;
}

.el-tag--warning {
    background: #fefce8;
    border-color: #e5e0c0;
    color: #947a4a;
}

.el-tag--danger {
    background: #fef2f2;
    border-color: #e5d0d0;
    color: #b45353;
}

.el-tag--success {
    background: #f0f9eb;
    border-color: #e1f3d8;
    color: #67c23a;
}

/* 全局分页样式覆盖 */
.el-pagination {
    .el-pager li {
        border-radius: 6px;
        transition: all 0.2s ease-in-out;

        &:hover {
            background: #f3f4f6;
            color: #374151;
        }

        &.is-active {
            background: #f3f4f6;
            color: #111827;
        }
    }
}

/* 全局空状态文字颜色 */
.el-empty__description {
    color: #9ca3af;
}

/* 全局下拉菜单圆角 */
.el-dropdown-menu {
    border-radius: 8px;
}

.el-select-dropdown__item {
    border-radius: 8px;
    transition: all 0.2s ease-in-out;

    &:hover {
        background: #f3f4f6;
    }
}

/* 全局输入框圆角 + 边框统一风格 */
.el-input__wrapper {
    border-radius: 8px;
    box-shadow: 0 0 0 1px #e5e7eb;
    transition: all 0.2s ease-in-out;

    &:hover {
        box-shadow: 0 0 0 1px #d1d5db;
    }

    &.is-focus {
        box-shadow: 0 0 0 1px #b3b3b3;
    }
}

.el-textarea__inner {
    border-radius: 8px;
    border-color: #e5e7eb;
    transition: all 0.2s ease-in-out;

    &:hover {
        border-color: #d1d5db;
    }

    &:focus {
        border-color: #b3b3b3;
    }
}

/* 全局对话框圆角 + 分割线 */
.el-dialog {
    border-radius: 16px;
    overflow: hidden;

    .el-dialog__header {
        padding: 20px 24px 16px;
        border-bottom: 1px solid #f3f4f6;

        .el-dialog__title {
            font-size: 17px;
            font-weight: 600;
            color: #1f2937;
        }
    }

    .el-dialog__body {
        padding: 24px;
    }

    .el-dialog__footer {
        padding: 16px 24px 20px;
        border-top: 1px solid #f3f4f6;
    }
}

/*
 * 修复：顶部导航 .front-header 的 backdrop-filter 毛玻璃会创建合成层，
 * 与 Element Plus 弹层（el-drawer / el-dialog 等 fixed overlay，打开时 body
 * 会带上 el-popup-parent--hidden）产生合成冲突，使弹层在导航栏以下区域被
 * “挖空”无法绘制。弹层打开时页面已被遮罩覆盖、毛玻璃本就无作用，此时临时
 * 关闭它即可，弹层关闭、class 移除后毛玻璃自动恢复。
 */
body.el-popup-parent--hidden .front-layout .front-header {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
}
</style>
