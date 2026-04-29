'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function ArbitrageView() {
  const ops = (useStateStore((s) => s.state).arb_opportunities ?? []) as any[];
  if (ops.length === 0) return <div className="text-neutral-400 text-sm">套利机会：空</div>;
  return (
    <table className="w-full font-mono text-sm">
      <thead className="text-left text-xs text-neutral-400 border-b border-neutral-800">
        <tr><th>类型</th><th>主体</th><th>说明</th><th>分数</th></tr>
      </thead>
      <tbody>
        {ops.map((o, i) => (
          <tr key={i} className="border-b border-neutral-900 hover:bg-neutral-900">
            <td className="py-1">{o.kind ?? o.type ?? ''}</td>
            <td>{o.code ?? o.theme ?? ''}</td>
            <td className="text-neutral-400">{o.note ?? o.desc ?? ''}</td>
            <td>{o.score?.toFixed?.(2) ?? ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
