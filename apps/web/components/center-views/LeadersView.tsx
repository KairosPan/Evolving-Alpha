'use client';
import { useStateStore } from '@/lib/store/stateStore';
import { useViewStore } from '@/lib/store/viewStore';

export function LeadersView() {
  const stack = (useStateStore((s) => s.state).leader_stack ?? []) as any[];
  const selectCode = useViewStore((s) => s.selectCode);
  if (stack.length === 0) return <div className="text-neutral-400 text-sm">龙头梯队：空</div>;
  return (
    <table className="w-full font-mono text-sm">
      <thead className="text-left text-xs text-neutral-400 border-b border-neutral-800">
        <tr><th>代码</th><th>名称</th><th>角色</th><th>板数</th><th>强度</th></tr>
      </thead>
      <tbody>
        {stack.map((l: any) => (
          <tr key={l.code} className="cursor-pointer hover:bg-neutral-900"
              onClick={() => selectCode(l.code)}>
            <td className="py-1">{l.code}</td><td>{l.name}</td><td>{l.role}</td>
            <td>{l.consec ?? ''}</td><td>{l.strength?.toFixed(2) ?? ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
