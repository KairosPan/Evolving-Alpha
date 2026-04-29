'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function ThemesView() {
  const themes = (useStateStore((s) => s.state).themes ?? {}) as Record<string, any>;
  const entries = Object.entries(themes);
  if (entries.length === 0) return <div className="text-neutral-400 text-sm">题材：空</div>;
  return (
    <div className="grid grid-cols-2 gap-3 font-mono text-sm">
      {entries.map(([name, t]) => (
        <div key={name} className="border border-neutral-800 rounded p-3">
          <div className="font-bold">{name}</div>
          <div className="text-neutral-400 text-xs">phase: {t.phase ?? '—'} · leader: {t.leader ?? '—'}</div>
          <div className="text-neutral-500 text-xs">members: {(t.members ?? []).join(', ')}</div>
        </div>
      ))}
    </div>
  );
}
