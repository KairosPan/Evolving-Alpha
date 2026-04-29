'use client';
import { useQuery } from '@tanstack/react-query';
import { getRunsList, getRunByDate } from '@/lib/api/client';
import { useStateStore } from '@/lib/store/stateStore';

export function DateNavigator() {
  const { data = [] } = useQuery({ queryKey: ['runs'], queryFn: getRunsList });
  const replace = useStateStore((s) => s.replace);

  async function loadDate(date: string) {
    const snap = await getRunByDate(date);
    replace(snap);
  }

  return (
    <div className="space-y-1 font-mono text-xs">
      <div className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1">历史</div>
      {data.map((r) => (
        <button key={r.date} onClick={() => loadDate(r.date)}
                className="w-full text-left hover:bg-neutral-900 px-2 py-1 rounded flex justify-between">
          <span>{r.date}</span>
          <span className="text-neutral-500">{r.candidates_count}c {r.errors_count}e</span>
        </button>
      ))}
    </div>
  );
}
