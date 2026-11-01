/**
 * SceneKit.tsx — 科普短片场景零件库（7 场 + 封面）
 *
 * 用法：拷到 Remotion 工程 src/ 下改名 MyVideo.tsx，
 *       **只改 CONTENT**，下面所有场景会自动跟着变。
 *
 * 关键机制：tts_narrate.py 是「一句一个 scene」，同一 id 的多句会在
 * 这里按 id 合并成一场，并记下每句的起始帧（at）。场景组件用 at[i]
 * 当 delay，实现「旁白念到第几句，画面才出第几个元素」。
 *
 * 设计约束（与 diagram-design 一致，别凭感觉突破）：
 *   · 一屏最多 6 个视觉元素，密度 4/10
 *   · 强调色只给 1–2 处，其余灰阶；不用阴影、不用渐变
 *   · 4px 网格；中文显式指定 PingFang SC（不写会渲染成方块）
 */
import React from 'react';
import {
  AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { SCENES, TOTAL_FRAMES } from './timing';

/* ========== 设计变量：改这里换整体气质 ========== */
const F = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif';
const MONO = '"SF Mono","Menlo","PingFang SC",monospace';
const BG = '#F6F5F1';
const INK = '#1A1A17';
const MUTED = '#8B8880';
const RULE = '#DCDCE0';
const RULE2 = '#E8E5DC';
const CA = '#2E6E8E';   // 主强调：蓝
const CB = '#B04E36';   // 次强调：砖红
const PAD = 110;

const CL = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const c01 = (v: number) => Math.min(1, Math.max(0, v));
/** 取第 i 句的起始帧；句数不够时退到最后一帧 */
const t = (at: number[], i: number) => at[Math.min(i, Math.max(0, at.length - 1))] ?? 0;

/* ============================================================
 * 改这里：本片文案
 * ============================================================ */
export const CONTENT = {
  header: { left: '{{AUTHOR}}', right: '科普 · 事件解读' },

  s1: {
    kicker: '2026.10.20 ｜ 一件被传歪的事',
    lines: ['被封的不是游戏', '是一个按钮'],
    accentLine: 1,
    sub: '三分钟讲清：为什么、怎么封、你该怎么办',
    params: [
      ['时间', '10 月 20 日'],
      ['版本', '2.99.0.0'],
      ['涉及', 'PCL / HMCL / PCL CE'],
      ['性质', '主动移除功能'],
    ] as const,
  },

  s2: {
    tag: '事实',
    title: '到底改了什么',
    note: '三家启动器，同一天，同一句话',
    events: [
      { time: '10-20 14:51', ver: '2.99.0.0', label: 'PCL 发布新版', sub: '不再提供下载', hot: true },
      { time: '10-20 16:50', ver: '3.17.0.362', label: 'HMCL 开发版跟进', sub: '', hot: true },
      { time: '10-20 当天', ver: 'PCL CE', label: '社区版限制安装', sub: '', hot: false },
    ],
    footnote: '来源：GitHub 发布记录 · commit 583e004',
  },

  s3: {
    tag: '归因',
    title: '为什么必须收手',
    note: '三条红线，一条比一条硬',
    items: [
      { no: '01', title: '没有版号', sub: '国际版在国内未取得出版许可' },
      { no: '02', title: '分发游戏本体', sub: '替没购买的人下载完整游戏文件' },
      { no: '03', title: '绕过正版验证', sub: '离线模式让认证形同虚设' },
    ],
    asideTitle: '待证实',
    asideSub: '某未成年私服充值，家长连带举报',
    asideNote: '无官方通报，无第二信源 —— 不能当结论',
  },

  s4: {
    tag: '机制',
    title: '两种封法，两种性格',
    note: '一个直接删，一个精准判断',
    left: {
      title: 'PCL',
      tagline: '硬移除',
      buttonText: '下载游戏',
      line1: '功能从程序里删掉',
      line2: '不分地区，不分网络',
    },
    right: {
      title: 'HMCL',
      tagline: '三重判断',
      chips: ['时区 UTC+8', '系统语言 CN', '地理编号 45'],
      netChip: 'IP 预检',
      banner: '请前往 mc.163.com 下载中国版',
      line: '两关都过，才显示提示',
    },
    footer: '没有 DNS 污染，也没有 IP 阻断 —— 那是编出来的',
  },

  s5: {
    tag: '影响',
    title: '谁疼，谁不疼',
    note: '同一个改动，三种处境',
    rows: [
      { who: '已装好游戏的老玩家', level: '几乎无感', pct: 0.12, tone: 'good' },
      { who: '刚换机 / 刚入坑的新玩家', level: '拿不到本体', pct: 0.86, tone: 'bad' },
      { who: '服主 / 整合包作者', level: '搭环境变麻烦', pct: 0.55, tone: 'warn' },
    ],
    boundary: '游戏没有下架：官网与官方启动器一直正常',
  },

  s6: {
    tag: '行动',
    title: '现在还能怎么玩',
    note: '三条正路，四个坑',
    paths: [
      { name: '网易中国版', cost: '免费', who: '想国内联机' },
      { name: '国际版官方启动器', cost: '约 89 元', who: '想进海外服' },
      { name: 'HMCL / Prism', cost: '开源', who: '管理已有实例' },
    ],
    avoidTitle: '四件事别做',
    avoid: [
      '买淘宝共享账号 —— 黑卡，短期封',
      '点「高速下载器」—— 捆绑挖矿',
      '用网盘破解包 —— 可能读通讯录',
      '付费迁移账号 —— 官方本来就免费',
    ],
  },

  s7: {
    tag: '判断力',
    title: '下次怎么自己判断',
    note: '四个问题，一条等待',
    questions: [
      '谁说的？有没有主语？',
      '有没有第二个独立信源？',
      '封的是一个功能，还是整个游戏？',
      '版本号对得上吗？',
    ],
    closing: '一个按钮的消失',
    closing2: '不等于一个时代的结束',
  },
};

type Props = { at: number[] };

/* ========== 通用零件 ========== */
const Reveal: React.FC<{
  delay?: number; y?: number; x?: number;
  children: React.ReactNode; style?: React.CSSProperties;
}> = ({ delay = 0, y = 24, x = 0, children, style }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: Math.max(0, f - delay), fps,
    config: { damping: 24, stiffness: 110, mass: 1 } });
  return (
    <div style={{
      opacity: c01(p),
      transform: `translate(${(1 - p) * x}px, ${(1 - p) * y}px)`,
      ...style,
    }}>{children}</div>
  );
};

const Head: React.FC<{ tag: string; title: string; note?: string; delay?: number }> =
  ({ tag, title, note, delay = 0 }) => (
    <div style={{ position: 'absolute', left: PAD, top: 156 }}>
      <Reveal delay={delay + 1}>
        <div style={{ fontFamily: F, fontSize: 24, letterSpacing: 4, color: MUTED }}>{tag}</div>
      </Reveal>
      <Reveal delay={delay + 4}>
        <div style={{ fontFamily: F, fontSize: 72, fontWeight: 600, color: INK,
          letterSpacing: -1, lineHeight: 1.15, marginTop: 14 }}>{title}</div>
      </Reveal>
      {note ? (
        <Reveal delay={delay + 9}>
          <div style={{ fontFamily: F, fontSize: 32, color: MUTED, marginTop: 10 }}>{note}</div>
        </Reveal>
      ) : null}
    </div>
  );

const Rule: React.FC<{ w?: number; color?: string; delay?: number }> =
  ({ w = 96, color = INK, delay = 0 }) => {
    const f = useCurrentFrame();
    const { fps } = useVideoConfig();
    const p = spring({ frame: Math.max(0, f - delay), fps,
      config: { damping: 30, stiffness: 90 } });
    return <div style={{ width: w * p, height: 4, background: color }} />;
  };

const Chip: React.FC<{ text: string; delay?: number; color?: string }> =
  ({ text, delay = 0, color = INK }) => (
    <Reveal delay={delay} y={10}>
      <div style={{ fontFamily: MONO, fontSize: 20, color,
        border: `1.5px solid ${RULE}`, padding: '7px 12px',
        whiteSpace: 'nowrap' }}>{text}</div>
    </Reveal>
  );

/* ========== s1 · 标题（3 句） ========== */
const S1 = ({ at }: Props) => {
  const c = CONTENT.s1;
  const a0 = t(at, 0), a1 = t(at, 1), a2 = t(at, 2);
  return (
    <>
      <div style={{ position: 'absolute', left: PAD, top: 268 }}>
        <Reveal delay={a0 + 2}>
          <div style={{ fontFamily: F, fontSize: 26, letterSpacing: 4, color: MUTED }}>
            {c.kicker}
          </div>
        </Reveal>
        {c.lines.map((ln, i) => (
          <Reveal key={i} delay={i === 0 ? a0 + 8 : a1 + 2}>
            <div style={{ fontFamily: F, fontSize: 104, fontWeight: 600,
              color: i === c.accentLine ? CA : INK,
              letterSpacing: -2, lineHeight: 1.18, marginTop: i === 0 ? 26 : 0 }}>
              {ln}
            </div>
          </Reveal>
        ))}
        <div style={{ marginTop: 42 }}><Rule w={132} delay={a1 + 14} /></div>
        <Reveal delay={a2 + 4}>
          <div style={{ fontFamily: F, fontSize: 32, color: MUTED, marginTop: 26 }}>{c.sub}</div>
        </Reveal>
      </div>

      <div style={{ position: 'absolute', right: PAD, top: 320, width: 420 }}>
        {c.params.map(([k, v], i) => (
          <Reveal key={k} delay={a2 + 10 + i * 6} x={-20}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 20,
              fontFamily: MONO, fontSize: 24, color: MUTED, lineHeight: 2.3 }}>
              <span style={{ opacity: 0.75 }}>{k}</span>
              <span style={{ color: i === 0 ? INK : MUTED, minWidth: 210, textAlign: 'right' }}>
                {v}
              </span>
            </div>
          </Reveal>
        ))}
      </div>
    </>
  );
};

/* ========== s2 · 时间线（5 句） ========== */
const S2 = ({ at }: Props) => {
  const c = CONTENT.s2;
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const AXIS_Y = 720;
  const X0 = 250, X1 = 1670;
  const n = c.events.length;
  const step = (X1 - X0) / Math.max(1, n - 1);
  const grow = spring({ frame: Math.max(0, f - t(at, 0)), fps,
    config: { damping: 40, stiffness: 60, mass: 1.4 } });

  // 句 → 事件：① 事件0 ② 事件0 注解 ③ 事件1 ④ 事件2 ⑤ 脚注
  const evDelay = [t(at, 0), t(at, 2), t(at, 3)];
  const subDelay = t(at, 1);

  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 4} />

      <svg width={1920} height={1080} style={{ position: 'absolute', left: 0, top: 0 }}>
        <line x1={X0} y1={AXIS_Y} x2={X0 + (X1 - X0) * grow} y2={AXIS_Y}
          stroke={RULE} strokeWidth={2} />
      </svg>

      {c.events.map((e, i) => {
        const d = evDelay[i] ?? t(at, 3);
        const appear = spring({ frame: Math.max(0, f - d), fps,
          config: { damping: 22, stiffness: 120 } });
        const x = X0 + i * step;
        return (
          <div key={i} style={{ position: 'absolute', left: x - 160, top: 428, width: 320,
            opacity: c01(appear) }}>
            <div style={{ textAlign: 'center', fontFamily: MONO, fontSize: 24, color: MUTED }}>
              {e.time}
            </div>
            <div style={{ textAlign: 'center', fontFamily: MONO, fontSize: e.hot ? 46 : 32,
              fontWeight: 600, color: e.hot ? INK : MUTED, marginTop: 18,
              letterSpacing: -0.5 }}>{e.ver}</div>
            <div style={{ width: 13, height: 13, borderRadius: 7,
              background: e.hot ? CB : MUTED, margin: '26px auto 0' }} />
            <div style={{ textAlign: 'center', fontFamily: F, fontSize: 27,
              color: e.hot ? INK : MUTED, marginTop: 26, lineHeight: 1.5 }}>
              {e.label}
            </div>
          </div>
        );
      })}

      {c.events[0].sub ? (
        <Reveal delay={subDelay} style={{ position: 'absolute', left: 90, top: 726, width: 340 }}>
          <div style={{ fontFamily: F, fontSize: 23, color: CB, textAlign: 'center' }}>
            {c.events[0].sub}
          </div>
        </Reveal>
      ) : null}

      <Reveal delay={t(at, 4)} style={{ position: 'absolute', left: PAD, top: 916 }}>
        <div style={{ fontFamily: F, fontSize: 25, color: MUTED }}>{c.footnote}</div>
      </Reveal>
    </>
  );
};

/* ========== s3 · 三条红线 + 待证实（6 句） ========== */
const S3 = ({ at }: Props) => {
  const c = CONTENT.s3;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 6} />

      {c.items.map((it, i) => (
        <Reveal key={it.no} delay={t(at, i + 1) - 24} style={{ position: 'absolute',
          left: PAD, top: 452 + i * 146, width: 1080 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 30 }}>
            <div style={{ fontFamily: MONO, fontSize: 40, color: CA, width: 62 }}>{it.no}</div>
            <div>
              <div style={{ fontFamily: F, fontSize: 44, fontWeight: 600, color: INK }}>{it.title}</div>
              <div style={{ fontFamily: F, fontSize: 26, color: MUTED, marginTop: 10 }}>{it.sub}</div>
            </div>
          </div>
        </Reveal>
      ))}

      {/* 外框先到，内容后到 —— 否则前 12 秒右侧空 800px */}
      <Reveal delay={t(at, 0) + 50} style={{ position: 'absolute', left: 1290, top: 440 }}>
        <div style={{ width: 480, border: `2px dashed ${RULE}`, padding: '34px 32px' }}>
          <div style={{ fontFamily: F, fontSize: 22, letterSpacing: 3, color: CB }}>{c.asideTitle}</div>
          <Reveal delay={t(at, 4)}>
            <div style={{ fontFamily: F, fontSize: 30, color: INK, marginTop: 18, lineHeight: 1.55 }}>
              {c.asideSub}
            </div>
            <div style={{ width: 60, height: 2, background: RULE, margin: '26px 0 20px' }} />
          </Reveal>
          <Reveal delay={t(at, 5)}>
            <div style={{ fontFamily: F, fontSize: 23, color: MUTED, lineHeight: 1.6 }}>
              {c.asideNote}
            </div>
          </Reveal>
        </div>
      </Reveal>
    </>
  );
};

/* ========== s4 · 左右对照（6 句） ========== */
const S4 = ({ at }: Props) => {
  const c = CONTENT.s4;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 6} />

      {/* 左：PCL 硬移除 —— 第 2 句 */}
      <Reveal delay={t(at, 1) - 24} style={{ position: 'absolute', left: PAD, top: 436, width: 800 }}>
        <div style={{ borderTop: `4px solid ${INK}`, paddingTop: 22 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16 }}>
            <span style={{ fontFamily: F, fontSize: 40, fontWeight: 600, color: INK }}>{c.left.title}</span>
            <span style={{ fontFamily: F, fontSize: 24, color: MUTED }}>{c.left.tagline}</span>
          </div>
          <div style={{ position: 'relative', marginTop: 40, width: 330, height: 96,
            background: INK, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontFamily: F, fontSize: 32, color: BG }}>{c.left.buttonText}</span>
            <svg width={330} height={96} style={{ position: 'absolute', left: 0, top: 0 }}>
              <line x1={16} y1={78} x2={314} y2={18} stroke={CB} strokeWidth={5} />
            </svg>
          </div>
          <div style={{ fontFamily: F, fontSize: 27, color: INK, marginTop: 34 }}>{c.left.line1}</div>
          <div style={{ fontFamily: F, fontSize: 27, color: MUTED, marginTop: 8 }}>{c.left.line2}</div>
        </div>
      </Reveal>

      {/* 右：HMCL 三重判断 —— 第 3~5 句 */}
      <Reveal delay={t(at, 2)} style={{ position: 'absolute', left: 990, top: 436, width: 820 }}>
        <div style={{ borderTop: `4px solid ${CA}`, paddingTop: 22 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16 }}>
            <span style={{ fontFamily: F, fontSize: 40, fontWeight: 600, color: INK }}>{c.right.title}</span>
            <span style={{ fontFamily: F, fontSize: 24, color: CA }}>{c.right.tagline}</span>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 32, width: 660 }}>
            {c.right.chips.map((txt, i) => (
              <Chip key={txt} text={txt} delay={t(at, 3) + i * 9} />
            ))}
            <Chip text={c.right.netChip} delay={t(at, 4)} color={CA} />
          </div>

          <Reveal delay={t(at, 5)}>
            <div style={{ marginTop: 30, padding: '20px 24px', background: '#EDEBE4',
              borderLeft: `4px solid ${CA}`, fontFamily: F, fontSize: 26, color: INK }}>
              {c.right.banner}
            </div>
          </Reveal>
          <Reveal delay={t(at, 5) + 12}>
            <div style={{ fontFamily: F, fontSize: 24, color: MUTED, marginTop: 18 }}>
              {c.right.line}
            </div>
          </Reveal>
        </div>
      </Reveal>

      <Reveal delay={t(at, 5) + 22} style={{ position: 'absolute', left: PAD, top: 916 }}>
        <div style={{ fontFamily: F, fontSize: 26, color: CB }}>{c.footer}</div>
      </Reveal>
    </>
  );
};

/* ========== s5 · 人群影响（5 句） ========== */
const toneColor = (s: string) => (s === 'bad' ? CB : s === 'warn' ? '#9A7A34' : CA);

const S5 = ({ at }: Props) => {
  const c = CONTENT.s5;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0)} />

      {c.rows.map((r, i) => (
        <Reveal key={r.who} delay={t(at, i + 1)} style={{ position: 'absolute',
          left: PAD, top: 468 + i * 138 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 40 }}>
            <div style={{ width: 470, fontFamily: F, fontSize: 31, color: INK }}>{r.who}</div>
            <div style={{ width: 620, height: 12, background: RULE2, position: 'relative' }}>
              <GrowBar pct={r.pct} color={toneColor(r.tone)} delay={t(at, i + 1) + 10} />
            </div>
            <div style={{ fontFamily: F, fontSize: 26, color: toneColor(r.tone),
              fontWeight: 600, width: 240 }}>{r.level}</div>
          </div>
        </Reveal>
      ))}

      <Reveal delay={t(at, 4)} style={{ position: 'absolute', left: PAD, top: 900 }}>
        <div style={{ fontFamily: F, fontSize: 27, color: INK, paddingLeft: 18,
          borderLeft: `4px solid ${CA}` }}>{c.boundary}</div>
      </Reveal>
    </>
  );
};

const GrowBar: React.FC<{ pct: number; color: string; delay: number }> = ({ pct, color, delay }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: Math.max(0, f - delay), fps,
    config: { damping: 26, stiffness: 80, mass: 1.2 } });
  return <div style={{ position: 'absolute', left: 0, top: 0, height: 12,
    width: `${pct * 100 * p}%`, background: color }} />;
};

/* ========== s6 · 三条路 + 四个坑（6 句） ========== */
const S6 = ({ at }: Props) => {
  const c = CONTENT.s6;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0)} />

      {c.paths.map((p, i) => (
        <Reveal key={p.name} delay={t(at, i + 1) - 24} style={{ position: 'absolute',
          left: PAD + i * 556, top: 448, width: 500 }}>
          <div style={{ border: `1.5px solid ${RULE}`, padding: '28px 26px 32px' }}>
            <div style={{ fontFamily: F, fontSize: 34, fontWeight: 600, color: INK }}>{p.name}</div>
            <div style={{ fontFamily: MONO, fontSize: 26, color: CA, marginTop: 20 }}>{p.cost}</div>
            <div style={{ fontFamily: F, fontSize: 24, color: MUTED, marginTop: 12 }}>{p.who}</div>
          </div>
        </Reveal>
      ))}

      <Reveal delay={t(at, 4)} style={{ position: 'absolute', left: PAD, top: 706 }}>
        <div style={{ fontFamily: F, fontSize: 24, letterSpacing: 3, color: CB }}>{c.avoidTitle}</div>
      </Reveal>
      {c.avoid.map((a, i) => (
        <Reveal key={a} delay={(i < 2 ? t(at, 4) : t(at, 5)) + 6 + (i % 2) * 9}
          style={{ position: 'absolute', left: PAD, top: 760 + i * 56 }}>
          <div style={{ display: 'flex', gap: 18, alignItems: 'baseline' }}>
            <span style={{ fontFamily: MONO, fontSize: 26, color: CB }}>×</span>
            <span style={{ fontFamily: F, fontSize: 27, color: INK }}>{a}</span>
          </div>
        </Reveal>
      ))}
    </>
  );
};

/* ========== s7 · 四问 + 收束（5 句） ========== */
const S7 = ({ at }: Props) => {
  const c = CONTENT.s7;
  // 句1 → 标题；句2 → 问 1、2；句3 → 问 3；句4 → 问 4；句5 → 收束
  const qDelay = [t(at, 1) - 20, t(at, 1) + 6, t(at, 2), t(at, 3)];
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0)} />

      {c.questions.map((q, i) => (
        <Reveal key={q} delay={qDelay[i]} style={{ position: 'absolute',
          left: PAD, top: 464 + i * 100 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 24 }}>
            <span style={{ fontFamily: MONO, fontSize: 28, color: MUTED }}>{`0${i + 1}`}</span>
            <span style={{ fontFamily: F, fontSize: 33, color: INK }}>{q}</span>
          </div>
        </Reveal>
      ))}

      <Reveal delay={t(at, 4)} style={{ position: 'absolute', left: 1120, top: 466, width: 700 }}>
        <div style={{ width: 88, height: 4, background: CB }} />
        <div style={{ fontFamily: F, fontSize: 52, fontWeight: 600, color: INK,
          lineHeight: 1.38, marginTop: 30 }}>
          {c.closing}
          <br />
          <span style={{ color: CB }}>{c.closing2}</span>
        </div>
      </Reveal>
    </>
  );
};

/* ================= 装配 ================= */
const COMPONENTS: Record<string, React.FC<Props>> = {
  s1: S1, s2: S2, s3: S3, s4: S4, s5: S5, s6: S6, s7: S7,
};

const NO_FADE_OUT = new Set<string>([]);
const NO_FADE_IN = new Set<string>([]);

/** 把「一句一场」的 SCENES 按 id 合并成「一场多句」，并记下每句起始帧 */
const buildScenes = () => {
  const out: { id: string; frames: number; at: number[]; start: number }[] = [];
  let cursor = 0;
  SCENES.forEach((s) => {
    const id = s.id as string;
    const last = out[out.length - 1];
    if (last && last.id === id) {
      last.at.push(cursor - last.start);
      last.frames += s.frames;
    } else {
      out.push({ id, frames: s.frames, at: [0], start: cursor });
    }
    cursor += s.frames;
  });
  // 最后一场吞掉片尾静默，否则结尾是纯背景拖尾
  if (out.length) out[out.length - 1].frames = TOTAL_FRAMES - out[out.length - 1].start;
  return out;
};

const SceneShell: React.FC<{ id: string; frames: number; at: number[]; index: number; total: number }> =
  ({ id, frames, at, index, total }) => {
    const f = useCurrentFrame();
    const Comp = COMPONENTS[id] ?? (() => null);
    const fin = NO_FADE_IN.has(id) ? 1 : interpolate(f, [0, 6], [0, 1], CL);
    const fout = NO_FADE_OUT.has(id) ? 1 : interpolate(f, [frames - 5, frames - 1], [1, 0], CL);
    return (
      <AbsoluteFill style={{ opacity: Math.min(fin, fout) }}>
        <Comp at={at} />
        <div style={{ position: 'absolute', left: PAD, bottom: 44, fontFamily: MONO,
          fontSize: 21, color: MUTED, letterSpacing: 1 }}>
          {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
        </div>
      </AbsoluteFill>
    );
  };

export const MyVideo: React.FC = () => {
  const scenes = buildScenes();
  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <div style={{ position: 'absolute', left: PAD, right: PAD, top: 54, display: 'flex',
        justifyContent: 'space-between', fontFamily: F, fontSize: 23, color: MUTED,
        letterSpacing: 2 }}>
        <span>{CONTENT.header.left}</span>
        <span>{CONTENT.header.right}</span>
      </div>
      <div style={{ position: 'absolute', left: PAD, right: PAD, top: 102, height: 1,
        background: RULE }} />
      {scenes.map((s, i) => (
        <Sequence key={`${s.id}-${i}`} from={s.start} durationInFrames={s.frames}>
          <SceneShell id={s.id} frames={s.frames} at={s.at} index={i} total={scenes.length} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

/* ================= 封面（16:9） ================= */
export const MyCover: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f, fps, config: { damping: 30, stiffness: 90 } });
  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <div style={{ position: 'absolute', left: 96, top: 118 }}>
        <div style={{ fontFamily: F, fontSize: 28, letterSpacing: 5, color: MUTED,
          opacity: c01(p) }}>{CONTENT.s1.kicker}</div>
        <div style={{ marginTop: 44, fontFamily: F, fontSize: 132, fontWeight: 600,
          lineHeight: 1.16, letterSpacing: -3, color: INK }}>
          {CONTENT.s1.lines[0]}
          <br />
          <span style={{ color: CA, opacity: c01((p - 0.3) / 0.7) }}>
            {CONTENT.s1.lines[1]}
          </span>
        </div>
        <div style={{ width: 160 * p, height: 6, background: CB, marginTop: 52 }} />
        <div style={{ fontFamily: F, fontSize: 36, color: MUTED, marginTop: 34,
          opacity: c01((p - 0.5) / 0.5) }}>{CONTENT.s1.sub}</div>
      </div>
      <div style={{ position: 'absolute', right: 96, bottom: 96, fontFamily: MONO,
        fontSize: 26, color: MUTED, textAlign: 'right', lineHeight: 1.9 }}>
        <div>PCL 2.99.0.0</div>
        <div>HMCL 3.17.0.362</div>
        <div style={{ color: INK }}>2026.10.20</div>
      </div>
    </AbsoluteFill>
  );
};
