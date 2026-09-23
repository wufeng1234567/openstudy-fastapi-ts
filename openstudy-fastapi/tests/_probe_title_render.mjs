/**
 * 一次性探针（跑完即删）：把 `AgentToolDetail` 的标题/去重**纯函数**抽出来，在 Node 里
 * 用**真实 payload 形状**执行一遍 —— 静态读代码看不出的地方（我上次就是把 `restOf`
 * 读成「只摘选中的那个」而实际摘的是整张表）在这里会立刻暴露。
 *
 * ⚠️ 只读前端文件、不写前端任何字节；脚本本身放在**后端**的 tests/ 下（我的面）。
 * 断言刻意包含一个**负对照**（既无题干也无题库名的对象）——
 * 否则「标题=题干」这类断言可能只是解析器坏了、恰好返回了空串。
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const VUE = path.resolve(
  'D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/src/components/AgentToolDetail/index.vue'
);
const src = fs.readFileSync(VUE, 'utf8');

// 抽出来的片段带 TS 类型注解，`new Function` 解析不了 → 借前端那份 typescript 转译一下。
// （只 require、不写前端的任何文件；用绝对路径从后端的 cwd 也能拿到。）
const require = createRequire(import.meta.url);
const ts = require('D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/node_modules/typescript');
const toJs = (code) =>
  ts.transpileModule(code, {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None }
  }).outputText;

const sliceBetween = (startMark, endMark) => {
  const i = src.indexOf(startMark);
  if (i < 0) throw new Error('找不到片段: ' + startMark);
  const j = src.indexOf(endMark, i);
  if (j < 0) throw new Error('找不到结束标记: ' + endMark);
  return src.slice(i, j + endMark.length);
};

// —— 只抽纯逻辑（常量 + titleKeyOf/titleOf/restOf/clip），不碰 Vue 的任何响应式东西
const parts = [
  src.match(/const MAX_TITLE = \d+/)[0],
  sliceBetween('const TITLE_GROUPS = [', '\n]'),
  src.match(/const TITLE_KEYS = TITLE_GROUPS\.flat\(\)/)[0],
  sliceBetween('const clip = (s: string, max: number) =>', '\n\n'),
  sliceBetween('function titleKeyOf(', '\n}'),
  sliceBetween('function titleOf(', '\n}'),
  sliceBetween('function restOf(', '\n}')
];

const ROWS = [];
const FAILED = [];
const check = (name, ok, detail = '') => {
  ROWS.push([name, !!ok]);
  if (!ok) FAILED.push(name);
  console.log((ok ? '  [OK]   ' : '  [FAIL] ') + name + (detail ? ' -> ' + detail : ''));
};

const factory = new Function(
  parts.join('\n') + '\nreturn { titleOf, restOf, titleKeyOf, TITLE_GROUPS, TITLE_KEYS };'
);
const { titleOf, restOf, TITLE_GROUPS, TITLE_KEYS } = factory();
console.log(`  抽取成功：TITLE_GROUPS=${TITLE_GROUPS.length} 组 / TITLE_KEYS=${TITLE_KEYS.length} 键`);
console.log(`  解析自检：TITLE_KEYS = ${JSON.stringify(TITLE_KEYS)}`);

// ---------------------------------------------------------------- 真实 payload 形状
// 以下字段集来自后端探针的实测输出（question_service.brief_of / question_brief / note_brief）
const flagErrorItem = {
  errorId: 257, questionId: 2663, bankId: 1096, bankName: '__probe__自测题库',
  questionType: 1, questionTypeText: '单选题', difficulty: 2, notes: null, tags: null,
  createTime: '2026-09-22 16:51:00', preview: '__probe__第一题：二次函数的最小值是多少？',
  errorCount: 1, isMastered: 0, lastErrorTime: '2026-09-22 16:51:00'
};
const questionManageItem = {   // question_brief：全文 + 80 字 preview（两条都要）
  questionId: 1, questionText: '完整的题干（很长很长……）', preview: '完整的题干（很长很长……）',
  questionType: 1, questionTypeText: '单选题', bankId: 3, bankName: '题库A', sortOrder: 1
};
const noteItem = { title: '我的笔记标题', noteId: 9, categoryId: 1, tags: 'a,b' };

// ① 我的 flag list 元素：只有 preview、没有 questionText
let t = titleOf(flagErrorItem);
let r = restOf(flagErrorItem);
check('① flag list 元素标题 = 题干（preview）', t.startsWith('__probe__第一题'), t);
check('① 标题**不是**题库名（组顺序生效）', !t.includes('自测题库'), t);
check('① 题库名作为一行**保留**（组外字段不摘）', 'bankName' in r, JSON.stringify(Object.keys(r)));
check('① preview 自身从键值区摘除（不重复显示）', !('preview' in r));
check('① 定位字段都在（id / 题干 / 计数）',
  ['errorId', 'questionId', 'bankId', 'questionTypeText', 'errorCount', 'isMastered'].every((k) => k in r),
  JSON.stringify(Object.keys(r)));

// ② question_manage 的列表元素：全文 + preview 同组，只显示一次
t = titleOf(questionManageItem);
r = restOf(questionManageItem);
check('② question_manage 元素标题 = questionText', t.startsWith('完整的题干'), t);
check('② 同组的 preview 被摘掉（题干不显示两遍）', !('preview' in r));
check('② 组外的 bankName / sortOrder 保留', 'bankName' in r && 'sortOrder' in r, JSON.stringify(Object.keys(r)));

// ③ note_manage 的元素走 title
t = titleOf(noteItem);
r = restOf(noteItem);
check('③ note 元素标题 = title', t === '我的笔记标题', t);
check('③ 其余字段保留', 'noteId' in r && 'categoryId' in r, JSON.stringify(Object.keys(r)));

// ④ 负对照：没有任何「可当标题」的键 → titleOf 返回空、restOf 原样返回
const bare = { a: 1, b: 'x' };
check('④ 负对照：无可当标题的键时 titleOf = ""', titleOf(bare) === '', JSON.stringify(titleOf(bare)));
check('④ 负对照：此时 restOf 原样返回（什么都不摘）',
  JSON.stringify(restOf(bare)) === JSON.stringify(bare), JSON.stringify(restOf(bare)));

// ⑤ 分类用的真值：只有 preview 时，titleKeyOf 落到的必须就是 preview
const keyOf = factory().titleKeyOf ?? null;
check('⑤ 解析器自检：TITLE_GROUPS 第一组含 preview 与 questionText（同义对）',
  TITLE_GROUPS[0].includes('preview') && TITLE_GROUPS[0].includes('questionText'),
  JSON.stringify(TITLE_GROUPS[0]));
check('⑤ bankName 与题干**不在同一组**（否则题干会挤掉题库名）',
  !TITLE_GROUPS.some((g) => g.includes('preview') && g.includes('bankName')),
  JSON.stringify(TITLE_GROUPS));

console.log(`\n== 汇总：${ROWS.length - FAILED.length}/${ROWS.length} 通过 ==`);
for (const f of FAILED) console.log('  FAILED:', f);
process.exit(FAILED.length ? 1 : 0);
