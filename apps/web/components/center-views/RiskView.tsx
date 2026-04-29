'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function RiskView() {
  const flags = (useStateStore((s) => s.state).risk_flags ?? []) as string[];
  if (flags.length === 0) return <div className="text-neutral-400 text-sm">无风控触发</div>;
  return (
    <ul className="space-y-1 font-mono text-sm">
      {flags.map((f, i) => (
        <li key={i} className="border border-neutral-800 rounded px-2 py-1">{f}</li>
      ))}
    </ul>
  );
}
