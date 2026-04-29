'use client';
import { ThreeColumnLayout } from '@/components/shell/ThreeColumnLayout';
import { TopBar } from '@/components/shell/TopBar';

export default function ConsolePage() {
  return (
    <ThreeColumnLayout
      top={<TopBar />}
      left={<div className="text-sm text-neutral-400">左：上下文（占位）</div>}
      center={<div className="text-sm text-neutral-400">中：当前视图（占位）</div>}
      right={<div className="text-sm text-neutral-400">右：Run 流（占位）</div>}
    />
  );
}
