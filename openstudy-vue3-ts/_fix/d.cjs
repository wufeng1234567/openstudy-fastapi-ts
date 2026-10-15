const fs=require("fs");
const F="D:/OpenStudy/apps/fastapi-v2/openstudy-fastapi/app/api/v1/notes.py";
const D="D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts/_fix/";
let L=fs.readFileSync(F,"utf8").split(/\r?\n/);
const i= L.findIndex(l=>l.startsWith("async def _send_comment_notification"));
if(i<0){console.log("MISS func");process.exit(1)}
// 函数体到下一个顶层 @router 或 def 之前
let e=i; while(e<L.length && !(e>i && /^(@router|async def |def )/.test(L[e]))) e++;
// 回退掉尾随空行
let end=e; while(end>i && L[end-1].trim()==="") end--;
console.log("replacing lines",i+1,"..",end);
const nu=fs.readFileSync(D+"notif.py.txt","utf8").replace(/\r?\n$/,"").split(/\r?\n/);
L.splice(i, end-i, ...nu);
fs.writeFileSync(F,L.join("\r\n"),"utf8");
console.log("notes.py: mention notification added");