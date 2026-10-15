const fs=require("fs");
const F="D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/src/components/CommentSection/CommentItem.vue";
let L=fs.readFileSync(F,"utf8").split(/\r?\n/);
const iDecl=L.findIndex(l=>l.startsWith("const formattedContent = computed"));
if(iDecl<0){console.log("MISS formattedContent");process.exit(1)}
let iEnd=iDecl; while(iEnd<L.length && L[iEnd].trim()!=="})") iEnd++;
console.log("replacing lines",iDecl+1,"..",iEnd+1);
const nu=[
"const AT_SPAN_STYLE =",
"  'cursor:pointer;color:#409eff;background:#e8f4ff;border-radius:3px;padding:1px 4px;font-weight:500;'",
"",
"/** 生成一个 @ 提及的 span（userId 为空表示老数据里只有昵称、没带 id） */",
"const atSpan = (userId: string | number, name: string) =>",
"  `<span class=\"at-mention\" style=\"${AT_SPAN_STYLE}\" data-userid=\"${userId}\" data-username=\"${name}\">@${name}</span>`",
"",
"const formattedContent = computed(() => {",
"  let text = props.comment.content || ''",
"  text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')",
"",
"  // ⚠️ 两条正则**必须分两步、且第二步不能碰第一步的产物**。",
"  //    旧实现是连续两次 replace：第一条先把 `@{42} 张三` 变成含 data-userid=\"42\" 的 span，",
"  //    第二条的 `(@|＠)(昵称)` 又会匹配到这个 span 内部的 `@张三`，把它**再包一层** ——",
"  //    结果是外层有 id、内层 data-userid=\"\"，而点击命中的是最内层那个空 id，",
"  //    于是点 @ 只能退化成「按昵称在前 100 个用户里猜」。",
"  //    这里用占位符把第一步的结果先藏起来，等第二步跑完再还原。",
"  const held: string[] = []",
"  text = text.replace(/@\\{(\\d+)\\}\\s*([\\u4e00-\\u9fa5a-zA-Z0-9_]+)/g, (_m, id, name) => {",
"    held.push(atSpan(id, name))",
"    return `\\u0000${held.length - 1}\\u0000`",
"  })",
"",
"  // 没有 id 的裸 @昵称（老数据 / 用户手打）：保留展示，但点不动（拿不到用户）",
"  text = text.replace(/(@|＠)([\\u4e00-\\u9fa5a-zA-Z0-9_]+)/g, (_m, _at, name) => atSpan('', name))",
"",
"  // 还原第一步生成的 span",
"  text = text.replace(/\\u0000(\\d+)\\u0000/g, (_m, i) => held[Number(i)] ?? '')",
"  return text",
"})"
];
L.splice(iDecl, iEnd-iDecl+1, ...nu);
fs.writeFileSync(F,L.join("\r\n"),"utf8");
console.log("CommentItem: two-step replace done");