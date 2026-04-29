'use client';
import { useState } from 'react';

interface Hit { pattern_id: string; filter_desc: string; target_subagent: string }
interface Props {
  snapshot: { pattern_hits?: Hit[]; emotion_phase?: string; succession_status?: string; index_phase?: string };
  onApprove(patch?: Record<string, unknown>): void | Promise<void>;
}

export function PatternMatcherReview({ snapshot, onApprove }: Props) {
  const initial: Hit[] = snapshot.pattern_hits ?? [];
  const [hits, setHits] = useState(initial);
  const dirty = JSON.stringify(hits) !== JSON.stringify(initial);

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-neutral-400">
        emotion: {snapshot.emotion_phase} · succession: {snapshot.succession_status} · index: {snapshot.index_phase}
      </div>
      <ul className="space-y-1">
        {hits.map((h, i) => (
          <li key={i} className="flex items-center justify-between border border-neutral-800 rounded px-2 py-1">
            <span>{h.pattern_id} → <span className="text-neutral-400">{h.target_subagent}</span></span>
            <button onClick={() => setHits(hits.filter((_, j) => j !== i))}
                    className="text-red-400 hover:text-red-300">×</button>
          </li>
        ))}
        {hits.length === 0 && <li className="text-neutral-500">空 — 子图分发将跳过</li>}
      </ul>
      <div className="flex gap-2">
        <button onClick={() => onApprove(dirty ? { pattern_hits: hits } : {})}
                className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded">
          {dirty ? '应用并继续' : '通过'}
        </button>
      </div>
    </div>
  );
}
