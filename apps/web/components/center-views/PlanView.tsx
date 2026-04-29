'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function PlanView() {
  const plan = (useStateStore((s) => s.state).plan ?? null) as any;
  if (!plan) return <div className="text-neutral-400 text-sm">尚无计划</div>;
  return (
    <div className="space-y-3 font-mono text-sm">
      <div className="border border-neutral-800 rounded p-3">
        <div className="text-[10px] uppercase text-neutral-500">仓位上限</div>
        <div className="text-lg">{((plan.position_total_max ?? 0) * 100).toFixed(0)}%</div>
      </div>
      <div className="border border-neutral-800 rounded p-3">
        <div className="text-[10px] uppercase text-neutral-500">候选</div>
        <ul>
          {(plan.candidates ?? []).map((c: any, i: number) => (
            <li key={i}>{c.code} {c.name ?? ''} weight={(c.weight ?? 0).toFixed?.(2) ?? c.weight}</li>
          ))}
        </ul>
      </div>
      {plan.notes && (
        <div className="border border-neutral-800 rounded p-3 whitespace-pre-wrap text-neutral-300">{plan.notes}</div>
      )}
    </div>
  );
}
