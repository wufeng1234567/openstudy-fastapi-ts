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
        <h2 class="tool-title">类图生成</h2>
        <p class="tool-desc">粘贴 Java 代码，自动生成 UML 类图，支持导出 SVG/PNG/JPG/Visio</p>
      </div>

      <div class="diagram-layout">
        <!-- 左栏：代码输入 -->
        <div class="code-panel">
          <div class="panel-title">
            <span>Java 代码</span>
            <el-button class="example-btn" size="small" @click="loadExample">示例代码</el-button>
          </div>
          <el-input v-model="javaCode" type="textarea" :rows="20"
            placeholder="粘贴 Java 代码（支持 class、interface、abstract class）..." class="code-input" />
          <div class="code-actions">
            <el-button class="parse-btn" @click="handleParse" :loading="isParsing">
              <el-icon>
                <DataLine />
              </el-icon>
              解析生成类图
            </el-button>
          </div>
        </div>

        <!-- 右栏：画布展示 -->
        <div class="canvas-panel">
          <div class="canvas-toolbar">
            <div class="toolbar-left">
              <el-button-group>
                <el-button size="small" @click="zoomIn" title="放大">
                  <el-icon>
                    <ZoomIn />
                  </el-icon>
                </el-button>
                <el-button size="small" @click="zoomOut" title="缩小">
                  <el-icon>
                    <ZoomIn />
                  </el-icon>
                </el-button>
                <el-button size="small" @click="fitView" title="适应画布">
                  <el-icon>
                    <FullScreen />
                  </el-icon>
                </el-button>
              </el-button-group>
              <el-button size="small" @click="clearCanvas" class="clear-btn">
                <el-icon>
                  <Delete />
                </el-icon>
                清空
              </el-button>
            </div>
            <div class="toolbar-right">
              <el-dropdown @command="handleExport" trigger="click">
                <el-button size="small" class="export-btn">
                  <el-icon>
                    <Download />
                  </el-icon>
                  导出
                  <el-icon class="el-icon--right">
                    <ArrowDown />
                  </el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="svg">导出 SVG（矢量图）</el-dropdown-item>
                    <el-dropdown-item command="png">导出 PNG（透明背景）</el-dropdown-item>
                    <el-dropdown-item command="jpg">导出 JPG（白色背景）</el-dropdown-item>
                    <el-dropdown-item command="vsdx">导出 Visio (.vsdx)</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>

          <div class="canvas-container" ref="canvasContainer" @wheel.prevent>
            <div class="canvas-area" ref="canvasArea" @wheel.prevent></div>
            <div v-if="!hasDiagram" class="canvas-empty">
              <el-icon class="empty-icon">
                <DataLine />
              </el-icon>
              <p>在左侧粘贴 Java 代码，点击"解析生成类图"</p>
            </div>
          </div>

          <!-- 右键菜单 -->
          <div v-if="contextMenu.visible" class="context-menu"
            :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.stop>
            <div class="menu-item" @click="deleteNode">删除节点</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontToolsClassDiagram' })
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, DataLine, ZoomIn, FullScreen, Delete, Download, ArrowDown
} from '@element-plus/icons-vue'
import { useJavaParser, EXAMPLE_JAVA_CODE } from '@/composables/useJavaParser'
import { useDiagramExport } from '@/composables/useDiagramExport'

// ---- 状态 ----
const javaCode = ref('')
const isParsing = ref(false)
const hasDiagram = ref(false)
const canvasContainer = ref(null)
const canvasArea = ref(null)

const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  nodeId: null
})

// ---- 解析器和导出 ----
const { parse } = useJavaParser()
const { exportSvg, exportPng, exportJpg, exportVisx } = useDiagramExport()

// ---- LogicFlow 实例 ----
let lf = null
let currentClasses = []
let currentRelations = []

// ---- LogicFlow 初始化 ----
function initLogicFlow() {
  Promise.all([
    import('@logicflow/core'),
    import('@logicflow/extension')
  ]).then(([coreModule, extModule]) => {
    const LogicFlow = coreModule.default
    const { HtmlNode, HtmlNodeModel, PolylineEdge, PolylineEdgeModel } = coreModule
    const { DndPanel, SelectionSelect } = extModule

    // 注册插件
    LogicFlow.use(DndPanel)
    LogicFlow.use(SelectionSelect)

    lf = new LogicFlow({
      container: canvasArea.value,
      grid: {
        visible: true,
        size: 20,
        type: 'dot'
      },
      background: {
        color: '#f7f8fa'
      },
      moveable: true,
      wheelZoom: true,
      zoom: {
        min: 0.3,
        max: 3,
        step: 0.1
      },
      keyboard: false
    })

    // 注册自定义 UML 类节点
    registerUmlClassNode(HtmlNode, HtmlNodeModel)

    // 注册自定义边
    registerEdges(PolylineEdge, PolylineEdgeModel)

    // 确保画布尺寸正确
    lf.resize()

    // 启用滚轮缩放
    lf.setWheelZoom(true)

    // 监听右键菜单
    lf.on('node:contextmenu', ({ data, e }) => {
      e.preventDefault()
      e.stopPropagation()
      contextMenu.value = {
        visible: true,
        x: e.clientX - canvasContainer.value.getBoundingClientRect().left,
        y: e.clientY - canvasContainer.value.getBoundingClientRect().top,
        nodeId: data.id
      }
    })

    // 点击空白处关闭菜单
    lf.on('blank:click', () => {
      contextMenu.value.visible = false
    })

    lf.render({})
  }).catch(err => {
    console.error('LogicFlow 初始化失败:', err)
  })
}

// ---- 注册 UML 类节点（使用 HtmlNode） ----
function registerUmlClassNode(HtmlNode, HtmlNodeModel) {
  class UmlClassModel extends HtmlNodeModel {
    setAttributes() {
      const { properties } = this
      const attrCount = (properties.attributes || []).length
      const methodCount = (properties.methods || []).length
      const lineHeight = 20
      const headerHeight = properties.type === 'class' ? 36 : 52
      const attrHeight = Math.max(attrCount, 1) * lineHeight + 12
      const methodHeight = Math.max(methodCount, 1) * lineHeight + 12

      this.width = 240
      this.height = headerHeight + attrHeight + methodHeight
      this.isShowAnchor = true
    }

    getDefaultAnchor() {
      const { width, height, x, y, id } = this
      return [
        {
          x: x - width / 2,
          y: y,
          type: 'left',
          id: `${id}_0`
        },
        {
          x: x + width / 2,
          y: y,
          type: 'right',
          id: `${id}_1`
        },
        {
          x: x,
          y: y - height / 2,
          type: 'top',
          id: `${id}_2`
        },
        {
          x: x,
          y: y + height / 2,
          type: 'bottom',
          id: `${id}_3`
        }
      ]
    }
  }

  class UmlClassView extends HtmlNode {
    setHtml(rootEl) {
      const { properties } = this.props.model
      const attrCount = (properties.attributes || []).length
      const methodCount = (properties.methods || []).length
      const lineHeight = 20
      const headerHeight = properties.type === 'class' ? 36 : 52
      const attrHeight = Math.max(attrCount, 1) * lineHeight + 12
      const methodHeight = Math.max(methodCount, 1) * lineHeight + 12
      const totalHeight = headerHeight + attrHeight + methodHeight
      const typeLabel = properties.type === 'interface' ? '«interface»'
        : properties.type === 'abstract' ? '«abstract»' : ''

      const div = document.createElement('div')
      div.className = 'uml-class-node'
      div.style.width = '240px'
      div.style.height = totalHeight + 'px'
      div.style.background = '#fff'
      div.style.border = '1.5px solid #303133'
      div.style.borderRadius = '4px'
      div.style.fontFamily = 'Consolas, Monaco, monospace'
      div.style.fontSize = '12px'
      div.style.overflow = 'hidden'
      div.style.boxSizing = 'border-box'

      const header = document.createElement('div')
      header.style.background = '#e8f4fd'
      header.style.padding = '6px 12px'
      header.style.borderBottom = '1px solid #303133'
      header.style.textAlign = 'center'
      header.style.fontWeight = 'bold'
      header.style.fontSize = '14px'
      header.style.color = '#1f2937'
      header.style.lineHeight = '1.3'
      if (typeLabel) {
        header.innerHTML = `<div style="font-size:10px;color:#606266;font-weight:normal">${typeLabel}</div>${escapeHtml(properties.name || '')}`
      } else {
        header.textContent = properties.name || ''
      }
      div.appendChild(header)

      const attrs = document.createElement('div')
      attrs.style.padding = '6px 12px'
      attrs.style.borderBottom = '1px solid #dcdfe6'
      attrs.style.minHeight = lineHeight + 'px'
      attrs.style.lineHeight = lineHeight + 'px'
      attrs.style.color = '#303133'
      if (properties.attributes && properties.attributes.length > 0) {
        attrs.innerHTML = properties.attributes.map(a => `<div>${escapeHtml(a)}</div>`).join('')
      } else {
        attrs.innerHTML = '&nbsp;'
      }
      div.appendChild(attrs)

      const methods = document.createElement('div')
      methods.style.padding = '6px 12px'
      methods.style.minHeight = lineHeight + 'px'
      methods.style.lineHeight = lineHeight + 'px'
      methods.style.color = '#303133'
      if (properties.methods && properties.methods.length > 0) {
        methods.innerHTML = properties.methods.map(m => `<div>${escapeHtml(m)}</div>`).join('')
      } else {
        methods.innerHTML = '&nbsp;'
      }
      div.appendChild(methods)

      rootEl.innerHTML = ''
      rootEl.appendChild(div)
    }
  }

  lf.register({
    type: 'uml-class',
    view: UmlClassView,
    model: UmlClassModel
  })
}

function escapeHtml(str) {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

// ---- 注册自定义边 ----
function registerEdges(PolylineEdge, PolylineEdgeModel) {
  class BaseEdge extends PolylineEdgeModel {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        fill: 'none'
      }
    }
  }

  class ExtendsEdge extends BaseEdge {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        fill: 'none',
        endArrow: {
          type: 'triangle',
          width: 10,
          height: 10,
          fill: '#fff',
          stroke: '#000',
          strokeWidth: 1
        }
      }
    }
  }

  class ImplementsEdge extends BaseEdge {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        strokeDasharray: '5 3',
        fill: 'none',
        endArrow: {
          type: 'triangle',
          width: 10,
          height: 10,
          fill: '#fff',
          stroke: '#000',
          strokeWidth: 1
        }
      }
    }
  }

  class AssociationEdge extends BaseEdge {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        fill: 'none',
        endArrow: {
          type: 'triangle',
          width: 8,
          height: 8,
          fill: '#000',
          stroke: '#000',
          strokeWidth: 1
        }
      }
    }
  }

  class DependencyEdge extends BaseEdge {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        strokeDasharray: '5 3',
        fill: 'none',
        endArrow: {
          type: 'triangle',
          width: 8,
          height: 8,
          fill: '#000',
          stroke: '#000',
          strokeWidth: 1
        }
      }
    }
  }

  class AggregationEdge extends BaseEdge {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        fill: 'none',
        endArrow: {
          type: 'diamond',
          width: 12,
          height: 12,
          fill: '#fff',
          stroke: '#000',
          strokeWidth: 1
        }
      }
    }
  }

  class CompositionEdge extends BaseEdge {
    getEdgeStyle() {
      return {
        stroke: '#000',
        strokeWidth: 1,
        fill: 'none',
        endArrow: {
          type: 'diamond',
          width: 12,
          height: 12,
          fill: '#000',
          stroke: '#000',
          strokeWidth: 1
        }
      }
    }
  }

  lf.register({ type: 'extends', view: ExtendsEdge, model: PolylineEdgeModel })
  lf.register({ type: 'implements', view: ImplementsEdge, model: PolylineEdgeModel })
  lf.register({ type: 'association', view: AssociationEdge, model: PolylineEdgeModel })
  lf.register({ type: 'dependency', view: DependencyEdge, model: PolylineEdgeModel })
  lf.register({ type: 'aggregation', view: AggregationEdge, model: PolylineEdgeModel })
  lf.register({ type: 'composition', view: CompositionEdge, model: PolylineEdgeModel })
}

// ---- 解析并渲染 ----
function handleParse() {
  if (!javaCode.value.trim()) {
    ElMessage.warning('请先输入 Java 代码')
    return
  }

  isParsing.value = true

  setTimeout(() => {
    try {
      const result = parse(javaCode.value)

      if (result.classes.length === 0) {
        ElMessage.warning('未解析到任何类，请检查代码格式')
        isParsing.value = false
        return
      }

      currentClasses = result.classes
      currentRelations = result.relations

      renderDiagram(result)
      hasDiagram.value = true
      ElMessage.success(`成功解析 ${result.classes.length} 个类，${result.relations.length} 条关系`)
    } catch (err) {
      console.error('解析失败:', err)
      ElMessage.error('代码解析失败，请检查代码格式')
    } finally {
      isParsing.value = false
    }
  }, 100)
}

// ---- 渲染类图到画布 ----
function renderDiagram({ classes, relations }) {
  if (!lf) {
    console.error('lf 实例不存在')
    return
  }

  // 清空画布
  lf.clearData()

  // 添加节点
  const nodeIdMap = {}
  for (const cls of classes) {
    try {
      const nodeData = lf.addNode({
        type: 'uml-class',
        x: cls.x,
        y: cls.y,
        properties: {
          name: cls.name,
          type: cls.type,
          attributes: cls.attributes,
          methods: cls.methods
        }
      })
      const nodeId = nodeData.id || nodeData
      nodeIdMap[cls.name] = nodeId
    } catch (err) {
      console.error('节点添加失败:', cls.name, err)
    }
  }

  // 统计每个目标节点的入边数量
  const targetEdgeCount = {}
  for (const rel of relations) {
    const targetId = nodeIdMap[rel.to]
    if (targetId) {
      targetEdgeCount[targetId] = (targetEdgeCount[targetId] || 0) + 1
    }
  }

  // 记录每个目标节点已分配的边索引
  const targetEdgeIndex = {}
  for (const targetId in targetEdgeCount) {
    targetEdgeIndex[targetId] = 0
  }

  // 添加边 - 根据相对位置选择锚点避免交叉
  for (const rel of relations) {
    const sourceId = nodeIdMap[rel.from]
    const targetId = nodeIdMap[rel.to]

    if (sourceId && targetId) {
      try {
        const sourceNode = lf.graphModel.getNodeModelById(sourceId)
        const targetNode = lf.graphModel.getNodeModelById(targetId)

        let edgeConfig = {
          type: rel.type,
          sourceNodeId: sourceId,
          targetNodeId: targetId
        }

        // 如果目标节点有多条边连接，则错开锚点
        if (targetEdgeCount[targetId] > 1) {
          const edgeIndex = targetEdgeIndex[targetId]

          const sx = sourceNode.x || 0
          const sy = sourceNode.y || 0
          const tx = targetNode.x || 0
          const ty = targetNode.y || 0
          const tw = targetNode.width || 120
          const th = targetNode.height || 80

          const isFromLeft = sx < tx
          const isFromTop = sy < ty

          const anchors = [
            { x: tx - tw / 2, y: ty },
            { x: tx + tw / 2, y: ty },
            { x: tx, y: ty - th / 2 },
            { x: tx, y: ty + th / 2 }
          ]

          let anchorIndex
          if (isFromLeft) {
            anchorIndex = edgeIndex % 2 === 0 ? 2 : 3
          } else if (sx > tx) {
            anchorIndex = edgeIndex % 2 === 0 ? 2 : 3
          } else if (isFromTop) {
            anchorIndex = edgeIndex % 2 === 0 ? 0 : 1
          } else {
            anchorIndex = edgeIndex % 2 === 0 ? 0 : 1
          }

          const endAnchor = anchors[anchorIndex]

          const sourceAnchors = [
            { x: sx + (sourceNode.width || 120) / 2, y: sy },
            { x: sx - (sourceNode.width || 120) / 2, y: sy },
            { x: sx, y: sy + (sourceNode.height || 80) / 2 },
            { x: sx, y: sy - (sourceNode.height || 80) / 2 }
          ]

          let sourceAnchorIndex
          if (anchorIndex === 0) sourceAnchorIndex = 1
          else if (anchorIndex === 1) sourceAnchorIndex = 0
          else if (anchorIndex === 2) sourceAnchorIndex = 3
          else sourceAnchorIndex = 2

          edgeConfig.startPoint = sourceAnchors[sourceAnchorIndex]
          edgeConfig.endPoint = endAnchor

          targetEdgeIndex[targetId]++
        }

        lf.addEdge(edgeConfig)
      } catch (err) {
        console.error('边添加失败:', err)
      }
    }
  }

  // 适应画布
  setTimeout(() => {
    if (lf) {
      lf.resize()
      lf.fitView()
      lf.resetZoom()
    }
  }, 100)
}

// ---- 工具栏操作 ----
function zoomIn() {
  if (lf) lf.zoom(0.1)
}

function zoomOut() {
  if (lf) lf.zoom(-0.1)
}

function fitView() {
  if (lf) lf.fitView()
}

function clearCanvas() {
  if (lf) {
    lf.clearData()
    hasDiagram.value = false
    currentClasses = []
    currentRelations = []
    ElMessage.success('画布已清空')
  }
}

// ---- 右键删除 ----
function deleteNode() {
  if (contextMenu.value.nodeId && lf) {
    lf.deleteNode(contextMenu.value.nodeId)
    contextMenu.value.visible = false
    ElMessage.success('节点已删除')
  }
}

// ---- 导出 ----
async function handleExport(format) {
  if (!hasDiagram.value) {
    ElMessage.warning('请先生成类图')
    return
  }

  try {
    switch (format) {
      case 'svg':
        exportSvg(lf)
        break
      case 'png':
        await exportPng(canvasArea.value)
        break
      case 'jpg':
        await exportJpg(canvasArea.value)
        break
      case 'vsdx':
        await exportVisx(currentClasses, currentRelations)
        break
    }
    ElMessage.success('导出成功')
  } catch (err) {
    console.error('导出失败:', err)
    ElMessage.error('导出失败: ' + (err.message || '未知错误'))
  }
}

// ---- 加载示例代码 ----
function loadExample() {
  javaCode.value = EXAMPLE_JAVA_CODE
}

// ---- 点击其他区域关闭菜单 ----
function handleClickOutside(e) {
  if (contextMenu.value.visible) {
    contextMenu.value.visible = false
  }
}

// ---- 生命周期 ----
onMounted(() => {
  initLogicFlow()
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
  if (lf) {
    lf.destroy()
    lf = null
  }
})
</script>

<style scoped lang="scss">
.tool-page {
  max-width: 1400px;
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
    margin-bottom: 24px;

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

  .diagram-layout {
    display: flex;
    gap: 20px;
    min-height: 600px;

    .code-panel {
      flex: 0 0 38%;
      display: flex;
      flex-direction: column;

      .panel-title {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        font-size: 14px;
        font-weight: 600;
        color: #1f2937;

        .example-btn {
          border-radius: 6px;
          font-size: 12px;
          color: #6b7280;
          background: #fff;
          border: 1px solid #e5e7eb;

          &:hover {
            border-color: #d1d5db;
            color: #4b5563;
          }
        }
      }

      .code-input {
        flex: 1;

        :deep(.el-textarea__inner) {
          height: 100% !important;
          font-family: Consolas, Monaco, 'Courier New', monospace;
          font-size: 13px;
          line-height: 1.6;
          border-radius: 12px;
          border-color: #e5e7eb;
          resize: none;

          &:focus {
            border-color: #9ca3af;
          }
        }
      }

      .code-actions {
        margin-top: 12px;
        display: flex;
        gap: 8px;

        .parse-btn {
          flex: 1;
          border-radius: 8px;
          font-weight: 500;
          color: #fff;
          background: #1f2937;
          border: none;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

          &:hover {
            background: #374151;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(31, 41, 55, 0.2);
          }
        }
      }
    }

    .canvas-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      position: relative;

      .canvas-toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        padding: 6px 8px;
        background: #f9fafb;
        border-radius: 8px;
        border: 1px solid #e5e7eb;

        .toolbar-left {
          display: flex;
          align-items: center;
          gap: 8px;

          .el-button-group {
            .el-button {
              border-radius: 6px;
              color: #6b7280;
              background: #fff;
              border: 1px solid #e5e7eb;

              &:hover {
                border-color: #d1d5db;
                color: #4b5563;
              }
            }
          }

          .clear-btn {
            border-radius: 6px;
            color: #b45353;
            background: #fff;
            border: 1px solid #e5e7eb;

            &:hover {
              background: #fef2f2;
              border-color: #e5d0d0;
            }
          }
        }

        .toolbar-right {
          .export-btn {
            border-radius: 6px;
            color: #6b7280;
            background: #fff;
            border: 1px solid #e5e7eb;

            &:hover {
              border-color: #d1d5db;
              color: #4b5563;
            }
          }
        }
      }

      .canvas-container {
        flex: 1;
        position: relative;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        overflow: hidden;
        background: #f7f8fa;
        height: 500px;

        .canvas-area {
          width: 100%;
          height: 100%;
        }

        .canvas-empty {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
          color: #9ca3af;
          pointer-events: none;

          .empty-icon {
            font-size: 48px;
            margin-bottom: 12px;
          }

          p {
            font-size: 14px;
            margin: 0;
          }
        }
      }

      .context-menu {
        position: absolute;
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        overflow: hidden;

        .menu-item {
          padding: 8px 16px;
          font-size: 13px;
          color: #b45353;
          cursor: pointer;
          transition: background 0.2s;

          &:hover {
            background: #fef2f2;
          }
        }
      }
    }
  }
}

@media (max-width: 900px) {
  .diagram-layout {
    flex-direction: column !important;

    .code-panel {
      flex: none !important;
    }
  }
}
</style>
