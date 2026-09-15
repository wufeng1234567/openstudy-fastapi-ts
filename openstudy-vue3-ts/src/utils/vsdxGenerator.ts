/**
 * Visio .vsdx 文件生成器
 * 将 UML 类图数据转换为 Visio 2013+ 格式 (.vsdx)
 * .vsdx 本质是 ZIP 包，内含 XML 文件
 */

import JSZip from 'jszip'
import { saveAs } from 'file-saver'

// Visio 坐标系：1 inch = 96px (屏幕) -> Visio 使用 inch 单位
const PX_TO_INCH = 1 / 96
// 画布到 Visio 的坐标偏移
const OFFSET_X = 1
const OFFSET_Y = 8

/** UML 类数据 */
interface UmlClass {
  name: string
  type?: string
  x?: number
  y?: number
  attributes: string[]
  methods: string[]
}

/** UML 关系数据 */
interface UmlRelation {
  from: string
  to: string
  type: string
}

/**
 * 转义 XML 特殊字符
 */
function escapeXml(str: string): string {
  if (!str) return ''
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

/**
 * 生成 [Content_Types].xml
 */
function generateContentTypes(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
  <Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
  <Override PartName="/visio/pages/_rels/page1.xml.rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
</Types>`
}

/**
 * 生成 _rels/.rels
 */
function generateRootRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/office/2006/relationships/officeDocument" Target="visio/document.xml"/>
</Relationships>`
}

/**
 * 生成 visio/document.xml
 */
function generateDocument(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <DocumentSettings>
    <DocumentProperties>
      <Title>UML Class Diagram</Title>
    </DocumentProperties>
  </DocumentSettings>
  <Pages>
    <Page ID="0" Name="Page-1">
      <PageSheet>
        <PageWidth>11</PageWidth>
        <PageHeight>8.5</PageHeight>
      </PageSheet>
      <Shapes/>
      <Connects/>
    </Page>
  </Pages>
</VisioDocument>`
}

/**
 * 生成 visio/pages/_rels/page1.xml.rels
 */
function generatePageRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>`
}

/**
 * 生成 UML 类的 Visio Shape XML
 */
function generateClassShape(cls: UmlClass, shapeId: number): string {
  const x = (cls.x || 0) * PX_TO_INCH + OFFSET_X
  const y = OFFSET_Y - (cls.y || 0) * PX_TO_INCH

  // 计算高度：类名(0.4) + 属性行数 * 0.25 + 分隔线 + 方法行数 * 0.25
  const headerHeight = 0.4
  const lineHeight = 0.22
  const attrHeight = Math.max(cls.attributes.length, 1) * lineHeight
  const methodHeight = Math.max(cls.methods.length, 1) * lineHeight
  const totalHeight = headerHeight + attrHeight + methodHeight + 0.1
  const width = 2.5

  // 属性文本
  const attrText = cls.attributes.length > 0
    ? cls.attributes.map(a => escapeXml(a)).join('&#10;')
    : ' '

  // 方法文本
  const methodText = cls.methods.length > 0
    ? cls.methods.map(m => escapeXml(m)).join('&#10;')
    : ' '

  const typeName = cls.type === 'interface' ? '«interface»' : cls.type === 'abstract' ? '«abstract»' : ''

  return `    <Shape ID="${shapeId}" Name="Class_${escapeXml(cls.name)}" Type="Group">
      <Cell N="PinX" V="${x.toFixed(4)}"/>
      <Cell N="PinY" V="${y.toFixed(4)}"/>
      <Cell N="Width" V="${width}"/>
      <Cell N="Height" V="${totalHeight.toFixed(4)}"/>
      <Cell N="FillForegnd" V="rgb(255,255,255)"/>
      <Cell N="LineColor" V="rgb(0,0,0)"/>
      <Cell N="LineWeight" V="0.01"/>
      <Shapes>
        <!-- 类名区域 -->
        <Shape ID="${shapeId + 1000}" Name="Header_${escapeXml(cls.name)}" Type="Shape">
          <Cell N="PinX" V="${(width / 2).toFixed(4)}"/>
          <Cell N="PinY" V="${(totalHeight - headerHeight / 2).toFixed(4)}"/>
          <Cell N="Width" V="${width}"/>
          <Cell N="Height" V="${headerHeight}"/>
          <Cell N="FillForegnd" V="rgb(221,235,247)"/>
          <Cell N="LinePattern" V="0"/>
          <Text>
            <cp IX="0"/><pp IX="0"/>
            <TextBlock>
              <Cell N="VerticalAlign" V="1"/>
            </TextBlock>
            ${typeName ? `<cp IX="1" Sz="8"/><pp IX="1"/>${typeName}&#10;` : ''}${escapeXml(cls.name)}
          </Text>
        </Shape>
        <!-- 属性区域 -->
        <Shape ID="${shapeId + 2000}" Name="Attributes_${escapeXml(cls.name)}" Type="Shape">
          <Cell N="PinX" V="${(width / 2).toFixed(4)}"/>
          <Cell N="PinY" V="${(totalHeight - headerHeight - attrHeight / 2).toFixed(4)}"/>
          <Cell N="Width" V="${width}"/>
          <Cell N="Height" V="${attrHeight.toFixed(4)}"/>
          <Cell N="LinePattern" V="0"/>
          <Text>${attrText}</Text>
        </Shape>
        <!-- 方法区域 -->
        <Shape ID="${shapeId + 3000}" Name="Methods_${escapeXml(cls.name)}" Type="Shape">
          <Cell N="PinX" V="${(width / 2).toFixed(4)}"/>
          <Cell N="PinY" V="${(totalHeight - headerHeight - attrHeight - methodHeight / 2).toFixed(4)}"/>
          <Cell N="Width" V="${width}"/>
          <Cell N="Height" V="${methodHeight.toFixed(4)}"/>
          <Cell N="LinePattern" V="0"/>
          <Text>${methodText}</Text>
        </Shape>
      </Shapes>
    </Shape>`
}

/**
 * 生成关系连线的 Visio Shape XML
 */
function generateRelationShape(relation: UmlRelation, shapeId: number, classes: UmlClass[]): string {
  const fromClass = classes.find(c => c.name === relation.from)
  const toClass = classes.find(c => c.name === relation.to)
  if (!fromClass || !toClass) return ''

  const fromX = (fromClass.x || 0) * PX_TO_INCH + OFFSET_X + 1.25
  const fromY = OFFSET_Y - (fromClass.y || 0) * PX_TO_INCH
  const toX = (toClass.x || 0) * PX_TO_INCH + OFFSET_X + 1.25
  const toY = OFFSET_Y - (toClass.y || 0) * PX_TO_INCH

  // 箭头样式
  let endArrow = 0
  let lineColor = 'rgb(0,0,0)'
  let linePattern = 1

  if (relation.type === 'extends') {
    endArrow = 4 // 空心三角
  } else if (relation.type === 'implements') {
    endArrow = 4
    linePattern = 2 // 虚线
  } else {
    endArrow = 1 // 普通箭头
  }

  return `    <Shape ID="${shapeId}" Name="Rel_${relation.from}_${relation.to}" Type="Shape">
      <Cell N="BeginX" V="${fromX.toFixed(4)}"/>
      <Cell N="BeginY" V="${fromY.toFixed(4)}"/>
      <Cell N="EndX" V="${toX.toFixed(4)}"/>
      <Cell N="EndY" V="${toY.toFixed(4)}"/>
      <Cell N="LineColor" V="${lineColor}"/>
      <Cell N="LineWeight" V="0.01"/>
      <Cell N="EndArrow" V="${endArrow}"/>
      <Cell N="LinePattern" V="${linePattern}"/>
      <Text>${escapeXml(relation.type)}</Text>
    </Shape>`
}

/**
 * 生成完整的 page1.xml
 */
function generatePage(classes: UmlClass[], relations: UmlRelation[]): string {
  const shapes: string[] = []
  let shapeId = 1

  // 生成类的 Shape
  const classShapeIds: Record<string, number> = {}
  for (const cls of classes) {
    classShapeIds[cls.name] = shapeId
    shapes.push(generateClassShape(cls, shapeId))
    shapeId += 4 // 每个类占 4 个 ID（group + 3 sub）
  }

  // 生成关系的 Shape
  for (const rel of relations) {
    shapes.push(generateRelationShape(rel, shapeId, classes))
    shapeId++
  }

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Page xmlns="http://schemas.microsoft.com/office/visio/2012/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  ID="0" Name="Page-1">
  <PageSheet>
    <Cell N="PageWidth" V="11"/>
    <Cell N="PageHeight" V="8.5"/>
  </PageSheet>
  <Shapes>
${shapes.join('\n')}
  </Shapes>
  <Connects/>
</Page>`
}

/**
 * 生成并下载 .vsdx 文件
 * @param classes 类数据数组
 * @param relations 关系数据数组
 * @param filename 文件名
 */
export async function generateVsdx(classes: UmlClass[], relations: UmlRelation[], filename: string = 'class-diagram.vsdx'): Promise<void> {
  const zip = new JSZip()

  // 添加文件到 ZIP
  zip.file('[Content_Types].xml', generateContentTypes())
  zip.file('_rels/.rels', generateRootRels())
  zip.file('visio/document.xml', generateDocument())
  zip.file('visio/pages/page1.xml', generatePage(classes, relations))
  zip.file('visio/pages/_rels/page1.xml.rels', generatePageRels())

  // 生成 ZIP 并下载
  const blob = await zip.generateAsync({
    type: 'blob',
    mimeType: 'application/vnd.ms-visio.drawing'
  })

  saveAs(blob, filename)
}
