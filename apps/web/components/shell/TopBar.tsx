'use client';
import { useState } from 'react';
import { startRun } from '@/lib/api/client';
import { useRunStore } from '@/lib/store/runStore';
import { subscribeRun } from '@/lib/sse';
import { useStateStore } from '@/lib/store/stateStore';

function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export function TopBar() {
  const [date, setDate] = useState(todayISO());
  const [useLlm, setUseLlm] = useState(true);
  const [refresh, setRefresh] = useState(false);
  const { tid, status, setTid, handleEvent, reset } = useRunStore();
  const merge = useStateStore((s) => s.merge);

  async function go() {
    reset();
    const { thread_id } = await startRun({ date, use_llm: useLlm, refresh });
    setTid(thread_id);
    subscribeRun(thread_id, (ev) => {
      handleEvent(ev);
      if (ev.type === 'node_end') merge(ev.state_patch);
      if (ev.type === 'done') merge(ev.final_state);
    });
  }

  return (
    <div className="flex items-center gap-3 font-mono text-sm">
      <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
             className="bg-neutral-900 border border-neutral-700 px-2 py-1 rounded" />
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> use-llm
      </label>
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} /> refresh
      </label>
      <button onClick={go} disabled={status === 'running' || status === 'interrupted'}
              className="bg-amber-600 hover:bg-amber-500 disabled:opacity-50 px-3 py-1 rounded">
        ▶ Run
      </button>
      <span className="text-neutral-400">{tid ? `tid: ${tid}` : 'idle'} · status: {status}</span>
    </div>
  );
}
