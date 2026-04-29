'use client';
import { useState } from 'react';

interface Plan {
  position_total_max?: number;
  candidates?: { code: string; name?: string; weight?: number }[];
  notes?: string;
}
interface Props {
  snapshot: { plan?: Plan; final_candidates?: any[] };
  onApprove(patch?: Record<string, unknown>): void | Promise<void>;
}

export function TradePlannerReview({ snapshot, onApprove }: Props) {
  const initial = snapshot.plan ?? { candidates: [], notes: '' };
  const [notes, setNotes] = useState(initial.notes ?? '');
  const dirty = notes !== (initial.notes ?? '');

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-neutral-400">仓位上限 {((initial.position_total_max ?? 0) * 100).toFixed(0)}% · 候选 {initial.candidates?.length ?? 0} 只</div>
      <ul>
        {(initial.candidates ?? []).map((c, i) => (
          <li key={i}>{c.code} {c.name} weight={(c.weight ?? 0).toFixed(2)}</li>
        ))}
      </ul>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                className="bg-neutral-900 border border-neutral-700 w-full px-2 py-1 h-20"
                placeholder="计划备注 / 三段执行" />
      <button onClick={() => onApprove(dirty ? { plan: { ...initial, notes } } : {})}
              className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded">
        {dirty ? '应用并继续' : '通过'}
      </button>
    </div>
  );
}
