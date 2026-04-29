'use client';
import { useStateStore } from '@/lib/store/stateStore';

function KPI({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border border-neutral-800 rounded p-3 font-mono">
      <div className="text-[10px] uppercase text-neutral-500">{label}</div>
      <div className="text-lg">{value}</div>
    </div>
  );
}

export function OverviewView() {
  const s = useStateStore((st) => st.state) as Record<string, any>;
  return (
    <div className="grid grid-cols-3 gap-3">
      <KPI label="情绪" value={s.emotion_phase ?? '—'} />
      <KPI label="情绪值" value={s.sentiment_value ?? '—'} />
      <KPI label="涨停 / 连板" value={`${s.limit_up_count ?? 0} / ${s.consec_top ?? 0}`} />
      <KPI label="炸板率" value={`${((s.blast_rate ?? 0) * 100).toFixed(1)}%`} />
      <KPI label="指数相位" value={s.index_phase ?? '—'} />
      <KPI label="主线" value={s.main_theme ?? '—'} />
    </div>
  );
}
