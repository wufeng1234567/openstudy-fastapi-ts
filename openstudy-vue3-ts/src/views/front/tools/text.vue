<template>
  <div class="tool-page">
    <div class="back-bar">
      <el-button class="back-btn" size="small" @click="$router.push('/front/tools')">
        <el-icon>
          <ArrowLeft />
        </el-icon>
        返回工具箱
      </el-button>
    </div>

    <div class="tool-container">
      <div class="tool-header">
        <h2 class="tool-title">文本工具</h2>
        <p class="tool-desc">文本对比、统计、正则测试、加密解密</p>
      </div>

      <div class="empty-state">
        <el-empty description="文本工具开发中，敬请期待" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from '@element-plus/icons-vue'
</script>

<style scoped lang="scss">
.tool-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;

  .back-bar {
    margin-bottom: 20px;

    .back-btn {
      border-radius: 8px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-1px);
      }
    }
  }

  .tool-container {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 32px;
  }

  .tool-header {
    text-align: center;
    margin-bottom: 32px;

    .tool-title {
      font-size: 20px;
      font-weight: 700;
      color: #1f2937;
      margin: 0 0 8px 0;
    }

    .tool-desc {
      font-size: 14px;
      color: #6b7280;
      margin: 0;
    }
  }

  .empty-state {
    padding: 60px 0;
  }
}
</style>