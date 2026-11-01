/**
 * GeometryKit.tsx — 几何主题科普短片零件库（6 场 + 封面 · navy）
 *
 * 用法：拷到 Remotion 工程 src/ 下改名 MyVideo.tsx，只改 CONTENT。
 * 机制同 SceneKit：tts_narrate.py 一句一场，这里按 id 合并并记 at[]。
 */
import React from 'react';
import {
  AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig,
} from 'remotion';
import { SCENES, TOTAL_FRAMES } from './timing';

/* ========== navy 设计变量 ========== */
const F = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif';
const MONO = '"SF Mono","Menlo","PingFang SC",monospace';
const BG = '#0A1628';
const INK = '#E6F0FF';
const MUTED = '#5C6B84';
const RULE = '#1C2A44';
const PANEL = '#0E1E36';
const CA = '#38D6C4';   // accent 青
const CB = '#FF6B6B';   // 错误红
const GOOD = '#5DD39E'; // 正确绿
const PAD = 110;

const CL = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const c01 = (v: number) => Math.min(1, Math.max(0, v));
const t = (at: number[], i: number) => at[Math.min(i, Math.max(0, at.length - 1))] ?? 0;

/* ============================================================
 * 本片文案
 * ============================================================ */
export const CONTENT = {
  header: { left: '{{AUTHOR}}', right: '科普 · 能力边界' },

  s1: {
    kicker: '一道几何题，一个出错的地方',
    lines: ['数字全对', '图是错的'],
    accentLine: 1,
    sub: 'AI 画几何图，错在哪、为什么错、怎么查',
  },

  s2: {
    tag: '现象',
    title: '四类错误',
    note: '没有一类，是数字能发现的',
    items: [
      { no: '01', name: '拓扑错', sub: '该连 A 到 D，连成了 A 到 C', variant: 'topology' as const },
      { no: '02', name: '标记漏', sub: '两边等长，只画了一组', variant: 'missing' as const },
      { no: '03', name: '线型错', sub: '该是虚线，画成了实线', variant: 'linetype' as const },
      { no: '04', name: '方向反', sub: '整张图左右镜像', variant: 'mirror' as const },
    ],
    footer: '三点共线成立、勾股数对得上、角度和也对 —— 一个都不报错',
  },

  s3: {
    tag: '归因',
    title: '为什么数字对，图还错',
    note: '三个缺口，一个比一个隐蔽',
    items: [
      { no: '01', title: '自洽不等于同一', sub: '自检只证明图自己没矛盾，证明不了它和原题是同一张' },
      { no: '02', title: '坐标系翻了个面', sub: '屏幕 y 轴朝下，数学 y 轴朝上，一搬就镜像' },
      { no: '03', title: '文字本来就会丢信息', sub: '你写「画一条高」，它不知道从哪个顶点画' },
    ],
  },

  s4: {
    tag: '机制',
    title: '怎么才算真的对过',
    note: '把两张图并排摆出来，八项逐条对',
    left: { title: '原题', variant: 'correct' as const },
    right: { title: '重绘', variant: 'topology' as const },
    checks: [
      { name: '拓扑', ok: false },
      { name: '点位顺序', ok: true },
      { name: '字母标注', ok: true },
      { name: '特殊标记', ok: false },
      { name: '线型', ok: true },
      { name: '左右方向', ok: true },
      { name: '图上数值', ok: true },
      { name: '坐标刻度', ok: true },
    ],
    footer: '错的那一项，一眼就能看见',
  },

  s5: {
    tag: '自查',
    title: '四步，两分钟',
    note: '交作业之前，值得走一遍',
    steps: [
      { no: '01', title: '先不看数字', sub: '只看形状对不对' },
      { no: '02', title: '并排对照', sub: '把原题放在旁边' },
      { no: '03', title: '八项逐条过', sub: '重点看拓扑和标记' },
      { no: '04', title: '改完必须重跑', sub: '凭记忆等于没改' },
    ],
    footer: '两分钟，换一次不返工',
  },

  s6: {
    tag: '收束',
    title: '验证比生成难',
    note: '这句话，可能是用好 AI 的关键',
    closing: 'AI 是草稿纸',
    closing2: '不是答案',
    footer: '数字对，不代表图对；图对，才代表题对',
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
    <div style={{ opacity: c01(p),
      transform: `translate(${(1 - p) * x}px, ${(1 - p) * y}px)`, ...style }}>{children}</div>
  );
};

const Head: React.FC<{ tag: string; title: string; note?: string; delay?: number }> =
  ({ tag, title, note, delay = 0 }) => (
    <div style={{ position: 'absolute', left: PAD, top: 150 }}>
      <Reveal delay={delay + 1}>
        <div style={{ fontFamily: F, fontSize: 24, letterSpacing: 4, color: MUTED }}>{tag}</div>
      </Reveal>
      <Reveal delay={delay + 4}>
        <div style={{ fontFamily: F, fontSize: 68, fontWeight: 600, color: INK,
          letterSpacing: -1, lineHeight: 1.15, marginTop: 14 }}>{title}</div>
      </Reveal>
      {note ? (
        <Reveal delay={delay + 9}>
          <div style={{ fontFamily: F, fontSize: 30, color: MUTED, marginTop: 10 }}>{note}</div>
        </Reveal>
      ) : null}
    </div>
  );

const Rule: React.FC<{ w?: number; color?: string; delay?: number }> =
  ({ w = 96, color = CA, delay = 0 }) => {
    const f = useCurrentFrame();
    const { fps } = useVideoConfig();
    const p = spring({ frame: Math.max(0, f - delay), fps,
      config: { damping: 30, stiffness: 90 } });
    return <div style={{ width: w * p, height: 4, background: color }} />;
  };

/* ========== 几何图零件 ========== */
type Variant = 'correct' | 'topology' | 'missing' | 'linetype' | 'mirror';

const GeoFigure: React.FC<{ variant: Variant; width?: number; reveal?: number }> = ({
  variant, width = 480, reveal = 1,
}) => {
  const A: [number, number] = [240, 70];
  const B: [number, number] = [80, 400];
  const C: [number, number] = [400, 400];
  const D: [number, number] = [240, 400];
  const Dp: [number, number] = [310, 400];

  const equalTick = (mx: number, my: number, nx: number, ny: number, color = INK) => {
    const dx = nx - mx, dy = ny - my;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = -dy / len, uy = dx / len;
    return (
      <g stroke={color} strokeWidth={3}>
        <line x1={mx + ux * 9} y1={my + uy * 9} x2={mx - ux * 9} y2={my - uy * 9} />
        <line x1={nx + ux * 9} y1={ny + uy * 9} x2={nx - ux * 9} y2={ny - uy * 9} />
      </g>
    );
  };

  const rightAngle = (cx: number, cy: number, size: number, color = MUTED) => (
    <polyline points={`${cx},${cy - size} ${cx + size},${cy - size} ${cx + size},${cy}`}
      fill="none" stroke={color} strokeWidth={2.5} />
  );

  const tri = (color = INK, dash?: string) => (
    <polygon points={`${A[0]},${A[1]} ${B[0]},${B[1]} ${C[0]},${C[1]}`}
      fill="none" stroke={color} strokeWidth={3.5} strokeLinejoin="round"
      strokeDasharray={dash} />
  );

  const del = (color = INK) => (
    <g fontFamily={MONO} fontSize={30} fill={color}>
      <text x={240} y={44} textAnchor="middle">A</text>
      <text x={52} y={424}>B</text>
      <text x={424} y={424}>C</text>
    </g>
  );

  const body = () => {
    if (variant === 'correct') {
      return (
        <>
          {tri()}
          <line x1={A[0]} y1={A[1]} x2={D[0]} y2={D[1]} stroke={CA} strokeWidth={3} />
          {equalTick((A[0] + B[0]) / 2, (A[1] + B[1]) / 2, (A[0] + C[0]) / 2, (A[1] + C[1]) / 2)}
          {rightAngle(D[0], D[1], 22)}
          {del()}
          <text x={254} y={426} fontFamily={MONO} fontSize={26} fill={CA}>D</text>
        </>
      );
    }
    if (variant === 'topology') {
      return (
        <>
          {tri()}
          <circle cx={D[0]} cy={D[1]} r={9} fill="none" stroke={MUTED} strokeWidth={2}
            strokeDasharray="4 4" />
          <line x1={A[0]} y1={A[1]} x2={326} y2={400} stroke={CB} strokeWidth={4} />
          <circle cx={326} cy={400} r={6} fill={CB} />
          <g stroke={CB} strokeWidth={4}>
            <line x1={268} y1={214} x2={294} y2={240} />
            <line x1={294} y1={214} x2={268} y2={240} />
          </g>
          {del()}
          <text x={254} y={426} fontFamily={MONO} fontSize={26} fill={MUTED}>D</text>
        </>
      );
    }
    if (variant === 'missing') {
      return (
        <>
          {tri()}
          <line x1={A[0]} y1={A[1]} x2={D[0]} y2={D[1]} stroke={CA} strokeWidth={3} />
          <g stroke={CB} strokeWidth={2.5} strokeDasharray="5 5" opacity={0.9}>
            <circle cx={(A[0] + B[0]) / 2} cy={(A[1] + B[1]) / 2} r={16} fill="none" />
            <circle cx={(A[0] + C[0]) / 2} cy={(A[1] + C[1]) / 2} r={16} fill="none" />
          </g>
          {del()}
          <text x={254} y={426} fontFamily={MONO} fontSize={26} fill={CA}>D</text>
        </>
      );
    }
    if (variant === 'linetype') {
      return (
        <>
          {tri()}
          <line x1={A[0]} y1={A[1]} x2={D[0]} y2={D[1]} stroke={CA} strokeWidth={3} />
          <line x1={C[0]} y1={C[1]} x2={470} y2={C[1]} stroke={CB} strokeWidth={4} />
          <text x={418} y={368} fontFamily={F} fontSize={20} fill={CB}>该虚线</text>
          {del()}
          <text x={254} y={426} fontFamily={MONO} fontSize={26} fill={CA}>D</text>
        </>
      );
    }
    // mirror
    return (
      <>
        <line x1={240} y1={40} x2={240} y2={440} stroke={MUTED} strokeWidth={1.5}
          strokeDasharray="6 8" opacity={0.6} />
        <g transform="translate(480 0) scale(-1 1)" opacity={0.35}>
          {tri(MUTED, '6 6')}
        </g>
        {tri()}
        <line x1={A[0]} y1={A[1]} x2={D[0]} y2={D[1]} stroke={CA} strokeWidth={3} />
        <g fontFamily={MONO} fontSize={30} fill={INK}>
          <text x={240} y={44} textAnchor="middle">A</text>
          <text x={424} y={424}>B</text>
          <text x={52} y={424}>C</text>
        </g>
        <text x={254} y={426} fontFamily={MONO} fontSize={26} fill={CA}>D</text>
        <g fontFamily={MONO} fontSize={26} fill={CB}>
          <text x={396} y={150}>⇄</text>
        </g>
      </>
    );
  };

  return (
    <svg width={width} height={width * (460 / 480)} viewBox="0 0 480 460"
      style={{ opacity: c01(reveal) }}>
      {body()}
    </svg>
  );
};

/* ========== s1 · 钩子（4 句） ========== */
const S1 = ({ at }: Props) => {
  const c = CONTENT.s1;
  const a0 = t(at, 0), a1 = t(at, 1), a2 = t(at, 2), a3 = t(at, 3);
  return (
    <>
      <div style={{ position: 'absolute', left: PAD, top: 250 }}>
        <Reveal delay={a0 + 2}>
          <div style={{ fontFamily: F, fontSize: 26, letterSpacing: 4, color: MUTED }}>{c.kicker}</div>
        </Reveal>
        {c.lines.map((ln, i) => (
          <Reveal key={i} delay={i === 0 ? a0 + 8 : a1 + 2}>
            <div style={{ fontFamily: F, fontSize: 100, fontWeight: 600,
              color: i === c.accentLine ? CB : INK, letterSpacing: -2, lineHeight: 1.18,
              marginTop: i === 0 ? 26 : 0 }}>{ln}</div>
          </Reveal>
        ))}
        <div style={{ marginTop: 42 }}><Rule w={132} delay={a1 + 14} /></div>
        <Reveal delay={a2 + 4}>
          <div style={{ fontFamily: F, fontSize: 30, color: MUTED, marginTop: 26 }}>{c.sub}</div>
        </Reveal>
      </div>

      <div style={{ position: 'absolute', right: 120, top: 210 }}>
        <Reveal delay={a1} x={-24}>
          <div style={{ background: PANEL, border: `1.5px solid ${RULE}`, borderRadius: 16,
            padding: 24 }}>
            <GeoFigure variant="topology" width={520} />
          </div>
        </Reveal>
      </div>

      <Reveal delay={a3} style={{ position: 'absolute', left: PAD, bottom: 160 }}>
        <div style={{ fontFamily: F, fontSize: 26, color: CB }}>它说连 A 到 D，图上 A 连到了 C</div>
      </Reveal>
    </>
  );
};

/* ========== s2 · 四类错误（10 句） ========== */
const S2 = ({ at }: Props) => {
  const c = CONTENT.s2;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 4} />

      {c.items.map((it, i) => (
        <Reveal key={it.no} delay={t(at, i === 0 ? 0 : i === 1 ? 3 : i === 2 ? 5 : 6) - 18}
          style={{ position: 'absolute', left: PAD + i * 410, top: 400, width: 380 }}>
          <div style={{ background: PANEL, border: `1.5px solid ${RULE}`, borderRadius: 14,
            padding: '18px 0 12px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '0 22px' }}>
              <span style={{ fontFamily: MONO, fontSize: 20, color: CB }}>{it.no}</span>
              <span style={{ fontFamily: F, fontSize: 30, fontWeight: 600, color: INK }}>
                {it.name}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 4 }}>
              <GeoFigure variant={it.variant} width={250} />
            </div>
            <div style={{ fontFamily: F, fontSize: 21, color: MUTED, padding: '0 22px',
              lineHeight: 1.5, minHeight: 62 }}>{it.sub}</div>
          </div>
        </Reveal>
      ))}

      <Reveal delay={t(at, 8)} style={{ position: 'absolute', left: PAD, bottom: 160 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ width: 4, height: 40, background: CB }} />
          <div style={{ fontFamily: F, fontSize: 27, color: INK }}>{c.footer}</div>
        </div>
      </Reveal>
    </>
  );
};

/* ========== s3 · 三列归因（9 句） ========== */
const S3 = ({ at }: Props) => {
  const c = CONTENT.s3;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 6} />

      {c.items.map((it, i) => (
        <Reveal key={it.no} delay={t(at, [1, 5, 7][i]) - 10}
          style={{ position: 'absolute', left: PAD + i * 545, top: 470, width: 490 }}>
          <div style={{ borderTop: `1.5px solid ${RULE}`, paddingTop: 24 }}>
            <div style={{ fontFamily: MONO, fontSize: 26, color: CA }}>{it.no}</div>
            <div style={{ fontFamily: F, fontSize: 36, fontWeight: 600, color: INK,
              marginTop: 14, lineHeight: 1.3 }}>{it.title}</div>
            <div style={{ fontFamily: F, fontSize: 24, color: MUTED, marginTop: 14,
              lineHeight: 1.7 }}>{it.sub}</div>
          </div>
        </Reveal>
      ))}

      <Reveal delay={t(at, 8)} style={{ position: 'absolute', left: PAD, bottom: 160 }}>
        <div style={{ fontFamily: F, fontSize: 26, color: CA }}>
          自洽是必要条件，不是充分条件
        </div>
      </Reveal>
    </>
  );
};

/* ========== s4 · 并排对照 + 八项（10 句） ========== */
const S4 = ({ at }: Props) => {
  const c = CONTENT.s4;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 6} />

      <Reveal delay={t(at, 1) - 16} style={{ position: 'absolute', left: PAD, top: 380 }}>
        <div style={{ background: PANEL, border: `1.5px solid ${RULE}`, borderRadius: 14,
          padding: '14px 18px 10px', width: 470 }}>
          <div style={{ fontFamily: F, fontSize: 24, color: GOOD, letterSpacing: 2 }}>{c.left.title}</div>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <GeoFigure variant={c.left.variant} width={400} />
          </div>
        </div>
      </Reveal>

      <Reveal delay={t(at, 2) - 16} style={{ position: 'absolute', right: PAD, top: 380 }}>
        <div style={{ background: PANEL, border: `1.5px solid ${CB}`, borderRadius: 14,
          padding: '14px 18px 10px', width: 470 }}>
          <div style={{ fontFamily: F, fontSize: 24, color: CB, letterSpacing: 2 }}>{c.right.title}</div>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <GeoFigure variant={c.right.variant} width={400} />
          </div>
        </div>
      </Reveal>

      <div style={{ position: 'absolute', left: 0, right: 0, top: 836, textAlign: 'center' }}>
        <Reveal delay={t(at, 3) - 10}>
          <span style={{ fontFamily: MONO, fontSize: 34, color: CA }}>⇄</span>
          <span style={{ fontFamily: F, fontSize: 26, color: MUTED, margin: '0 16px' }}>
            八项逐条对
          </span>
        </Reveal>
      </div>

      <div style={{ position: 'absolute', left: PAD, right: PAD, top: 890,
        display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
        {c.checks.map((ck, i) => (
          <Reveal key={ck.name} delay={t(at, 4 + Math.min(i, 3)) - 6} y={12}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px',
              border: `1.5px solid ${ck.ok ? RULE : CB}`, borderRadius: 8,
              background: ck.ok ? 'transparent' : 'rgba(255,107,107,0.08)' }}>
              <span style={{ fontFamily: MONO, fontSize: 20,
                color: ck.ok ? GOOD : CB }}>{ck.ok ? '✓' : '×'}</span>
              <span style={{ fontFamily: F, fontSize: 22,
                color: ck.ok ? MUTED : INK }}>{ck.name}</span>
            </div>
          </Reveal>
        ))}
      </div>

      {/* 这句与字幕重复，删掉，避免 B 版同一句话出现两次 */}
    </>
  );
};

/* ========== s5 · 自查四步（9 句） ========== */
const S5 = ({ at }: Props) => {
  const c = CONTENT.s5;
  return (
    <>
      <Head tag={c.tag} title={c.title} note={c.note} delay={t(at, 0) - 4} />

      {c.steps.map((s, i) => (
        <Reveal key={s.no} delay={t(at, i + 1) - 20}
          style={{ position: 'absolute', left: PAD, top: 450 + i * 122, width: 1500 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 36 }}>
            <div style={{ width: 72, height: 72, borderRadius: 36, border: `1.5px solid ${CA}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: MONO, fontSize: 26, color: CA }}>{s.no}</span>
            </div>
            <div style={{ width: 380, fontFamily: F, fontSize: 38, fontWeight: 600, color: INK }}>
              {s.title}
            </div>
            <div style={{ fontFamily: F, fontSize: 26, color: MUTED }}>{s.sub}</div>
          </div>
        </Reveal>
      ))}

      <Reveal delay={t(at, 7)} style={{ position: 'absolute', left: PAD, bottom: 160 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ width: 40, height: 4, background: CB }} />
          <div style={{ fontFamily: F, fontSize: 26, color: CB }}>{c.footer}</div>
        </div>
      </Reveal>
    </>
  );
};

/* ========== s6 · 收束（6 句） ========== */
const S6 = ({ at }: Props) => {
  const c = CONTENT.s6;
  return (
    <>
      <div style={{ position: 'absolute', left: PAD, top: 200 }}>
        <Reveal delay={t(at, 0) + 2}>
          <div style={{ fontFamily: F, fontSize: 24, letterSpacing: 4, color: MUTED }}>{c.tag}</div>
        </Reveal>
        <Reveal delay={t(at, 1)}>
          <div style={{ fontFamily: F, fontSize: 76, fontWeight: 600, color: INK,
            letterSpacing: -1, marginTop: 18 }}>{c.title}</div>
        </Reveal>
        <Reveal delay={t(at, 2)}>
          <div style={{ fontFamily: F, fontSize: 28, color: MUTED, marginTop: 14 }}>{c.note}</div>
        </Reveal>
      </div>

      <Reveal delay={t(at, 3)} style={{ position: 'absolute', right: PAD, top: 236, width: 700 }}>
        <div style={{ width: 88, height: 4, background: CB }} />
        <div style={{ fontFamily: F, fontSize: 58, fontWeight: 600, color: INK,
          lineHeight: 1.38, marginTop: 28 }}>
          {c.closing}
          <br />
          <span style={{ color: CA }}>{c.closing2}</span>
        </div>
      </Reveal>

      <Reveal delay={t(at, 5)} style={{ position: 'absolute', left: PAD, bottom: 170 }}>
        <div style={{ fontFamily: F, fontSize: 30, color: MUTED }}>{c.footer}</div>
      </Reveal>
    </>
  );
};

/* ================= 装配 ================= */
const COMPONENTS: Record<string, React.FC<Props>> = {
  s1: S1, s2: S2, s3: S3, s4: S4, s5: S5, s6: S6,
};

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
  if (out.length) out[out.length - 1].frames = TOTAL_FRAMES - out[out.length - 1].start;
  return out;
};

const SceneShell: React.FC<{ id: string; frames: number; at: number[]; index: number; total: number }> =
  ({ id, frames, at, index, total }) => {
    const f = useCurrentFrame();
    const Comp = COMPONENTS[id] ?? (() => null);
    const fin = interpolate(f, [0, 6], [0, 1], CL);
    const fout = interpolate(f, [frames - 6, frames - 1], [1, 0], CL);
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

/* ================= 封面 ================= */
export const MyCover: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f, fps, config: { damping: 30, stiffness: 90 } });
  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <div style={{ position: 'absolute', left: 96, top: 120 }}>
        <div style={{ fontFamily: F, fontSize: 28, letterSpacing: 5, color: MUTED,
          opacity: c01(p) }}>一道几何题 · 一个出错的地方</div>
        <div style={{ marginTop: 42, fontFamily: F, fontSize: 126, fontWeight: 600,
          lineHeight: 1.16, letterSpacing: -3, color: INK }}>
          数字全对
          <br />
          <span style={{ color: CB, opacity: c01((p - 0.3) / 0.7) }}>图是错的</span>
        </div>
        <div style={{ width: 160 * p, height: 6, background: CA, marginTop: 48 }} />
        <div style={{ fontFamily: F, fontSize: 36, color: MUTED, marginTop: 32,
          opacity: c01((p - 0.5) / 0.5) }}>
          AI 画几何图，错在哪、为什么错、怎么查
        </div>
      </div>
      <div style={{ position: 'absolute', right: 96, top: 150, opacity: c01((p - 0.2) / 0.8) }}>
        <div style={{ background: PANEL, border: `1.5px solid ${RULE}`, borderRadius: 16, padding: 26 }}>
          <GeoFigure variant="topology" width={520} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
