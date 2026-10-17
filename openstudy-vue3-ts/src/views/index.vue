<template>
  <div class="app-container home-page">
    <!-- 轮播图区域 -->
    <div class="carousel-wrapper" v-loading="loading">
      <el-carousel
        v-if="carouselList.length > 0"
        :interval="5000"
        arrow="always"
        height="420px"
        indicator-position="outside"
      >
        <el-carousel-item v-for="item in carouselList" :key="item.id">
          <div class="carousel-item-content" @click="goTarget(item.targetUrl)">
            <img
              :src="item.imageUrl"
              :alt="item.title"
              loading="lazy"
              class="carousel-img"
            />
            <div class="carousel-overlay">
              <h3 class="carousel-title">{{ item.title }}</h3>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>
      <div v-else class="empty-carousel">暂无轮播图</div>
    </div>

    <!-- 活动介绍 -->
    <div class="activity-intro">
      <h2>openstudy 正式上线</h2>
      <p>全新「OpenStudy」已全面启用。本系统为在校学生打造高效、专注、个性化的自主学习环境。</p>
      <ul>
        <li><OsIcon name="check-circle" :size="15" class="li-ico" />智能制定个性化学习计划</li>
        <li><OsIcon name="check-circle" :size="15" class="li-ico" />实时在线答疑与辅导支持</li>
        <li><OsIcon name="check-circle" :size="15" class="li-ico" />海量优质学习资源库（视频 / 题库 / 笔记）</li>
        <li><OsIcon name="check-circle" :size="15" class="li-ico" />学习进度自动追踪与周报反馈</li>
        <li><OsIcon name="check-circle" :size="15" class="li-ico" />自习室预约、专注计时、成就激励</li>
      </ul>
      <p style="margin-top: 16px; text-align: center; color: var(--os-accent);">
        快来体验，开启你的高效学习之旅
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Index' })
import { ref, onMounted } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { listCarouselAll } from '@/api/carousel/carousel'

const carouselList = ref([])
const loading = ref(true)

function fetchCarouselList() {
  loading.value = true
  listCarouselAll()
    .then(response => {
      const data = response.data || []
      // 拼接完整图片路径，并确保是字符串
      carouselList.value = data.map(item => ({
        ...item,
        imageUrl: (import.meta.env.VITE_APP_BASE_API || '') + (item.imageUrl || '')
      }))
    })
    .finally(() => {
      loading.value = false
    })
}

onMounted(() => {
  fetchCarouselList()
})

function goTarget(url) {
  if (url && url.trim()) {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}
</script>

<style scoped lang="scss">
.home-page {
  padding: 20px;

  .carousel-wrapper {
    margin-bottom: 32px;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    background-color: #f5f7fa;

    .empty-carousel {
      height: 320px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #909399;
      font-size: 16px;
    }

    .carousel-item-content {
      position: relative;
      width: 100%;
      height: 100%;
      cursor: pointer;
      user-select: none;

      .carousel-img {
        width: 100%;
        height: 100%;
        object-fit: cover; /* 关键：保证图片填充且不变形 */
        display: block;
      }

      .carousel-overlay {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: linear-gradient(to top, rgba(0, 0, 0, 0.6), transparent);
        padding: 20px 24px 12px;
        color: white;

        .carousel-title {
          margin: 0;
          font-size: 20px;
          font-weight: 600;
          letter-spacing: 1px;
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
        }
      }
    }
  }

  .activity-intro {
    max-width: 800px;
    max-width: 100%;
    margin: 0 auto;
    padding: 24px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 16px rgba(0, 0, 0, 0.06);
    line-height: 1.7;

    h2 {
      text-align: center;
      color: #1d4ed8;
      margin-bottom: 20px;
      font-size: 26px;
    }

    p {
      color: #4b5563;
      margin-bottom: 16px;
    }

    ul {
      padding-left: 0;
      margin: 16px 0;
      list-style: none;

      li {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-bottom: 10px;
        color: var(--os-text-2);
        line-height: 1.6;
      }

      .li-ico {
        margin-top: 2px;
        color: var(--os-accent);
        flex: none;
      }
    }
  }
}

// 响应式优化
@media (max-width: 868px) {
  .home-page {
    padding: 12px;

    .carousel-wrapper {
      border-radius: 6px;
    }

    .activity-intro {
      padding: 18px;
    }

    .carousel-title {
      font-size: 18px !important;
    }
  }
}
</style>