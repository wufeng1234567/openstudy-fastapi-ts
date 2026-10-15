<template>
  <el-dialog v-model="dialogVisible" title="图片编辑" width="800px" :close-on-click-modal="false" append-to-body
    class="image-editor-dialog" @closed="handleClosed">
    <div class="image-editor-body" v-loading="loading">
      <div class="cropper-container" v-if="src">
        <cropper ref="cropperRef" class="cropper" :src="imgSrc" :stencil-props="stencilProps"
          :image-restriction="imageRestriction" :default-boundaries="defaultBoundaries"
          :transformer-wrapper="transformerWrapper" :style="{ width: '100%', height: '100%' }" />
      </div>
    </div>

    <template #footer>
      <div class="editor-footer">
        <div class="toolbar-left" v-if="showToolbar">
          <el-button-group>
            <el-tooltip content="向左旋转" placement="top">
              <el-button class="toolbar-btn" :icon="RefreshLeft" @click="rotate(-90)" />
            </el-tooltip>
            <el-tooltip content="向右旋转" placement="top">
              <el-button class="toolbar-btn" :icon="RefreshRight" @click="rotate(90)" />
            </el-tooltip>
          </el-button-group>
          <el-tooltip content="水平翻转" placement="top">
            <el-button class="toolbar-btn" :icon="ScaleToOriginal" @click="flipHorizontal" />
          </el-tooltip>
          <el-tooltip content="垂直翻转" placement="top">
            <el-button class="toolbar-btn" :icon="FullScreen" @click="flipVertical" />
          </el-tooltip>
          <el-tooltip content="放大" placement="top">
            <el-button class="toolbar-btn" :icon="ZoomIn" @click="zoomIn" />
          </el-tooltip>
          <el-tooltip content="缩小" placement="top">
            <el-button class="toolbar-btn" :icon="ZoomOut" @click="zoomOut" />
          </el-tooltip>
          <el-button class="toolbar-btn reset-btn" @click="reset">重置</el-button>
        </div>
        <div class="toolbar-right">
          <el-button class="footer-cancel-btn" @click="handleCancel">取消</el-button>
          <el-button class="footer-save-btn" @click="handleSave" :loading="saving">确认</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Cropper } from 'vue-advanced-cropper'
import { RefreshLeft, RefreshRight, ScaleToOriginal, FullScreen, ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import 'vue-advanced-cropper/dist/style.css'

const props = defineProps({
  src: { type: String, default: '' },
  visible: { type: Boolean, default: false },
  cropperProps: { type: Object, default: () => ({}) },
  showToolbar: { type: Boolean, default: true }
})

const emit = defineEmits(['update:visible', 'save', 'cancel'])

const dialogVisible = ref(false)
const cropperRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const imgSrc = ref('')

const stencilProps = computed(() => ({
  ...props.cropperProps,
  handlers: {},
  lines: {}
}))

const imageRestriction = ref('fit-area')
const defaultBoundaries = ref('fill')

const transformerWrapper = ref({
  grid: true
})

watch(() => props.visible, (val) => {
  dialogVisible.value = val
  if (val && props.src) {
    imgSrc.value = props.src
  }
})

watch(dialogVisible, (val) => {
  emit('update:visible', val)
})

const getCropper = () => {
  return cropperRef.value
}

const rotate = (deg) => {
  const cropper = getCropper()
  if (cropper) {
    cropper.rotate(deg)
  }
}

const flipHorizontal = () => {
  const cropper = getCropper()
  if (cropper) {
    cropper.flip(true, false)
  }
}

const flipVertical = () => {
  const cropper = getCropper()
  if (cropper) {
    cropper.flip(false, true)
  }
}

const zoomIn = () => {
  const cropper = getCropper()
  if (cropper) {
    cropper.zoom(1.2)
  }
}

const zoomOut = () => {
  const cropper = getCropper()
  if (cropper) {
    cropper.zoom(0.8)
  }
}

const reset = () => {
  const cropper = getCropper()
  if (cropper) {
    cropper.reset()
  }
}

const handleSave = async () => {
  const cropper = getCropper()
  if (!cropper) return

  saving.value = true
  try {
    const { canvas } = cropper.getResult()
    if (canvas) {
      canvas.toBlob((blob) => {
        if (blob) {
          emit('save', blob)
        }
        saving.value = false
        dialogVisible.value = false
      }, 'image/png')
    } else {
      saving.value = false
      dialogVisible.value = false
    }
  } catch (e) {
    saving.value = false
    emit('save', null)
    dialogVisible.value = false
  }
}

const handleCancel = () => {
  emit('cancel')
  dialogVisible.value = false
}

const handleClosed = () => {
  imgSrc.value = ''
}
</script>

<style scoped lang="scss">
.image-editor-dialog {
  :deep(.el-dialog__body) {
    padding: 0;
  }

  .image-editor-body {
    min-height: 400px;
    background: #f3f4f6;
  }

  .cropper-container {
    width: 100%;
    height: 450px;
  }

  .cropper {
    width: 100%;
    height: 100%;
  }

  .editor-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;

    .toolbar-left {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .toolbar-btn {
      border-radius: 6px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-1px);
      }

      &.reset-btn {
        font-size: 12px;
        padding: 7px 12px;
      }
    }

    .toolbar-right {
      display: flex;
      gap: 8px;
      flex-shrink: 0;

      .footer-cancel-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 7px 20px;
        color: #6b7280;
        background: #fff;
        border: 1px solid #e5e7eb;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          border-color: #d1d5db;
          color: #4b5563;
          transform: translateY(-2px);
        }
      }

      .footer-save-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 7px 20px;
        color: #1f2937;
        background: #fff;
        border: 1px solid #d1d5db;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          border-color: #9ca3af;
          color: #1f2937;
          transform: translateY(-2px);
        }
      }
    }
  }
}
</style>