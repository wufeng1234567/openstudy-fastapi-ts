<template>
  <div v-if="visible" class="at-user-selector" :style="popupStyle" @click.stop>
    <div class="at-search">
      <el-input ref="searchInputRef" v-model="searchKeyword" placeholder="搜索用户..." size="small" clearable
        @input="handleSearch">
        <template #prefix>
          <span class="at-symbol">@</span>
        </template>
      </el-input>
    </div>

    <div v-loading="loading" class="at-user-list">
      <div v-for="(user, index) in filteredUsers" :key="user.userId" class="at-user-item"
        :class="{ 'is-active': index === activeIndex }" @click="selectUser(user)" @mouseenter="activeIndex = index">
        <UserAvatar :src="user.avatar" :name="user.nickName || user.userName" :size="32" class="at-user-avatar" />
        <div class="at-user-info">
          <span class="at-user-name">{{ user.nickName || user.userName }}</span>
          <span class="at-user-account">@{{ user.userName }}</span>
        </div>
      </div>
      <el-empty v-if="!loading && filteredUsers.length === 0" description="暂无匹配用户" :image-size="40" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { listUserFront } from '@/api/system/user'
import useUserStore from '@/store/modules/user'
import UserAvatar from '@/components/UserAvatar/index.vue'

const props = defineProps({
  visible: Boolean,
  inputEl: { type: Object, default: null },
  selectedUserIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['select', 'close'])

const userStore = useUserStore()
const currentUserId = computed(() => userStore.id)

const searchKeyword = ref('')
const activeIndex = ref(0)
const loading = ref(false)
const allUsers = ref([])
const searchInputRef = ref(null)

const popupStyle = computed(() => {
  if (!props.inputEl) return {}
  const rect = props.inputEl.getBoundingClientRect()
  return {
    position: 'fixed',
    left: rect.left + 'px',
    top: (rect.top - 260) + 'px',
    width: Math.max(rect.width, 280) + 'px',
    maxHeight: '240px'
  }
})

const filteredUsers = computed(() => {
  let list = allUsers.value.filter(u => {
    if (u.userId === currentUserId.value) return false
    if (props.selectedUserIds.includes(u.userId)) return false
    return true
  })
  if (searchKeyword.value.trim()) {
    const kw = searchKeyword.value.trim().toLowerCase()
    list = list.filter(u =>
      (u.nickName || u.userName).toLowerCase().includes(kw) ||
      u.userName.toLowerCase().includes(kw)
    )
  }
  return list.slice(0, 50)
})

const fetchUsers = async () => {
  loading.value = true
  try {
    const res = await listUserFront({ pageNum: 1, pageSize: 200 })
    allUsers.value = res.rows || []
  } catch (e) {
    allUsers.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    fetchUsers()
    searchKeyword.value = ''
    activeIndex.value = 0
    nextTick(() => {
      searchInputRef.value?.focus()
    })
  }
})

const handleKeydown = (e) => {
  if (!props.visible) return
  const len = filteredUsers.value.length
  if (len === 0) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % len
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + len) % len
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const user = filteredUsers.value[activeIndex.value]
    if (user) selectUser(user)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

const selectUser = (user) => {
  emit('select', user)
  searchKeyword.value = ''
  activeIndex.value = 0
}

const handleSearch = () => {
  activeIndex.value = 0
}

defineExpose({ handleKeydown })
</script>

<style scoped lang="scss">
.at-user-selector {
  z-index: 2100;
  background: rgba(255, 255, 255, 0.97);
  backdrop-filter: blur(8px);
  border: 1px solid #e8eaed;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: popIn 0.25s cubic-bezier(0.4, 0, 0.2, 1);

  .at-search {
    padding: 8px 10px;
    border-bottom: 1px solid #f3f4f6;

    .at-symbol {
      font-size: 15px;
      font-weight: 600;
      color: #9ca3af;
      transition: color 0.2s;
    }

    &:focus-within .at-symbol {
      color: #409eff;
    }

    :deep(.el-input__wrapper) {
      border-radius: 8px;
      box-shadow: none;
      border: 1px solid #e5e7eb;
      background: #f9fafb;
      padding: 2px 8px;

      &:hover,
      &.is-focus {
        border-color: #d1d5db;
        box-shadow: none;
      }
    }

    :deep(.el-input__inner) {
      font-size: 13px;
      color: #1f2937;
    }
  }

  .at-user-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px 8px;
    max-height: 200px;

    &::-webkit-scrollbar {
      width: 4px;
    }

    &::-webkit-scrollbar-thumb {
      background: #e5e7eb;
      border-radius: 2px;

      &:hover {
        background: #d1d5db;
      }
    }

    .at-user-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      position: relative;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      user-select: none;

      &:hover {
        background: #f5f7fa;
        transform: scale(1.01);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      }

      &.is-active {
        background: #f0f4ff;
        transform: scale(1.01);
        box-shadow: 0 2px 8px rgba(64, 158, 255, 0.06);

        .at-user-name {
          color: #1f2937;
        }

        &::before {
          content: '';
          position: absolute;
          left: 0;
          top: 8px;
          bottom: 8px;
          width: 3px;
          background: #409eff;
          border-radius: 0 2px 2px 0;
        }
      }

      .at-user-avatar {
        flex-shrink: 0;
        border-color: #f3f4f6;
        transition: border-color 0.2s, transform 0.2s;
      }

      &:hover .at-user-avatar {
        border-color: #d0ddf6;
      }

      &.is-active .at-user-avatar {
        border-color: #409eff;
        transform: scale(1.05);
      }

      .at-user-info {
        display: flex;
        flex-direction: column;
        gap: 2px;
        min-width: 0;

        .at-user-name {
          font-size: 14px;
          font-weight: 500;
          color: #1f2937;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          transition: color 0.2s;
        }

        &:hover .at-user-name {
          color: #1a1a1a;
        }

        .at-user-account {
          font-size: 12px;
          color: #9ca3af;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          transition: color 0.2s;
        }
      }

      &.is-active .at-user-account {
        color: #7ba9e0;
      }
    }
  }
}

@keyframes popIn {
  0% {
    opacity: 0;
    transform: translateY(6px);
  }

  100% {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
