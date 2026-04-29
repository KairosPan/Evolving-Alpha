'use client';
import { useRunStore } from '@/lib/store/runStore';
import { resumeRun } from '@/lib/api/client';
import { PatternMatcherReview } from './reviews/PatternMatcherReview';
import { RiskGuardReview } from './reviews/RiskGuardReview';
import { TradePlannerReview } from './reviews/TradePlannerReview';

export function InterruptDrawer() {
  const tid = useRunStore((s) => s.tid);
  const interrupts = useRunStore((s) => s.interrupts);
  const last = interrupts.at(-1);
  if (!last || !tid) return null;

  async function approve(patch: Record<string, unknown> = {}) {
    await resumeRun(tid!, { action: Object.keys(patch).length ? 'edit' : 'approve', patch });
    useRunStore.setState({
      interrupts: useRunStore.getState().interrupts.slice(0, -1),
      status: 'running',
    });
  }

  return (
    <div className="mt-3 border-t border-amber-700 pt-3">
      <div className="text-amber-400 text-xs uppercase tracking-wider mb-2">⏸ Review · {last.node}</div>
      {last.node === 'pattern_matcher' && (
        <PatternMatcherReview snapshot={last.snapshot as any} onApprove={approve} />
      )}
      {last.node === 'risk_guard' && (
        <RiskGuardReview snapshot={last.snapshot as any} onApprove={approve} />
      )}
      {last.node === 'trade_planner' && (
        <TradePlannerReview snapshot={last.snapshot as any} onApprove={approve} />
      )}
    </div>
  );
}
