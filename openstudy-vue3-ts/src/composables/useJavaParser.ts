/**
 * Java 代码解析器 - 使用正则匹配提取类、属性、方法和关系
 */

// 访问修饰符映射为 UML 符号
const ACCESS_MAP: Record<string, string> = {
  'public': '+',
  'protected': '#',
  'private': '-',
  '': '~'
}

interface ParsedClass {
  name: string
  type: string
  extendsClass: string | null
  implementsList: string[]
  attributes: string[]
  methods: string[]
  x?: number
  y?: number
}

interface ParsedRelation {
  from: string
  to: string
  type: string
}

interface ParseResult {
  classes: ParsedClass[]
  relations: ParsedRelation[]
}

/**
 * 解析访问修饰符
 */
function parseAccessModifier(line: string): string {
  const trimmed = line.trim()
  for (const [keyword, symbol] of Object.entries(ACCESS_MAP)) {
    if (keyword && trimmed.startsWith(keyword)) {
      return symbol
    }
  }
  return '~'
}

/**
 * 清理注解和注释行
 */
function cleanLines(code: string): string {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, '') // 块注释
    .replace(/\/\/.*$/gm, '') // 行注释
    .replace(/@\w+(\([^)]*\))?/g, '') // 注解
}

/**
 * 解析类/接口声明
 */
function parseClassDeclarations(code: string): ParsedClass[] {
  const classes: ParsedClass[] = []
  // 匹配 class/interface/abstract class 声明
  const classRegex = /(?:(abstract)\s+)?(class|interface|enum)\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s,]+))?\s*\{/g
  let match: RegExpExecArray | null

  while ((match = classRegex.exec(code)) !== null) {
    const isAbstract = !!match[1]
    const kind = match[2]
    const name = match[3]
    const extendsClass = match[4] || null
    const implementsList = match[5]
      ? match[5].split(',').map(s => s.trim()).filter(Boolean)
      : []

    classes.push({
      name,
      type: isAbstract ? 'abstract' : kind,
      extendsClass,
      implementsList,
      attributes: [],
      methods: []
    })
  }

  return classes
}

/**
 * 从类体中提取属性和方法
 */
function extractClassBody(code: string, className: string): { attributes: string[]; methods: string[] } {
  // 找到类的起始位置
  const classPattern = new RegExp(
    `(?:abstract\\s+)?(?:class|interface|enum)\\s+${className}\\b[^{]*\\{`,
    'g'
  )
  const classMatch = classPattern.exec(code)
  if (!classMatch) return { attributes: [], methods: [] }

  let braceCount = 1
  let start = classMatch.index + classMatch[0].length
  let pos = start

  // 找到匹配的右花括号
  while (pos < code.length && braceCount > 0) {
    if (code[pos] === '{') braceCount++
    if (code[pos] === '}') braceCount--
    pos++
  }

  const body = code.substring(start, pos - 1)
  const attributes: string[] = []
  const methods: string[] = []

  const lines = body.split('\n')

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line || line === '{' || line === '}') continue
    if (line.startsWith('//') || line.startsWith('/*') || line.startsWith('*')) continue
    if (line.startsWith('@')) continue

    // 方法匹配：有括号的行
    const methodMatch = line.match(
      /^(?:(public|private|protected|static|final|abstract|synchronized|native)\s+)*(\w+(?:<[^>]+>)?(?:\[\])?)\s+(\w+)\s*\(([^)]*)\)/
    )
    if (methodMatch) {
      const access = parseAccessModifier(line)
      const returnType = methodMatch[2]
      const methodName = methodMatch[3]
      const params = methodMatch[4].trim()

      const paramStr = params
        ? params.split(',').map(p => {
            const parts = p.trim().split(/\s+/)
            return parts.length >= 2 ? `${parts[parts.length - 1]}: ${parts.slice(0, -1).join(' ')}` : p.trim()
          }).join(', ')
        : ''

      methods.push(`${access}${methodName}(${paramStr}): ${returnType}`)
      continue
    }

    // 属性匹配：以分号结尾的行
    const attrMatch = line.match(
      /^(?:(public|private|protected|static|final|volatile|transient)\s+)*(\w+(?:<[^>]+>)?(?:\[\])?)\s+(\w+)\s*[;=]/
    )
    if (attrMatch) {
      const access = parseAccessModifier(line)
      const type = attrMatch[2]
      const name = attrMatch[3]
      attributes.push(`${access}${name}: ${type}`)
    }
  }

  return { attributes, methods }
}

/**
 * 推断关系（基于类型引用）
 */
function inferRelations(classes: ParsedClass[], code: string): ParsedRelation[] {
  const relations: ParsedRelation[] = []
  const classNames = new Set(classes.map(c => c.name))

  // 1. 继承关系
  for (const cls of classes) {
    if (cls.extendsClass && classNames.has(cls.extendsClass)) {
      relations.push({
        from: cls.name,
        to: cls.extendsClass,
        type: 'extends'
      })
    }
  }

  // 2. 实现关系
  for (const cls of classes) {
    for (const iface of cls.implementsList) {
      if (classNames.has(iface)) {
        relations.push({
          from: cls.name,
          to: iface,
          type: 'implements'
        })
      }
    }
  }

  // 3. 关联关系（通过成员变量类型推断）
  for (const cls of classes) {
    for (const attr of cls.attributes) {
      // 提取类型部分（去掉访问符号和变量名）
      const typeMatch = attr.match(/[:\s]+(\w+(?:<[^>]+>)?)/)
      if (typeMatch) {
        let typeName = typeMatch[1]
        // 处理泛型 List<User> -> User
        const genericMatch = typeName.match(/(\w+)<(\w+)>/)
        if (genericMatch) {
          typeName = genericMatch[2]
        }
        if (classNames.has(typeName) && typeName !== cls.name) {
          // 避免重复关系
          const exists = relations.some(
            r => r.from === cls.name && r.to === typeName
          )
          if (!exists) {
            relations.push({
              from: cls.name,
              to: typeName,
              type: 'association'
            })
          }
        }
      }
    }
  }

  // 4. 依赖关系（通过方法参数类型推断）
  for (const cls of classes) {
    for (const method of cls.methods) {
      const paramSection = method.match(/\(([^)]*)\)/)
      if (paramSection && paramSection[1]) {
        const params = paramSection[1].split(',')
        for (const param of params) {
          const paramType = param.trim().split(/[\s:]+/)[0]
          if (classNames.has(paramType) && paramType !== cls.name) {
            const exists = relations.some(
              r => r.from === cls.name && r.to === paramType
            )
            if (!exists) {
              relations.push({
                from: cls.name,
                to: paramType,
                type: 'dependency'
              })
            }
          }
        }
      }
    }
  }

  return relations
}

/**
 * 计算节点布局位置（简单的网格布局）
 */
function layoutClasses(classes: ParsedClass[]) {
  const cols = Math.ceil(Math.sqrt(classes.length))
  const cellWidth = 280
  const cellHeight = 200
  const startX = 50
  const startY = 50

  classes.forEach((cls, index) => {
    const col = index % cols
    const row = Math.floor(index / cols)
    cls.x = startX + col * (cellWidth + 60)
    cls.y = startY + row * (cellHeight + 80)
  })
}

/**
 * 主解析函数
 * @param code - Java 源代码
 * @returns {{ classes: Array, relations: Array }}
 */
export function useJavaParser() {
  function parse(code: string): ParseResult {
    if (!code || !code.trim()) {
      return { classes: [], relations: [] }
    }

    const cleanedCode = cleanLines(code)
    const classes = parseClassDeclarations(cleanedCode)

    // 提取每个类的属性和方法
    for (const cls of classes) {
      const { attributes, methods } = extractClassBody(cleanedCode, cls.name)
      cls.attributes = attributes
      cls.methods = methods
    }

    // 推断关系
    const relations = inferRelations(classes, cleanedCode)

    // 计算布局
    layoutClasses(classes)

    return { classes, relations }
  }

  return { parse }
}

/**
 * 示例 Java 代码
 */
export const EXAMPLE_JAVA_CODE = `public abstract class Animal {
    protected String name;
    protected int age;

    public abstract void makeSound();

    public String getName() {
        return name;
    }
}

public class Dog extends Animal implements Pet {
    private String breed;
    private Owner owner;

    @Override
    public void makeSound() {
        System.out.println("Woof!");
    }

    public void fetch(String item) {
        // fetch logic
    }
}

public class Cat extends Animal implements Pet {
    private boolean isIndoor;

    @Override
    public void makeSound() {
        System.out.println("Meow!");
    }

    public void purr() {
        // purr logic
    }
}

public interface Pet {
    void makeSound();
}

public class Owner {
    private String name;
    private List<Pet> pets;

    public void adopt(Pet pet) {
        pets.add(pet);
    }
}

public class VeterinaryClinic {
    private List<Animal> patients;

    public void examine(Animal animal) {
        // examine logic
    }
}
`
