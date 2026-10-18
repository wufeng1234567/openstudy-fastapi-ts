import { createWebHashHistory, createRouter } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

/** 扩展的路由记录类型（RuoYi 框架在路由上挂载的自定义字段） */
export type AppRouteRecordRaw = RouteRecordRaw & {
  hidden?: boolean
  permissions?: string[]
  children?: AppRouteRecordRaw[]
}

// 公共路由
export const constantRoutes: AppRouteRecordRaw[] = [
  {
    path: '/redirect',
    component: () => import('@/layout/index.vue'),
    hidden: true,
    children: [
      {
        path: '/redirect/:path(.*)',
        component: () => import('@/views/redirect/index.vue')
      }
    ]
  },
  {
    path: '/login',
    component: () => import('@/views/auth.vue'),
    hidden: true
  },
  {
    path: '/register',
    component: () => import('@/views/auth.vue'),
    hidden: true
  },
  {
    path: "/:pathMatch(.*)*",
    component: () => import('@/views/error/404.vue'),
    hidden: true
  },
  {
    path: '/401',
    component: () => import('@/views/error/401.vue'),
    hidden: true
  },

  // 后台首页
  {
    path: '/index',
    component: () => import('@/layout/index.vue'),
    redirect: '/index/home',
    meta: { title: '后台首页', icon: 'dashboard' },
    children: [
      {
        path: 'home',
        name: 'Index',
        component: () => import('@/views/admin/dashboard.vue'),
        meta: { title: '后台首页', icon: 'dashboard', affix: true }
      }
    ]
  },

  // 根路径重定向：直接进智能对话（取代原来的"首页轮播"落地页）
  {
    path: '/',
    redirect: '/front/agent/chat'
  },

  // 后台评论管理
  {
    path: '/system/comment',
    component: () => import('@/layout/index.vue'),
    redirect: '/system/comment',
    meta: { title: '评论管理', icon: 'comment' },
    children: [
      {
        path: '',
        component: () => import('@/views/comment/comment/index.vue'),
        name: 'Comment',
        meta: { title: '评论管理', icon: 'comment' }
      }
    ]
  },

  // 后台AI配置管理
  {
    path: '/system/ai',
    component: () => import('@/layout/index.vue'),
    redirect: '/system/ai/config',
    meta: { title: 'AI配置', icon: 'ai' },
    children: [
      {
        path: 'config',
        component: () => import('@/views/ai/config/index.vue'),
        name: 'AiConfig',
        meta: { title: 'AI配置', icon: 'ai' }
      }
    ]
  },

  // 后台题库管理
  {
    path: '/questionBank/questionBank',
    component: () => import('@/layout/index.vue'),
    redirect: '/questionBank/questionBank',
    meta: { title: '题库管理', icon: 'questionBank' },
    children: [
      {
        path: '',
        component: () => import('@/views/questionBank/questionBank/index.vue'),
        name: 'QuestionBank',
        meta: { title: '题库管理', icon: 'questionBank' }
      }
    ]
  },

  // 后台题目管理
  {
    path: '/questionMain/questionMain',
    component: () => import('@/layout/index.vue'),
    redirect: '/questionMain/questionMain',
    meta: { title: '题目管理', icon: 'questionMain' },
    children: [
      {
        path: '',
        component: () => import('@/views/questionMain/questionMain/index.vue'),
        name: 'QuestionMain',
        meta: { title: '题目管理', icon: 'questionMain' }
      }
    ]
  },

  // 后台错题记录管理
  {
    path: '/questionError/questionError',
    component: () => import('@/layout/index.vue'),
    redirect: '/questionError/questionError',
    meta: { title: '错题记录', icon: 'questionError' },
    children: [
      {
        path: '',
        component: () => import('@/views/questionError/questionError/index.vue'),
        name: 'QuestionError',
        meta: { title: '错题记录', icon: 'questionError' }
      }
    ]
  },

  // 后台斩题管理
  {
    path: '/questionMarked/questionMarked',
    component: () => import('@/layout/index.vue'),
    redirect: '/questionMarked/questionMarked',
    meta: { title: '斩题管理', icon: 'questionMarked' },
    children: [
      {
        path: '',
        component: () => import('@/views/questionMarked/questionMarked/index.vue'),
        name: 'QuestionMarked',
        meta: { title: '斩题管理', icon: 'questionMarked' }
      }
    ]
  },

  // 后台题库收藏管理
  {
    path: '/favoriteBank/favoriteBank',
    component: () => import('@/layout/index.vue'),
    redirect: '/favoriteBank/favoriteBank',
    meta: { title: '题库收藏', icon: 'favoriteBank' },
    children: [
      {
        path: '',
        component: () => import('@/views/favoriteBank/favoriteBank/index.vue'),
        name: 'FavoriteBank',
        meta: { title: '题库收藏', icon: 'favoriteBank' }
      }
    ]
  },

  // 后台题目收藏管理
  {
    path: '/favoriteQuestion/favoriteQuestion',
    component: () => import('@/layout/index.vue'),
    redirect: '/favoriteQuestion/favoriteQuestion',
    meta: { title: '题目收藏', icon: 'favoriteQuestion' },
    children: [
      {
        path: '',
        component: () => import('@/views/favoriteQuestion/favoriteQuestion/index.vue'),
        name: 'FavoriteQuestion',
        meta: { title: '题目收藏', icon: 'favoriteQuestion' }
      }
    ]
  },

  // 后台个人中心 - 使用后台 Layout
  {
    path: '/user',
    component: () => import('@/layout/index.vue'),
    hidden: true,
    redirect: 'noredirect',
    children: [
      {
        path: 'profile',
        component: () => import('@/views/system/user/profile/index.vue'),
        name: 'Profile',
        meta: { title: '个人中心', icon: 'user' }
      }
    ]
  },

  // 前台路由
  {
    path: '/front',
    component: () => import('@/layout/front.vue'),
    hidden: true,
    redirect: '/front/agent/chat',
    meta: { layout: 'front' },
    children: [
      // 旧首页地址保留为重定向（老书签 / 分享出去的链接不会 404）
      {
        path: 'index',
        name: 'FrontIndexLegacy',
        redirect: '/front/agent/chat',
        meta: { title: '智能对话', layout: 'front' },
        hidden: true
      },
      {
        path: 'questionPractice',
        name: 'FrontQuestionPractice',
        component: () => import('@/views/questionPractice/questionPractice/index.vue'),
        meta: { title: '题库练习', layout: 'front' },
        hidden: true,
        children: [
          {
            path: '',
            name: 'FrontQuestionBankList',
            component: () => import('@/views/questionPractice/questionPractice/bankList.vue'),
            meta: { title: '题库练习', layout: 'front', keepAlive: true }
          },
          {
            path: ':bankId',
            name: 'FrontQuestionBankDetail',
            component: () => import('@/views/questionPractice/questionPractice/bankDetail.vue'),
            meta: { title: '题库详情', layout: 'front', keepAlive: true }
          },
          {
            path: ':bankId/practice/:moduleType',
            name: 'FrontQuestionPracticePlay',
            component: () => import('@/views/questionPractice/questionPractice/practice.vue'),
            meta: { title: '刷题练习', layout: 'front', keepAlive: true, requiresLogin: true }
          }
        ]
      },
      {
        path: 'tools',
        name: 'FrontTools',
        component: () => import('@/views/front/tools/index.vue'),
        meta: { title: '实用工具箱', layout: 'front' },
        redirect: '/front/tools/home',
        children: [
          {
            path: 'home',
            name: 'FrontToolsHome',
            component: () => import('@/views/front/tools/home.vue'),
            meta: { title: '实用工具箱', layout: 'front', keepAlive: true },
            hidden: true
          },
          {
            path: 'watermark',
            name: 'FrontToolsWatermark',
            component: () => import('@/views/front/resources/index.vue'),
            meta: { title: '图片水印工具', layout: 'front', keepAlive: true },
            hidden: true
          },
          {
            path: 'convert',
            name: 'FrontToolsConvert',
            component: () => import('@/views/front/tools/convert.vue'),
            meta: { title: '文档转换工具', layout: 'front', keepAlive: true },
            hidden: true
          },
          {
            path: 'image',
            name: 'FrontToolsImage',
            component: () => import('@/views/front/tools/image.vue'),
            meta: { title: '图片处理工具', layout: 'front', keepAlive: true },
            hidden: true
          },
          {
            path: 'classDiagram',
            name: 'FrontToolsClassDiagram',
            component: () => import('@/views/front/tools/classDiagram.vue'),
            meta: { title: '类图生成', layout: 'front', keepAlive: true },
            hidden: true
          }
        ]
      },
      {
        path: 'profile/:userId?',
        name: 'FrontProfile',
        component: () => import('@/views/system/user/profile/index.vue'),
        meta: { title: '个人中心', layout: 'front' },
        hidden: true
      },

      // ✅ 题库分享落地页（B 打开分享链接后领取）
      {
        path: 'share/:token',
        name: 'FrontBankShare',
        component: () => import('@/views/front/share/index.vue'),
        meta: { title: '题库分享', layout: 'front' },
        hidden: true
      },

      // ✅ 消息中心
      {
        path: 'messages',
        name: 'FrontMessages',
        component: () => import('@/views/front/messages/index.vue'),
        meta: { title: '消息中心', layout: 'front', requiresLogin: true },
        redirect: '/front/messages/notifications',
        children: [
          {
            path: 'notifications',
            name: 'FrontMessagesNotifications',
            component: () => import('@/views/front/messages/notifications.vue')
          },
          {
            path: 'mentions',
            name: 'FrontMessagesMentions',
            component: () => import('@/views/front/messages/mentions.vue')
          },
          {
            // 私信（暂时下线，先隐藏不删除）：保留组件文件，访问时重定向到系统通知
            path: 'chats',
            name: 'FrontMessagesChats',
            redirect: '/front/messages/notifications'
            // component: () => import('@/views/front/messages/chats.vue')
          },
          {
            path: 'shareNotices',
            name: 'FrontMessagesShareNotices',
            component: () => import('@/views/front/messages/shareNotices.vue')
          }
        ]
      },

      // ✅ 我的学习聚合页面
      {
        path: 'myQuestion',
        name: 'FrontMyQuestion',
        component: () => import('@/views/front/myQuestion/index.vue'),
        // redirect: '/front/myQuestion/myBank',
        meta: { title: '我的学习', layout: 'front', requiresLogin: true },
        hidden: true,
        children: [
          {
            /*
             * 题库收藏已合并进「我的题库」（用户 2026-10-18）。
             * 保留这条路由只为了兼容旧链接 / 书签 —— 直接重定向过去，
             * 不再指向那个独立页面（两个入口展示同一批数据，本来就没必要）。
             */
            path: 'bankCollect',
            name: 'FrontBankCollect',
            redirect: '/front/myQuestion/myBank?tab=favorite',
            meta: { title: '题库收藏', layout: 'front' },
            hidden: true
          },
          {
            path: 'questionCollect',
            name: 'FrontQuestionCollect',
            component: () => import('@/views/front/myQuestion/myFavoriteQuestion/index.vue'),
            meta: { title: '题目收藏', layout: 'front' },
            hidden: true
          },
          {
            path: 'wrongQuestion',
            name: 'FrontWrongQuestion',
            component: () => import('@/views/front/myQuestion/myMistakes/index.vue'),
            meta: { title: '我的错题', layout: 'front' },
            hidden: true
          },
          {
            path: 'masteredQuestion',
            name: 'FrontMasteredQuestion',
            component: () => import('@/views/front/myQuestion/myMarked/index.vue'),
            meta: { title: '我的斩题', layout: 'front' },
            hidden: true
          },
          {
            path: 'myBank',
            name: 'FrontMyBank',
            component: () => import('@/views/front/myQuestion/myBank/index.vue'),
            meta: { title: '我的题库', layout: 'front' },
            hidden: true
          },
          {
            path: 'myShares',
            name: 'FrontMyShares',
            component: () => import('@/views/front/myQuestion/myShares/index.vue'),
            meta: { title: '我的分享', layout: 'front' },
            hidden: true
          },
          {
            path: 'myNotes',
            name: 'FrontMyNotes',
            component: () => import('@/views/front/myQuestion/myNotes/index.vue'),
            meta: { title: '我的笔记', layout: 'front' },
            hidden: true
          },
          {
            path: 'myStats',
            name: 'FrontMyStats',
            component: () => import('@/views/front/myQuestion/myStats/index.vue'),
            meta: { title: '学习统计', layout: 'front' },
            hidden: true
          }
        ]
      },
      // studio 题库搭建模块（直接进入 create 页面）
      {
        path: 'studio',
        name: 'FrontStudio',
        component: () => import('@/views/front/studio/index.vue'),  // 容器组件（重定向到 create）
        meta: { title: '上传题库', layout: 'front', requiresLogin: true },
        hidden: true,
        redirect: '/front/studio/create?type=public',
        children: [
          {
            path: 'create',
            name: 'FrontStudioCreate',
            component: () => import('@/views/front/studio/create/index.vue'),
            meta: { title: '创建题库', layout: 'front', keepAlive: true }
          }
        ]
      },

      {
        path: 'english',
        name: 'FrontEnglish',
        component: () => import('@/views/front/english/index.vue'),
        meta: { title: '英语学习', layout: 'front' },
        hidden: true,
        children: [
          {
            path: 'home',
            name: 'FrontEnglishHome',
            component: () => import('@/views/front/english/home/index.vue'),
            meta: { title: '英语学习', layout: 'front', keepAlive: true },
            hidden: true
          },
          {
            path: 'ocr',
            name: 'FrontEnglishOcr',
            component: () => import('@/views/front/english/ocr/index.vue'),
            meta: { title: '拍照识词', layout: 'front', keepAlive: true, requiresLogin: true },
            hidden: true
          },
          {
            path: 'vocabulary',
            name: 'FrontEnglishVocabulary',
            component: () => import('@/views/front/english/vocabulary/index.vue'),
            meta: { title: '我的词库', layout: 'front', keepAlive: true, requiresLogin: true },
            hidden: true
          },
          {
            path: 'vocabulary/:id',
            name: 'FrontEnglishVocabularyDetail',
            component: () => import('@/views/front/english/vocabulary/detail.vue'),
            meta: { title: '词库详情', layout: 'front', keepAlive: true, requiresLogin: true },
            hidden: true
          },
          {
            path: 'listening',
            name: 'FrontEnglishListening',
            component: () => import('@/views/front/english/listening/index.vue'),
            meta: { title: '听力练习', layout: 'front', keepAlive: true, requiresLogin: true },
            hidden: true
          },
          {
            path: 'reading',
            name: 'FrontEnglishReading',
            component: () => import('@/views/front/english/reading/index.vue'),
            meta: { title: '阅读练习', layout: 'front', keepAlive: true },
            hidden: true
          }
        ]
      },

      // 学习分享
      {
        path: 'notes',
        name: 'FrontNotes',
        component: () => import('@/views/front/notes/index.vue'),
        meta: { title: '学习分享', layout: 'front' },
        hidden: true,
        children: [
          {
            path: 'list',
            name: 'FrontNotesList',
            component: () => import('@/views/front/notes/list.vue'),
            meta: { title: '学习分享', layout: 'front', keepAlive: true }
          },
          {
            path: 'detail/:id',
            name: 'FrontNotesDetail',
            component: () => import('@/views/front/notes/detail.vue'),
            meta: { title: '笔记详情', layout: 'front', keepAlive: true }
          },
          {
            path: 'editor',
            name: 'FrontNotesEditor',
            component: () => import('@/views/front/notes/editor.vue'),
            meta: { title: '写笔记', layout: 'front', requiresLogin: true },
            hidden: true
          }
        ]
      },

      // 智能体（大屏 OS 助手 + 工具调用）
      // 形态对齐 sp3：聚合页只负责「回到上次访问的子页」，真正的页面在 children 里。
      {
        path: 'agent',
        name: 'FrontAgent',
        component: () => import('@/views/front/agent/index.vue'),
        meta: { title: '智能体', layout: 'front', requiresLogin: true },
        hidden: true,
        children: [
          {
            path: 'chat',
            name: 'FrontAgentChat',
            component: () => import('@/views/front/agent/chat.vue'),
            meta: { title: '智能体', layout: 'front', keepAlive: true, requiresLogin: true }
          }
        ]
      }
    ]
  }
]

// 动态路由
export const dynamicRoutes: AppRouteRecordRaw[] = [
  {
    path: '/system/user-auth',
    component: () => import('@/layout/index.vue'),
    hidden: true,
    permissions: ['system:user:edit'],
    children: [
      {
        path: 'role/:userId(\\d+)',
        component: () => import('@/views/system/user/authRole.vue'),
        name: 'AuthRole',
        meta: { title: '分配角色', activeMenu: '/system/user' }
      }
    ]
  },
  {
    path: '/system/role-auth',
    component: () => import('@/layout/index.vue'),
    hidden: true,
    permissions: ['system:role:edit'],
    children: [
      {
        path: 'user/:roleId(\\d+)',
        component: () => import('@/views/system/role/authUser.vue'),
        name: 'AuthUser',
        meta: { title: '分配用户', activeMenu: '/system/role' }
      }
    ]
  },
  {
    path: '/system/dict-data',
    component: () => import('@/layout/index.vue'),
    hidden: true,
    permissions: ['system:dict:list'],
    children: [
      {
        path: 'index/:dictId(\\d+)',
        component: () => import('@/views/system/dict/data.vue'),
        name: 'Data',
        meta: { title: '字典数据', activeMenu: '/system/dict' }
      }
    ]
  },
  {
    path: '/monitor/job-log',
    component: () => import('@/layout/index.vue'),
    hidden: true,
    permissions: ['monitor:job:list'],
    children: [
      {
        path: 'index/:jobId(\\d+)',
        component: () => import('@/views/monitor/job/log.vue'),
        name: 'JobLog',
        meta: { title: '调度日志', activeMenu: '/monitor/job' }
      }
    ]
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes: constantRoutes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  },
})

export default router
