const fs=require("fs");
const F="D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/src/components/CommentSection/CommentItem.vue";
let L=fs.readFileSync(F,"utf8").split(/\r?\n/);
const iDecl=L.findIndex(l=>l.startsWith("const formattedContent = computed"));
if(iDecl<0){console.log("MISS");process.exit(1)}
let iEnd=iDecl; while(iEnd<L.length && L[iEnd].trim()!=="})") iEnd++;
const nu=[
"const formattedContent = computed(() => {",
"  let text = props.comment.content || ''",
"  text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')",
"",
"  // ⚠️ 用**一条**正则、**一趟**替换，别拆成两次 replace。",
"  //    旧实现是连续两次：第一条把 `@{42} 张三` 换成带 data-userid=\"42\" 的 span，",
"  //    第二条的 `(@|＠)(昵称)` 又会匹配到该 span 内部的 `@张三`，再包一层 ——",
"  //    于是最内层那个 data-userid=\"\" 成了点击目标，点 @ 只能按昵称去前 100 个用户里猜。",
"  //    合并成一条后，`@{id} 昵称` 与裸 `@昵称` 是同一个正则的两个分支，互不嵌套。",
"  //    分支一：@\\{(\\d+)\\}\\s*(昵称) —— 带 userId 的规范格式（CommentInput 写入的）",
"  //    分支二：(\\u0040|\\uFF20)(昵称)        —— 老数据 / 用户手打的裸 @，没有 id",
"  text = text.replace(",
"    /@\\{(\\d+)\\}\\s*([\\u4e00-\\u9fa5a-zA-Z0-9_]+)|(\\u0040|\\uFF20)([\\u4e00-\\u9fa5a-zA-Z0-9_]+)/g,",
"    (_m, id, nameWithId, _at, bareName) => atSpan(id ?? '', nameWithId ?? bareName)",
"  )",
"  return text",
"})"
];
L.splice(iDecl, iEnd-iDecl+1, ...nu);
fs.writeFileSync(F,L.join("\r\n"),"utf8");
console.log("CommentItem: single-pass replace installed");