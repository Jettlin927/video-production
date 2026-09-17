# 统一时间轴与验收

## 唯一编辑计划

最小数据结构示意，字段是本 Skill 的约定，不冒充任何后端的原生导入格式：

```json
{
  "revision": "cut-001",
  "source": {"id": "raw-01", "path": "absolute/raw.mp4", "duration_s": 60},
  "fps": {"num": 50, "den": 1},
  "duration_frames": 350,
  "segments": [
    {"id": "k1", "source_in_s": 1, "source_out_s": 4, "final_in_s": 0, "final_out_s": 3},
    {"id": "k2", "source_in_s": 6, "source_out_s": 10, "final_in_s": 3, "final_out_s": 7}
  ],
  "deletions": [
    {"source_in_s": 0, "source_out_s": 1, "reason": "示意：开机准备"},
    {"source_in_s": 4, "source_out_s": 6, "reason": "示意：无效等待"},
    {"source_in_s": 10, "source_out_s": 60, "reason": "示意：其余拍摄废片，实用时须逐段核实"}
  ],
  "seams": [{"left": "k1", "right": "k2", "relation": "因果延续", "review": "not_checked"}]
}
```

默认原速、无重叠，区间用秒、半开区间 `[in,out)`，原片源时码从解码时间原点开始并记录偏移。`final_in` 是此前实际保留时长之和；`final_out-final_in = source_out-source_in`。

保留区间内词的时间映射为 `final_t = final_in + (source_t - source_in)`。例如源片 6.2–6.5 秒的词映射到上例 3.2–3.5 秒。

对候选或已应用的原速时间轴，执行 `python scripts/map_words.py --transcript transcript.source.json --plan edit-plan.json --out words.final.json`，再把 `words.final.json` 交给 `caption_pages.py`。跨切口词会报错要求回源，不偷偷夹短；复用段使用独立 instance_id，不把二次出现去重。候选计划通过映射检查只代表计划可执行，媒体应用后仍需验证。

精确音频气口使用 [semantic-pacing.md](semantic-pacing.md) 的 `sample_audio_cumulative_video` 模式：`final_in_s/out_s` 按采样连续，视频 `final_in_frame/out_frame` 按累计时刻取整；`audio_duration_s/audio_samples/sample_rate` 记录未补尾的声音时长，`duration_frames/duration_s` 记录完整视频时长。只允许片尾补不足一帧；两种时基不混用，字幕词时码以声音为准。子片段保存 `parent_instance_id`；旧删减范围通过 `previous_revision` 和保存的 `selection-plan.json` 追溯，新增删除表用 `old_final_in_s/out_s` 明确标出旧时间轴。

约束与异常：

- 所有 source 区间在媒体范围内；final 区间按顺序连续。默认 source 也顺序且不重叠；用户要求重排/复用时，每个出现实例有独立 ID，禁止把复用词错误去重。
- 不把跨越删除边界的词直接夹短以通过时间检查；它说明切口或对齐需要复查。被完整删除的词不出现在 final 字幕；保留词须在对应段内。
- 重排时 final 时序重新生成，并复查代词指代、前后因果及标题。变速、交叉淡化、J/L cut 属于另一种映射，需显式表达后才能使用。
- 实际后端按帧量化后导出应用结果，作为最终映射依据；输出边界统一量化一次。帧取整后的总时长、音频采样与字幕允许的误差要有明确检查，不能用浮点计划冒充渲染时长。
- `captions.final.json` 每条包含源 word IDs、出现实例 ID、final 起止、显示文本、正文/重点片段、布局与动画；记录所用 revision。
- OpenChatCut 的原生工程是实际编辑状态的依据；从应用后状态生成计划记录或核对对应关系，不让一个手写计划与实际工程并行分叉。

## 质检

| 必检项 | 检查方法 | 失败如何处理 |
|---|---|---|
| 内容保真 | 原稿、保留句和成片对照；复核否定、金额、人名、例子及重说边界 | 回源恢复误删或替换完整 take；ASR 比较只辅助 |
| 连续表达 | 完整顺序视听成片，关注因果、列举、段落转向 | 按语义修接句，避免全片统一缩停顿 |
| 切口完整 | 每个改动切口前后约 1–2 秒视听，覆盖词头尾音、呼吸、爆音、嘴型及手势 | 移动边界、恢复声尾/弱起音、局部淡化，再听 |
| 字幕准确 | 所有字幕文本对照保留原声，检查专业词、数字和中英文混排 | 修文字或重新对齐，不靠显示隐藏修音频 |
| 字幕时机 | 检查所有分页/强调边界，异常短卡、长句及每次剪辑附近；核对开始/中间/结束实帧和原声 | 重建对应时间映射或分页；记录具体时码 |
| 视觉可读 | 实际输出尺寸看正文/重点/双行，检查缺字、溢出、遮脸、标题安全区、突兀黑帧 | 调整字体、布局、镜头或补画面 |
| 音频 | 全片听审，测响度及真峰值，查看音轨是否完整；有 BGM 时检查遮声 | 修人声/音乐电平并复测；数值不能替代听感 |
| 编码后同步 | 在同一 final 时基比较 PCM 与最终 MP4 解码音轨，开中末及有声接缝窗口量 lag | 固定偏移定位封装/编码，累计漂移查时间映射；修后再测 |
| 生成素材 | 每处核对清单与实际入片起/中/末帧、清晰度、语义、字幕遮挡和静音 | 更换/缩小/移除不合格素材；全片时长不因素材增加 |
| 文件 | ffprobe 或等效工具核对规格、时长和轨道；全片解码检查损坏/截断 | 修导出/时间轴，重新验证受影响结果 |

响度可以采用 -16 LUFS、真峰值不高于 -1 dBTP 作原声社交口播起点；这是本流程工程预设，不是所有平台发布标准，按素材与用户需求调整。没有测量工具则记录未测。音视频计划时长需吻合，编码延迟等差异须解释，明显累计漂移不能通过。

`qc.json` 最少包含：时间轴 revision、输出路径、各检查的状态/方法/覆盖范围/证据路径、具体问题时码与修复、总体 `ready_for_review / review_required / passed`。仅当所有必检项实际 pass 才可用 `passed`；`ready_for_review` 也不代表已完成视听验收。

## 用本次两对素材校准

确认配对后：一对用于调节，另一对用冻结后的预设验证迁移。对同一 raw 分别查看人工成片和 Skill 结果，比较独有信息保留、残留重说、误删吞字、接缝自然度、字幕错字/不同步、风格接近程度和人工返修时间。记录具体问题而非只比较时长或删除比例。

第一条 raw 已在独立任务完成 149.44 秒可审片版，后续对照人工成片暴露了语义重点与画面包装差距，详见 [validation.md](validation.md)。第二对迁移验证和完整听审尚未完成，不能推出任意 raw 均可无人验收发布。真正检验“一条 raw＋定调”的是后续生产输入是否仍需用户逐句补计划，而不是 Skill 文档是否写完。
