<template>
  <div class="comment-input">
    <div v-if="replyTarget" class="reply-tag">
      <span>回复 @{{ replyTarget.userName || replyTarget.name }}</span>
      <el-icon class="cancel-reply" @click="$emit('cancelReply')">
        <Close />
      </el-icon>
    </div>
    <AtUserSelector ref="atSelectorRef" :visible="showAtSelector" :input-el="textareaEl" :selected-user-ids="mentionedUserIds"
      @select="handleAtSelect" @close="showAtSelector = false" />
    <el-input ref="textareaRef" v-model="content" type="textarea" :rows="3" :placeholder="placeholder"
      class="comment-textarea" @keydown="handleKeydown" @keydown.ctrl.enter="handleSubmit" @input="handleInput" />
    <div class="input-footer">
      <span class="input-hint">Ctrl + Enter 发送</span>
      <el-button class="submit-btn" size="small" @click="handleSubmit">
        {{ submitText }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import AtUserSelector from './AtUserSelector.vue'
import { isNameChar } from './mention'

const props = defineProps({
  replyTarget: {
    type: Object,
    default: null
  },
  placeholder: {
    type: String,
    default: '写下你的评论...'
  },
  submitText: {
    type: String,
    default: '发表'
  }
})

const emit = defineEmits(['submit', 'cancelReply'])

const content = ref('')
const showAtSelector = ref(false)
/**
 * 已经 @ 到的人。输入框里**只显示 `@昵称`**，用户 id 藏在这里，
 * 提交时（handleSubmit → toWireContent）才还原成线上的 `@{106} 演示用户2`。
 * 这样用户看不到 `{106}` 这种实现细节，而 CommentItem / 后端解析的格式一点没变。
 */
const mentionedUsers = ref([])
const mentionedUserIds = computed(() => mentionedUsers.value.map(u => u.id))
const textareaRef = ref(null)
const atSelectorRef = ref(null)
const cursorBeforeAt = ref(-1)

const textareaEl = computed(() => {
  return textareaRef.value?.$el?.querySelector('textarea') || null
})

const handleKeydown = (e) => {
  if (!showAtSelector.value && (e.key === '@' || e.key === '＠')) {
    e.preventDefault()
    const textarea = textareaEl.value
    if (textarea) {
      cursorBeforeAt.value = textarea.selectionStart
      showAtSelector.value = true
    }
    return
  }

  if (showAtSelector.value && ['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(e.key)) {
    e.preventDefault()
    atSelectorRef.value?.handleKeydown(e)
  }
}

const handleInput = () => {
  if (showAtSelector.value) return
  const textarea = textareaEl.value
  if (!textarea) return
  const cursorPos = textarea.selectionStart
  const current = content.value
  if (cursorPos > 0) {
    const charBefore = current.charAt(cursorPos - 1)
    if (charBefore === '@' || charBefore === '＠') {
      cursorBeforeAt.value = cursorPos - 1
      showAtSelector.value = true
    }
  }
}

const handleAtSelect = (user) => {
  const name = user.nickName || user.userName
  const userId = user.userId
  // ⚠️ 输入框里只放 `@昵称`（不露 id），id 记进 mentionedUsers，
  //    提交时再还原成线上的 `@{userId} 昵称` —— 见 toWireContent。
  //    格式契约没变：CommentItem 靠 `@{id}` 才能把 data-userid 写进 DOM，
  //    后端也靠 `re.findall(r"@\{(\d+)\}")` 才知道要通知谁。
  const atText = `@${name} `

  if (!mentionedUsers.value.some(u => String(u.id) === String(userId))) {
    mentionedUsers.value.push({ id: userId, name })
  }

  const textarea = textareaEl.value
  if (textarea) {
    const start = cursorBeforeAt.value >= 0 ? cursorBeforeAt.value : textarea.selectionStart
    const before = content.value.substring(0, start)
    const after = content.value.substring(textarea.selectionEnd)
    content.value = before + atText + after

    setTimeout(() => {
      const newPos = start + atText.length
      textarea.setSelectionRange(newPos, newPos)
      textarea.focus()
    }, 0)
  }

  showAtSelector.value = false
}

/**
 * 把输入框里给人看的 `@昵称` 还原成线上格式 `@{id} 昵称`。
 *
 * ⚠️ 匹配不到就**放它过去**（退回成裸 `@昵称`）：用户可能事后把昵称改掉了，
 *    这时不该硬塞一个 id 进去（那会通知错人 / 通知到已经不叫这个名字的人）。
 * ⚠️ 命中后要确认后面不再跟昵称字符，否则 `@张三` 会吃掉 `@张三丰` 的前缀。
 */
const toWireContent = (display) => {
  let out = display
  for (const { id, name } of mentionedUsers.value) {
    if (!name) continue
    const token = `@${name}`
    let from = 0
    while (true) {
      const idx = out.indexOf(token, from)
      if (idx === -1) break
      const nextChar = out.charAt(idx + token.length)
      if (nextChar && isNameChar(nextChar)) {
        from = idx + token.length
        continue
      }
      out = out.slice(0, idx) + `@{${id}} ${name}` + out.slice(idx + token.length)
      break
    }
  }
  return out
}

const handleDocumentClick = (e) => {
  if (!showAtSelector.value) return
  const wrapper = textareaRef.value?.$el?.closest('.comment-input')
  if (wrapper && !wrapper.contains(e.target)) {
    showAtSelector.value = false
  }
}

watch(() => showAtSelector.value, (val) => {
  if (val) {
    setTimeout(() => document.addEventListener('click', handleDocumentClick), 0)
  } else {
    document.removeEventListener('click', handleDocumentClick)
  }
})

const handleSubmit = () => {
  const text = content.value.trim()
  if (!text) {
    ElMessage.warning('请输入评论内容')
    return
  }
  // 字数按**用户看到的**文本算（输入框里没有 id，所以别拿序列化后的串去算）
  if (text.length > 500) {
    ElMessage.warning('评论内容不能超过500字')
    return
  }

  emit('submit', toWireContent(text))
  content.value = ''
  mentionedUsers.value = []
}

defineExpose({
  clear: () => {
    content.value = ''
    mentionedUsers.value = []
  }
})
</script>

<style scoped lang="scss">
.comment-input {
  background: #fff;
  padding: 12px;
  border-top: 1px solid #e5e7eb;
  position: relative;

  .reply-tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: #f3f4f6;
    border-radius: 4px;
    font-size: 13px;
    color: #6b7280;
    margin-bottom: 8px;

    .cancel-reply {
      cursor: pointer;
      font-size: 14px;
      color: #9ca3af;
      transition: color 0.2s;

      &:hover {
        color: #f56c6c;
      }
    }
  }

  .comment-textarea {
    :deep(.el-textarea__inner) {
      border-radius: 8px;
      border: 1px solid #e5e7eb;
      box-shadow: none;
      font-size: 14px;
      line-height: 1.6;
      transition: border-color 0.3s;

      &:hover {
        border-color: #d1d5db;
      }

      &:focus {
        border-color: #409eff;
      }
    }
  }

  .input-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 8px;

    .input-hint {
      font-size: 12px;
      color: #9ca3af;
    }

    .submit-btn {
      background: #fff;
      border: 1px solid #e5e7eb;
      color: #6b7280;
      border-radius: 8px;
      font-weight: 500;
      padding: 5px 16px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #409eff;
        color: #409eff;
        transform: translateY(-2px);
      }

      &:active {
        transform: translateY(0);
      }
    }
  }
}
</style>
