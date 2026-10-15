// composables/useStreamGeneration.ts
import { ref, nextTick } from 'vue'
import type { Ref } from 'vue'

interface StreamGenerationOptions {
    onChunk?: (chunk: string) => void
    onComplete?: (parsedData: any) => void
    onError?: (error: any) => void
}

/**
 * 通用流式生成组合式函数
 *
 * @example
 * const stream = useStreamGeneration({
 *   onChunk: (chunk) => console.log(chunk),
 *   onComplete: (result) => console.log('完成', result),
 *   onError: (err) => console.error(err)
 * })
 *
 * // 调用方式
 * stream.start((handleChunk, handleComplete, handleError, signal) => {
 *   yourStreamApi(params, handleChunk, handleComplete, handleError, signal)
 * })
 */
export function useStreamGeneration(options: StreamGenerationOptions = {}) {
    const isGenerating = ref(false)
    const isPaused = ref(false)
    const streamContent = ref('')
    const abortController = ref<AbortController | null>(null)

    // 暂停缓存
    let pendingChunks: string[] = []
    let pendingComplete: any = null

    // 处理收到的数据块
    const handleChunk = (chunk: string) => {
        if (isPaused.value) {
            pendingChunks.push(chunk)
            return
        }
        streamContent.value = chunk
        options.onChunk?.(chunk)
    }

    // 处理流完成
    const handleComplete = (parsedData: any) => {
        if (isPaused.value) {
            pendingComplete = parsedData
        } else {
            finishGeneration(parsedData)
        }
    }

    const finishGeneration = (parsedData: any) => {
        isGenerating.value = false
        abortController.value = null
        isPaused.value = false
        options.onComplete?.(parsedData)
    }

    // 处理错误
    const handleError = (error: any) => {
        if (error?.name === 'AbortError') return
        isGenerating.value = false
        abortController.value = null
        isPaused.value = false
        options.onError?.(error)
    }

    // 逐块消费暂停时缓存的数据
    const processPendingChunks = async () => {
        if (isPaused.value) return
        if (pendingChunks.length === 0) {
            if (pendingComplete) {
                const data = pendingComplete
                pendingComplete = null
                finishGeneration(data)
            }
            return
        }
        const chunk = pendingChunks.shift() as string
        streamContent.value = chunk
        options.onChunk?.(chunk)
        await nextTick()
        setTimeout(() => processPendingChunks(), 10)
    }

    // 切换暂停/继续
    const togglePause = () => {
        if (isPaused.value) {
            isPaused.value = false
            if (pendingChunks.length > 0) {
                processPendingChunks()
            }
            if (pendingComplete && pendingChunks.length === 0) {
                const data = pendingComplete
                pendingComplete = null
                finishGeneration(data)
            }
        } else {
            isPaused.value = true
        }
    }

    // 开始流式生成
    // executor: (handleChunk, handleComplete, handleError, signal) => void
    const start = (executor: (handleChunk: (chunk: string) => void, handleComplete: (parsedData: any) => void, handleError: (error: any) => void, signal: AbortSignal) => void) => {
        // 重置状态
        isGenerating.value = true
        isPaused.value = false
        streamContent.value = ''
        pendingChunks = []
        pendingComplete = null
        abortController.value = new AbortController()

        try {
            executor(handleChunk, handleComplete, handleError, abortController.value.signal)
        } catch (error) {
            handleError(error)
        }
    }

    // 中止生成
    const abort = () => {
        if (abortController.value) {
            abortController.value.abort()
            abortController.value = null
        }
        isGenerating.value = false
        isPaused.value = false
    }

    // 清空内容
    const clear = () => {
        streamContent.value = ''
        pendingChunks = []
        pendingComplete = null
    }

    // 重置所有状态
    const reset = () => {
        abort()
        clear()
        isGenerating.value = false
        isPaused.value = false
    }

    return {
        // 状态
        isGenerating,
        isPaused,
        streamContent,
        abortController,

        // 方法
        start,
        togglePause,
        abort,
        clear,
        reset
    }
}
