'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function DataQualityBanner() {
  const errors = (useStateStore((s) => s.state).errors as string[] | undefined) ?? [];
  const incomplete = errors.some((e) => /no .* data|RemoteDisconnected|fetch failed/i.test(e));
  if (!incomplete) return null;
  return (
    <div className="bg-amber-950/40 border-b border-amber-800 px-4 py-1 text-xs font-mono text-amber-300">
      📊 数据不全，结论仅供参考
    </div>
  );
}
