<template>
    <div class="reading-page">
        <div class="page-header">
            <div class="header-left" @click="goBack">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                <span>返回</span>
            </div>
            <div class="header-title">阅读练习</div>
            <div class="header-right"></div>
        </div>

        <div class="page-content">
            <div class="empty-state">
                <el-icon :size="48">
                    <Reading />
                </el-icon>
                <span>阅读功能开发中...</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishReading' })
import { useRouter } from 'vue-router'
import { ArrowLeft, Reading } from '@element-plus/icons-vue'

const router = useRouter()

const goBack = () => {
    router.back()
}
</script>

<style scoped lang="scss">
.reading-page {
    min-height: 100vh;

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
            width: 60px;
        }
    }

    .page-content {
        padding: 20px;

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 80px 0;
            color: #9ca3af;
            font-size: 14px;
            gap: 12px;
        }
    }
}
</style>