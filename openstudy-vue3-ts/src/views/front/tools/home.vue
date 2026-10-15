<template>
    <div class="home-page">
        <div class="page-header">
            <h1 class="page-title">🔧 实用工具箱</h1>
            <p class="page-subtitle">一站式文件处理与转换工具</p>
        </div>

        <div class="tool-grid">
            <div class="tool-card" @click="goTo('watermark')">
                <div class="tool-icon" style="background: #e8f4ff;">
                    <el-icon :size="32">
                        <Picture />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">图片水印工具</h3>
                    <p class="tool-desc">为图片添加文字水印，支持旋转、透明度调整</p>
                </div>
                <div class="tool-arrow">
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </div>
            </div>

            <div class="tool-card" @click="goTo('convert')">
                <div class="tool-icon" style="background: #f0f9eb;">
                    <el-icon :size="32">
                        <Document />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">文档转换工具</h3>
                    <p class="tool-desc">PDF ↔ Word ↔ MD ↔ TXT ↔ 图片，支持双向互转</p>
                </div>
                <div class="tool-arrow">
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </div>
            </div>

            <div class="tool-card" @click="goTo('image')">
                <div class="tool-icon" style="background: #fdf6ec;">
                    <el-icon :size="32">
                        <MagicStick />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">图片处理工具</h3>
                    <p class="tool-desc">图片裁剪、旋转、缩放、翻转</p>
                </div>
                <div class="tool-arrow">
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </div>
            </div>

            <div class="tool-card" @click="goTo('classDiagram')">
                <div class="tool-icon" style="background: #f3e8ff;">
                    <el-icon :size="32">
                        <DataLine />
                    </el-icon>
                </div>
                <div class="tool-content">
                    <h3 class="tool-title">类图生成</h3>
                    <p class="tool-desc">粘贴 Java 代码，自动生成 UML 类图，支持导出</p>
                </div>
                <div class="tool-arrow">
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontToolsHome' })
import { useRouter } from 'vue-router'
import { Picture, Document, MagicStick, DataLine, ArrowRight } from '@element-plus/icons-vue'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

const goTo = (path) => {
    cacheStore.setLastVisited('tools', path)
    router.push(`/front/tools/${path}`)
}
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