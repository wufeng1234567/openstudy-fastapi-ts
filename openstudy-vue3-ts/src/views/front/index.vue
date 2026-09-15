<template>
    <div class="front-home">

        <!-- ==================== 轮播图区域 ==================== -->
        <!-- 使用 Element Plus 的 el-carousel 组件实现自动轮播 -->
        <!-- v-loading 指令在数据加载时显示加载动画 -->
        <div class="carousel-wrapper" v-loading="loading">
            <!-- interval=5000 表示每5秒自动切换，arrow="always" 始终显示左右箭头 -->
            <el-carousel v-if="carouselList.length > 0" :interval="5000" arrow="always" height="420px"
                indicator-position="outside">
                <el-carousel-item v-for="item in carouselList" :key="item.id">
                    <!-- 点击轮播图可跳转到目标链接 -->
                    <div class="carousel-item-content" @click="goTarget(item.linkUrl)">
                        <!-- 图片地址需要拼接 API 基础路径 -->
                        <img :src="item.imageUrl" :alt="item.title" class="carousel-img" />
                        <div class="carousel-overlay">
                            <h3 class="carousel-title">{{ item.title }}</h3>
                        </div>
                    </div>
                </el-carousel-item>
            </el-carousel>
            <div v-else class="empty-carousel">暂无轮播图</div>
        </div>

        <!-- ==================== 平台介绍区域 ==================== -->
        <!-- 展示平台的核心功能特点 -->
        <div class="activity-intro">
            <h2>📚 OpenStudy 开放学习平台</h2>
            <p>基于 AI 驱动的智能学习平台，为学习者提供高效、便捷的一站式学习体验。</p>
            <ul>
                <li>✅ 海量题库智能刷题，错题本精准复习</li>
                <li>✅ AI 解析与智能出题，高效掌握知识点</li>
                <li>✅ 题库搭建，上传文档智能解析生成题库</li>
                <li>✅ Markdown 笔记分享，打造个人知识库</li>
                <li>✅ 实用工具箱，图片处理与文档转换</li>
            </ul>
            <p style="margin-top: 16px; text-align: center; color: #409eff;">
                🎉 快来体验吧，开启你的高效学习之旅！
            </p>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontIndex' })
/**
 * 首页组件
 * 功能：展示轮播图和平台介绍
 * 数据来源：轮播图数据从后端 API 获取
 */
import { ref, onMounted } from 'vue'
import { listCarouselAll } from '@/api/carousel/carousel'

// ==================== 响应式数据 ====================
const carouselList = ref([])  // 轮播图列表数据
const loading = ref(true)     // 加载状态控制

// ==================== 获取轮播图数据 ====================
// 调用后端 API 获取所有轮播图，并拼接完整的图片 URL
function fetchCarouselList() {
    loading.value = true
    listCarouselAll()
        .then(response => {
            const data = response.data || []
            // 拼接 API 基础路径，确保图片地址可访问
            carouselList.value = data.map(item => ({
                ...item,
                imageUrl: (import.meta.env.VITE_APP_BASE_API || '') + (item.imageUrl || '')
            }))
        })
        .finally(() => {
            loading.value = false
        })
}

// ==================== 跳转目标链接 ====================
// 点击轮播图时在新窗口打开目标链接
function goTarget(url) {
    if (url && url.trim()) {
        window.open(url, '_blank', 'noopener,noreferrer')
    }
}

// ==================== 生命周期钩子 ====================
// 组件挂载后立即获取轮播图数据
onMounted(() => {
    fetchCarouselList()
})
</script>

<style scoped lang="scss">
// 设计系统变量
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

.front-home {
    .switch-bar {
        text-align: right;
        margin-bottom: 20px;
    }

    .carousel-wrapper {
        margin-bottom: 40px;
        border-radius: 16px;
        overflow: hidden;
        background: white;
        border: 1px solid var(--gray-200);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

        :deep(.el-carousel__container) {
            border-radius: 16px;
        }

        :deep(.el-carousel__indicators) {
            bottom: 16px;

            .el-carousel__indicator {
                padding: 0 4px;

                .el-carousel__button {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    background: rgba(255, 255, 255, 0.5);
                    transition: all 0.3s ease;
                }

                &.is-active .el-carousel__button {
                    width: 24px;
                    border-radius: 4px;
                    background: white;
                }
            }
        }

        :deep(.el-carousel__arrow) {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid var(--gray-200);
            color: var(--gray-600);
            width: 40px;
            height: 40px;
            border-radius: 50%;
            transition: all 0.2s ease;

            &:hover {
                background: white;
                color: var(--primary-600);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
        }

        .empty-carousel {
            height: 420px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--gray-400);
            background: var(--gray-50);
            font-size: 16px;
        }

        .carousel-item-content {
            position: relative;
            width: 100%;
            height: 100%;
            cursor: pointer;

            .carousel-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                transition: transform 0.5s ease;
            }

            &:hover .carousel-img {
                transform: scale(1.02);
            }

            .carousel-overlay {
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                background: linear-gradient(to top, rgba(17, 24, 39, 0.8), rgba(17, 24, 39, 0.2), transparent);
                padding: 48px 32px 32px;
                color: white;

                .carousel-title {
                    margin: 0;
                    font-size: 28px;
                    font-weight: 600;
                    letter-spacing: -0.5px;
                }
            }
        }
    }

    .activity-intro {
        background: white;
        border-radius: 16px;
        padding: 48px;
        border: 1px solid var(--gray-200);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        line-height: 1.8;

        h2 {
            text-align: center;
            color: var(--gray-900);
            margin-bottom: 32px;
            font-size: 32px;
            font-weight: 600;
            letter-spacing: -0.5px;
        }

        p {
            color: var(--gray-600);
            margin-bottom: 24px;
            font-size: 16px;
            line-height: 1.8;
        }

        ul {
            padding-left: 0;
            list-style: none;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin: 32px 0;

            li {
                color: var(--gray-700);
                font-size: 15px;
                padding: 16px 20px;
                background: var(--gray-50);
                border-radius: 16px;
                border: 1px solid var(--gray-200);
                transition: all 0.2s ease;

                &:hover {
                    background: var(--primary-50);
                    border-color: var(--primary-100);
                    transform: translateY(-2px);
                }
            }
        }

        p:last-child {
            text-align: center;
            color: var(--primary-600);
            font-weight: 500;
            margin-top: 32px;
            padding: 16px 24px;
            background: var(--primary-50);
            border-radius: 16px;
            display: inline-block;
            width: 100%;
        }
    }
}

@media (max-width: 768px) {
    .front-home {
        .carousel-wrapper {
            margin-bottom: 24px;
            border-radius: 16px;

            .carousel-item-content .carousel-overlay {
                padding: 32px 20px 24px;

                .carousel-title {
                    font-size: 20px;
                }
            }

            .empty-carousel {
                height: 280px;
            }
        }

        .activity-intro {
            padding: 28px 20px;

            h2 {
                font-size: 24px;
                margin-bottom: 24px;
            }

            ul {
                grid-template-columns: 1fr;
                gap: 12px;

                li {
                    padding: 14px 16px;
                    font-size: 14px;
                    border-radius: 16px;
                }
            }
        }
    }
}
</style>