'use client';
import { useViewStore } from '@/lib/store/viewStore';
import { KLineChart } from '@/components/charts/KLineChart';

export function LeaderDrawer() {
  const code = useViewStore((s) => s.selectedCode);
  const close = () => useViewStore.getState().selectCode(null);
  if (!code) return null;
  return (
    <div className="fixed right-0 top-0 h-full w-[480px] bg-neutral-950 border-l border-neutral-800 z-50 p-4 overflow-y-auto">
      <div className="flex justify-between mb-3">
        <h3 className="font-mono">{code}</h3>
        <button onClick={close} className="text-neutral-400 hover:text-neutral-200">×</button>
      </div>
      <KLineChart code={code} days={60} height={320} />
    </div>
  );
}
