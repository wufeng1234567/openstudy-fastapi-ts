<template>
    <div class="home-page">
        <div class="page-header">
            <h1 class="page-title">📚 英语学习</h1>
            <p class="page-subtitle">轻量级英语学习工具箱</p>
        </div>

        <div class="tool-grid">
            <!-- 拍照识词 -->
            <div class="tool-card" @click="goToOcr">
                <div class="tool-icon" style="background: #e8f4ff;">
                    <el-icon :size="32">
                        <Camera />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">拍照识词</h3>
                    <p class="tool-desc">拍照或上传图片，快速识别单词</p>
                </div>
                <div class="tool-arrow">
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </div>
            </div>

            <!-- 我的词库 -->
            <div class="tool-card" @click="goToVocabulary">
                <div class="tool-icon" style="background: #f0f9eb;">
                    <el-icon :size="32">
                        <Notebook />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">我的词库</h3>
                    <p class="tool-desc">管理你的单词本和词组库</p>
                </div>
                <div class="tool-arrow">
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </div>
            </div>

            <!-- 听力练习（开发中） -->
            <div class="tool-card" @click="goToListListening">
                <div class="tool-icon" style="background: #fdf6ec;">
                    <el-icon :size="32">
                        <Headset />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">听力练习</h3>
                    <p class="tool-desc">单词听写，提升听力水平</p>
                    <el-tag size="small" type="info">开发中</el-tag>
                </div>
            </div>

            <!-- 阅读练习（开发中） -->
            <div class="tool-card disabled">
                <div class="tool-icon" style="background: #fef0f0;">
                    <el-icon :size="32">
                        <Reading />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">阅读练习</h3>
                    <p class="tool-desc">短文阅读，积累生词</p>
                    <el-tag size="small" type="info">开发中</el-tag>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishHome' })
import { useRouter } from 'vue-router'
import { Camera, Notebook, Headset, Reading, ArrowRight } from '@element-plus/icons-vue'
import { onMounted, onActivated, onDeactivated } from 'vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
const router = useRouter()
const cacheStore = useFrontPageCacheStore()
const goToOcr = () => {
    cacheStore.setLastVisited('english', 'ocr')
    router.push('/front/english/ocr')
}


const goToVocabulary = () => {
    cacheStore.setLastVisited('english', 'vocabulary')
    router.push('/front/english/vocabulary')
}

const goToListListening = () => {
    cacheStore.setLastVisited('english', 'listening')
    router.push('/front/english/listening')
}

onMounted(() => {
    console.log('🆕 首页工具箱 - mounted（首次创建）')
})

onActivated(() => {
    console.log('✅ 首页工具箱 - activated（从缓存恢复）')
})

onDeactivated(() => {
    console.log('💾 首页工具箱 - deactivated（被缓存）')
})
</script>

<style scoped lang="scss">
.home-page {
    max-width: 900px;
    margin: 0 auto;
    padding: 24px 20px;

    .page-header {
        text-align: center;
        margin-bottom: 40px;

        .page-title {
            font-size: 20px;
            font-weight: 700;
            color: #1f2937;
            margin: 0 0 8px 0;
        }

        .page-subtitle {
            font-size: 15px;
            color: #6b7280;
            margin: 0;
        }
    }

    .tool-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 20px;
    }

    .tool-card {
        display: flex;
        align-items: center;
        padding: 24px;
        background: #fff;
        border-radius: 16px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
            border-color: #d1d5db;
        }

        &.disabled {
            opacity: 0.6;
            cursor: not-allowed;

            &:hover {
                transform: none;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
                border-color: #e5e7eb;
            }
        }

        .tool-icon {
            width: 64px;
            height: 64px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #6b7280;
            margin-right: 20px;
            flex-shrink: 0;
        }

        .tool-content {
            flex: 1;

            .tool-title {
                font-size: 18px;
                font-weight: 600;
                color: #1f2937;
                margin: 0 0 6px 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .tool-desc {
                font-size: 13px;
                color: #9ca3af;
                margin: 0;
            }
        }

        .tool-arrow {
            color: #9ca3af;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            flex-shrink: 0;
        }

        &:hover .tool-arrow {
            transform: translateX(4px);
            color: #6b7280;
        }
    }
}

@media (max-width: 640px) {
    .tool-grid {
        grid-template-columns: 1fr;
    }
}
</style>