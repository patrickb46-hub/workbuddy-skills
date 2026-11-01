---
name: single-file-html-verify
description: 在无人点击的沙箱里验证「单文件 HTML 小工具」的逻辑与界面。适用于用户让改一个自包含的 .html（内置 <script>、零依赖、靠 onclick + getElementById 工作），而需要确认改动真的生效、且没破坏原有功能时。两大手段：① 抽出 <script> 用 node vm + 最小 DOM stub 跑断言（秒级、可批量、能覆盖边界与报错分支）；② 用 playwright 打开 file:// 实跑点击与截图（验证按钮位置、显示/隐藏、窄屏折行、控制台 0 报错）。触发词：单文件 HTML、小工具、计算器、不依赖服务器、stub DOM、无头验证、把交付物验证一遍、回归、改完确认没坏。
agent_created: true
---

# 单文件 HTML 工具的无头验证

## 何时用

- 改的是一个 **自包含 HTML**（样式内联、JS 内联、无构建、无外部依赖），靠 `onclick="fn()"` + `document.getElementById` 驱动。
- 需要「改完证明它是对的」，尤其是数学/逻辑内核改动、或新增了输入控件与模式切换。
- 不想靠手点、也不想只截一张图就交付。

**不要**只靠肉眼看截图。截图只能证明"某个状态看起来对"，证明不了：
边界输入、报错分支、以及"原来能用的功能是否还正常"（回归）。

## 两步走（顺序别换）

### 第一步：stub DOM + vm 跑断言（覆盖逻辑与边界，秒级）

把 `<script>` 抽出来，在 Node 里造一个最小 DOM，直接调函数、读结果。

```js
const fs=require('fs'), vm=require('vm');
const code=fs.readFileSync(HTML,'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];

function El(id){
  this.id=id; this.value=''; this.innerHTML=''; this.textContent='';
  this.style={}; this.children=[]; this.parentNode=null;
  var s={};
  this.classList={add:c=>{s[c]=1;},remove:c=>{delete s[c];},contains:c=>!!s[c],
    toggle:(c,v)=>{if(v===undefined)v=!s[c]; v?s[c]=1:delete s[c]; return v;}};
  this.className='';
}
Object.assign(El.prototype,{
  appendChild:function(c){this.children.push(c);return c;},
  setAttribute:function(k,v){this['attr_'+k]=v;},
  getAttribute:function(k){return this['attr_'+k]||null;},
  addEventListener:function(){}, querySelectorAll:function(){return [];},
  querySelector:function(){return null;}, closest:function(){return null;}
});

const cache={};
const doc={getElementById:id=>cache[id]||(cache[id]=new El(id)),
  createElement:t=>new El('new-'+t), querySelectorAll:()=>[]};
const sandbox={document:doc, window:{scrollTo(){}}, Option:function(){},
  console, Math, Number, String, Object, Array, JSON, isFinite, isNaN, parseInt, parseFloat};
sandbox.globalThis=sandbox;
vm.createContext(sandbox);
/* 关键：初始化代码常常读某个 <select> 的值，不预置就会在 IIFE 里直接抛错 */
cache['un-cat']=new El('un-cat'); cache['un-cat'].value='length';
/* 把要测的函数挂到全局，才能从外面调用 */
vm.runInContext(code+'\n;globalThis.API={fn1:fn1,fn2:fn2};',sandbox);
```

调用范式：给输入框塞值 → 调入口函数 → 读结果元素的 `innerHTML`。

```js
doc.getElementById('qu-a').value='1';
sandbox.quadratic();                     // 顶层 function 声明会挂到全局
const html=doc.getElementById('qu-result').innerHTML;
```

**断言要把结构化 HTML 拍平**，否则分式/上下标会被拼成乱码（`<frac>1+√3 / 2</frac>` 直接去标签会变成 `1 + √32`）：

```js
function strip(h){
  h=String(h).replace(/<span class="frac"><span class="num">([\s\S]*?)<\/span><span class="den">([\s\S]*?)<\/span><\/span>/g,
    (m,a,b)=>'('+a+')/'+b);          // 先把分式转成 (分子)/分母
  return h.replace(/<[^>]*>/g,'').replace(/\s+/g,' ').trim();
}
```

用例要覆盖四类：**① 回归**（原有干净用例逐字不变）**② 新功能正确值** **③ 边界与非法输入**（空/0/负数/字母/超限 → 应给出友好提示而不是崩）**④ 交互**（模式开关是否切对了属性、清空是否生效）。

### 第二步：playwright 打开 file:// 实跑（覆盖布局与真实交互）

```js
const {chromium}=require('playwright');
const page=await browser.newPage({viewport:{width:1280,height:1000}});
page.on('pageerror',e=>errs.push(e.message));      // 收尾检查 0 报错
await page.goto('file://'+encodeURI(localPath));   // 中文路径必须 encodeURI
```

要验的四件事（截图只能作补充）：

1. **位置关系**用 `boundingBox()` 比数值，别靠眼睛：
   `btn.x >= inp.x + inp.width` → 按钮确实在输入框右侧。
2. **显示/隐藏**用 `isVisible()` 断言，同时断言"该隐藏的还隐藏着"（多子模式页面容易漏）。
3. **清空/重置**：`inputValue()` 应为空。
4. **窄屏**：`setViewportSize({width:390,...})` 后再比一次位置（应折到下方）。

**坑**：`page.click('button:has-text("清空")')` 会命中**第一个**同名按钮（可能在被 `display:none` 的面板里）→ 必须加面板前缀 `#sec-pyth button:has-text("清空")`。

## 收尾

- 断言脚本与截图放 `/tmp` 下，验证完 `rm -rf` 删掉，只留成品（用户习惯：不留过程文件）。
- 交付前再跑一次 `node --check`（把 `<script>` 抽成 .js 检查语法）。

## 触发词

单文件 HTML、小工具、计算器、无头验证、stub DOM、回归、改完确认没坏、playwright 验界面。
