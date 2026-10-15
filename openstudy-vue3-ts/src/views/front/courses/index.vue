<template>
    <div class="courses-page">
        <div class="page-card">
            <div class="page-icon">
                <el-icon :size="48" color="var(--primary-600)">
                    <Reading />
                </el-icon>
            </div>
            <h1 class="page-title">课程中心</h1>
            <p class="page-desc">精选课程助你高效学习成长</p>
            <div class="page-status">
                <el-tag type="info" size="large" effect="plain">功能开发中，敬请期待...</el-tag>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontCourses' })
import { Reading } from '@element-plus/icons-vue'
</script>

<style scoped lang="scss">
:root {
    --primary-50: #eef2ff;
    --primary-100: #e0e7ff;
    --primary-500: #6366f1;
    --primary-600: #4f46e5;
    --primary-700: #4338ca;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-900: #111827;
}

.courses-page {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: calc(100vh - 200px);
    padding: 40px 24px;

    .page-card {
        background: white;
        border-radius: 16px;
        padding: 64px 48px;
        border: 1px solid var(--gray-200);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        text-align: center;
        max-width: 480px;
        width: 100%;

        .page-icon {
            width: 80px;
            height: 80px;
            margin: 0 auto 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--primary-50);
            border-radius: 50%;
        }

        .page-title {
            font-size: 20px;
            font-weight: 700;
            color: #1f2937;
            margin: 0 0 12px;
            letter-spacing: -0.5px;
        }

        .page-desc {
            font-size: 16px;
            color: var(--gray-500);
            margin: 0 0 32px;
        }

        .page-status {
            display: inline-block;
        }
    }
}

@media (max-width: 768px) {
    .courses-page {
        .page-card {
            padding: 48px 32px;

            .page-title {
                font-size: 24px;
            }

            .page-desc {
                font-size: 14px;
            }
        }
    }
}
</style>