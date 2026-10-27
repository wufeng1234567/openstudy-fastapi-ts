<template>
  <div class="notes-manager" style="display: flex; height: 100vh; width: 100%; position: relative;">
    <!-- 笔记本侧边栏 -->
    <div
      v-if="!isEditingMode"
      class="sidebar"
      :style="{
        width: isSidebarExpanded ? '250px' : '0',
        borderRight: isSidebarExpanded ? '1px solid #dcdfe6' : 'none',
        padding: isSidebarExpanded ? '10px' : '0',
        overflowY: 'auto',
        transition: 'width 0.3s ease',
        flexShrink: 0
      }"
    >
      <el-button type="primary" @click="createNewNote" style="width: 100%; margin-bottom: 10px;">
        新建笔记
      </el-button>

      <el-button
        :type="selectedNodes.length > 0 ? 'danger' : ''"
        :plain="selectedNodes.length === 0"
        :disabled="selectedNodes.length === 0"
        @click="batchDeleteSelected"
        style="width: 100%; margin-bottom: 10px; margin-left: 0px;"
      >
        删除
      </el-button>

      <el-input
        v-model="searchText"
        placeholder="搜索笔记"
        style="margin-bottom: 10px;"
        @input="filterNotes"
      />

      <el-tree
        :key="searchText"
        :data="notebooks"
        :props="treeProps"
        ref="treeRef"
        node-key="id"
        default-expand-all
        :expand-on-click-node="false"
        :highlight-current="false"
        @node-click="handleNodeClick"
      >
        <template #default="{ node, data }">
          <div
            class="tree-node-row"
            :class="{ 'selected-node': selectedNodes.some(n => n.id === data.id) }"
            @click.stop="handleRowClick(node, data, $event)"
            @contextmenu.prevent="openContextMenu($event, data, data.isLeaf ? 'note' : 'category')"
            style="
              display: flex;
              align-items: center;
              justify-content: space-between;
              width: 100%;
              padding: 4px 8px;
              border-radius: 4px;
              cursor: pointer;
            "
          >
            <span class="tree-node-text">{{ data.label }}</span>
            <el-checkbox
              :model-value="selectedNodes.some(n => n.id === data.id)"
              @change="(checked) => toggleSelection(data, checked)"
              :disabled="!isSelectable(data)"
              style="flex-shrink: 0; margin-right: -8px;"
              @click.stop
            />
          </div>
        </template>
      </el-tree>
    </div>

    <!-- 主内容区 -->
    <div
      class="main-content"
      :style="{
        flex: 1,
        padding: '20px',
        overflow: 'hidden',
        transition: 'all 0.3s ease',
        width: isSidebarExpanded && !isEditingMode ? 'calc(100% - 250px)' : '100%',
        boxSizing: 'border-box'
      }"
    >
      <!-- 预览模式 -->
      <div v-if="!isEditingMode && currentnote.noteId" style="height: 100%; width: 100%; display: flex; flex-direction: column;">
        <div class="preview-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
          <h2 style="margin: 0; color: #303133;">{{ currentNote.title }}</h2>
          <div class="preview-actions">
            <el-button type="primary" @click="enterEditMode">编辑</el-button>
          </div>
        </div>

        <div class="preview-content" style="flex: 1; width: 100%; min-width: 0; overflow: hidden;">
          <div style="height: 100%; width: 100%; overflow-y: auto; overflow-x: hidden;">
            <md-preview
              :model-value="currentNote.markdownContent || ''"
              style="
                width: 100%;
                min-width: 0;
                padding: 24px;
                background: #fff;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
              "
              preview-theme="github"
              code-theme="github"
            />
          </div>
        </div>
      </div>

      <!-- 编辑模式 -->
      <div v-else-if="isEditingMode" style="height: 100%; width: 100%; display: flex; flex-direction: column;">
        <el-form :model="currentNote" label-width="100px" style="flex: 1; width: 100%; display: flex; flex-direction: column;">
          <el-form-item label="标题">
            <el-input v-model="currentNote.title" placeholder="请输入笔记标题" />
          </el-form-item>
          <el-form-item label="内容" style="flex: 1; width: 100%; margin-bottom: 0;">
            <div style="height: 100%; width: 100%; min-height: 400px; border: 1px solid #e4e7ed; border-radius: 4px;">
              <!-- 公式按钮（2026-10-27）：笔记正文里也会写公式（数学笔记），
                   挂一个按钮把 LaTeX 插到光标处，不用手写命令。
                   md-editor 的 `insert` 通过 ref 调用。 -->
              <div class="note-math-bar">
                <button type="button" class="note-math-btn" title="插入公式" @click="openMathForNote">
                  <span class="note-fx">ƒx</span> 插入公式
                </button>
                <span class="note-math-hint">插入后用 $...$ 包裹，预览区会渲染成排版公式</span>
              </div>
              <md-editor
                ref="mdEditorRef"
                v-model="currentNote.markdownContent"
                style="height: 100%; width: 100%;"
                preview-theme="github"
                code-theme="github"
                @on-upload-img="handleUploadImg"
              />
            </div>
          </el-form-item>
          <el-form-item style="margin-top: 20px;">
            <el-button type="primary" @click="saveNote">保存</el-button>
            <el-button @click="exitEditMode">取消</el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 空状态 - 修改为居中显示 -->
      <div
        v-else
        class="empty-state-container"
      >
        <div class="empty-state-content">
          <el-icon size="80" class="empty-icon">
            <Document />
          </el-icon>
          <p class="empty-title">暂无笔记</p>
          <p class="empty-desc">请选择一篇笔记，或点击"新建笔记"</p>
        </div>
      </div>
    </div>

    <!-- 侧边栏开关按钮 -->
    <div
      v-if="!isEditingMode"
      class="sidebar-toggle-btn"
      :style="{
        position: 'absolute',
        top: '20px',
        left: isSidebarExpanded ? '250px' : '0px',
        transform: 'translateX(-50%)',
        zIndex: 10,
        width: '24px',
        height: '24px',
        background: '#fff',
        border: '1px solid #dcdfe6',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'left 0.3s ease',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
      }"
      @click="isSidebarExpanded = !isSidebarExpanded"
    >
      <el-icon :style="{ transform: isSidebarExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.3s' }">
        <ArrowRight />
      </el-icon>
    </div>

    <!-- 新建笔记弹窗 -->
    <el-dialog
      v-model="showSelectCategoryDialog"
      title="新建笔记"
      width="400px"
      @close="() => {
        showSelectCategoryDialog = false;
        selectedCategoryId = null;
        newCategoryName = '';
      }"
    >
      <el-form label-width="80px">
        <el-form-item label="所属分类">
          <el-select
            v-model="selectedCategoryId"
            placeholder="请选择分类"
            style="width: 100%"
            filterable
            @change="onCategoryChange"
          >
            <el-option
              v-for="category in rawNotebooks"
              :key="category.id"
              :label="category.label"
              :value="category.id"
            />
            <el-divider style="margin: 4px 0;" />
            <el-option
              label="创建新分类..."
              value="create_new"
            />
          </el-select>
        </el-form-item>

        <el-form-item
          v-if="selectedCategoryId === 'create_new'"
          label="新分类名"
          prop="newCategoryName"
          :rules="[{ required: true, message: '请输入分类名称', trigger: 'blur' }]"
        >
          <el-input
            v-model="newCategoryName"
            placeholder="例如：学习笔记、工作记录"
            clearable
            maxlength="30"
            show-word-limit
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showSelectCategoryDialog = false">取消</el-button>
          <el-button
            type="primary"
            :loading="creatingNote"
            @click="handleConfirmCreateNote"
          >
            确定
        </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 右键菜单 -->
    <div ref="contextMenuRef" class="context-menu" style="display: none; position: fixed; z-index: 9999;">
      <div class="menu-item" @click="onEditItem">修改</div>
      <div class="menu-item" @click="onDeleteItem">删除</div>
    </div>

    <!-- 公式符号面板（2026-10-27）：点「ƒx」打开，确定后插到 Markdown 光标处 -->
    <MathEditor ref="mathEditorRef" title="插入公式" @confirm="onNoteMathInsert" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'NotesEditor' })
import { ref, reactive, getCurrentInstance, computed, watch, nextTick } from 'vue';
import { MdEditor, MdPreview } from 'md-editor-v3';
import 'md-editor-v3/lib/style.css';
import { Document, ArrowRight } from '@element-plus/icons-vue';
// 公式编辑（2026-10-27）：笔记正文写数学公式时，用符号面板代替手打 LaTeX。
// md-editor-v3 默认**不渲染公式**，必须显式喂 katex 才能让 `$...$` 变成排版。
import MathEditor from '@/components/MathEditor/index.vue';
import katex from 'katex';
import 'katex/dist/katex.min.css';

// API
import { addNoteCategory, getAllNoteCategory, updateNoteCategory, delNoteCategory } from "@/api/noteCategory/noteCategory";
import { listNote, addNote, updateNote, delNote } from "@/api/notes/note";
import { uploadImage } from "@/api/common/common";
import useUserStore from "@/store/modules/user";

const { proxy } = getCurrentInstance();
const userStore = useUserStore();
const userId = computed(() => userStore.id);

/**
 * md-editor-v3 的公式配置（2026-10-27）
 *
 * ⚠️ 这个库**默认不渲染公式** —— 不喂 `config()` 的话，笔记里写
 *    `$\frac{a}{b}$` 在预览区就是原样文字。项目里 katex 已有，
 *    直接接上即可（零新增依赖）。
 */
MdEditor.config({
  editorExtensions: {
    katex: {
      katexInstance: katex,
      // 用 katex 自带的 CSS，避免公式字号/字体与其它页面不一致
      katexCSS: '',
    },
  },
});

// ====== 原有逻辑（完全保留）======
const isEditingMode = ref(false);
const searchText = ref('');
const notebooks = ref([]);
const rawNotebooks = ref([]);
const treeRef = ref(null);
const showSelectCategoryDialog = ref(false);
const selectedCategoryId = ref(null);
const newCategoryName = ref('');
const isSidebarExpanded = ref(true);
const creatingNote = ref(false);
const selectedNodes = ref([]);

const treeProps = {
  children: 'children',
  label: 'label',
  isLeaf: 'isLeaf'
};

const currentNote = reactive({
  id: null,
  userId: null,
  categoryId: null,
  title: '',
  filename: '',
  markdownContent: '',
  htmlContent: '',
  wordCount: 0,
  tags: [],
  isPublic: 0,
  status: 'draft',
  sortOrder: 0
});

function loadNotes() {
  if (!userId.value) return;

  Promise.all([
    listNote({ userId: userId.value }),
    getAllNoteCategory({ userId: userId.value })
  ])
    .then(([noteRes, categoryRes]) => {
      const categories = categoryRes.data || [];
      const validCategories = new Set();

      categories.forEach(cat => {
        validCategories.add(String(cat.id));
      });

      const noteGroups = {};

      categories.forEach(cat => {
        const idStr = String(cat.id);
        noteGroups[idStr] = {
          id: idStr,
          label: cat.name,
          children: [],
          isLeaf: false
        };
      });

      noteGroups['uncategorized'] = {
        id: 'uncategorized',
        label: '未分类',
        children: [],
        isLeaf: false
      };

      (noteRes.rows || []).forEach(note => {
        let targetCategoryId;
        if (note.categoryId != null && validCategories.has(String(note.categoryId))) {
          targetCategoryId = String(note.categoryId);
        } else {
          targetCategoryId = 'uncategorized';
        }

        noteGroups[targetCategoryId].children.push({
          ...note,
          id: note.noteId,
          label: note.title,
          isLeaf: true
        });
      });

      rawNotebooks.value = Object.values(noteGroups).filter(
        group => group.children.length > 0 || group.id !== 'uncategorized'
      );
      notebooks.value = [...rawNotebooks.value];
      selectedNodes.value = [];
    })
    .catch(err => {
      console.error('加载笔记失败', err);
      proxy?.$modal?.msgError("加载笔记失败");
    });
}

const handleNoteSelect = (data) => {
  if (data && data.isLeaf) {
    Object.assign(currentNote, {
      id: data.id,
      userId: data.userId,
      categoryId: data.categoryId,
      title: data.title,
      filename: data.filename || data.title + '.md',
      markdownContent: data.markdownContent || '',
      htmlContent: data.htmlContent || '',
      wordCount: data.wordCount || 0,
      tags: Array.isArray(data.tags) ? data.tags : [],
      isPublic: data.isPublic || 0,
      status: data.status || 'draft',
      sortOrder: data.sortOrder || 0
    });
    isEditingMode.value = false;
  }
};

const toggleSelection = (data, checked) => {
  const isLeaf = data.isLeaf;
  const nodeId = data.id;

  if (checked) {
    if (isLeaf) {
      const parentId = String(data.categoryId);
      const parentSelected = selectedNodes.value.some(n => !n.isLeaf && n.id === parentId);
      if (parentSelected) {
        proxy?.$message?.warning('父分类已选中，不能同时选择子笔记');
        return;
      }
    } else {
      const childSelected = selectedNodes.value.some(
        n => n.isLeaf && String(n.categoryId) === nodeId
      );
      if (childSelected) {
        proxy?.$message?.warning('子笔记已选中，不能同时选择父分类');
        return;
      }
    }

    if (!selectedNodes.value.some(n => n.id === nodeId)) {
      selectedNodes.value.push({ ...data });
    }
  } else {
    const index = selectedNodes.value.findIndex(n => n.id === nodeId);
    if (index >= 0) {
      selectedNodes.value.splice(index, 1);
    }
  }

  nextTick(() => {
    if (treeRef.value) {
      treeRef.value.update();
    }
  });
};

const isSelectable = (nodeData) => {
  if (selectedNodes.value.some(n => n.id === nodeData.id)) {
    return true;
  }
  if (nodeData.isLeaf) {
    const parentId = String(nodeData.categoryId);
    return !selectedNodes.value.some(n => !n.isLeaf && n.id === parentId);
  } else {
    return !selectedNodes.value.some(n => n.isLeaf && String(n.categoryId) === nodeData.id);
  }
};

const handleNodeClick = (node, data) => {
  if (!data.isLeaf) {
    treeRef.value.setCurrentKey(null);
  }
};

const createNewNote = () => {
  if (rawNotebooks.value.length === 0) {
    selectedCategoryId.value = 'create_new';
    newCategoryName.value = '';
  } else {
    selectedCategoryId.value = rawNotebooks.value[0].id;
    newCategoryName.value = '';
  }
  showSelectCategoryDialog.value = true;
};

const onCategoryChange = (val) => {
  if (val !== 'create_new') {
    newCategoryName.value = '';
  }
};

const handleConfirmCreateNote = () => {
  showSelectCategoryDialog.value = false;

  if (selectedCategoryId.value === 'create_new') {
    const name = newCategoryName.value?.trim();
    if (!name) {
      proxy.$modal.msgError("请输入新分类名称");
      showSelectCategoryDialog.value = true;
      return;
    }

    addNoteCategory({
      userId: userId.value,
      name: name,
      orderNum: 0
    }).then(res => {
      if (res.code === 200) {
        const categoryId = res.data;
        Object.assign(currentNote, {
          id: null,
          userId: userId.value,
          categoryId: categoryId,
          title: '新笔记',
          filename: '新笔记.md',
          markdownContent: '# 新笔记\n\n开始记录你的想法...',
          htmlContent: '',
          wordCount: 0,
          tags: [],
          isPublic: 0,
          status: 'draft',
          sortOrder: 0
        });
        isEditingMode.value = true;
      } else {
        proxy.$modal.msgError("创建分类失败：" + res.msg);
        showSelectCategoryDialog.value = true;
      }
    }).catch(err => {
      console.error('创建分类异常', err);
      showSelectCategoryDialog.value = true;
    });
  } else if (selectedCategoryId.value && selectedCategoryId.value !== 'uncategorized') {
    const categoryId = Number(selectedCategoryId.value);
    Object.assign(currentNote, {
      id: null,
      userId: userId.value,
      categoryId: categoryId,
      title: '新笔记',
      filename: '新笔记.md',
      markdownContent: '# 新笔记\n\n开始记录你的想法...',
      htmlContent: '',
      wordCount: 0,
      tags: [],
      isPublic: 0,
      status: 'draft',
      sortOrder: 0
    });
    isEditingMode.value = true;
  } else {
    Object.assign(currentNote, {
      id: null,
      userId: userId.value,
      categoryId: null,
      title: '新笔记',
      filename: '新笔记.md',
      markdownContent: '# 新笔记\n\n开始记录你的想法...',
      htmlContent: '',
      wordCount: 0,
      tags: [],
      isPublic: 0,
      status: 'draft',
      sortOrder: 0
    });
    isEditingMode.value = true;
  }
};

const enterEditMode = () => isEditingMode.value = true;
const exitEditMode = () => isEditingMode.value = false;

const saveNote = () => {
  const note = { ...currentNote };

  if (note.categoryId === null || note.categoryId === 'null' || note.categoryId === '' || note.categoryId === undefined) {
    note.categoryId = null;
  } else {
    const parsed = Number(note.categoryId);
    note.categoryId = isNaN(parsed) ? null : parsed;
  }

  if (Array.isArray(note.tags)) {
    note.tags = note.tags.join(',');
  }

  note.filename = note.title + '.md';
  note.wordCount = (note.markdownContent || '').replace(/\s+/g, '').length;

  const savePromise = note.noteId
    ? updateNote(note)
    : addNote(note).then(res => {
        note.noteId = res.data;
        Object.assign(currentNote, note);
      });

  savePromise
    .then(() => {
      proxy.$modal.msgSuccess(note.noteId ? "更新成功" : "新增成功");
      loadNotes();
    })
    .catch(err => {
      console.error('保存失败', err);
    });
};

const filterNotes = () => {
  const keyword = searchText.value.trim().toLowerCase();

  if (!keyword) {
    notebooks.value = [...rawNotebooks.value];
    return;
  }

  const filtered = rawNotebooks.value
    .map(group => {
      const children = Array.isArray(group.children) ? group.children : [];
      const categoryMatches = typeof group.label === 'string' &&
                              group.label.toLowerCase().includes(keyword);
      const matchedChildren = children.filter(child =>
        typeof child.label === 'string' &&
        child.label.toLowerCase().includes(keyword)
      );

      if (categoryMatches) {
        return { ...group, children: [...children] };
      } else if (matchedChildren.length > 0) {
        return { ...group, children: matchedChildren };
      }
      return null;
    })
    .filter(Boolean);

  notebooks.value = filtered;
};

/* ===== 公式编辑（2026-10-27）=====
   笔记正文里常写数学公式。之前只能手打 LaTeX，
   现在点「ƒx」→ 符号面板（纯鼠标）→ 确定后插到光标处。 */
const mdEditorRef = ref<any>(null)
const mathEditorRef = ref<any>(null)

function openMathForNote() {
  mathEditorRef.value?.open('')
}

/** 面板确定：插到 md-editor 的光标处 */
function onNoteMathInsert(latex: string) {
  if (!latex) return
  // md-editor-v3 的实例方法：insert(cfg) 在光标处插入
  const inst = mdEditorRef.value
  if (inst && typeof inst.insert === 'function') {
    inst.insert(() => ({ targetValue: latex }))
  } else {
    // 兜底：拿不到实例就追加到末尾（至少内容进去了）
    currentNote.markdownContent = (currentNote.markdownContent || '') + latex
  }
}

const handleUploadImg = (files, callback) => {
  Promise.all(
    files.map(file => {
      const formData = new FormData();
      formData.append('file', file);
      return uploadImage(formData);
    })
  )
    .then(responses => {
      const urls = responses
        .filter(res => res.code === 200 && res.url)
        .map(res => {
          let url = import.meta.env.VITE_APP_BASE_API + res.url;
          return url.replace(/ /g, '%20');
        });
      callback(urls);
    })
    .catch(() => {
      proxy.$modal.msgError('上传失败');
      callback([]);
    });
};

if (userId.value) {
  loadNotes();
} else {
  const unwatch = watch(userId, (newId) => {
    if (newId) {
      loadNotes();
      unwatch();
    }
  });
}

// ====== 右键菜单逻辑 ======
const contextMenuRef = ref(null);
const contextTarget = ref(null);
const contextType = ref('');

const openContextMenu = (event, data, type) => {
  if (!selectedNodes.value.some(n => n.id === data.id)) {
    selectedNodes.value = [{ ...data }];
  }

  contextTarget.value = data;
  contextType.value = type;

  const menu = contextMenuRef.value;
  menu.style.display = 'block';
  menu.style.left = event.clientX + 'px';
  menu.style.top = event.clientY + 'px';

  const closeHandler = () => {
    menu.style.display = 'none';
    document.removeEventListener('click', closeHandler);
  };
  document.addEventListener('click', closeHandler);
  event.stopPropagation();
};

const onEditItem = () => {
  const menu = contextMenuRef.value;
  menu.style.display = 'none';

  if (contextType.value === 'category') {
    proxy.$prompt('修改分类名称', '请输入新名称', {
      inputValue: contextTarget.value.label
    }).then(({ value }) => {
      if (!value?.trim()) {
        proxy.$message.error('名称不能为空');
        return;
      }
      updateNoteCategory({
        id: Number(contextTarget.value.id),
        name: value.trim()
      }).then(res => {
        if (res.code === 200) {
          proxy.$message.success('修改成功');
          loadNotes();
        } else {
          proxy.$message.error(res.msg || '修改失败');
        }
      }).catch(() => {
        proxy.$message.error('修改失败');
      });
    }).catch(() => {});
  } else {
    proxy.$prompt('修改笔记标题', '请输入新标题', {
      inputValue: contextTarget.value.label
    }).then(({ value }) => {
      if (!value?.trim()) {
        proxy.$message.error('标题不能为空');
        return;
      }
      updateNote({
        id: contextTarget.value.id,
        title: value.trim(),
        categoryId: contextTarget.value.categoryId,
        filename: value.trim() + '.md',
        markdownContent: contextTarget.value.markdownContent,
        htmlContent: contextTarget.value.htmlContent,
        userId: userId.value
      }).then(res => {
        if (res.code === 200) {
          proxy.$message.success('修改成功');
          loadNotes();
          if (currentnote.noteId === contextTarget.value.id) {
            currentNote.title = value.trim();
          }
        } else {
          proxy.$message.error(res.msg || '修改失败');
        }
      }).catch(() => {
        proxy.$message.error('修改失败');
      });
    }).catch(() => {});
  }
};

const onDeleteItem = () => {
  const menu = contextMenuRef.value;
  menu.style.display = 'none';

  const typeName = contextType.value === 'category' ? '分类' : '笔记';

  if (contextType.value === 'category') {
    const hasNotes = rawNotebooks.value.some(cat =>
      String(cat.id) === String(contextTarget.value.id) && cat.children && cat.children.length > 0
    );
    if (hasNotes) {
      proxy.$message.warning('该分类下存在笔记，无法删除！');
      return;
    }
  }

  proxy.$confirm(`确定要删除该${typeName}吗？`, '提示', {
    type: 'warning'
  }).then(() => {
    if (contextType.value === 'category') {
      delNoteCategory(Number(contextTarget.value.id))
        .then(res => {
          if (res.code === 200) {
            proxy.$message.success('删除成功');
            loadNotes();
          } else {
            proxy.$message.error(res.msg || '删除失败');
          }
        })
        .catch(() => {
          proxy.$message.error('删除失败');
        });
    } else {
      delNote(contextTarget.value.id)
        .then(res => {
          if (res.code === 200) {
            proxy.$message.success('删除成功');
            loadNotes();
            if (currentnote.noteId === contextTarget.value.id) {
              Object.keys(currentNote).forEach(key => {
                currentNote[key] = null;
              });
              currentNote.markdownContent = '';
              currentNote.tags = [];
            }
          } else {
            proxy.$message.error(res.msg || '删除失败');
          }
        })
        .catch(() => {
          proxy.$message.error('删除失败');
        });
    }
  }).catch(() => {});
};

const handleRowClick = (node, data, event) => {
  const isCtrl = event.ctrlKey || event.metaKey;
  const isSelected = selectedNodes.value.some(n => n.id === data.id);

  if (data.isLeaf) {
    handleNoteSelect(data);
  }

  if (isCtrl) {
    toggleSelection(data, !isSelected);
  } else {
    selectedNodes.value = [];
    toggleSelection(data, true);
  }
};

const batchDeleteSelected = () => {
  if (selectedNodes.value.length === 0) return;

  const categoriesToDelete = selectedNodes.value.filter(n => !n.isLeaf);
  const notesToDelete = selectedNodes.value.filter(n => n.isLeaf);

  let hasNonEmptyCategory = false;
  for (const cat of categoriesToDelete) {
    const hasNotes = rawNotebooks.value.some(c =>
      String(c.id) === String(cat.id) && c.children && c.children.length > 0
    );
    if (hasNotes) {
      hasNonEmptyCategory = true;
      break;
    }
  }

  if (hasNonEmptyCategory) {
    proxy.$message.warning('所选分类中包含非空分类，无法删除！');
    return;
  }

  proxy.$confirm(`确定要删除选中的 ${selectedNodes.value.length} 项吗？`, '删除确认', {
    type: 'warning'
  }).then(() => {
    const deletePromises = [];

    notesToDelete.forEach(note => {
      deletePromises.push(delNote(note.noteId));
    });

    categoriesToDelete.forEach(cat => {
      deletePromises.push(delNoteCategory(Number(cat.id)));
    });

    Promise.all(deletePromises)
      .then(results => {
        const failed = results.some(res => res.code !== 200);
        if (failed) {
          proxy.$message.error('部分删除失败');
        } else {
          proxy.$message.success('删除成功');
        }
        loadNotes();
        if (notesToDelete.some(n => n.id === currentnote.noteId)) {
          Object.keys(currentNote).forEach(k => currentNote[k] = null);
          currentNote.markdownContent = '';
          currentNote.tags = [];
        }
        selectedNodes.value = [];
      })
      .catch(() => {
        proxy.$message.error('删除失败');
      });
  }).catch(() => {});
};
</script>

<style scoped>
/* ===== 公式按钮条（2026-10-27）===== */
.note-math-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-bottom: 1px solid #eef0f3;
  background: #fcfdfe;
  flex-wrap: wrap;
}

.note-math-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  font-size: 12px;
  color: #409eff;
  background: #f2f8ff;
  border: 1px solid #cfe3fb;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.12s;
}

.note-math-btn:hover {
  background: #e4f1ff;
  border-color: #409eff;
}

.note-fx {
  font-style: italic;
  font-weight: 600;
}

.note-math-hint {
  font-size: 11px;
  color: #9aa4b2;
}

.notes-manager {
  background-color: #f5f7fa;
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  flex-shrink: 0;
  background: #fff;
  height: 100%;
  box-sizing: border-box;
  position: relative;
  z-index: 1;
}

.main-content {
  flex: 1;
  background: #f5f7fa;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
  position: relative;
}

/* 空状态容器样式 */
.empty-state-container {
  display: flex;
  align-items: center;
  justify-content: center;
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 100%;
  padding: 20px;
  box-sizing: border-box;
}

.empty-state-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  max-width: 800px;
  /* border-radius: 12px; */
  /* box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); */
}

.empty-icon {
  color: #c0c4cc;
  margin-bottom: 20px;
  opacity: 0.8;
}

.empty-title {
  font-size: 26px;
  color: #303133;
  margin: 0 0 8px 0;
  font-weight: 500;
}

.empty-desc {
  font-size: 24px;
  color: #909399;
  margin: 0;
  opacity: 0.8;
  line-height: 1.5;
}

.preview-content {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.sidebar-toggle-btn {
  position: absolute;
  z-index: 1000;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: left 0.3s ease;
}

.sidebar-toggle-btn:hover {
  background: #f0f2f5;
  border-color: #c0c4cc;
}

.sidebar-toggle-btn .el-icon {
  font-size: 12px;
  color: #606266;
  transition: transform 0.3s;
}

.context-menu {
  background: white;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0,0,0,.1);
  min-width: 100px;
}

.menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
}

.menu-item:hover {
  background-color: #f5f7fa;
}

.selected-node {
  background-color: #e6f7ff;
  border-radius: 4px;
  padding: 2px 4px;
}

.tree-node-row:hover {
  background-color: #f0f2f5;
}

.selected-node {
  background-color: #e6f7ff !important;
}

/* 确保md-preview容器宽度正确 */
:deep(.md-editor-preview-wrapper) {
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}

:deep(.md-editor-preview) {
  width: 100% !important;
  max-width: 100% !important;
}

:deep(.md-editor-preview .markdown-body) {
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}
</style>