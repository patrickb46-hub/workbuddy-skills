/**
 * my-index.tsx — 独立入口，不动 Remotion 工程原有的 Root.tsx
 * 渲染：npx remotion render src/my-index.tsx Explainer out.mp4
 * 好处：多个视频各自一个入口，互不干扰。
 *
 * ⚠️ 拷贝后必须把下一行的 './ExplainerTemplate' 改成你实际的文件名（如 './MyVideo'），
 *    否则报 Module not found。这是改名后唯一必须同步的地方。
 */
import React from 'react';
import { Composition, registerRoot } from 'remotion';
import { Explainer } from './ExplainerTemplate';
import { FPS, TOTAL_FRAMES } from './timing';

const Root: React.FC = () => (
  <Composition
    id="Explainer"
    component={Explainer}
    durationInFrames={TOTAL_FRAMES}
    fps={FPS}
    width={1920}
    height={1080}
  />
);

registerRoot(Root);
