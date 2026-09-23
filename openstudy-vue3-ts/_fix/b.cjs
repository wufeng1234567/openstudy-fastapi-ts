// 复现 CommentItem 的两条渲染正则，验证是否会把 data-userid 覆盖成空
function fmt(text){
  text = text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  text = text.replace(/@\{(\d+)\}\s*([\u4e00-\u9fa5a-zA-Z0-9_]+)/g,
    "<span class=at data-userid=\"$1\" data-username=\"$2\">@$2</span>");
  text = text.replace(/(@|\uff20)([\u4e00-\u9fa5a-zA-Z0-9_]+)/g,
    "<span class=at data-userid=\"\" data-username=\"$2\">$1$2</span>");
  return text;
}
console.log("输入: @{42} 张三 你好");
console.log("输出:", fmt("@{42} 张三 你好"));