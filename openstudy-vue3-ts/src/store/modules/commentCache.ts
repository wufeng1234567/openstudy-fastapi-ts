import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useCommentCacheStore = defineStore('commentCache', () => {
  const currentPage = ref<number>(1)
  const expandedThreads = ref<Set<number | string>>(new Set())
  const replyTarget = ref<any>(null)
  const currentNoteId = ref<number | string | null>(null)

  const setNoteId = (noteId: number | string) => {
    if (currentNoteId.value !== noteId) {
      currentNoteId.value = noteId
      currentPage.value = 1
      expandedThreads.value = new Set()
      replyTarget.value = null
    }
  }

  const toggleThread = (commentId: number | string) => {
    const set = new Set(expandedThreads.value)
    if (set.has(commentId)) {
      set.delete(commentId)
    } else {
      set.add(commentId)
    }
    expandedThreads.value = set
  }

  const setReplyTarget = (target: any) => {
    replyTarget.value = target
  }

  const clearReplyTarget = () => {
    replyTarget.value = null
  }

  const setPage = (page: number) => {
    currentPage.value = page
  }

  const reset = () => {
    currentPage.value = 1
    expandedThreads.value = new Set()
    replyTarget.value = null
    currentNoteId.value = null
  }

  return {
    currentPage,
    expandedThreads,
    replyTarget,
    currentNoteId,
    setNoteId,
    toggleThread,
    setReplyTarget,
    clearReplyTarget,
    setPage,
    reset
  }
})
