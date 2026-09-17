"""V2 visual plans: editorial provenance, shared art direction and review binding.

These checks validate recorded decisions; they do not perform visual understanding.
"""
import hashlib
import json
import math


STYLE_FIELDS = ('medium', 'palette', 'rendering', 'composition', 'avoid')
REVIEW_FIELDS = ('asset_review', 'review_notes', 'style_review',
                 'style_review_notes', 'style_reference_sha256')

# Art-direction presets, documented in references/visual-styles.md. One film uses exactly
# one preset. A plan may still carry a custom style, but claiming a preset id commits it to
# that preset's fields, so a plan cannot be labelled 'real-biz-01' while describing cartoon.
ASPECTS = {
    'portrait': '竖幅 9:16，成片为竖屏',
    'landscape': '横幅 16:9，成片为横屏',
}

STYLE_PRESETS = {
    'real-biz-01': {
        'label': '写实商务纪实',
        'use_when': '真人经历、门店/工厂/办公场景、人群、地点、劳作动作；实拍口播片的默认选择',
        'medium': '写实摄影，商业纪实/编辑摄影质感；非插画、非三维渲染',
        'palette': '真实自然色调，整体低饱和；以环境光为准——暖白日光、窗边冷灰、木色与肤色为主；不让某个品牌色统摄画面',
        'rendering': '真实材质与皮肤质感；浅景深（等效 f/2）；自然光或窗光为唯一主光方向，不做多灯影棚感；高光柔和滚降、暗部保留细节；35mm–50mm 视角无畸变；轻微胶片颗粒',
        'composition': '主体置于画面中上部，视线方向留出空气；背景交代行业环境而非纯色背景；下方为平缓低对比区域供字幕',
        'avoid': '矢量插画、三维塑料质感、霓虹与赛博光效、HDR 过锐、摆拍露齿假笑、可读文字与商标、过度磨皮的塑料皮肤',
        'prompt_suffix': '写实摄影质感，自然光，浅景深，真实材质与皮肤，低饱和自然色调，35mm 视角，非插画非三维渲染',
    },
    'tech-blue-01': {
        'label': '深色科技蓝',
        'use_when': 'AI/智能体/系统/自动化/数据流/技术原理；纯排版片或概念段',
        'medium': '高保真三维科技概念视觉',
        'palette': '深蓝黑底（#0A1220–#101B33）；主光电光蓝 #2E9BFF；青色 #56E1FF 作边缘光；白色只用于最高光；不使用暖色',
        'rendering': '玻璃拟态与半透明面板；金属与亚克力反射；体积光与辉光溢出；细网格与粒子；发光描边；主体由自身发光，置于暗场中',
        'composition': '发光主体居中偏上，周围环绕半透明数据面板或节点连线；四周自然暗角；底部保持低亮度以便承字幕',
        'avoid': '写实人脸、暖色与金色、扁平插画、卡通、真实品牌标识、任何可读文字或数字',
        'prompt_suffix': '深蓝黑背景，电光蓝与青色辉光，玻璃拟态半透明面板，体积光，细网格与粒子，暗角，无文字',
    },
    'warm-gold-01': {
        'label': '金棕奢华商业',
        'use_when': '行业与品类陈列、产品与服务清单、餐饮/美业/汽车等实体行业质感',
        'medium': '高端商业静物视觉；写实底图 + 金色三维物件',
        'palette': '深棕 #2B1B10 至暖棕 #4A2F1C 的暗底；香槟金 #D9B472 与 #F0D9A8 为主材；暖白高光；不使用冷色',
        'rendering': '金色拉丝与抛光金属质感；玻璃通透感；写实背景大光圈虚化；柔和方向光与暖色反射；物件有真实重量感与落地投影',
        'composition': '上方留出标题区，中部为等距物件阵列（每件独立、留空隙），底部为低对比暖色过渡区供字幕',
        'avoid': '冷色与霓虹、赛博光效、扁平插画、可读文字与数字（金额与标签一律本地排版）、真实品牌、杂物堆叠',
        'prompt_suffix': '深棕暖色背景，香槟金金属与玻璃质感，柔和方向光，大光圈虚化，物件等距陈列，无文字',
    },
    'clean-ui-01': {
        'label': '明亮产品界面',
        'use_when': '软件能力、功能清单、指标看板、流程步骤',
        'medium': '现代 SaaS 产品界面视觉，半写实界面感',
        'palette': '白 #FFFFFF 与浅灰 #F4F6FA 为底；品牌蓝 #2F6BFF 与淡紫 #7C6BFF 渐变作强调；深灰 #1F2937 作层级块面（示意为无色块，不写字）',
        'rendering': '卡片式布局，1px 浅描边，柔和多层投影；大圆角；细线图标；数据以抽象图形表达；界面元素有层级与浮起感',
        'composition': '上方为顶栏示意，中部为主卡片与图表区，元素按规则栅格水平对齐，底部渐隐',
        'avoid': '真实品牌界面、可读文字与数字（一律本地排版）、写实人脸、照片元素、暗色科技辉光',
        'prompt_suffix': '浅色界面感，白与浅灰底，蓝色与淡紫渐变强调，卡片式布局，柔和投影，抽象图表，无文字',
    },
    'native-snap-01': {
        'label': '原生随拍（受限）',
        'use_when': '需要临场感但确实没有实拍；仅限 explanation/pacing，不得用于 evidence',
        'medium': '手机随拍/UGC 质感的日常记录',
        'palette': '现场色，允许混合色温与偏色，不做统一调色',
        'rendering': '手机广角；构图略显随意、可有轻微倾斜；允许高光溢出与轻微噪点；非专业布光；环境允许杂乱',
        'composition': '随手取景，主体不一定居中，允许前景遮挡',
        'avoid': '影棚布光、商业修图、插画感、精致摆拍、可读文字',
        'prompt_suffix': '手机随拍质感，现场混合光，构图随意，轻微噪点，非专业布光，无文字',
    },
}


def style_preset(style_id, aspect='portrait'):
    """Build a visual_style block from a preset, with the film's aspect written in."""
    if style_id not in STYLE_PRESETS:
        raise ValueError('Unknown style preset: ' + str(style_id))
    if aspect not in ASPECTS:
        raise ValueError('Unknown aspect; expected one of ' + ', '.join(sorted(ASPECTS)))
    preset = STYLE_PRESETS[style_id]
    return {'id': style_id, 'composition': preset['composition'] + '；' + ASPECTS[aspect],
            **{key: preset[key] for key in STYLE_FIELDS if key != 'composition'}}


def known_style_ids():
    return sorted(STYLE_PRESETS)


def check_preset_consistency(style):
    """A plan may use a custom style; if it claims a preset id, its fields must match."""
    preset = STYLE_PRESETS.get(style.get('id'))
    if not preset:
        return
    for key in STYLE_FIELDS:
        if key == 'composition':
            continue
        if style.get(key) != preset[key]:
            raise ValueError(f'visual_style.{key} does not match preset {style["id"]}')
    if preset['composition'] not in (style.get('composition') or ''):
        raise ValueError(f'visual_style.composition must build on preset {style["id"]}')


def generated(job):
    return job.get('source_type', 'generated') == 'generated'


def required_text(obj, key):
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        raise ValueError('Required non-empty text: ' + key)


def positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate_visual_plan(plan):
    version = plan.get('schema_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unsupported visual plan schema_version')
    if version == 1:
        return  # Existing projects remain readable; new plans use v2.
    generated_jobs = [j for j in plan['jobs'] if generated(j)]
    if generated_jobs:
        style = plan.get('visual_style', {})
        for key in ('id',) + STYLE_FIELDS:
            required_text(style, key)
        check_preset_consistency(style)
        budget = plan.get('budget', {})
        for key in ('max_total_jobs', 'max_attempts_per_shot'):
            if type(budget.get(key)) is not int or budget[key] < 1:
                raise ValueError('Positive integer budget required: ' + key)
        if not positive_number(budget.get('max_estimated_cost')):
            raise ValueError('Positive max_estimated_cost required')
        required_text(budget, 'currency')
    for job in plan['jobs']:
        if job.get('source_type') not in ('generated', 'local_real', 'template'):
            raise ValueError('Unknown source_type')
        if job.get('purpose') not in ('evidence', 'explanation', 'pacing'):
            raise ValueError('Unknown visual purpose')
        for key in ('source_text', 'visual_goal', 'claim_scope'):
            required_text(job, key)
        ids = job.get('source_word_ids')
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x.strip() for x in ids):
            raise ValueError('Source word/script IDs required')
        if job['purpose'] == 'evidence':
            if job['source_type'] != 'local_real':
                raise ValueError('Evidence requires local_real material, not a generated illustration')
            required_text(job, 'evidence_basis')
        if generated(job):
            required_text(job, 'prompt')
            required_text(job, 'shot_id')
            if job.get('style_id') != plan['visual_style']['id']:
                raise ValueError('Every generated shot must use the shared visual style_id')
            if not positive_number(job.get('estimated_cost')):
                raise ValueError('Positive estimated_cost required for generated assets')
        else:
            required_text(job, 'path')
            required_text(job, 'source_note')


def styled_prompt(job, style=None):
    prompt = job['prompt'].strip()
    if not style:
        return prompt
    # The API receives the same art direction for every shot, not just a style ID.
    shared = '\n'.join(f'{key}: {style[key]}' for key in STYLE_FIELDS)
    return ('整片统一视觉规范（所有镜头保持一致）：\n' + shared
            + '\n本镜头内容（在上述画风内呈现）：\n' + prompt)


def review_context(plan, job):
    fields = ('id', 'kind', 'source_type', 'purpose', 'source_text', 'source_word_ids',
              'visual_goal', 'claim_scope', 'evidence_basis', 'source_note', 'style_id',
              'start_frame', 'end_frame', 'placement', 'rect', 'reason', 'source_in_s',
              'sha256', 'request_hash')
    context = {'revision': plan['revision'], 'fps': plan['fps'],
               'duration_frames': plan['duration_frames'],
               'visual_style': plan.get('visual_style'),
               'job': {k: job.get(k) for k in fields}}
    return hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check_budget(plan, states, new_jobs):
    """Reserve conservatively, including failed/uncertain prior submissions.

    One output directory is the ledger for one film, including calibration/retries.
    Estimates are limits on planned spend, not provider billing reconciliation.
    """
    if plan.get('schema_version') != 2 or not new_jobs:
        return
    budget = plan['budget']
    reservations = []
    for state in states:
        reservation = state.get('cost_reservation')
        if not reservation or reservation['currency'] != budget['currency']:
            raise ValueError('Existing cost ledger missing or currency differs; reconcile before submitting')
        if (state.get('status') in ('submission_unknown', 'pending')
                and any(j['shot_id'] == reservation['shot_id'] for j in new_jobs)):
            raise ValueError('Existing shot submission uncertain or pending; resolve it before regenerating')
        reservations.append(reservation)
    reservations += [{'shot_id': j['shot_id'], 'amount': j['estimated_cost'],
                      'currency': budget['currency']} for j in new_jobs]
    if len(reservations) > budget['max_total_jobs']:
        raise ValueError('Whole-film max_total_jobs exceeded')
    if sum(r['amount'] for r in reservations) > budget['max_estimated_cost'] + 1e-9:
        raise ValueError('Whole-film estimated cost budget exceeded')
    for shot in {r['shot_id'] for r in reservations}:
        if sum(r['shot_id'] == shot for r in reservations) > budget['max_attempts_per_shot']:
            raise ValueError('Shot regeneration limit exceeded: ' + shot)


def require_visual_review(plan, job):
    if plan.get('schema_version') != 2:
        return
    if job.get('review_context_hash') != review_context(plan, job):
        raise ValueError('Visual review context changed; rebuild manifest and review again')
    if generated(job):
        reference = plan.get('style_reference', {})
        if not reference.get('path') or not reference.get('sha256'):
            raise ValueError('Choose and inspect a style_reference before staging')
        if (job.get('style_review') != 'pass' or not job.get('style_review_notes')
                or job.get('style_reference_sha256') != reference['sha256']):
            raise ValueError('Compare actual asset with style_reference and record style_review=pass')
