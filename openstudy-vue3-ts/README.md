# OpenStudy 前端 - 开放学习平台

<p align="center">
  <img alt="logo" src="https://oscimg.oschina.net/oscnet/up-d3d0a9303e11d522a06cd263f3079027715.png">
</p>

<h4 align="center">基于 Vue 3 + Element Plus 的智能化学习平台前端</h4>

<p align="center">
  <a href="https://github.com/wufeng1234567/open-study-frontend"><img src="https://img.shields.io/badge/GitHub-Frontend-green.svg"></a>
  <a href="https://github.com/wufeng1234567/open-study-backend"><img src="https://img.shields.io/badge/GitHub-Backend-blue.svg"></a>
  <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue-3.x-brightgreen.svg"></a>
  <a href="https://vitejs.dev/"><img src="https://img.shields.io/badge/Vite-5.x-blue.svg"></a>
  <a href="https://element-plus.org/"><img src="https://img.shields.io/badge/Element%20Plus-2.x-orange.svg"></a>
  <a href="https://pinia.vuejs.org/"><img src="https://img.shields.io/badge/Pinia-2.x-yellow.svg"></a>
</p>

---

## 项目简介

**OpenStudy 前端**是基于 Vue 3 + Vite 构建的现代化单页应用，与 Spring Boot 3 后端配合，提供完整的智能化学习平台用户体验。系统深度集成 AI 能力，支持智能刷题、知识分享、英语学习、RAG 知识库等多种功能模块。

### 项目仓库

| 项目 | 地址 |
|------|------|
| 后端 | https://github.com/wufeng1234567/open-study-backend |
| 前端 | https://github.com/wufeng1234567/open-study-frontend |

---

## 技术栈

### 核心技术

| 技术 | 版本 | 说明 |
|------|------|------|
| Vue | 3.x | 渐进式 JavaScript 框架 |
| Vite | 5.x | 下一代前端构建工具 |
| Element Plus | 2.x | Vue 3 UI 组件库 |
| Pinia | 2.x | Vue 状态管理 |
| Vue Router | 4.x | Vue 官方路由 |
| Axios | 0.27.x | HTTP 请求库 |
| SCSS | 1.69.x | CSS 预处理器 |

### AI 相关

| 技术 | 说明 |
|------|------|
| TipTap | 富文本编辑器 |
| VueUse | Vue 组合式 API 工具集 |

---

## 系统架构

### 前后台分离架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户浏览器                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Vue 3 前端 (Port 80)                    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    /front/*                         │    │
│  │                                                       │    │
│  │   首页 / 题库练习 / 我的学习 / 英语学习 / 知识库       │    │
│  │   学习分享 / 工具箱 / 题库搭建 / 消息中心              │    │
│  │                                                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    /index/*                          │    │
│  │   首页 / 用户管理 / 角色管理 / 菜单管理 / 系统监控     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              /login  /register                       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                     Proxy: /dev-api/* → :8086
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Spring Boot 3 后端 (Port 8086)             │
└─────────────────────────────────────────────────────────────┘
```

### 前端路由架构

```
/
├── /login                    # 登录页面
├── /register                 # 注册页面
├── /index/*                  # 后台管理页面（带左侧菜单）
│   └── layout/index.vue      # 后台布局组件
│
└── /front/*                  # 前台用户页面（统一头部底部）
    └── layout/front.vue      # 前台布局组件（Header + Footer + AI助手）
```

---

## 功能模块

### 1. 题库练习模块

**路由**: `/front/questionPractice`

| 页面 | 路由 | 功能 |
|------|------|------|
| 题库列表 | `/front/questionPractice` | 浏览所有公开题库，收藏管理 |
| 题库详情 | `/front/questionPractice/:bankId` | 题库信息、章节统计、专项练习入口 |
| 刷题练习 | `/front/questionPractice/:bankId/practice/:moduleType` | 顺序/随机/自定义/模拟考试 |

**核心组件**:
- `BankCardGrid.vue` - 题库卡片网格展示
- `BankCardList.vue` - 题库卡片列表展示
- `PracticeComponent/` - 刷题核心组件
- `PracticeSettings.vue` - 刷题设置弹窗

**功能特色**:
- 四种练习模式：顺序练习、随机练习、自定义练习、模拟考试
- 刷题进度实时保存
- 错题自动收录到错题本
- 斩题标记已掌握题目
- 收藏重点题目

### 2. 我的学习模块

**路由**: `/front/myQuestion`

| 页面 | 路由 | 功能 |
|------|------|------|
| 我的学习 | `/front/myQuestion` | 学习模块主页（左侧导航） |
| 我的题库 | `/front/myQuestion/myBank` | 管理创建的题库 |
| 题库收藏 | `/front/myQuestion/bankCollect` | 收藏的题库列表 |
| 题目收藏 | `/front/myQuestion/questionCollect` | 收藏的题目 |
| 我的错题 | `/front/myQuestion/wrongQuestion` | 错题复习 |
| 我的斩题 | `/front/myQuestion/masteredQuestion` | 已掌握题目 |
| 我的笔记 | `/front/myQuestion/myNotes` | 个人笔记管理 |

**核心组件**:
- `LeftMenu.vue` - 左侧菜单导航
- `QuestionBankDetail/` - 题库详情组件（被多页面复用）

### 3. 学习笔记模块

**路由**: `/front/notes`

| 页面 | 路由 | 功能 |
|------|------|------|
| 笔记广场 | `/front/notes/list` | 浏览其他用户分享的笔记 |
| 笔记详情 | `/front/notes/detail/:id` | 查看笔记内容、评论互动 |
| 写笔记 | `/front/notes/editor` | 创建/编辑笔记 |

**核心组件**:
- `CommentSection/` - 评论组件
- TipTap 富文本编辑器（图片、代码块支持）

**功能特色**:
- 富文本编辑：支持插入图片、代码块、链接
- 笔记关联题库：一键跳转到相关题库练习
- 公开分享：优质笔记可发布到笔记广场
- 互动评论：对笔记进行评论和点赞
- 留言功能：笔记作者可回复评论

### 4. AI 智能助手

**组件**: `components/AiAssistant/`

**功能特色**:
- 全局悬浮助手：页面右下角固定
- 多 AI 提供商切换：智谱 AI / DeepSeek
- 流式输出：SSE 实时显示回答
- 上下文记忆：多轮对话连贯
- RAG 知识库问答：基于上传文档的精准回答

### 5. 英语学习模块

**路由**: `/front/english`

| 页面 | 路由 | 功能 |
|------|------|------|
| 英语学习 | `/front/english/home` | 模块主页 |
| 拍照识词 | `/front/english/ocr` | OCR 识别图片中的单词 |
| 我的词库 | `/front/english/vocabulary` | 词汇管理 |
| 词库详情 | `/front/english/vocabulary/:id` | 查看词库单词 |
| 听力练习 | `/front/english/listening` | 听力材料练习 |
| 阅读练习 | `/front/english/reading` | 阅读理解训练 |

**核心组件**:
- `OcrRecognizer/` - OCR 识别组件
- `Dictation/` - 听写组件

### 6. 知识库模块

**路由**: `/front/knowledge`

| 页面 | 路由 | 功能 |
|------|------|------|
| 知识库 | `/front/knowledge/home` | 模块主页 |
| 知识库列表 | `/front/knowledge/list` | 浏览知识库 |
| 上传文档 | `/front/knowledge/upload/:id` | 上传知识库文档 |
| 文档列表 | `/front/knowledge/docs/:id` | 查看知识库文档 |
| 知识问答 | `/front/knowledge/qa/:id` | RAG 智能问答 |

**功能特色**:
- 文档上传：支持 PDF、DOCX、TXT、MD
- 智能分块：自动将文档分割为可检索片段
- RAG 问答：基于文档内容的精准回答
- 向量检索：语义相似度匹配

### 7. 实用工具箱

**路由**: `/front/tools`

| 页面 | 路由 | 功能 |
|------|------|------|
| 工具箱主页 | `/front/tools/home` | 工具列表 |
| 图片水印 | `/front/tools/watermark` | 添加水印 |
| 文档转换 | `/front/tools/convert` | 格式转换 |
| 图片处理 | `/front/tools/image` | 压缩裁剪 |
| 文本工具 | `/front/tools/text` | 文本处理 |

### 8. 题库搭建

**路由**: `/front/studio`

| 页面 | 路由 | 功能 |
|------|------|------|
| 题库搭建 | `/front/studio` | 题库管理 |
| 创建题库 | `/front/studio/create` | 新建题库、添加章节题目 |

**核心组件**:
- `QuestionBuilder.vue` - 题目构建器
- `QuestionFullEditor.vue` - 题目完整编辑器
- `CardOption.vue` - 卡片选项组件

**功能特色**:
- 可视化创建题库
- 按章节组织题目
- AI 辅助出题：根据知识点描述自动生成题目
- 支持多种题型：单选、多选、判断、填空、阅读理解

### 9. 消息中心

**路由**: `/front/messages`

| 页面 | 路由 | 功能 |
|------|------|------|
| 通知 | `/front/messages/notifications` | 系统通知 |
| @我 | `/front/messages/mentions` | @提及通知 |
| 私信 | `/front/messages/chats` | 用户私信聊天 |

### 10. 后台管理

**路由**: `/index/*`

| 模块 | 路由 | 功能 |
|------|------|------|
| 首页 | `/index/home` | 数据统计仪表盘 |
| 用户管理 | `/system/user` | 用户增删改查 |
| 角色管理 | `/system/role` | 角色权限配置 |
| 菜单管理 | `/system/menu` | 系统菜单配置 |
| 部门管理 | `/system/dept` | 组织架构管理 |
| 字典管理 | `/system/dict` | 数据字典维护 |
| 参数管理 | `/system/config` | 系统参数配置 |
| 通知公告 | `/system/notice` | 公告发布管理 |
| 在线用户 | `/monitor/online` | 实时在线监控 |
| 操作日志 | `/monitor/operlog` | 操作审计追踪 |
| 登录日志 | `/monitor/logininfor` | 登录记录查询 |
| 代码生成 | `/tool/gen` | CRUD 代码生成 |

---

## 页面路由

### 前台用户页面

| 路径 | 功能 |
|------|------|
| `/front/index` | 前台首页 |
| `/front/questionPractice` | 题库练习 |
| `/front/questionPractice/:bankId` | 题库详情 |
| `/front/questionPractice/:bankId/practice/:moduleType` | 刷题练习 |
| `/front/myQuestion` | 我的学习 |
| `/front/myQuestion/myBank` | 我的题库 |
| `/front/myQuestion/bankCollect` | 题库收藏 |
| `/front/myQuestion/questionCollect` | 题目收藏 |
| `/front/myQuestion/wrongQuestion` | 我的错题 |
| `/front/myQuestion/masteredQuestion` | 我的斩题 |
| `/front/myQuestion/myNotes` | 我的笔记 |
| `/front/english` | 英语学习 |
| `/front/knowledge` | 知识库 |
| `/front/notes` | 学习分享 |
| `/front/tools` | 实用工具箱 |
| `/front/studio` | 上传题库 |
| `/front/messages` | 消息中心 |
| `/front/profile` | 个人中心 |

### 后台管理页面

| 路径 | 功能 |
|------|------|
| `/index/home` | 后台首页 |
| `/system/user` | 用户管理 |
| `/system/role` | 角色管理 |
| `/system/menu` | 菜单管理 |
| `/system/dept` | 部门管理 |
| `/system/dict` | 字典管理 |
| `/system/config` | 参数管理 |
| `/system/notice` | 通知公告 |
| `/monitor/online` | 在线用户 |
| `/monitor/operlog` | 操作日志 |
| `/monitor/logininfor` | 登录日志 |
| `/tool/gen` | 代码生成 |

### 认证页面

| 路径 | 功能 |
|------|------|
| `/login` | 登录页面 |
| `/register` | 注册页面 |

---

## 公共组件

| 组件路径 | 功能说明 |
|----------|----------|
| `AiAssistant/` | AI 悬浮助手组件 |
| `BankCardGrid/` | 题库卡片网格组件 |
| `BankCardList/` | 题库卡片列表组件 |
| `FavoriteButton/` | 收藏按钮组件 |
| `PracticeComponent/` | 刷题核心组件 |
| `QuestionBankDetail/` | 题库详情组件 |
| `ImageUpload/` | 图片上传组件 |
| `CommentSection/` | 评论组件 |
| `OcrRecognizer/` | OCR 识别组件 |
| `Dictation/` | 听写组件 |

---

## 项目结构

```
openstudy-vue3/
├── src/
│   ├── api/                        # API 接口封装
│   │   ├── ai/                     # AI 相关接口
│   │   ├── carousel/               # 轮播图接口
│   │   ├── courses/                # 课程接口
│   │   ├── document/               # 文档转换接口
│   │   ├── english/                # 英语学习接口
│   │   ├── favoriteBank/           # 题库收藏接口
│   │   ├── favoriteNote/           # 笔记收藏接口
│   │   ├── favoriteQuestion/       # 题目收藏接口
│   │   ├── knowledge/             # 知识库接口
│   │   ├── noteCategory/          # 笔记分类接口
│   │   ├── noteImage/             # 笔记图片接口
│   │   ├── notes/                 # 笔记接口
│   │   ├── ocr/                  # OCR 接口
│   │   ├── questionBank/          # 题库接口
│   │   ├── questionError/         # 错题接口
│   │   ├── questionMain/          # 题目接口
│   │   ├── questionMarked/        # 斩题接口
│   │   ├── system/                # 系统接口
│   │   ├── wordBooks/             # 单词本接口
│   │   ├── words/                 # 单词接口
│   │   └── login.js               # 登录注册接口
│   │
│   ├── assets/                     # 静态资源
│   │   ├── icons/                 # SVG 图标
│   │   ├── images/               # 图片资源
│   │   └── styles/               # 全局样式
│   │       ├── btn.scss           # 按钮样式
│   │       ├── element-ui.scss    # Element Plus 覆盖
│   │       ├── index.scss         # 全局样式入口
│   │       └── variables.module.scss  # SCSS 变量
│   │
│   ├── components/                 # 公共组件
│   │   ├── AiAssistant/          # AI 悬浮助手
│   │   ├── AiAnalysisDialog/     # AI 分析弹窗
│   │   ├── AiModelManager/       # AI 模型管理
│   │   ├── BankCardGrid/         # 题库卡片网格
│   │   ├── BankCardList/         # 题库卡片列表
│   │   ├── CommentSection/       # 评论组件
│   │   ├── Dictation/            # 听写组件
│   │   ├── FavoriteButton/       # 收藏按钮
│   │   ├── ImageUpload/          # 图片上传
│   │   ├── OcrRecognizer/        # OCR 识别
│   │   ├── PracticeComponent/    # 刷题组件
│   │   │   ├── PracticeSettings.vue    # 刷题设置
│   │   │   ├── QuestionCard.vue        # 题目卡片
│   │   │   ├── AnswerOptions.vue       # 答题选项
│   │   │   └── ...
│   │   └── QuestionBankDetail/   # 题库详情
│   │
│   ├── composables/                # 组合式函数
│   │   └── useAuth.js            # 权限判断 hooks
│   │
│   ├── directive/                  # 自定义指令
│   │   └── permission/            # 权限指令
│   │
│   ├── layout/                     # 布局组件
│   │   ├── index.vue              # 后台布局（侧边栏+主内容）
│   │   ├── front.vue              # 前台布局（头部+底部+AI助手）
│   │   └── components/            # 布局子组件
│   │       ├── Sidebar/           # 侧边栏
│   │       ├── Navbar.vue         # 导航栏
│   │       ├── TagsView.vue       # 标签页
│   │       └── AppMain.vue        # 主内容区
│   │
│   ├── plugins/                    # 插件配置
│   │   ├── element.js             # Element Plus 按需引入
│   │   └── index.js               # 插件入口
│   │
│   ├── router/                     # 路由配置
│   │   └── index.js               # 路由定义
│   │
│   ├── store/                      # Pinia 状态管理
│   │   └── modules/
│   │       ├── user.js            # 用户状态
│   │       ├── permission.js      # 权限状态
│   │       ├── app.js             # 应用状态
│   │       ├── settings.js        # 设置状态
│   │       ├── tagsView.js        # 标签页状态
│   │       └── frontPageCache.js  # 前台页面缓存
│   │
│   ├── utils/                      # 工具函数
│   │   ├── request.js             # Axios 封装
│   │   ├── auth.js               # 认证工具
│   │   ├── permission.js          # 权限判断
│   │   ├── theme.js              # 主题处理
│   │   ├── index.js              # 通用工具
│   │   └── validate.js            # 表单验证
│   │
│   └── views/                      # 页面组件
│       ├── admin/                 # 后台页面
│       │   └── dashboard.vue     # 后台首页
│       │
│       ├── front/                 # 前台页面
│       │   ├── index.vue         # 前台首页
│       │   ├── myQuestion/       # 我的学习
│       │   ├── questionPractice/ # 题库练习
│       │   ├── notes/           # 学习分享
│       │   ├── knowledge/       # 知识库
│       │   ├── english/         # 英语学习
│       │   ├── tools/           # 实用工具
│       │   ├── studio/         # 题库搭建
│       │   └── messages/        # 消息中心
│       │
│       ├── system/               # 系统配置页面
│       │   ├── user/            # 用户管理
│       │   ├── role/            # 角色管理
│       │   ├── menu/            # 菜单管理
│       │   └── ...
│       │
│       ├── monitor/             # 系统监控页面
│       │
│       ├── login.vue            # 登录页面
│       ├── register.vue         # 注册页面
│       └── error/               # 错误页面
│           ├── 401.vue
│           └── 404.vue
│
├── .env.development              # 开发环境变量
├── .env.production               # 生产环境变量
├── vite.config.js               # Vite 配置
└── package.json                 # 依赖配置
```

---

## 快速开始

### 环境要求

- Node.js 16+
- pnpm / npm / yarn

### 安装依赖

```bash
cd openstudy-vue3
pnpm install
```

### 开发启动

```bash
pnpm dev
```

### 构建生产

```bash
pnpm build
```

---

## 环境配置

### 开发环境变量 (.env.development)

```bash
# 页面标题
VITE_APP_TITLE = openstudy

# 环境标识
VITE_APP_ENV = 'development'

# API 基础路径（代理到后端）
VITE_APP_BASE_API = '/dev-api'
```

### Vite 代理配置

```javascript
// vite.config.js
server: {
  port: 80,
  proxy: {
    // /dev-api/* 代理到后端 8086
    '/dev-api': {
      target: 'http://localhost:8086',
      changeOrigin: true
    },
    // /ai/* 代理到后端（AI 接口）
    '/ai': {
      target: 'http://localhost:8086',
      changeOrigin: true
    },
    // WebSocket 代理
    '/ws': {
      target: 'http://localhost:8086',
      ws: true
    }
  }
}
```

---

## 访问地址

| 页面 | 地址 | 说明 |
|------|------|------|
| 前台首页 | http://localhost | 学习平台主页 |
| 登录页面 | http://localhost/login | 用户登录 |
| 注册页面 | http://localhost/register | 用户注册 |
| 后台管理 | http://localhost/#/login | 系统后台 |

---

## 特色亮点

### 前后台一体

- 前台和后台共用同一前端端口（80）
- 通过路由区分：`/front/*` 为前台，`/index/*` 为后台
- 共用登录认证体系

### AI 深度集成

- 全局 AI 悬浮助手：随时随地提问
- 多 AI 提供商切换：智谱 AI / DeepSeek
- RAG 知识库问答：基于文档的精准回答
- AI 辅助出题：自动生成高质量题目

### 组件化开发

- 丰富的可复用组件库
- 统一的设计语言和样式规范
- 组件 props 驱动，行为可控

### 页面缓存优化

- 基于 keep-alive 的页面缓存
- 支持页面状态保持
- 三个钩子标准写法：onMounted + onActivated + watch

### 权限精细控制

- 基于 RBAC 的权限模型
- 角色权限：`admin` / `common`
- 前后台权限隔离

---

## 致谢

本项目前端基于 **若依前后端分离框架 Vue 3 版本** 二次开发，感谢若依框架提供的前端架构和组件规范。

> 若依官网：https://ruoyi.vip
>
> 若依文档：http://doc.ruoyi.vip

---

## 许可证

本项目采用 MIT 许可证开源。
