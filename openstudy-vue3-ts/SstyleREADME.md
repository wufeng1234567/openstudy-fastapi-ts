# 前台全局样式统一 - 最终版提示词

请严格遵循以下规范，逐页修改所有前台页面及组件样式。**只改 CSS/SCSS，不动任何 HTML 结构、业务逻辑、路由和功能代码。不删除任何文件。**

---
front.vue 不需要修改了 目前这个样式就挺好
## 核心原则

**背景颜色**：和当前 `front.vue` 整体背景保持一致，不要额外加灰色背景。如果某页面本身没有设置背景，就保持原样。

**按钮颜色**：
- **普通按钮**：白底 + 细边框
- **删除按钮**：允许使用红色文字（`#b45353`），背景淡红（`#fef2f2`）
- **编辑/信息按钮**：淡灰底或白底
- **文档/警告按钮**：淡暖色底，淡暖色文字
- **新建/主操作按钮**：白底 + 稍深边框

**禁止**：大面积灰色背景、Element Plus 默认高饱和蓝紫绿橙背景色、文字对比度不够。

---

## 样式生效方式 ★★★

**优先使用类名覆盖，如果修改 Element Plus 内部元素（如 `el-table__header`、`el-pager` 等）类名覆盖无效时，可使用 `:deep()` 穿透。**

在每个页面或组件的 `<style>` 中，通过具体类名直接写样式。如果需要覆盖 Element Plus 默认样式，使用**不带 `scoped` 的 `<style lang="scss">` 块**，通过父容器类名限定作用范围。

示例：
```vue
<style lang="scss">
.knowledge-list-container .actions .el-button {
    border-radius: 8px;
    ...
}
.knowledge-list-container .actions .el-button--danger {
    background: #fef2f2;
    ...
}
</style>
```

---

## 按钮规范

**通用按钮**：
```scss
border-radius: 8px;
font-weight: 500;
padding: 6px 14px;
transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
background: #fff;
border: 1px solid #e5e7eb;
color: #6b7280;

&:hover { transform: translateY(-2px); border-color: #b3b3b3; color: #4b5563; }
&:active { transform: translateY(0); }
```

**编辑/信息按钮**：
```scss
background: #f3f4f6; border-color: #e5e7eb; color: #6b7280;
&:hover { background: #fff; border-color: #b3b3b3; color: #4b5563; }
```

**文档/警告按钮**：
```scss
background: #fefce8; border-color: #e5e0c0; color: #947a4a;
&:hover { background: #fff; border-color: #b3a080; color: #7a6238; }
```

**删除/危险按钮**：
```scss
background: #fef2f2; border-color: #e5d0d0; color: #b45353;
&:hover { background: #fff; border-color: #b38080; color: #9b3a3a; }
```

---

## 颜色参考

```
标题文字:  #1f2937
正文文字:  #6b7280
浅色文字:  #9ca3af
边框颜色:  #e5e7eb
边框悬浮:  #d1d5db
分割线:    #f3f4f6
```

---

## 页面标题统一 ★★★

所有页面的标题必须统一：
```scss
font-size: 20px;
font-weight: 700;
color: #1f2937;
```

---

## 圆角规范

| 元素     | 圆角 |
|----------|------|
| 卡片     | 16px |
| 对话框   | 16px |
| 按钮     | 8px  |
| 输入框   | 8px  |
| 标签 Tag | 4px  |

---

## 动画规范

```scss
transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

// 按钮悬浮
&:hover { transform: translateY(-2px); }
&:active { transform: translateY(0); }

// 卡片悬浮
&:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
    border-color: #d1d5db;
}
```

**禁止**：box-shadow 彩色光晕、背景剧烈变色、scale 缩放。

---

## 卡片规范

```scss
border-radius: 16px;
border: 1px solid #e5e7eb;
box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
background: #fff;

&:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08); border-color: #d1d5db; }
```

---

## 输入框规范

```scss
.el-input__wrapper {
    border-radius: 8px;
    box-shadow: 0 0 0 1px #e5e7eb;
    &:hover { box-shadow: 0 0 0 1px #d1d5db; }
    &.is-focus { box-shadow: 0 0 0 1px #b3b3b3; }
}
```

---

## 对话框规范

```scss
.el-dialog {
    border-radius: 16px;
    overflow: hidden;
    .el-dialog__header { padding: 20px 24px 16px; border-bottom: 1px solid #f3f4f6; }
    .el-dialog__body { padding: 24px; }
    .el-dialog__footer { padding: 16px 24px 20px; border-top: 1px solid #f3f4f6; }
}
```

---

## 导航栏 + 用户区域

**导航栏（已锁定，无需修改）**：`front.vue` 中导航栏样式已确认良好，以下仅为记录当前样式，不需要再次修改：

```scss
.nav-menu a {
    color: #6b7280; font-weight: 500; padding: 8px 16px; border-radius: 8px;
    &:hover { color: #1f2937; background: #f3f4f6; }
    &.router-link-active { color: #1f2937; background: #f3f4f6; }
}
```
用户区域（需要修改）：用户区域尚未统一，包括登录/注册按钮、用户头像下拉菜单、退出登录等，需要按以下规范修改：
// 登录按钮 - 文字按钮，低调灰色
// 注册按钮 - 白底 + 细边框，悬浮时上浮 + 边框微深
// 用户下拉菜单项 - 圆角 8px，悬浮时淡灰背景




整体已经很完善了，但还有几个容易踩坑的地方需要明确：

---

## 建议补充的内容

### 1. 表格样式
你的 `docs.vue`、词库详情页等都用到了 `el-table`，Element Plus 的表格默认样式也需要覆盖：

```

**表格 (el-table)**（表头允许使用淡灰底以区分内容行）：
表格规范：
.el-table {
    border-radius: 8px;
    overflow: hidden;

    .el-table__header th {
        background: #f8f9fa;
        color: #6b7280;
        font-weight: 500;
        border-bottom: 1px solid #e5e7eb;
    }

    .el-table__body td {
        color: #1f2937;
        border-bottom: 1px solid #f3f4f6;
    }

    .el-table__row:hover > td {
        background: #fafafa;
    }
}
```

### 2. 分页组件
`el-pagination` 也需要统一：

```
.el-pagination {
    .el-pager li {
        border-radius: 6px;
        &.is-active { background: #f3f4f6; color: #1f2937; }
    }
}
```

### 3. 标签 Tag 颜色
Element Plus 的 `el-tag` 默认颜色很鲜艳，必须覆盖：

```
.el-tag--info { background: #f3f4f6; border-color: #e5e7eb; color: #6b7280; }
.el-tag--success { background: #f0f9eb; border-color: #e1f3d8; color: #67c23a; }  // 允许保留绿色
.el-tag--warning { background: #fefce8; border-color: #e5e0c0; color: #947a4a; }
.el-tag--danger { background: #fef2f2; border-color: #e5d0d0; color: #b45353; }
```

### 4. 空状态组件
很多页面用 `el-empty`，描述文字颜色要清晰：

```
.el-empty__description {
    color: #9ca3af;
}
```

### 5. 下拉菜单
用户区域和筛选用到的 `el-dropdown-menu` 和 `el-select-dropdown`：

```
.el-dropdown-menu,
.el-select-dropdown__item {
    border-radius: 8px;
    &:hover { background: #f3f4f6; }
}
```

### 6. 明确“不要改”的元素
有些组件已有好的样式，不需要动：

- `QuestionCard.vue` 中各种题型标签的颜色可以保留（它在卡片头部已经有区分作用）
- 轮播图 `el-carousel` 保持原样
- OCR 页面的图片编辑器已有深色背景设计，不用改

---

## 修改后的完整补充部分

把以下内容追加到你的提示词末尾：

---

### 其他组件规范

**表格 (el-table)**：
```
.el-table {
    border-radius: 8px;
    overflow: hidden;
}
.el-table__header th {
    background: #f8f9fa;
    color: #6b7280;
    font-weight: 500;
    border-bottom: 1px solid #e5e7eb;
}
.el-table__body td {
    color: #1f2937;
    border-bottom: 1px solid #f3f4f6;
}
.el-table__row:hover > td {
    background: #fafafa;
}
```

**分页 (el-pagination)**：
```
.el-pager li {
    border-radius: 6px;
}
.el-pager li.is-active {
    background: #f3f4f6;
    color: #1f2937;
}
```

**标签 (el-tag)**：
```
.el-tag--info { background: #f3f4f6; border-color: #e5e7eb; color: #6b7280; }
.el-tag--warning { background: #fefce8; border-color: #e5e0c0; color: #947a4a; }
.el-tag--danger { background: #fef2f2; border-color: #e5d0d0; color: #b45353; }
```

**空状态 (el-empty)**：
```
.el-empty__description { color: #9ca3af; }
```

**下拉菜单**：
```
.el-dropdown-menu,
.el-select-dropdown__item {
    border-radius: 8px;
}
.el-dropdown-menu__item:hover,
.el-select-dropdown__item:hover {
    background: #f3f4f6;
}
```

### 不需要修改的组件

- `QuestionCard.vue` 题型标签颜色保留
- `el-carousel` 轮播图保持原样
- OCR 图片编辑器保持原样

---


在提示词中单独加一节，把"一致性"讲清楚：

---

## 页面布局一致性 ★★★ 最重要

### 规则：每个模块下的所有子页面，布局结构必须完全相同

**英语学习模块**（`english/`）下：
- `home/index.vue`
- `listening/index.vue`
- `ocr/index.vue`
- `vocabulary/index.vue`
- `vocabulary/detail.vue`
- `reading/index.vue`

**这些页面的标题栏必须统一**：返回按钮在左、标题居中、右侧空或放功能按钮。

**知识库模块**（`knowledge/`）下：
- `home.vue`
- `list.vue`
- `upload.vue`
- `qa.vue`
- `docs.vue`

**这些页面的标题栏 / 内容区域必须统一**。

**我的题目模块**（`myQuestion/`）下：
- `myBank/index.vue`
- `myFavoriteBank/index.vue`
- `myFavoriteQuestion/index.vue`
- `myMistakes/index.vue`
- `myMarked/index.vue`

**这些页面的标题必须统一**（字号、字重、颜色），卡片布局、筛选区域的位置也要一致。

### 具体做法

1. 先在某个模块中挑一个已经改好的页面作为**该模块的基准**
2. 该模块下的其他页面，**直接复制基准页面的标题样式、卡片样式、间距、圆角、按钮样式**
3. 最终效果：**同一模块下切换子路由时，视觉上毫无违和感，像在同一个页面里换了个内容区**

**已有基准页面参考**：
- 知识库：`src/views/front/knowledge/list.vue`
- 英语学习、我的题目等模块也要各自确定基准页面，统一风格

---





---

## 修改范围

以下所有文件及它们引用的所有子组件：
- `src/views/front/` 下所有页面
- `src/layout/front.vue`
- `src/components/` 下所有被前台页面引用的组件

**不修改** `src/views/admin/` 及任何后台文件。

**不删除任何文件。**

---

## 唯一基准参考

**以 `src/views/front/knowledge/list.vue` 为唯一样式基准。**

---

## 关键约束

1. 背景颜色不许乱加灰色
2. 所有页面标题统一（20px / 700 / #1f2937）
3. 按钮文字清晰可读
4. 使用类名覆盖，不用 `:deep()` 穿透
5. 删除按钮允许红色，其余按钮低调处理
6. 只改样式，不动功能和结构
7. 不删除任何文件

---

## 若依框架 API 响应数据格式 ★★★

本系统后端接口遵循若依框架规范：

**分页列表接口（`TableDataInfo`）：**
```json
{ "code": 200, "rows": [...], "total": 100 }
```
→ 前端取值：`res.rows`、`res.total`

**详情/非分页接口（`AjaxResult`）：**
```json
{ "code": 200, "data": { ... } }
```
→ 前端取值：`res.data`

### 判断规则

- Controller 返回类型是 `TableDataInfo` 或调用了 `startPage()` → 取 `res.rows`
- Controller 返回类型是 `AjaxResult` → 取 `res.data`

### 常见错误

```javascript
const res = await listPublicNotes(...)
const notes = res.data || []  // ❌ 分页接口数据在 res.rows
const notes = res.rows || []  // ✅
```

新增任何分页列表接口时，先用 `console.log(res)` 确认结构。默认假定分页接口数据在 `res.rows` 里。

### 已修复的相关 Bug

- `list.vue` `fetchNotes`：`res.data?.records` → `res.rows`
- `detail.vue` `fetchNavigationNotes`：`res.data` → `res.rows`

---

## keep-alive 缓存组件中详情页的数据刷新 ★★★

### 问题场景

详情页（如笔记详情、词库详情、题库详情）被 `keep-alive` 缓存后，用户从列表页点击不同条目进入详情时，因为组件实例被复用，`onMounted` 不会重新执行，导致始终显示第一次打开的内容。

### 解决方案

在详情页组件中添加 `onActivated` 钩子，监听路由参数变化：

```javascript
import { ref, onMounted, onActivated } from 'vue'

onMounted(() => {
    fetchDetail()
})

onActivated(() => {
    const newId = route.params.id
    if (detailData.value.id !== Number(newId)) {
        resetData()
        fetchDetail()
    }
})

function resetData() {
    detailData.value = {}
    // 重置其他相关状态
}
```

### 核心要点

1. **必须同时使用 `onMounted` 和 `onActivated`**：前者处理首次加载，后者处理缓存恢复
2. **必须比较 ID 是否变化**：避免相同 ID 时重复请求
3. **必须重置旧数据**：在获取新数据前清空旧数据，防止短暂显示旧内容
4. **ID 类型统一**：使用 `Number()` 或 `String()` 确保类型一致

### 已应用此方案的页面

- `src/views/front/notes/detail.vue`：笔记详情页
- `src/views/front/english/vocabulary/detail.vue`：词库详情页
- 其他所有带参数路由的详情页都应遵循此规范

### 参考模板

```javascript
const route = useRoute()
const detailData = ref({})

const fetchDetail = async () => {
    const id = route.params.id
    // 请求数据...
    detailData.value = res.data || {}
}

onMounted(() => {
    fetchDetail()
})

onActivated(() => {
    const newId = route.params.id
    if (detailData.value.id !== Number(newId)) {
        detailData.value = {}
        fetchDetail()
    }
})
```

---

## keep-alive 缓存下同一路由参数变化的处理 ★★★

### 问题场景

在同一个详情页组件内，通过上一篇/下一篇导航切换内容时，`route.params.id` 变化了，但 `onMounted` 和 `onActivated` 都不会触发，导致页面内容不更新。

### 解决方案

添加 `watch` 监听 `route.params.id`：

```javascript
import { ref, onMounted, onActivated, watch } from 'vue'

watch(() => route.params.id, (newId, oldId) => {
    if (newId && newId !== oldId) {
        resetData()
        fetchDetail()
    }
})
```

### 三个钩子分工

| 钩子 | 触发场景 |
|------|--------|
| `onMounted` | 首次进入页面 |
| `onActivated` | 从其他模块切换回来（keep-alive 恢复） |
| `watch route.params.id` | 同一页面内参数变化（上一篇/下一篇） |

### 已应用此方案的页面

- `src/views/front/notes/detail.vue`：笔记详情页