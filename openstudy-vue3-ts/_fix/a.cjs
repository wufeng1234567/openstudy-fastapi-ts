const fs=require("fs");
const F="D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/src/components/CommentSection/CommentInput.vue";
let s=fs.readFileSync(F,"utf8");
const old="  const atText = `@${name} `";
if(!s.includes(old)){console.log("MISS atText");process.exit(1)}
// 插入格式改为 @{userId} 昵称 —— 与 CommentItem 的渲染正则配套
const neu=[
"  // \u26a0\ufe0f 必须写成 `@{userId} 昵称`（不能只写 @昵称）：",
"  //    CommentItem 靠 @{id} 才能把 data-userid 写进 DOM，点击 @ 时才知道要跳谁；",
"  //    只写 @昵称 会退化成「在前 100 个用户里按昵称猜」，大概率点不动。",
"  const atText = `@{${userId}} ${name} `"
].join("\n");
s=s.replace(old,neu);
fs.writeFileSync(F,s,"utf8");
console.log("CommentInput: atText now carries userId");