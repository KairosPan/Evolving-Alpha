'use client';
import { useRunStore } from '@/lib/store/runStore';

const ORDER = [
  'market_sensor', 'index_cycle', 'cycle_switch', 'emotion',
  'theme_analyst', 'leader_tracker', 'pattern_matcher',
  'first_board', 'weak_to_strong', 'continuous', 'setback_reversal',
  'arbitrage', 'risk_guard', 'trade_planner', 'post_mortem',
] as const;

const DOT_CLASS = {
  pending: 'bg-neutral-700',
  running: 'bg-amber-500 animate-pulse',
  done: 'bg-emerald-500',
  error: 'bg-red-500',
} as const;

export function NodeTimeline() {
  const nodes = useRunStore((s) => s.nodes);
  const interrupts = useRunStore((s) => s.interrupts);
  const interruptedNode = interrupts.at(-1)?.node;

  return (
    <div className="space-y-1 font-mono text-xs">
      <div className="text-neutral-400 mb-2 text-[10px] uppercase tracking-wider">Run flow</div>
      {ORDER.map((n) => {
        const info = nodes[n];
        const status = interruptedNode === n ? 'running' : (info?.status ?? 'pending');
        return (
          <div key={n} className="flex items-center gap-2" title={info?.error ?? ''}>
            <span className={`inline-block w-2 h-2 rounded-full ${DOT_CLASS[status]}`} />
            <span className={status === 'pending' ? 'text-neutral-600' : 'text-neutral-200'}>{n}</span>
            {interruptedNode === n && <span className="text-amber-400">⏸ review</span>}
          </div>
        );
      })}
    </div>
  );
}
