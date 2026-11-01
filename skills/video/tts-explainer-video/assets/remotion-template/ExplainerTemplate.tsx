/**
 * ExplainerTemplate.tsx — 讲解视频骨架（浅色、扁平、代码绘制）
 *
 * 用法：拷进 Remotion 工程的 src/，改 SCENES 对应的 4 个 Scene 组件。
 * 时长由 timing.ts 决定（tts_narrate.py 生成），不要手写秒数。
 *
 * 设计约束（与 diagram-design 一致）：
 *   · 一屏最多 6 个视觉元素，密度 4/10
 *   · 强调色只给 1–2 处，其余灰阶
 *   · 4px 网格，不用阴影、不用渐变
 *   · 中文用 PingFang SC（系统自带，不必打包字体）
 */
import React from 'react';
import {
  AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { SCENES, TOTAL_FRAMES } from './timing';

/* ---------------- 设计变量：改这里换整体气质 ---------------- */
const F = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif';
const MONO = '"SF Mono","Menlo","PingFang SC",monospace';
const BG = '#F6F5F1';      // 暖白，比纯白耐看，投影时也不刺眼
const INK = '#1A1A17';
const MUTED = '#8B8880';
const RULE = '#DCD8CE';
const CA = '#2E6E8E';      // 主强调色（A 组）
const CB = '#B04E36';      // 次强调色（B 组）
const PAD = 110;

const CL = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const c01 = (v: number) => Math.min(1, Math.max(0, v));

/* ---------------- 通用零件 ---------------- */
const Reveal: React.FC<{ delay?: number; y?: number; children: React.ReactNode; style?: React.CSSProperties }> =
  ({ delay = 0, y = 26, children, style }) => {
    const f = useCurrentFrame();
    const { fps } = useVideoConfig();
    const p = spring({ frame: Math.max(0, f - delay), fps,
      config: { damping: 22, stiffness: 110, mass: 1 } });
    return (
      <div style={{ opacity: c01(p), transform: `translateY(${(1 - p) * y}px)`, ...style }}>
        {children}
      </div>
    );
  };

const Head: React.FC<{ tag: string; title: string; note?: string }> = ({ tag, title, note }) => (
  <div style={{ position: 'absolute', left: PAD, top: 168 }}>
    <Reveal delay={2}>
      <div style={{ fontFamily: F, fontSize: 25, letterSpacing: 3, color: MUTED, marginBottom: 16 }}>
        {tag}
      </div>
    </Reveal>
    <Reveal delay={6}>
      <div style={{ fontFamily: F, fontSize: 74, fontWeight: 600, color: INK,
        letterSpacing: -1, lineHeight: 1.12 }}>{title}</div>
    </Reveal>
    {note ? (
      <Reveal delay={12}>
        <div style={{ fontFamily: F, fontSize: 36, color: MUTED, marginTop: 12 }}>{note}</div>
      </Reveal>
    ) : null}
  </div>
);

/* ---------------- 柱状图 ---------------- */
const PLOT_X = 110, PLOT_W = 1700, PLOT_TOP = 430, PLOT_BOT = 880, MAXV = 80;
const COL_W = PLOT_W / 4, BAR_W = 190;
const yOf = (v: number) => PLOT_BOT - (v / MAXV) * (PLOT_BOT - PLOT_TOP);
const cxOf = (i: number) => PLOT_X + i * COL_W + COL_W / 2;

type Bar = {
  label: string; sub?: string; value: number; color: string;
  grow?: boolean; dim?: boolean; tag?: string; tagColor?: string; placeholder?: boolean;
};

const Chart: React.FC<{
  bars: Bar[]; delay?: number; stagger?: number;
  guide?: { value: number; x1: number; x2: number; label: string };
}> = ({ bars, delay = 14, stagger = 30, guide }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <>
      <svg width={1920} height={1080} style={{ position: 'absolute', left: 0, top: 0 }}>
        {[0, 20, 40, 60, 80].map((v) => (
          <g key={v}>
            <line x1={PLOT_X} y1={yOf(v)} x2={PLOT_X + PLOT_W} y2={yOf(v)}
              stroke={v === 0 ? RULE : '#E8E5DC'} strokeWidth={v === 0 ? 2 : 1} />
            <text x={PLOT_X - 14} y={yOf(v) - 10} textAnchor="end" fontFamily={MONO}
              fontSize={21} fill={MUTED}
              opacity={c01(interpolate(f, [delay - 8, delay], [0, 1], CL))}>{v}</text>
          </g>
        ))}
        {guide ? (
          <g opacity={c01(interpolate(f, [delay + 16, delay + 30], [0, 1], CL))}>
            <line x1={guide.x1} y1={yOf(guide.value)} x2={guide.x2} y2={yOf(guide.value)}
              stroke={MUTED} strokeWidth={2} strokeDasharray="7 7" />
            <text x={guide.x2} y={yOf(guide.value) - 14} textAnchor="end" fontFamily={F}
              fontSize={24} fill={MUTED}>{guide.label}</text>
          </g>
        ) : null}
      </svg>

      {bars.map((b, i) => {
        const p = b.grow
          ? c01(spring({ frame: Math.max(0, f - delay - i * stagger), fps,
              config: { damping: 16, stiffness: 90, mass: 1.2 } }))
          : 1;
        const h = (b.value / MAXV) * (PLOT_BOT - PLOT_TOP) * p;
        const appear = c01(interpolate(f, [delay, delay + 10], [0, 1], CL));
        const op = b.dim ? 0.28 : 1;
        return (
          <div key={i}>
            {b.placeholder ? null : (
              <div style={{ position: 'absolute', left: cxOf(i) - BAR_W / 2, top: PLOT_BOT - h,
                width: BAR_W, height: h, background: b.color, opacity: op * appear }} />
            )}
            <div style={{ position: 'absolute', left: cxOf(i) - COL_W / 2, width: COL_W,
              top: PLOT_BOT - h - 62, textAlign: 'center', fontFamily: MONO, fontSize: 44,
              fontWeight: 600, color: b.dim ? MUTED : INK,
              opacity: c01((p - 0.55) / 0.45) * (b.dim ? 0.6 : 1) }}>
              {b.placeholder ? '—' : b.value === 0 ? '0%' : `${(b.value * p).toFixed(1)}%`}
            </div>
            {b.tag ? (
              <div style={{ position: 'absolute', left: cxOf(i) - COL_W / 2, width: COL_W,
                top: PLOT_BOT - h - 118, textAlign: 'center', fontFamily: F, fontSize: 27,
                fontWeight: 600, color: b.tagColor ?? INK,
                opacity: c01((p - 0.7) / 0.3), letterSpacing: 1 }}>{b.tag}</div>
            ) : null}
            <div style={{ position: 'absolute', left: cxOf(i) - COL_W / 2, width: COL_W,
              top: PLOT_BOT + 24, textAlign: 'center', fontFamily: F, fontSize: 34,
              fontWeight: b.tag ? 600 : 400, color: b.dim ? MUTED : INK, opacity: appear }}>
              {b.label}
              {b.sub ? <div style={{ fontSize: 23, color: MUTED, marginTop: 6 }}>{b.sub}</div> : null}
            </div>
          </div>
        );
      })}
    </>
  );
};

/* ---------------- 箭头 / 方块 ---------------- */
const Arrow: React.FC<{ x1: number; y1: number; x2: number; y2: number; color?: string;
  label?: string; dur?: number; delay?: number; dashed?: boolean }> =
  ({ x1, y1, x2, y2, color = MUTED, label, dur = 16, delay = 0, dashed }) => {
    const f = useCurrentFrame();
    const p = c01(interpolate(f, [delay, delay + dur], [0, 1], CL));
    const ang = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
    return (
      <g>
        <line x1={x1} y1={y1} x2={x1 + (x2 - x1) * p} y2={y1 + (y2 - y1) * p}
          stroke={color} strokeWidth={3} strokeDasharray={dashed ? '10 8' : undefined} />
        {p > 0.92 ? <polygon points="-2,-9 14,0 -2,9" fill={color}
          transform={`translate(${x2},${y2}) rotate(${ang})`} /> : null}
        {label ? (
          <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 16} textAnchor="middle"
            fontFamily={F} fontSize={26} fill={MUTED} opacity={p}>{label}</text>
        ) : null}
      </g>
    );
  };

const Box: React.FC<{ x: number; y: number; w: number; h: number; label: string; sub?: string;
  fill?: string; color?: string; outline?: boolean; dashed?: boolean; delay?: number; fs?: number }> =
  ({ x, y, w, h, label, sub, fill, color = INK, outline, dashed, delay = 0, fs = 40 }) => {
    const f = useCurrentFrame();
    const { fps } = useVideoConfig();
    const p = spring({ frame: Math.max(0, f - delay), fps, config: { damping: 20, stiffness: 110 } });
    return (
      <div style={{ position: 'absolute', left: x, top: y, width: w, height: h,
        background: outline ? 'transparent' : fill ?? INK,
        border: outline ? `2px ${dashed ? 'dashed' : 'solid'} ${RULE}` : 'none',
        color: outline ? MUTED : color, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', fontFamily: F,
        opacity: c01(p), transform: `scale(${0.94 + 0.06 * p})` }}>
        <div style={{ fontSize: fs, fontWeight: 600, letterSpacing: 1 }}>{label}</div>
        {sub ? <div style={{ fontSize: 24, marginTop: 10, opacity: 0.72 }}>{sub}</div> : null}
      </div>
    );
  };

/* ================= 场景：改成你的内容 ================= */

/* s1 · 标题页 —— 一行主张 + 右侧参数栏 */
const S1 = () => (
  <>
    <div style={{ position: 'absolute', left: PAD, top: 300 }}>
      <Reveal delay={4}>
        <div style={{ fontFamily: F, fontSize: 26, letterSpacing: 4, color: MUTED }}>
          一句钩子 ｜ 时间 ｜ 做的事
        </div>
      </Reveal>
      <Reveal delay={10}>
        <div style={{ fontFamily: F, fontSize: 108, fontWeight: 600, color: INK,
          letterSpacing: -2, lineHeight: 1.18, marginTop: 26 }}>
          主标题第一行
          <br />
          主标题第二行
        </div>
      </Reveal>
      <Reveal delay={22}>
        <div style={{ width: 132, height: 4, background: INK, marginTop: 44 }} />
      </Reveal>
      <Reveal delay={26}>
        <div style={{ fontFamily: F, fontSize: 34, color: MUTED, marginTop: 30 }}>
          一行副标题：设备 / 规模 / 时间
        </div>
      </Reveal>
    </div>
    <Reveal delay={30} style={{ position: 'absolute', right: PAD, top: 340, width: 430 }}>
      <div style={{ fontFamily: MONO, fontSize: 25, lineHeight: 2.05, color: MUTED, textAlign: 'right' }}>
        <div>KEY  value</div>
        <div>KEY  value</div>
        <div style={{ color: INK }}>KEY  value</div>
      </div>
    </Reveal>
  </>
);

/* s2 · 两件事对照 —— 两个方块 + 一句结论 */
const S2 = () => (
  <>
    <Head tag="对照组" title="A 和 B 差在哪" note="一句话说明差距的量级" />
    <Box x={485} y={640} w={150} h={150} label="" fill={INK} delay={8} />
    <Box x={801} y={472} w={318} h={318} label="" outline dashed delay={14} />
    <div style={{ position: 'absolute', left: 410, top: 816, width: 300, textAlign: 'center',
      fontFamily: F, fontSize: 30, color: INK }}>
      A 组
      <div style={{ fontSize: 23, color: MUTED, marginTop: 8 }}>说明</div>
    </div>
    <div style={{ position: 'absolute', left: 750, top: 816, width: 420, textAlign: 'center',
      fontFamily: F, fontSize: 30, color: MUTED }}>
      B 组
      <div style={{ fontSize: 23, color: MUTED, marginTop: 8 }}>说明</div>
    </div>
    <Reveal delay={40} style={{ position: 'absolute', left: 1262, top: 592 }}>
      <div style={{ fontFamily: F, fontSize: 31, color: CB, fontWeight: 600 }}>关键差异</div>
      <div style={{ fontFamily: F, fontSize: 24, color: MUTED, marginTop: 12 }}>补充一句</div>
    </Reveal>
    <svg width={1920} height={1080} style={{ position: 'absolute', left: 0, top: 0 }}>
      <Arrow x1={1252} y1={672} x2={1132} y2={672} delay={44} dashed color={CB} />
    </svg>
  </>
);

/* s3 · 柱子对比 —— 柱子按旁白念到的顺序逐根长出 */
const S3 = () => (
  <>
    <Head tag="数据" title="结论就写在这行" note="补充说明 / 对照量" />
    <Chart
      bars={[
        { label: '甲', sub: '对照', value: 48.3, color: '#BFB9AD', grow: true },
        { label: '乙', sub: '方法一', value: 53.3, color: CA, grow: true },
        { label: '丙', sub: '方法二', value: 66.7, color: CB, grow: true, tag: '最高' },
        { label: '丁', sub: '参照', value: 71.7, color: '#6B6862', grow: true },
      ]}
      guide={{ value: 48.3, x1: 620, x2: 1780, label: '「甲」的水平 48.3%' }}
    />
  </>
);

/* s4 · 结论页 —— 两行大字 */
const S4 = () => (
  <>
    <Reveal delay={2} style={{ position: 'absolute', left: PAD, top: 210 }}>
      <div style={{ fontFamily: F, fontSize: 26, letterSpacing: 4, color: MUTED }}>一句话的区别</div>
    </Reveal>
    {[
      { k: '方法一', v: '学得像', c: CA, top: 300, d: 8 },
      { k: '方法二', v: '真的会', c: CB, top: 470, d: 18 },
    ].map((r) => (
      <Reveal key={r.k} delay={r.d} style={{ position: 'absolute', left: PAD, top: r.top }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 34 }}>
          <div style={{ width: 58, height: 8, background: r.c, marginBottom: 16 }} />
          <div style={{ fontFamily: F, fontSize: 62, color: MUTED }}>{r.k}</div>
          <div style={{ fontFamily: F, fontSize: 96, fontWeight: 600, color: INK }}>
            {r.v.slice(0, r.v.length - 1)}
            <span style={{ color: r.c }}>{r.v.slice(-1)}</span>
          </div>
        </div>
      </Reveal>
    ))}
    <Reveal delay={30} style={{ position: 'absolute', left: PAD, top: 660 }}>
      <div style={{ width: 700, height: 2, background: RULE }} />
      <div style={{ fontFamily: F, fontSize: 32, color: MUTED, marginTop: 28, lineHeight: 1.75 }}>
        收束句：把整片的结论压成一句。
        <div style={{ fontSize: 26, marginTop: 14 }}>出处 / 样本量 / 统计量</div>
      </div>
    </Reveal>
  </>
);

/* ================= 装配 ================= */
const COMPONENTS: Record<string, React.FC> = { s1: S1, s2: S2, s3: S3, s4: S4 };

/* 需要"同一张图直接硬切"时，把前一场加进 NO_FADE_OUT、后一场加进 NO_FADE_IN，
   并把该场的柱子改成 grow:false（已在位）+ 只让新柱 grow */
const NO_FADE_OUT = new Set<string>([]);
const NO_FADE_IN = new Set<string>([]);

const SceneShell: React.FC<{ id: string; frames: number; index: number }> = ({ id, frames, index }) => {
  const f = useCurrentFrame();
  const Comp = COMPONENTS[id] ?? (() => null);
  const fin = NO_FADE_IN.has(id) ? 1 : interpolate(f, [0, 6], [0, 1], CL);
  const fout = NO_FADE_OUT.has(id) ? 1 : interpolate(f, [frames - 5, frames - 1], [1, 0], CL);
  return (
    <AbsoluteFill style={{ opacity: Math.min(fin, fout) }}>
      <Comp />
      <div style={{ position: 'absolute', left: PAD, bottom: 44, fontFamily: MONO,
        fontSize: 22, color: MUTED, letterSpacing: 1 }}>
        {String(index + 1).padStart(2, '0')} / {SCENES.length}
      </div>
    </AbsoluteFill>
  );
};

export const Explainer: React.FC = () => {
  let acc = 0;
  const items = SCENES.map((s, i) => {
    const from = acc;
    acc += s.frames;
    const last = i === SCENES.length - 1;
    // 最后一场必须吞掉片尾静默，否则结尾有 1 秒多纯背景拖尾
    const frames = last ? TOTAL_FRAMES - from : s.frames;
    return { ...s, from, frames, i };
  });

  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <div style={{ position: 'absolute', left: PAD, right: PAD, top: 54, display: 'flex',
        justifyContent: 'space-between', fontFamily: F, fontSize: 24, color: MUTED, letterSpacing: 2 }}>
        <span>频道 / 项目名</span>
        <span>这一期的主题</span>
      </div>
      <div style={{ position: 'absolute', left: PAD, right: PAD, top: 104, height: 1, background: RULE }} />
      {items.map((s) => (
        <Sequence key={s.id} from={s.from} durationInFrames={s.frames}>
          <SceneShell id={s.id} frames={s.frames} index={s.i} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
