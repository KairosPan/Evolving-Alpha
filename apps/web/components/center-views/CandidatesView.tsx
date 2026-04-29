'use client';
import { useStateStore } from '@/lib/store/stateStore';

interface Candidate {
  code: string; name?: string; score?: number;
  branch?: string; suggested_price?: number; suggested_position?: number;
}

export function CandidatesView() {
  const cands = (useStateStore((s) => s.state).candidates as Candidate[] | undefined) ?? [];
  if (cands.length === 0) return <div className="text-neutral-400 text-sm">候选池：空</div>;
  return (
    <table className="w-full font-mono text-sm">
      <thead className="text-left text-xs text-neutral-400 border-b border-neutral-800">
        <tr><th className="py-1">代码</th><th>名称</th><th>得分</th><th>分支</th><th>建议价</th><th>建议仓位</th></tr>
      </thead>
      <tbody>
        {cands.map((c) => (
          <tr key={c.code} className="border-b border-neutral-900 hover:bg-neutral-900">
            <td className="py-1">{c.code}</td><td>{c.name ?? ''}</td>
            <td>{c.score?.toFixed(2) ?? ''}</td><td>{c.branch ?? ''}</td>
            <td>{c.suggested_price?.toFixed(2) ?? ''}</td>
            <td>{c.suggested_position != null ? `${(c.suggested_position * 100).toFixed(0)}%` : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
