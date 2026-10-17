<!-- ==================== 消息中心主页 ==================== -->
<!-- 功能：通知分为两类 -->
<!--   系统通知：管理员发布的系统公告 -->
<!--   用户通知：普通用户产生（评论 / 回复 / @我），统一放在「回复与@」 -->
<!-- 布局：左侧菜单栏 + 右侧内容区（子路由） -->
<!-- 红点机制：通过 provide/inject 向子组件提供 refreshBadge 方法 -->
<template>
  <div class="messages-layout">
    <!-- ==================== 左侧菜单栏 ==================== -->
    <div class="messages-sidebar">
      <div class="sidebar-label">消息</div>
      <!-- 菜单项，每个菜单项显示未读数红点 -->
      <el-menu :default-active="activeMenu" class="sidebar-menu" @select="handleSelect">
        <!-- 系统通知：仅管理员发布的系统公告 -->
        <el-menu-item index="/front/messages/notifications">
          <el-icon><Bell /></el-icon>
          <span>系统通知</span>
          <el-badge v-if="sysUnreadCount > 0" :value="sysUnreadCount" :max="99" class="menu-badge" />
        </el-menu-item>
        <!-- 用户通知：普通用户对你的笔记评论、回复你的留言，或 @ 你 -->
        <el-menu-item index="/front/messages/mentions">
          <el-icon><ChatDotSquare /></el-icon>
          <span>回复与@</span>
          <el-badge v-if="userUnreadCount > 0" :value="userUnreadCount" :max="99" class="menu-badge" />
        </el-menu-item>
        <!-- 私信：用户之间的实时聊天消息（暂时下线，保留代码，v-if="false" 隐藏） -->
        <el-menu-item v-if="false" index="/front/messages/chats">
          <el-icon><Message /></el-icon>
          <span>私信</span>
          <el-badge v-if="chatUnreadCount > 0" :value="chatUnreadCount" :max="99" class="menu-badge" />
        </el-menu-item>
        <!-- 分享通知：题库分享相关的定向通知（领取提醒 / 失效提醒） -->
        <el-menu-item index="/front/messages/shareNotices">
          <el-icon><Share /></el-icon>
          <span>分享通知</span>
          <el-badge v-if="shareUnreadCount > 0" :value="shareUnreadCount" :max="99" class="menu-badge" />
        </el-menu-item>
      </el-menu>
    </div>
    <!-- 右侧内容区：根据路由显示对应的子组件 -->
    <div class="messages-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 消息中心主组件
 * 核心职责：
 * 1. 管理各类消息的未读数（系统通知 / 用户通知 / 分享通知）
 * 2. 向子组件提供 refreshBadge 方法实现实时红点更新
 * 3. 路由切换时自动刷新未读数
 */
import { ref, computed, onMounted, watch, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, Bell, ChatDotSquare, Message, Share } from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import { listAllNotice } from '@/api/system/notice'
import { getUnreadCount as getChatUnreadCount } from '@/api/system/chat'
import { getNotificationUnreadCount } from '@/api/notification/notification'
import { isSystemNotice, isUserNoticeFor } from '@/utils/notice'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// ==================== 未读数状态 ====================
const sysUnreadCount = ref(0)      // 系统通知未读数（仅管理员公告）
const userUnreadCount = ref(0)     // 用户通知未读数（评论 / 回复 / @我 → 「回复与@」）
const chatUnreadCount = ref(0)     // 私信未读数（功能已隐藏，仅保留变量避免报错）
const shareUnreadCount = ref(0)    // 分享通知未读数

// ==================== 当前激活菜单 ====================
// 根据路由路径自动高亮对应的菜单项
const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/front/messages/notifications')) return '/front/messages/notifications'
  if (path.startsWith('/front/messages/mentions')) return '/front/messages/mentions'
  if (path.startsWith('/front/messages/shareNotices')) return '/front/messages/shareNotices'
  if (path.startsWith('/front/messages/chats')) return '/front/messages/chats'
  return '/front/messages/notifications'
})

// 菜单点击跳转
const handleSelect = (index) => {
  router.push(index)
}

// ==================== 获取未读数 ====================
// 一次性获取所有通知，按 remark.type 区分：
//   系统通知 = 管理员公告（无 remark / 非用户通知类型）
//   用户通知 = 评论 / 回复 / @我，且发给当前用户
const fetchUnreadCounts = async () => {
  try {
    const res = await listAllNotice()
    const all = res.data || []
    let sysCount = 0
    let userCount = 0
    const myId = userStore.id
    for (const n of all) {
      if (n.read) continue  // 跳过已读通知
      if (isUserNoticeFor(n, myId)) {
        userCount++         // 用户通知（评论 / 回复 / @我）
      } else if (isSystemNotice(n)) {
        sysCount++          // 系统通知（管理员公告）
      }
      // 发给其他用户的用户通知：不计入任何未读
    }
    sysUnreadCount.value = sysCount
    userUnreadCount.value = userCount
  } catch (e) { }

  // 获取私信未读数（单独接口，私信已隐藏，保留调用以便后续恢复）
  try {
    const chatRes = await getChatUnreadCount()
    chatUnreadCount.value = chatRes.data || 0
  } catch (e) { }

  // 获取分享通知未读数（定向站内通知）
  try {
    const shareRes = await getNotificationUnreadCount()
    shareUnreadCount.value = shareRes.data || 0
  } catch (e) { }
}

// ==================== 红点刷新方法 ====================
// 通过 provide/inject 机制，子组件可以直接调用此方法更新红点
// 无需等待下次 fetchUnreadCounts 调用
const refreshBadge = (type, count) => {
  if (type === 'sys') {
    sysUnreadCount.value = Math.max(0, count)
  } else if (type === 'user') {
    userUnreadCount.value = Math.max(0, count)
  } else if (type === 'chat') {
    chatUnreadCount.value = Math.max(0, count)
  } else if (type === 'share') {
    shareUnreadCount.value = Math.max(0, count)
  }
}

// 通过 provide 向所有子组件提供 refreshBadge 方法
provide('refreshBadge', refreshBadge)

// ==================== 生命周期 ====================
// 组件挂载时获取未读数
onMounted(() => {
  fetchUnreadCounts()
})

// 路由变化时刷新未读数（用户切换消息类型时自动更新）
watch(() => route.path, () => {
  fetchUnreadCounts()
})
</script>

<style scoped lang="scss">
.messages-layout {
  display: flex;
  height: 100%;
  min-height: 0;
  gap: 0;

  .messages-sidebar {
    width: 200px;
    flex-shrink: 0;
    padding: 16px 12px;
    box-sizing: border-box;
    border-right: 1px solid var(--os-border-soft);
    background: #fff;
    overflow-y: auto;
  }

  /* 二级导航的小标题（一级标题在顶栏，不在这里重复） */
  .sidebar-label {
    padding: 2px 9px 10px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.06em;
    color: var(--os-text-4);
    user-select: none;
  }

  .sidebar-menu {
    border-right: none;
    background: transparent;

    .el-menu-item {
      position: relative;
      height: 36px;
      line-height: 36px;
      border-radius: var(--os-radius-sm);
      margin-bottom: 2px;
      padding: 0 9px;
      color: var(--os-text-2);
      font-weight: 400;
      transition: background-color 0.15s ease, color 0.15s ease;

      &:hover {
        background: var(--os-bg-hover);
        color: var(--os-text);
      }

      &.is-active {
        background: var(--dsw-specific-sidebar-nav-item-active);
        color: var(--os-text);
        font-weight: 500;
        border-left: none;
      }

      .el-icon {
        font-size: 16px;
        margin-right: 8px;
      }

      span {
        font-size: 13.5px;
      }
    }

    .menu-badge {
      margin-left: auto;

      :deep(.el-badge__content) {
        font-size: 11px;
        height: 18px;
        line-height: 18px;
        padding: 0 5px;
        border: none;
      }
    }
  }
}

.messages-content {
  flex: 1;
  min-width: 0;
  max-width: 1040px;
  height: 100%;
  overflow-y: auto;
  padding: 22px 28px 48px;
  box-sizing: border-box;
}

@media (max-width: 900px) {
  .messages-layout {
    .messages-sidebar {
      width: 150px;
      padding: 12px 8px;
    }
  }

  .messages-content {
    padding: 16px 16px 40px;
  }
}
</style>
