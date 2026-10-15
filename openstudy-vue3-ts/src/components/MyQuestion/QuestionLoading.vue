<!-- src/components/MyQuestion/QuestionLoading.vue -->
<template>
  <div class="loading-container">
    <el-skeleton :rows="6" animated />
  </div>
</template>

<style scoped>
.loading-container {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
</style>