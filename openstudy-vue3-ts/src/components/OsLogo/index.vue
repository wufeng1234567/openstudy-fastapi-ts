<!--
  OsLogo —— OpenStudy 品牌标（黑底圆角 + 白色字母 O）
  ============================================================================
  几何与 `public/favicon.svg` **同一套**：黑色圆角方块 + 居中白色 O。
  抽成组件是为了三处共用、不再各写一遍：

    1. 侧栏品牌行（26px）
    2. 对话页 hero 的圆标（40px，原来那个星星图标）
    3. 登录页等需要露 logo 的地方

  ⚠️ 为什么不放进 `OsIcon`：
     OsIcon 是「24 栅格 + 1.75 描边 + currentColor」的**线性图标集**，
     而这是**实心品牌标**（自带底色、反白文字）。混进去会破坏那套约定
     （stroke/fill 一改，整批图标都会走形）。

  ⚠️ 为什么用路径画 O 而不是 <text>：
     <text> 依赖系统字体，在不同机器上字宽/字重会漂 —— favicon 与界内 logo
     就不一致了；路径在任何尺寸下都稳定，16px 也清晰。
-->
<template>
  <span
    class="os-logo"
    :style="{
      width: size + 'px',
      height: size + 'px',
      borderRadius: Math.round(size * 0.3) + 'px',
      background: bg,
      color: fg
    }"
    aria-hidden="true"
  >
    <svg :width="size" :height="size" viewBox="0 0 64 64" fill="none">
      <!-- 与 favicon.svg 完全相同的 O 路径（fill-rule=evenodd 挖出内孔） -->
      <path
        fill="currentColor"
        fill-rule="evenodd"
        d="M32 15a17 17 0 1 0 0 34 17 17 0 0 0 0-34zm0 9.6a7.4 7.4 0 1 1 0 14.8 7.4 7.4 0 0 1 0-14.8z"
      />
    </svg>
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 边长（px）；圆角按 30% 自动算，与侧栏 26px/8px 的比例一致 */
    size?: number
    /** 底色，默认主色（近黑） */
    bg?: string
    /** 字母颜色 */
    fg?: string
  }>(),
  {
    size: 26,
    bg: 'var(--os-primary)',
    fg: '#fff'
  }
)
</script>

<style scoped lang="scss">
.os-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  /* 图形自带内边距感：O 的画布是 64，O 本身占 34/64，视觉上已经留白 */
  overflow: hidden;

  svg {
    display: block;
  }
}
</style>
