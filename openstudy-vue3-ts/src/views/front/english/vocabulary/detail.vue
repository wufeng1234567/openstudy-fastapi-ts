<template>
    <div class="vocabulary-detail-page">
        <!-- 顶部导航栏 -->
        <div class="page-header">
            <div class="header-left" @click="goBack">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                <span>返回</span>
            </div>
            <div class="header-title">{{ bookInfo.name || '词库详情' }}</div>
            <div class="header-right">
                <el-button type="primary" size="small" @click="ocrDialogVisible = true">
                    <el-icon>
                        <Camera />
                    </el-icon>
                    拍照识词
                </el-button>
                <el-button type="success" size="small" @click="startLearning" v-if="wordList.length > 0">
                    <el-icon>
                        <Notebook />
                    </el-icon>
                    开始学习
                </el-button>
            </div>
        </div>

        <!-- 统计卡片 -->
        <div class="stats-section">
            <div class="stat-card">
                <div class="stat-icon"><OsIcon name="book" :size="20" /></div>
                <div class="stat-info">
                    <span class="stat-value">{{ wordList.length }}</span>
                    <span class="stat-label">总单词</span>
                </div>
            </div>
            <div class="stat-card mastered">
                <div class="stat-icon"><OsIcon name="check-circle" :size="20" /></div>
                <div class="stat-info">
                    <span class="stat-value">{{ masteredCount }}</span>
                    <span class="stat-label">已掌握</span>
                </div>
            </div>
            <div class="stat-card unmastered">
                <div class="stat-icon"><OsIcon name="pen-line" :size="20" /></div>
                <div class="stat-info">
                    <span class="stat-value">{{ unmasteredCount }}</span>
                    <span class="stat-label">未掌握</span>
                </div>
            </div>
            <div class="stat-card progress">
                <div class="stat-icon"><OsIcon name="chart-column" :size="20" /></div>
                <div class="stat-info">
                    <span class="stat-value">{{ masteryPercent }}%</span>
                    <span class="stat-label">掌握率</span>
                </div>
            </div>
        </div>

        <!-- 搜索和筛选 -->
        <div class="filter-section">
            <el-input v-model="searchKeyword" placeholder="搜索单词..." clearable class="search-input">
                <template #prefix>
                    <el-icon>
                        <Search />
                    </el-icon>
                </template>
            </el-input>
            <el-select v-model="filterType" placeholder="类型" class="type-select" clearable>
                <el-option label="全部" value="all" />
                <el-option label="单词" value="word" />
                <el-option label="词组" value="phrase" />
                <el-option label="句子" value="sentence" />
            </el-select>
            <el-select v-model="filterStatus" placeholder="掌握状态" class="status-select">
                <el-option label="全部" value="all" />
                <el-option label="未掌握" value="unmastered" />
                <el-option label="已掌握" value="mastered" />
            </el-select>
        </div>

        <!-- 单词列表 -->
        <div class="word-list-section" v-loading="loading">
            <el-empty v-if="filteredWordList.length === 0" :description="emptyDescription" />

            <div class="word-cards" v-else>
                <div v-for="word in paginatedWordList" :key="word.id" class="word-card"
                    :class="{ mastered: word.isMastered === 1 }">
                    <div class="card-left">
                        <div class="word-type-badge" :class="getTypeClass(word.wordType)">
                            {{ getTypeIcon(word.wordType) }}
                        </div>
                        <div class="word-info">
                            <div class="word-english">
                                {{ word.english }}
                                <el-button class="pronounce-btn" text size="small"
                                    @click="playPronunciation(word.english)">
                                    <el-icon>
                                        <Microphone />
                                    </el-icon>
                                </el-button>
                            </div>
                            <div class="word-chinese">{{ word.chinese }}</div>
                            <div class="word-phonetic" v-if="word.phonetic">{{ word.phonetic }}</div>
                        </div>
                    </div>
                    <div class="card-right">
                        <el-button type="primary" text size="small" @click.stop="handleEditWord(word)">
                            <el-icon>
                                <Edit />
                            </el-icon>
                        </el-button>
                        <el-switch v-model="word.isMastered" :active-value="1" :inactive-value="0" active-text="已掌握"
                            inactive-text="未掌握" @change="toggleMastered(word)" :loading="word.toggling"
                            style="margin-left: 8px" />
                        <el-button type="danger" text size="small" @click.stop="handleDeleteWord(word)"
                            :loading="word.deleting" style="margin-left: 8px">
                            <el-icon>
                                <Delete />
                            </el-icon>
                        </el-button>
                    </div>
                </div>
            </div>

            <!-- 分页 -->
            <div class="pagination-wrapper" v-if="filteredWordList.length > pageSize">
                <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="filteredWordList.length"
                    layout="prev, pager, next" small />
            </div>
        </div>
    </div>

    <!-- OCR 识词组件 -->
    <OcrRecognizer v-model="ocrDialogVisible" :word-book-id="bookId" @success="fetchWordList" />
    <!-- 编辑单词对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑单词" width="450px" :close-on-click-modal="false" destroy-on-close>
        <el-form ref="editFormRef" :model="editForm" :rules="editFormRules" label-width="80px" label-position="top">
            <el-form-item label="英文" prop="english">
                <el-input v-model="editForm.english" placeholder="请输入英文单词/词组/句子" clearable />
            </el-form-item>

            <el-form-item label="中文释义" prop="chinese">
                <el-input v-model="editForm.chinese" placeholder="请输入中文释义" clearable />
            </el-form-item>

            <el-form-item label="音标" prop="phonetic">
                <el-input v-model="editForm.phonetic" placeholder="请输入音标（选填）" clearable />
            </el-form-item>

            <el-form-item label="类型" prop="wordType">
                <el-select v-model="editForm.wordType" placeholder="请选择类型" style="width: 100%">
                    <el-option label="单词" :value="1" />
                    <el-option label="词组" :value="2" />
                    <el-option label="句子" :value="3" />
                </el-select>
            </el-form-item>
        </el-form>

        <template #footer>
            <el-button @click="editDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleSaveEdit" :loading="editSaving">
                保存
            </el-button>
        </template>
    </el-dialog>
</template>

<script setup lang="ts">
import OsIcon from '@/components/OsIcon/index.vue'
defineOptions({ name: 'FrontEnglishVocabularyDetail' })
import { ref, computed, onMounted, onActivated, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, Search, Notebook, Microphone, Camera, Delete, Edit } from '@element-plus/icons-vue'
import { getWordBooks } from '@/api/wordBooks/wordBooks'
import { listWords, updateWords, delWords } from '@/api/words/words'  // ✅ 添加 delWords
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import OcrRecognizer from '@/components/OcrRecognizer/index.vue'

const router = useRouter()
const route = useRoute()
const cacheStore = useFrontPageCacheStore()

// 编辑相关
const editDialogVisible = ref(false)
const editSaving = ref(false)
const editFormRef = ref(null)
const editingWord = ref(null)

const editForm = ref({
    id: null,
    english: '',
    chinese: '',
    phonetic: '',
    wordType: 1
})

const editFormRules = {
    english: [
        { required: true, message: '请输入英文', trigger: 'blur' },
        { min: 1, max: 255, message: '长度在 1 到 255 个字符', trigger: 'blur' }
    ],
    chinese: [
        { required: true, message: '请输入中文释义', trigger: 'blur' },
        { min: 1, max: 255, message: '长度在 1 到 255 个字符', trigger: 'blur' }
    ]
}

// OCR 对话框
const ocrDialogVisible = ref(false)

// 词库ID
const bookId = ref(null)

// 词库信息
const bookInfo = ref({
    id: null,
    name: '',
    description: '',
    isDefault: 0
})

// 单词列表
const wordList = ref([])
const loading = ref(false)

// 类型筛选
const filterType = ref('all')

// 搜索和筛选
const searchKeyword = ref('')
const filterStatus = ref('all')

// 分页
const currentPage = ref(1)
const pageSize = ref(10)

// 打开编辑对话框
const handleEditWord = (word) => {
    editingWord.value = word
    editForm.value = {
        id: word.id,
        english: word.english || '',
        chinese: word.chinese || '',
        phonetic: word.phonetic || '',
        wordType: word.wordType || 1
    }
    editDialogVisible.value = true

    // 清空表单验证
    nextTick(() => {
        editFormRef.value?.clearValidate()
    })
}

// 保存编辑
const handleSaveEdit = async () => {
    try {
        await editFormRef.value?.validate()
    } catch {
        return
    }

    editSaving.value = true
    try {
        const response = await updateWords({
            id: editForm.value.id,
            english: editForm.value.english,
            chinese: editForm.value.chinese,
            phonetic: editForm.value.phonetic || '',
            wordType: editForm.value.wordType
        })

        if (response.code === 200) {
            ElMessage.success('保存成功')
            editDialogVisible.value = false

            // 更新列表中的单词
            if (editingWord.value) {
                editingWord.value.english = editForm.value.english
                editingWord.value.chinese = editForm.value.chinese
                editingWord.value.phonetic = editForm.value.phonetic
                editingWord.value.wordType = editForm.value.wordType
            }
        } else {
            ElMessage.error(response.msg || '保存失败')
        }
    } catch (error) {
        console.error('保存失败:', error)
        ElMessage.error('保存失败')
    } finally {
        editSaving.value = false
    }
}

// 加载数据的方法
const loadData = () => {
    if (bookId.value) {
        fetchBookInfo()
        fetchWordList()
    }
}

// 计算属性
const masteredCount = computed(() => {
    return wordList.value.filter(w => w.isMastered === 1).length
})

const unmasteredCount = computed(() => {
    return wordList.value.filter(w => w.isMastered !== 1).length
})

const masteryPercent = computed(() => {
    if (wordList.value.length === 0) return 0
    return Math.round((masteredCount.value / wordList.value.length) * 100)
})

// 删除单词
// 删除单词
const handleDeleteWord = async (word) => {
    try {
        await ElMessageBox.confirm(
            `确定要删除单词 "${word.english}" 吗？`,
            '删除确认',
            {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                type: 'warning'
            }
        )

        word.deleting = true
        const response = await delWords(word.id)

        if (response.code === 200) {
            ElMessage.success('删除成功')
            const index = wordList.value.findIndex(w => w.id === word.id)
            if (index !== -1) {
                wordList.value.splice(index, 1)
            }
        } else {
            ElMessage.error(response.msg || '删除失败')
        }
    } catch (error) {
        if (error !== 'cancel') {
            console.error('删除失败:', error)
            ElMessage.error('删除失败')
        }
    } finally {
        word.deleting = false
    }
}

// 过滤后的单词列表
const filteredWordList = computed(() => {
    let list = wordList.value

    if (filterType.value === 'word') {
        list = list.filter(w => w.wordType === 1)
    } else if (filterType.value === 'phrase') {
        list = list.filter(w => w.wordType === 2)
    } else if (filterType.value === 'sentence') {
        list = list.filter(w => w.wordType === 3)
    }

    if (filterStatus.value === 'mastered') {
        list = list.filter(w => w.isMastered === 1)
    } else if (filterStatus.value === 'unmastered') {
        list = list.filter(w => w.isMastered !== 1)
    }

    if (searchKeyword.value) {
        const keyword = searchKeyword.value.toLowerCase()
        list = list.filter(w => {
            return (w.english || '').toLowerCase().includes(keyword) ||
                (w.chinese || '').toLowerCase().includes(keyword)
        })
    }

    return list
})

// 分页后的单词列表
const paginatedWordList = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    const end = start + pageSize.value
    return filteredWordList.value.slice(start, end)
})

// 空状态描述
const emptyDescription = computed(() => {
    if (searchKeyword.value) return '未找到相关单词'
    if (filterStatus.value === 'mastered') return '还没有已掌握的单词'
    if (filterStatus.value === 'unmastered') return '所有单词都已掌握，太棒了！'
    return '词库中还没有单词，快去添加吧'
})

// 获取类型图标
const getTypeIcon = (type) => {
    if (type === 1) return '单词'
    if (type === 2) return '词组'
    return '句子'
}

// 获取类型样式
const getTypeClass = (type) => {
    if (type === 1) return 'type-word'
    if (type === 2) return 'type-phrase'
    return 'type-sentence'
}

// 加载词库信息
const fetchBookInfo = async () => {
    try {
        const response = await getWordBooks(bookId.value)
        if (response.code === 200) {
            bookInfo.value = response.data || {}
        } else {
            ElMessage.error(response.msg || '获取词库信息失败')
        }
    } catch (error) {
        console.error('获取词库信息失败:', error)
        ElMessage.error('获取词库信息失败')
    }
}

// 加载单词列表
const fetchWordList = async () => {
    loading.value = true
    try {
        const response = await listWords({
            pageNum: 1,
            pageSize: 1000,
            wordBookId: bookId.value
        })
        if (response.code === 200) {
            wordList.value = (response.rows || []).map(word => ({
                ...word,
                toggling: false,
                pronouncing: false,
                deleting: false  // ✅ 添加删除状态
            }))
        } else {
            ElMessage.error(response.msg || '获取单词列表失败')
        }
    } catch (error) {
        console.error('获取单词列表失败:', error)
        ElMessage.error('获取单词列表失败')
    } finally {
        loading.value = false
    }
}

// 切换掌握状态
const toggleMastered = async (word) => {
    word.toggling = true
    try {
        const response = await updateWords({
            id: word.id,
            isMastered: word.isMastered
        })
        if (response.code === 200) {
            ElMessage.success(word.isMastered === 1 ? '已标记为掌握' : '已取消掌握标记')
        } else {
            word.isMastered = word.isMastered === 1 ? 0 : 1
            ElMessage.error(response.msg || '更新失败')
        }
    } catch (error) {
        word.isMastered = word.isMastered === 1 ? 0 : 1
        console.error('更新失败:', error)
        ElMessage.error('更新失败')
    } finally {
        word.toggling = false
    }
}

// 播放读音
const playPronunciation = (word) => {
    if (!word) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(word)
    utterance.lang = 'en-US'
    utterance.rate = 0.8
    utterance.pitch = 1
    window.speechSynthesis.speak(utterance)
}

// 开始学习
const startLearning = () => {
    ElMessage.info('学习功能开发中...')
}

// 返回
const goBack = () => {
    cacheStore.setLastVisited('english', 'vocabulary')
    router.push('/front/english/vocabulary')
}

// 监听筛选变化
watch([searchKeyword, filterType, filterStatus], () => {
    currentPage.value = 1
})

// 组件激活时
onActivated(() => {
    const newId = route.params.id
    if (bookId.value !== newId) {
        bookId.value = newId
        currentPage.value = 1
        searchKeyword.value = ''
        filterStatus.value = 'all'
        filterType.value = 'all'
        loadData()
    }
})

// 首次加载
onMounted(() => {
    bookId.value = route.params.id
    loadData()
})
</script>

<style scoped lang="scss">
.vocabulary-detail-page {
    min-height: 100vh;
    display: flex;
    flex-direction: column;

    .page-header {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        align-items: center;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;

        .header-left {
            display: flex;
            align-items: center;
            gap: 4px;
            color: #6b7280;
            cursor: pointer;
            font-size: 15px;
            justify-self: start;
            width: fit-content;

            &:hover {
                color: #4b5563;
            }
        }

        .header-title {
            font-size: 20px;
            font-weight: 700;
            color: #1f2937;
            text-align: center;
            white-space: nowrap;
        }

        .header-right {
            justify-self: end;
            display: flex;
            gap: 8px;
        }
    }

    .stats-section {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;

        .stat-card {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            background: #f8f9fa;
            border-radius: 16px;
            border: 1px solid #e5e7eb;

            .stat-icon {
                font-size: 28px;
            }

            .stat-info {
                display: flex;
                flex-direction: column;

                .stat-value {
                    font-size: 22px;
                    font-weight: 700;
                    color: #1f2937;
                    line-height: 1.2;
                }

                .stat-label {
                    font-size: 13px;
                    color: #6b7280;
                }
            }

            &.mastered .stat-value {
                color: #67c23a;
            }

            &.unmastered .stat-value {
                color: #e6a23c;
            }

            &.progress .stat-value {
                color: #409eff;
            }
        }
    }

    .filter-section {
        display: flex;
        gap: 12px;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;

        .search-input {
            flex: 1;
            max-width: 250px;
        }

        .type-select {
            width: 120px;
        }

        .status-select {
            width: 130px;
        }
    }

    .word-list-section {
        flex: 1;
        padding: 20px;
        min-height: 400px;

        .word-cards {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .word-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            background: #fff;
            border-radius: 16px;
            border: 1px solid #e5e7eb;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

            &:hover {
                border-color: #d1d5db;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
            }

            &.mastered {
                background: #f6ffed;
                border-color: #b7eb8f;
            }

            .card-left {
                display: flex;
                align-items: center;
                gap: 16px;
                flex: 1;

                .word-type-badge {
                    width: 40px;
                    height: 40px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 18px;
                    border-radius: 8px;
                    background: #f3f4f6;
                    flex-shrink: 0;

                    &.type-word {
                        background: #e8f4ff;
                    }

                    &.type-phrase {
                        background: #f0f9eb;
                    }

                    &.type-sentence {
                        background: #fefce8;
                    }
                }

                .word-info {
                    .word-english {
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        font-size: 18px;
                        font-weight: 600;
                        color: #1f2937;
                        margin-bottom: 4px;

                        .pronounce-btn {
                            padding: 4px;
                            color: #409eff;
                            opacity: 0.6;
                            transition: opacity 0.2s;

                            &:hover {
                                opacity: 1;
                            }
                        }
                    }

                    .word-chinese {
                        font-size: 14px;
                        color: #6b7280;
                        margin-bottom: 2px;
                    }

                    .word-phonetic {
                        font-size: 12px;
                        color: #9ca3af;
                        font-family: monospace;
                    }
                }
            }

            .card-right {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }
        }

        .pagination-wrapper {
            display: flex;
            justify-content: center;
            margin-top: 24px;
            padding-top: 16px;
        }
    }
}

@media (max-width: 768px) {
    .vocabulary-detail-page {
        .stats-section {
            grid-template-columns: repeat(2, 1fr);
        }

        .filter-section {
            flex-direction: column;

            .search-input {
                max-width: 100%;
            }

            .type-select,
            .status-select {
                width: 100%;
            }
        }

        .word-list-section .word-card {
            flex-direction: column;
            align-items: flex-start;
            gap: 16px;

            .card-right {
                width: 100%;
                display: flex;
                justify-content: flex-end;
                gap: 8px;
            }
        }
    }
}
</style>