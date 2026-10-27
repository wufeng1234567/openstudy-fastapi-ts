<template>
  <div class="tiptap-editor" :class="{ 'is-disabled': disabled }">
    <div class="editor-toolbar" v-if="!hideToolbar">
      <div class="toolbar-group">
        <button type="button" @click="editor.chain().focus().undo().run()"
          :disabled="!editor?.can().chain().undo().run()" class="toolbar-btn" title="撤销">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().redo().run()"
          :disabled="!editor?.can().chain().redo().run()" class="toolbar-btn" title="重做">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M11.5 8c-4.65 0-8.58 3.03-9.97 7.22l2.37.78C5.45 12.31 8.46 10 12 10c1.96 0 3.73.72 5.12 1.88L13.5 15.5h9v-9l-3.62 3.62C17.55 8.99 15.15 8 12.5 8z" />
          </svg>
        </button>
      </div>
      <span class="toolbar-divider"></span>
      <div class="toolbar-group">
        <button type="button" @click="editor.chain().focus().toggleBold().run()"
          :class="{ 'is-active': editor?.isActive('bold') }" class="toolbar-btn" title="加粗"><strong>B</strong></button>
        <button type="button" @click="editor.chain().focus().toggleItalic().run()"
          :class="{ 'is-active': editor?.isActive('italic') }" class="toolbar-btn" title="斜体"><em>I</em></button>
        <button type="button" @click="editor.chain().focus().toggleUnderline().run()"
          :class="{ 'is-active': editor?.isActive('underline') }" class="toolbar-btn" title="下划线"><u>U</u></button>
        <button type="button" @click="editor.chain().focus().toggleStrike().run()"
          :class="{ 'is-active': editor?.isActive('strike') }" class="toolbar-btn" title="删除线"><s>S</s></button>
      </div>
      <span class="toolbar-divider"></span>
      <div class="toolbar-group">
        <button type="button" @click="editor.chain().focus().toggleHeading({ level: 1 }).run()"
          :class="{ 'is-active': editor?.isActive('heading', { level: 1 }) }" class="toolbar-btn"
          title="标题 1">H1</button>
        <button type="button" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()"
          :class="{ 'is-active': editor?.isActive('heading', { level: 2 }) }" class="toolbar-btn"
          title="标题 2">H2</button>
        <button type="button" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()"
          :class="{ 'is-active': editor?.isActive('heading', { level: 3 }) }" class="toolbar-btn"
          title="标题 3">H3</button>
      </div>
      <span class="toolbar-divider"></span>
      <div class="toolbar-group">
        <button type="button" @click="editor.chain().focus().toggleBulletList().run()"
          :class="{ 'is-active': editor?.isActive('bulletList') }" class="toolbar-btn" title="无序列表">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M4 10.5c-.83 0-1.5.67-1.5 1.5s.67 1.5 1.5 1.5 1.5-.67 1.5-1.5-.67-1.5-1.5-1.5zm0-6c-.83 0-1.5.67-1.5 1.5S3.17 7.5 4 7.5 5.5 6.83 5.5 6 4.83 4.5 4 4.5zm0 12c-.83 0-1.5.68-1.5 1.5s.68 1.5 1.5 1.5 1.5-.68 1.5-1.5-.67-1.5-1.5-1.5zM7 19h14v-2H7v2zm0-6h14v-2H7v2zm0-8v2h14V5H7z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().toggleOrderedList().run()"
          :class="{ 'is-active': editor?.isActive('orderedList') }" class="toolbar-btn" title="有序列表">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M2 17h2v.5H3v1h1v.5H2v1h3v-4H2v1zm1-9h1V4H2v1h1v3zm-1 3h1.8L2 13.1v.9h3v-1H3.2L5 10.9V10H2v1zm5-6v2h14V5H7zm0 14h14v-2H7v2zm0-6h14v-2H7v2z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().toggleTaskList().run()"
          :class="{ 'is-active': editor?.isActive('taskList') }" class="toolbar-btn" title="任务列表">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14zM17.99 9l-1.41-1.42-6.59 6.59-2.58-2.57-1.42 1.41 4 3.99z" />
          </svg>
        </button>
      </div>
      <span class="toolbar-divider"></span>
      <div class="toolbar-group">
        <button type="button" @click="setLink" :class="{ 'is-active': editor?.isActive('link') }" class="toolbar-btn"
          title="链接">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z" />
          </svg>
        </button>
        <button type="button" v-if="!disabledImage" @click="handleImageBtnClick" class="toolbar-btn" title="图片">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" />
          </svg>
        </button>
        <button type="button" @click="insertTable" class="toolbar-btn" title="表格">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M20 3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 2v3H4V5h16zm0 5v4H4v-4h16zM4 19v-4h16v4H4z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().toggleCodeBlock().run()"
          :class="{ 'is-active': editor?.isActive('codeBlock') }" class="toolbar-btn" title="代码块">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().toggleBlockquote().run()"
          :class="{ 'is-active': editor?.isActive('blockquote') }" class="toolbar-btn" title="引用">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor" d="M6 17h3l2-4V7H5v6h3zm8 0h3l2-4V7h-6v6h3z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().setHorizontalRule().run()" class="toolbar-btn" title="分割线">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor" d="M3 17h18v-2H3v2zm0-3h18v-1H3v1zm0-5h18V7H3v2z" />
          </svg>
        </button>
      </div>
      <span class="toolbar-divider"></span>
      <div class="toolbar-group">
        <button type="button" @click="editor.chain().focus().setTextAlign('left').run()"
          :class="{ 'is-active': editor?.isActive({ textAlign: 'left' }) }" class="toolbar-btn" title="左对齐">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M15 15H3v2h12v-2zm0-8H3v2h12V7zM3 13h18v-2H3v2zm0 8h18v-2H3v2zM3 3v2h18V3H3z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().setTextAlign('center').run()"
          :class="{ 'is-active': editor?.isActive({ textAlign: 'center' }) }" class="toolbar-btn" title="居中">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor" d="M7 15v2h10v-2H7zm-4 6h18v-2H3v2zm0-8h18v-2H3v2zm4-6v2h10V7H7zM3 3v2h18V3H3z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().setTextAlign('right').run()"
          :class="{ 'is-active': editor?.isActive({ textAlign: 'right' }) }" class="toolbar-btn" title="右对齐">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor" d="M3 21h18v-2H3v2zm6-4h12v-2H9v2zm-6-4h18v-2H3v2zm6-4h12V7H9v2zM3 3v2h18V3H3z" />
          </svg>
        </button>
        <button type="button" @click="editor.chain().focus().setTextAlign('justify').run()"
          :class="{ 'is-active': editor?.isActive({ textAlign: 'justify' }) }" class="toolbar-btn" title="两端对齐">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor" d="M3 21h18v-2H3v2zm0-4h18v-2H3v2zm0-4h18v-2H3v2zm0-4h18V7H3v2zm0-6v2h18V3H3z" />
          </svg>
        </button>
      </div>
      <span class="toolbar-divider"></span>
      <div class="toolbar-group">
        <button type="button" @click="editor.chain().focus().toggleHighlight().run()"
          :class="{ 'is-active': editor?.isActive('highlight') }" class="toolbar-btn" title="高亮">
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path fill="currentColor"
              d="M6 20l3.42-3.42c-.84-.58-1.59-1.3-2.19-2.12L6 20zm13.94-13.06c.39-.39.39-1.02 0-1.41l-2.47-2.47c-.39-.39-1.02-.39-1.41 0L8 11.97c-.32.32-.53.71-.65 1.13l-.87 3.49 3.49-.87c.42-.11.82-.33 1.13-.64l9.84-10.18z" />
          </svg>
        </button>
      </div>
    </div>
    <editor-content :editor="editor" class="editor-content" @click="handleEditorClick" />
    <input type="file" ref="fileInputRef" accept="image/*" style="display:none" @change="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import TextAlign from '@tiptap/extension-text-align'
import { TextStyle } from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import { Table } from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import { all, createLowlight } from 'lowlight'
import { ref, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { ElMessageBox } from 'element-plus'
import { uploadImage } from '@/api/common/common'
import { marked } from 'marked'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '开始写下你的笔记...'
  },
  hideToolbar: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  readonly: {
    type: Boolean,
    default: false
  },
  disabledImage: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'imageUpload', 'preview-image'])

const fileInputRef = ref(null)

const handleEditorClick = (e) => {
  const img = e.target.closest('img')
  if (img && img.src) {
    e.preventDefault()
    e.stopPropagation()
    emit('preview-image', img.src)
  }
}

const lowlight = createLowlight(all)

const languageAliases = {
  'js': 'javascript', 'JS': 'javascript', 'javascript': 'javascript', 'es6': 'javascript',
  'py': 'python', 'PY': 'python', 'python': 'python', 'python3': 'python',
  'java': 'java', 'JAVA': 'java',
  'cpp': 'cpp', 'CPP': 'cpp', 'c++': 'cpp', 'C++': 'cpp', 'c': 'cpp',
  'html': 'html', 'HTML': 'html', 'xml': 'html',
  'css': 'css', 'CSS': 'css', 'scss': 'css', 'sass': 'css',
  'bash': 'bash', 'sh': 'bash', 'shell': 'bash', 'zsh': 'bash',
  'json': 'json', 'JSON': 'json',
  'sql': 'sql', 'SQL': 'sql',
  'go': 'go', 'golang': 'go',
  'rust': 'rust', 'RS': 'rust',
  'ruby': 'ruby', 'rb': 'ruby', 'Ruby': 'ruby',
  'php': 'php', 'PHP': 'php',
  'swift': 'swift', 'Swift': 'swift',
  'kotlin': 'kotlin', 'kt': 'kotlin',
  'typescript': 'typescript', 'ts': 'typescript', 'TS': 'typescript',
  'text': 'text', 'plain': 'text', 'txt': 'text'
}

function detectLanguage(content) {
  if (!content || content.trim().length === 0) return 'text'

  const code = content.trim()

  if (/<!DOCTYPE|<html|<div|<span|<p>|<head>|<body>/i.test(code)) return 'html'
  if (/\{[^}]*:\s*[^;]+;?\s*\}/.test(code) && (code.includes('color:') || code.includes('margin:') || code.includes('padding:') || code.includes('background:'))) return 'css'

  if (/^\s*(import|from)\s+\w+/.test(code) && /def\s+\w+\s*\(/i.test(code)) return 'python'
  if (/^\s*import\s+[\w.]+;?\s*$/.test(code) && /print\s*\(/.test(code)) return 'python'
  if (/print\s*\(/.test(code) && !/console\.log/.test(code)) return 'python'

  if (/^#include\s*</.test(code)) return 'cpp'
  if (/std::/.test(code)) return 'cpp'
  if (/cout\s*<</.test(code) || /cin\s*>>/.test(code)) return 'cpp'
  if (/printf\s*\(/.test(code) && !/System\.out/.test(code)) return 'cpp'

  if (/public\s+(static\s+)?(void|class|interface)/.test(code)) return 'java'
  if (/System\.out\.print/.test(code)) return 'java'
  if (/class\s+\w+\s*(extends|implements)/.test(code)) return 'java'

  if (/func\s+\w+\s*\(/.test(code) && /\)\s*(->|:)/.test(code)) return 'swift'
  if (/import\s+Foundation|import\s+UIKit/.test(code)) return 'swift'

  if (/fun\s+\w+\s*\(/.test(code)) return 'kotlin'
  if (/package\s+\w+/.test(code) && /fun\s+main/.test(code)) return 'kotlin'

  if (/fn\s+\w+\s*\(/.test(code)) return 'rust'
  if (/let\s+mut\s+/.test(code)) return 'rust'
  if (/use\s+std::/.test(code)) return 'rust'

  if (/func\s+\w+\s*\(/.test(code)) return 'go'
  if (/package\s+main/.test(code)) return 'go'
  if (/fmt\.Print/.test(code)) return 'go'

  if (/function\s+\w+/.test(code)) return 'javascript'
  if (/const\s+\w+\s*=/.test(code)) return 'javascript'
  if (/let\s+\w+\s*=/.test(code)) return 'javascript'
  if (/=>\s*[\{\(]/.test(code)) return 'javascript'
  if (/console\.log/.test(code)) return 'javascript'
  if (/document\.|window\./.test(code)) return 'javascript'
  if (/async\s+function|await\s+/.test(code)) return 'javascript'
  if (/require\s*\(/.test(code)) return 'javascript'
  if (/module\.exports/.test(code)) return 'javascript'

  if (/SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+.+\s+SET|DELETE\s+FROM/i.test(code)) return 'sql'

  if (/^\s*\{[\s\S]*"[\w]+"\s*:/.test(code) && /[\s\S]*\}/.test(code) && !/function/.test(code)) return 'json'

  return 'text'
}

function normalizeLanguage(lang) {
  if (!lang) return 'text'
  const normalized = lang.toLowerCase().trim()
  return languageAliases[normalized] || normalized || 'text'
}

const CustomCodeBlockLowlight = CodeBlockLowlight.extend({
  addNodeView() {
    return ({ node, HTMLAttributes, children, getPos, editor }) => {
      const language = node.attrs.language || 'text'
      const dom = document.createElement('div')
      dom.className = 'code-block-wrapper'

      const pre = document.createElement('pre')
      pre.className = `language-${language}`

      const code = document.createElement('code')
      code.className = `language-${language}`

      const badge = document.createElement('span')
      badge.className = 'code-language-badge'
      badge.textContent = language
      badge.style.cursor = 'pointer'

      let isEditing = false

      const startEdit = () => {
        if (isEditing) return
        isEditing = true
        const currentLang = badge.textContent

        ElMessageBox.prompt('请输入代码语言', '切换语言', {
          inputValue: currentLang,
          confirmButtonText: '确定',
          cancelButtonText: '取消'
        }).then(({ value }) => {
          if (value && value.trim()) {
            const normalized = normalizeLanguage(value.trim())
            if (typeof getPos === 'function') {
              const pos = getPos()
              if (pos !== false && pos !== undefined) {
                editor.chain().focus().command(({ tr }) => {
                  tr.setNodeMarkup(pos, undefined, { language: normalized })
                  return true
                }).run()
              }
            }
          }
          isEditing = false
        }).catch(() => {
          isEditing = false
        })
      }

      badge.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        startEdit()
      })

      const copyBtn = document.createElement('button')
      copyBtn.className = 'code-copy-btn'
      copyBtn.innerHTML = '📋'
      copyBtn.title = '复制代码'

      copyBtn.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        const codeText = node.textContent
        navigator.clipboard.writeText(codeText).then(() => {
          ElMessage.success('复制成功')
        }).catch(() => {
          ElMessage.error('复制失败')
        })
      })

      code.style.cursor = 'pointer'
      code.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        const codeText = node.textContent
        navigator.clipboard.writeText(codeText).then(() => {
          ElMessage.success('复制成功')
        }).catch(() => {
          ElMessage.error('复制失败')
        })
      })

      pre.appendChild(code)
      dom.appendChild(pre)
      dom.appendChild(badge)
      dom.appendChild(copyBtn)

      return {
        dom,
        contentDOM: code,
        update: (updatedNode) => {
          if (updatedNode.type !== this.type) {
            return false
          }
          const newLanguage = updatedNode.attrs.language || 'text'
          badge.textContent = newLanguage
          pre.className = `language-${newLanguage}`
          code.className = `language-${newLanguage}`
          return true
        }
      }
    }
  }
})

const editor = useEditor({
  content: props.modelValue,
  editable: !props.disabled,
  extensions: [
    StarterKit.configure({
      history: {
        depth: 100
      },
      codeBlock: false,
      table: false
    }),
    Underline,
    Link.configure({
      openOnClick: true,
      autolink: true,
      HTMLAttributes: {
        rel: 'noopener noreferrer',
        target: '_blank'
      }
    }),
    Image.configure({
      inline: false,
      allowBase64: false,
      HTMLAttributes: {
        class: 'tiptap-image'
      }
    }),
    Placeholder.configure({
      placeholder: props.placeholder
    }),
    TextAlign.configure({
      types: ['heading', 'paragraph']
    }),
    TextStyle,
    Color,
    Highlight.configure({
      multicolor: true
    }),
    Table.configure({
      resizable: true,
      allowTableNodeSelection: true
    }),
    TableRow,
    TableCell,
    TableHeader,
    TaskList,
    TaskItem.configure({
      nested: true
    }),
    CustomCodeBlockLowlight.configure({
      lowlight,
      defaultLanguage: 'text'
    })
  ],
  editorProps: {
    handlePaste: (view, event, slice) => {
      const text = event.clipboardData?.getData('text/plain')
      if (text) {
        // 检测是否是代码块：以 ``` 开头或者包含 ``` 标记
        const lines = text.split('\n')
        // 检测模式1：以 ``` 开头（标准 Markdown 代码块）
        if (lines.length > 1 && lines[0].startsWith('```')) {
          try {
            event.preventDefault()

            // 提取语言和代码内容
            const firstLine = lines[0].trim()
            // 提取语言：去掉开头的 ```，剩下的就是语言
            let language = firstLine.replace(/```/g, '').trim() || 'text'
            // 如果语言为空，使用 detectLanguage 自动检测
            const content = lines.slice(1, lines.length - 1).join('\n')

            // 如果语言为空，尝试从内容中检测
            if (!language || language === '') {
              language = detectLanguage(content) || 'text'
            }

            // 使用 Tiptap 的 API 直接创建代码块节点
            const { schema } = view.state
            const codeBlockType = schema.nodes.codeBlock
            const textNode = schema.text(content)
            const node = codeBlockType.create({ language }, textNode)

            // 替换当前选区
            view.dispatch(view.state.tr.replaceSelectionWith(node))
            return true
          } catch (e) {
            console.error('Code block paste error (pattern 1):', e)
            return false
          }
        }

        // 检测模式2：文本中有 ``` 标记（非标准 Markdown，但可能包含代码块）
        if (/```/.test(text)) {
          try {
            event.preventDefault()
            // 尝试使用 marked 解析，并设置 parseOptions 为 true
            const html = marked.parse(text)
            editor.value.commands.setContent(html, {
              parseOptions: {
                preserveWhitespace: true
              }
            })
            return true
          } catch (e) {
            console.error('Markdown paste error (pattern 2):', e)
            return false
          }
        }
      }
      return false
    },
    handleKeyDown: (view, event) => {
      if (event.key === 'Tab') {
        const { state } = view
        const { selection } = state
        const { $anchor } = selection
        const pos = view.state.doc.resolve($anchor.pos)

        let inCodeBlock = false
        for (let d = pos.depth; d > 0; d--) {
          const node = pos.node(d)
          if (node.type.name === 'codeBlock') {
            inCodeBlock = true
            break
          }
        }

        if (inCodeBlock) {
          event.preventDefault()
          const { tr } = state
          const from = selection.from
          const to = selection.to
          tr.insertText('\t', from, to)
          view.dispatch(tr)
          return true
        }
      }
      return false
    }
  },
  onTransaction: ({ editor, transaction }) => {
    if (transaction.docChanged && editor.isActive('codeBlock')) {
      const { state } = editor
      let shouldUpdate = false
      state.doc.descendants((node, pos) => {
        if (node.type.name === 'codeBlock') {
          const currentLang = node.attrs.language || 'text'
          const content = node.textContent
          if (currentLang === 'text' && content && content.trim().length > 5) {
            const detected = detectLanguage(content)
            if (detected !== 'text') {
              const { tr } = state
              tr.setNodeMarkup(pos, undefined, { language: detected })
              editor.view.dispatch(tr)
              shouldUpdate = true
            }
          }
        }
      })
    }
  },
  onUpdate: ({ editor }) => {
    emit('update:modelValue', editor.getHTML())
  }
})

watch(() => props.modelValue, (newVal) => {
  if (editor.value && newVal !== editor.value.getHTML()) {
    editor.value.commands.setContent(newVal || '', false)
  }
})

watch(() => props.disabled, (newVal) => {
  if (editor.value) {
    editor.value.setEditable(!newVal)
  }
})

const setLink = () => {
  const previousUrl = editor.value.getAttributes('link').href
  const url = window.prompt('请输入链接地址', previousUrl || 'https://')
  if (url === null) return
  if (url === '') {
    editor.value.chain().focus().extendMarkRange('link').unsetLink().run()
    return
  }
  editor.value.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
}

const handleImageBtnClick = () => {
  fileInputRef.value?.click()
}

const handleFileSelected = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']
  if (!allowedTypes.includes(file.type)) {
    ElMessage.warning('仅支持 PNG、JPG、GIF、WebP 格式的图片')
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 5MB')
    return
  }

  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await uploadImage(formData)
    if (res.code === 200 && res.url) {
      let url = res.url
      const baseUrl = import.meta.env.VITE_APP_BASE_API || ''
      if (!url.startsWith('http')) {
        url = baseUrl + url
      }
      editor.value.chain().focus().setImage({ src: url.replace(/ /g, '%20') }).run()
      ElMessage.success('图片插入成功')
    } else {
      ElMessage.error('图片上传失败')
    }
  } catch (error) {
    ElMessage.error('图片上传失败')
    console.error('图片上传失败:', error)
  }

  event.target.value = ''
}

const insertTable = () => {
  editor.value.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
}

onBeforeUnmount(() => {
  editor.value?.destroy()
})

defineExpose({
  setContent: (html) => {
    if (editor.value) {
      editor.value.commands.setContent(html || '', false)
    }
  },
  getHTML: () => {
    return editor.value?.getHTML() || ''
  },
  /**
   * 在光标处插入一段纯文本（2026-10-27）
   *
   * 用途：公式面板确定后，把 `$\frac{a}{b}$` 插到用户正在编辑的位置。
   *
   * ⚠️ 没有光标焦点时（用户先点了面板按钮，编辑区失焦），
   *    `insertContent` 会插到文档末尾 —— 这是可接受的降级：
   *    至少内容进去了，用户自己剪贴调整即可，比"插入失败"好。
   */
  insertText: (text) => {
    if (!text) return
    editor.value?.chain().focus().insertContent(text).run()
  }
})
</script>

<style lang="scss">
@import '@/assets/styles/code-highlight.scss';

.tiptap-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;

  &.is-disabled {
    .editor-toolbar {
      display: none;
    }
  }

  .editor-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 2px;
    padding: 6px 8px;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    user-select: none;

    .toolbar-group {
      display: flex;
      align-items: center;
      gap: 1px;
    }

    .toolbar-divider {
      display: inline-block;
      width: 1px;
      height: 24px;
      background: #e5e7eb;
      margin: 0 4px;
      flex-shrink: 0;
    }

    .toolbar-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      padding: 0;
      border: none;
      border-radius: 6px;
      background: transparent;
      color: #6b7280;
      font-size: 13px;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        background: #e5e7eb;
        color: #1f2937;
      }

      &.is-active {
        background: #e5e7eb;
        color: #1f2937;
      }

      &:disabled {
        opacity: 0.3;
        cursor: not-allowed;

        &:hover {
          background: transparent;
          color: #6b7280;
        }
      }

      strong,
      em,
      u,
      s {
        font-size: 14px;
        font-weight: 700;
      }

      em {
        font-style: italic;
      }

      u {
        text-decoration: underline;
      }

      s {
        text-decoration: line-through;
      }

      svg {
        width: 18px;
        height: 18px;
      }
    }
  }

  .editor-content {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
    line-height: 1.7;
    font-size: 16px;
    color: #1f2937;

    .ProseMirror {
      outline: none;
      min-height: 100%;
      word-wrap: break-word;

      p {
        margin: 0 0 8px;
      }

      p.is-editor-empty:first-child::before {
        color: #9ca3af;
        content: attr(data-placeholder);
        float: left;
        height: 0;
        pointer-events: none;
      }

      h1,
      h2,
      h3,
      h4,
      h5,
      h6 {
        margin: 1.2em 0 0.6em;
        color: #1f2937;
        font-weight: 700;
        line-height: 1.3;
      }

      h1 {
        font-size: 2em;
      }

      h2 {
        font-size: 1.5em;
      }

      h3 {
        font-size: 1.25em;
      }

      ul,
      ol {
        padding-left: 1.5em;
        margin: 0.5em 0;

        li {
          margin-bottom: 4px;
        }
      }

      ul[data-type="taskList"] {
        list-style: none;
        padding-left: 0;

        li {
          display: flex;
          align-items: flex-start;
          gap: 8px;

          label {
            flex-shrink: 0;
            margin-top: 3px;

            input[type="checkbox"] {
              cursor: pointer;
              width: 16px;
              height: 16px;
              accent-color: #6b7280;
            }
          }

          div {
            flex: 1;
          }
        }
      }

      blockquote {
        margin: 0.8em 0;
        padding: 8px 16px;
        border-left: 4px solid #d1d5db;
        color: #6b7280;
        background: #f9fafb;
        border-radius: 0 8px 8px 0;
      }

      pre {
        background: #1f2937;
        color: #e5e7eb;
        padding: 16px;
        border-radius: 8px;
        margin: 0.8em 0;
        overflow-x: auto;
        font-size: 14px;
        line-height: 1.5;
        position: relative;

        code {
          color: inherit;
          background: none;
          padding: 0;
          font-size: inherit;
        }
      }

      .code-block-wrapper {
        position: relative;
        margin: 0.8em 0;

        &:hover .code-language-badge {
          opacity: 1;
        }
      }

      .code-language-badge {
        position: absolute;
        bottom: 8px;
        right: 12px;
        font-size: 11px;
        color: #9ca3af;
        background: rgba(0, 0, 0, 0.3);
        padding: 2px 8px;
        border-radius: 4px;
        opacity: 0.7;
        transition: opacity 0.2s ease;
        text-transform: lowercase;
      }

      .code-copy-btn {
        position: absolute;
        top: 8px;
        right: 8px;
        opacity: 0;
        transition: opacity 0.2s ease;
        background: rgba(255, 255, 255, 0.1);
        border: none;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 14px;
        color: #fff;
      }

      .code-block-wrapper:hover .code-copy-btn {
        opacity: 1;
      }

      code {
        background: #f3f4f6;
        color: #b45353;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.9em;
      }

      a {
        color: #6b7280;
        text-decoration: underline;
        cursor: pointer;

        &:hover {
          color: #1f2937;
        }
      }

      img {
        max-width: 100%;
        height: auto;
        border-radius: 8px;
        margin: 0.8em 0;
        border: 1px solid #f3f4f6;
        cursor: pointer;
        transition: opacity 0.2s;

        &:hover {
          opacity: 0.85;
        }
      }

      hr {
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 1.5em 0;
      }

      table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.8em 0;
        overflow: hidden;
        border-radius: 8px;

        th,
        td {
          border: 1px solid #e5e7eb;
          padding: 10px 14px;
          text-align: left;
          min-width: 80px;
        }

        th {
          background: #f9fafb;
          font-weight: 600;
          color: #1f2937;
        }

        td {
          color: #6b7280;
        }

        .selectedCell {
          background: #f3f4f6;
        }
      }

      mark {
        background: #fef3c7;
        padding: 1px 3px;
        border-radius: 2px;
      }

      p[style*="text-align"] {
        margin: 0 0 8px;
      }
    }
  }
}
</style>
