<template>
    <div class="vocabulary-page">
        <!-- 顶部导航栏 -->
        <div class="page-header">
            <div class="header-left" @click="goBack">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                <span>返回</span>
            </div>
            <div class="header-title">我的词库</div>
            <div class="header-right">
                <el-button type="primary" size="small" @click="handleCreate">
                    <el-icon>
                        <Plus />
                    </el-icon>
                    新建
                </el-button>
            </div>
        </div>

        <!-- 搜索区域 -->
        <div class="search-section">
            <el-input v-model="searchKeyword" placeholder="搜索词库名称" clearable @input="handleSearchInput"
                @clear="handleSearchClear" class="search-input">
                <template #prefix>
                    <el-icon>
                        <Search />
                    </el-icon>
                </template>
            </el-input>
        </div>

        <!-- 内容区域 -->
        <div class="page-content">
            <!-- 加载中 -->
            <div v-if="loading" class="loading-state">
                <el-icon class="is-loading" :size="32">
                    <Loading />
                </el-icon>
                <span>加载中...</span>
            </div>

            <!-- 空状态 -->
            <div v-else-if="filteredBookList.length === 0 && !searchKeyword" class="empty-state">
                <el-empty description="还没有词库">
                    <el-button type="primary" @click="handleCreate">新建词库</el-button>
                </el-empty>
            </div>

            <!-- 搜索无结果 -->
            <div v-else-if="filteredBookList.length === 0 && searchKeyword" class="empty-state">
                <el-empty description="未找到相关词库">
                    <el-button @click="handleSearchClear">清空搜索</el-button>
                </el-empty>
            </div>

            <!-- 词库列表 -->
            <template v-else>
                <!-- 默认单词本 -->
                <div v-if="defaultBooks.length > 0" class="section-title">默认单词本</div>
                <div v-if="defaultBooks.length > 0" class="book-grid">
                    <div v-for="book in defaultBooks" :key="book.id" class="book-card default-card"
                        @click="handleCardClick(book)">
                        <div class="card-icon"><OsIcon name="book" :size="20" /></div>
                        <div class="card-content">
                            <h3 class="book-name">{{ book.name }}</h3>
                            <p class="book-desc">{{ book.description || '系统默认单词本' }}</p>
                        </div>
                        <div class="card-badge">
                            <el-tag type="info" size="small">默认</el-tag>
                        </div>
                    </div>
                </div>

                <!-- 我的词库 -->
                <div v-if="customBooks.length > 0" class="section-title">我的词库</div>
                <div v-if="customBooks.length > 0" class="book-grid">
                    <div v-for="book in customBooks" :key="book.id" class="book-card" @click="handleCardClick(book)">
                        <div class="card-icon"><OsIcon name="book" :size="20" /></div>
                        <div class="card-content">
                            <h3 class="book-name">{{ book.name }}</h3>
                            <p class="book-desc">{{ book.description || '暂无描述' }}</p>
                            <div class="book-meta">
                                <span class="create-time">{{ formatTime(book.createdTime) }}</span>
                            </div>
                        </div>
                        <div class="card-arrow">
                            <el-icon>
                                <ArrowRight />
                            </el-icon>
                        </div>
                    </div>
                </div>
            </template>
        </div>
    </div>
    <!-- 新建词库对话框 -->
    <el-dialog v-model="dialogVisible" title="新建词库" width="400px" :close-on-click-modal="false" destroy-on-close>
        <el-form ref="formRef" :model="formData" :rules="formRules" label-width="80px" label-position="top">
            <el-form-item label="词库名称" prop="name">
                <el-input v-model="formData.name" placeholder="请输入词库名称" maxlength="50" show-word-limit clearable />
            </el-form-item>
            <el-form-item label="词库描述" prop="description">
                <el-input v-model="formData.description" type="textarea" placeholder="请输入词库描述（选填）" maxlength="200"
                    show-word-limit :rows="3" />
            </el-form-item>
            <!-- 管理员专属：设为默认词库选项 -->
            <el-form-item v-if="isAdmin" label="词库类型">
                <el-checkbox v-model="formData.isDefault">
                    设为默认单词本
                </el-checkbox>
                <div class="form-tip">
                    <el-icon>
                        <InfoFilled />
                    </el-icon>
                    <span>勾选后将作为系统默认单词本</span>
                </div>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
                确定
            </el-button>
        </template>
    </el-dialog>
</template>

<script setup lang="ts">
import OsIcon from '@/components/OsIcon/index.vue'
defineOptions({ name: 'FrontEnglishVocabulary' })
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Plus, Search, Loading, InfoFilled } from '@element-plus/icons-vue'
import { listFrontWordBooks, addWordBooks } from '@/api/wordBooks/wordBooks'
import useUserStore from '@/store/modules/user'
import { ElMessage } from 'element-plus'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
// 1. 导入权限判断函数（在现有 import 后添加）
import { checkPermi, checkRole } from '@/utils/permission'
const cacheStore = useFrontPageCacheStore()


const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const searchKeyword = ref('')
const bookList = ref([])

// 2. 添加管理员判断（在现有 ref 声明区域添加）
const isAdmin = computed(() => {
    return checkRole(['admin'])
})

// 在现有 ref 声明后添加
const dialogVisible = ref(false)
const submitLoading = ref(false)
const formRef = ref(null)

// 3. 修改 formData 结构
const formData = ref({
    name: '',
    description: '',
    isDefault: false  // 默认为 false，非管理员不显示此选项
})

const formRules = {
    name: [
        { required: true, message: '请输入词库名称', trigger: 'blur' },
        { min: 1, max: 50, message: '长度在 1 到 50 个字符', trigger: 'blur' }
    ],
    description: [
        { max: 200, message: '描述不能超过 200 个字符', trigger: 'blur' }
    ]
}

// 4. 修改 handleCreate 方法
const handleCreate = () => {
    dialogVisible.value = true
    formData.value = {
        name: '',
        description: '',
        isDefault: false
    }
    // 清空表单验证
    setTimeout(() => {
        formRef.value?.clearValidate()
    }, 0)
}


// 提交表单
const handleSubmit = async () => {
    try {
        await formRef.value?.validate()
    } catch (error) {
        return
    }

    submitLoading.value = true
    try {
        const userId = userStore.id

        // 构建提交数据
        const submitData = {
            userId: userId,
            name: formData.value.name,
            description: formData.value.description,
            // 只有管理员且勾选了设为默认，才设置为默认词库
            isDefault: isAdmin.value && formData.value.isDefault ? 1 : 0
        }

        // 调用创建词库 API
        const response = await addWordBooks(submitData)

        if (response.code === 200) {
            ElMessage.success('创建成功')
            dialogVisible.value = false
            // 刷新列表
            await fetchBookList()
        } else {
            ElMessage.error(response.msg || '创建失败')
        }
    } catch (error) {
        console.error('创建失败：', error)
        ElMessage.error('创建失败，请稍后重试')
    } finally {
        submitLoading.value = false
    }
}


// 过滤后的词库列表
const filteredBookList = computed(() => {
    if (!searchKeyword.value) return bookList.value
    const keyword = searchKeyword.value.toLowerCase()
    return bookList.value.filter(book => {
        const name = (book.name || '').toLowerCase()
        const description = (book.description || '').toLowerCase()
        return name.includes(keyword) || description.includes(keyword)
    })
})

// 加载词库列表
const fetchBookList = async () => {
    loading.value = true
    try {
        const userId = userStore.id
        const response = await listFrontWordBooks({
            pageNum: 1,
            pageSize: 100,
            userId: userId
        })
        if (response.code === 200) {
            bookList.value = response.rows || []
        } else {
            ElMessage.error(response.msg || '获取词库失败')
        }
    } catch (error) {
        console.error('获取词库失败:', error)
        ElMessage.error('获取词库失败')
    } finally {
        loading.value = false
    }
}

const defaultBooks = computed(() => {
    return filteredBookList.value.filter(book => book.isDefault === 1)
})

const customBooks = computed(() => {
    return filteredBookList.value.filter(book => book.isDefault !== 1)
})



const goBack = () => {
    cacheStore.setLastVisited('english', 'home')
    router.push('/front/english/home')
}





const handleSearchClear = () => {
    searchKeyword.value = ''
}


// 格式化时间
const formatTime = (time) => {
    if (!time) return ''
    const date = new Date(time)
    const now = new Date()
    const diff = now - date
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
}

// 点击卡片
const handleCardClick = (book) => {
    router.push(`/front/english/vocabulary/${book.id}`)
}

onMounted(() => {
    fetchBookList()
})
</script>

<style scoped lang="scss">
.vocabulary-page {
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
        }

        .header-right {
            justify-self: end;
            display: flex;
            justify-content: flex-end;
        }
    }

    .search-section {
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;

        .search-input {
            max-width: 400px;

            :deep(.el-input__wrapper) {
                border-radius: 8px;
            }
        }
    }

    .page-content {
        flex: 1;
        padding: 20px;

        .section-title {
            font-size: 15px;
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 16px;
            margin-top: 8px;

            &:first-of-type {
                margin-top: 0;
            }
        }

        .book-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
    }

    .loading-state,
    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 80px 0;
        color: #9ca3af;
    }

    .loading-state {
        color: #6b7280;
    }

    .book-card {
        background: #fff;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        border: 1px solid #e5e7eb;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        display: flex;
        position: relative;

        &:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
            border-color: #d1d5db;
        }

        &.default-card {
            background: #fff;
            border-left: 4px solid #e5e7eb;
        }

        .card-icon {
            font-size: 36px;
            margin-right: 16px;
        }

        .card-content {
            flex: 1;

            .book-name {
                font-size: 16px;
                font-weight: 600;
                color: #1f2937;
                margin: 0 0 6px 0;
            }

            .book-desc {
                font-size: 13px;
                color: #9ca3af;
                margin: 0 0 8px 0;
            }

            .book-meta {
                font-size: 12px;
                color: #9ca3af;

                .create-time {
                    display: flex;
                    align-items: center;
                    gap: 4px;
                }
            }
        }

        .card-badge {
            position: absolute;
            top: 16px;
            right: 16px;
        }

        .card-arrow {
            display: flex;
            align-items: center;
            color: #9ca3af;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        &:hover .card-arrow {
            transform: translateX(4px);
            color: #6b7280;
        }
    }

    .form-tip {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: #9ca3af;
        margin-top: 6px;

        .el-icon {
            font-size: 14px;
        }
    }

}
</style>

<style lang="scss">
.vocabulary-page .el-dialog {
    border-radius: 16px;
    overflow: hidden;

    .el-dialog__header {
        padding: 20px 24px 16px;
        border-bottom: 1px solid #f3f4f6;

        .el-dialog__title {
            font-size: 17px;
            font-weight: 600;
            color: #1f2937;
        }
    }

    .el-dialog__body {
        padding: 24px;
    }

    .el-dialog__footer {
        padding: 16px 24px 20px;
        border-top: 1px solid #f3f4f6;

        .el-button {
            border-radius: 8px;
            font-weight: 500;
            padding: 8px 20px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            background: #fff;
            border: 1px solid #e5e7eb;
            color: #6b7280;

            &:hover {
                transform: translateY(-2px);
                border-color: #d1d5db;
                color: #4b5563;
            }

            &:active {
                transform: translateY(0);
            }

            &.el-button--primary {
                background: #fff;
                border-color: #d1d5db;
                color: #1f2937;

                &:hover {
                    border-color: #9ca3af;
                    color: #1f2937;
                }
            }
        }
    }
}
</style>