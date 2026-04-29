'use client';
import { useStateStore } from '@/lib/store/stateStore';
import { useRunStore } from '@/lib/store/runStore';
import { editState } from '@/lib/api/client';
import { subscribeRun } from '@/lib/sse';

export function RiskView() {
  const flags = (useStateStore((s) => s.state).risk_flags ?? []) as string[];
  const tid = useRunStore((s) => s.tid);
  const { setTid, handleEvent, reset } = useRunStore.getState();
  const merge = useStateStore((s) => s.merge);

  async function remove(idx: number) {
    if (!tid) return;
    const next = flags.filter((_, i) => i !== idx);
    const { rerun_tid } = await editState(tid, 'risk_flags', next);
    reset();
    setTid(rerun_tid);
    subscribeRun(rerun_tid, (ev) => {
      handleEvent(ev);
      if (ev.type === 'node_end') merge(ev.state_patch);
      if (ev.type === 'done') merge(ev.final_state);
    });
  }

  if (flags.length === 0) return <div className="text-neutral-400 text-sm">无风控触发</div>;
  return (
    <ul className="space-y-1 font-mono text-sm">
      {flags.map((f, i) => (
        <li key={i} className="flex justify-between border border-neutral-800 rounded px-2 py-1">
          <span>{f}</span>
          <button onClick={() => remove(i)} className="text-red-400 hover:text-red-300">驳回</button>
        </li>
      ))}
    </ul>
  );
}
