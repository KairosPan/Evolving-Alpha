'use client';
import { useState } from 'react';

interface Props {
  snapshot: {
    risk_flags?: string[];
    candidates?: { code: string; name?: string }[];
    plan_position_cap?: number;
  };
  onApprove(patch?: Record<string, unknown>): void | Promise<void>;
}

export function RiskGuardReview({ snapshot, onApprove }: Props) {
  const initialFlags = snapshot.risk_flags ?? [];
  const [flags, setFlags] = useState<string[]>(initialFlags);
  const [cap, setCap] = useState(snapshot.plan_position_cap ?? 1);
  const flagsDirty = flags.length !== initialFlags.length;
  const capDirty = cap !== (snapshot.plan_position_cap ?? 1);

  function toggle(f: string) {
    setFlags((cur) => cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]);
  }

  function apply() {
    const patch: Record<string, unknown> = {};
    if (flagsDirty) patch.risk_flags = flags;
    if (capDirty) patch.position_total_max = cap;
    onApprove(patch);
  }

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-neutral-400">候选 {snapshot.candidates?.length ?? 0} 只 · 当前仓位上限 {(cap * 100).toFixed(0)}%</div>
      <ul className="space-y-1">
        {initialFlags.map((f) => (
          <li key={f} className="flex items-center gap-2">
            <input type="checkbox" checked={flags.includes(f)} onChange={() => toggle(f)} />
            <span>{f}</span>
          </li>
        ))}
        {initialFlags.length === 0 && <li className="text-neutral-500">无禁忌触发</li>}
      </ul>
      <label className="flex items-center gap-2">
        <span>仓位上限</span>
        <input type="number" min={0} max={1} step={0.1} value={cap}
               onChange={(e) => setCap(Number(e.target.value))}
               className="bg-neutral-900 border border-neutral-700 px-1 w-16" />
      </label>
      <button onClick={apply}
              className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded">通过</button>
    </div>
  );
}
