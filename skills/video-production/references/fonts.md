# 字幕字体

已内置原始字体文件，不依赖 Windows 安装字体。所有文件、固定来源 commit 和 SHA256 见 `assets/fonts/manifest.json`；许可证随各字体存放。

|风格|文件与字重|使用方式|
|---|---|---|
|商业、科技、干练|SourceHanSansSC-Light.otf / Bold.otf，300 / 700|正文细黑体，完整重点短语白色粗体；主题色用于结构|
|文化、成熟、叙述|SourceHanSerifSC-Regular.otf / Bold.otf，400 / 700|宋体正文与重点，避免小字号细横笔画不清|
|生活、亲切、轻叙事|LXGWWenKai-Regular.ttf，400|文楷正文；仅有真实 Regular，不伪造 Bold|
|清晰、现代、可调字重|notosanssc/NotoSansSC[wght].ttf，100–900可变|Noto Sans SC；普通正文400/500，强调700–900，可作为通用默认|
|强观点、金额、短结论|zcoolqingkehuangyou/ZCOOLQingKeHuangYou-Regular.ttf，400|站酷庆科黄油体，窄长圆润字形；正文保持黑体，短重点切该字体并加下划线|
|文化、情绪、态度金句|mashanzheng/MaShanZheng-Regular.ttf，400|马善政楷书，笔意明显；用于短标题或独立重点，不铺满长字幕|
|轻松、生活、活泼|zcoolkuaile/ZCOOLKuaiLe-Regular.ttf，400|站酷快乐体；少量短关键词/标题，严肃商业正文避免大量使用|

来源：[Adobe 思源黑体](https://github.com/adobe-fonts/source-han-sans)、[Adobe 思源宋体](https://github.com/adobe-fonts/source-han-serif)、[霞鹜文楷](https://github.com/lxgw/LxgwWenKai)。三者提供 SIL Open Font License 1.1，可用于商业视频及随工程分发；分发字体须保留版权/许可，字体不能单独售卖，修改字体时遵守保留字体名称条款。这里使用未修改的上游文件。准确授权以随附 LICENSE.txt / OFL.txt 为准。

新增四款来自 [Google Fonts 官方字体仓库](https://github.com/google/fonts/tree/809e4d8b8d7e9364a914909bb777679606c178b8/ofl)，固定 commit `809e4d8b8d7e9364a914909bb777679606c178b8`；各自目录附 `OFL.txt` 和 `METADATA.pb`。按所附 SIL OFL 1.1 条款可用于商业视频，随工程分发时保留版权和许可；未修改字体文件，来源及 SHA256 均已入 manifest。不要从网站“免费”字样推断无任何许可条件。

通用配对优先 Noto Sans SC 400 正文＋同字体800重点；当前强观点样例试用 Noto 400＋庆科黄油400，仅重点词切换字体。一个视频常用最多两种字形；字体选择随风格变化，不随机轮换。后两款装饰字体只在内容语气合适时启用。可变字体的 FontFace 字重描述写 `100 900`，CSS 才能选择真实400/800；单字重艺术字体只用400，禁用合成粗体。

Remotion：把本次使用的字体和许可复制至工程 `public/fonts/`，用 `FontFace` 加载 staticFile URL，`document.fonts.add()` 后等待 `document.fonts.ready` 再解除 delayRender。CSS 使用实际注册名和实际字重，禁用 font-synthesis；不依赖网络 Google Fonts。字幕组件示例在口播子 Skill 的 `assets/remotion/CaptionLayer.tsx`，复制到工程并按自己的构图调整位置和字号。

按全片字幕实际字符检查 cmap，数字、英文、标点和生僻人名都要覆盖；有缺字时换支持该字的字体或明确回退，不能用方框交付。检查真实渲染的长句、两行、强调词和平台安全区，字体加载成功不等同字幕可读性通过。
