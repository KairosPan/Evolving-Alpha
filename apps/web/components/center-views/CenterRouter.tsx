'use client';
import { useViewStore, type CenterView } from '@/lib/store/viewStore';
import { OverviewView } from './OverviewView';
import { ThemesView } from './ThemesView';
import { LeadersView } from './LeadersView';
import { CandidatesView } from './CandidatesView';
import { ArbitrageView } from './ArbitrageView';
import { RiskView } from './RiskView';
import { PlanView } from './PlanView';

const VIEWS: { id: CenterView; label: string }[] = [
  { id: 'overview', label: '概览' }, { id: 'themes', label: '题材' },
  { id: 'leaders', label: '龙头' }, { id: 'candidates', label: '候选池' },
  { id: 'arbitrage', label: '套利' }, { id: 'risk', label: '风控' },
  { id: 'plan', label: '计划' },
];

export function CenterRouter() {
  const { view, setView } = useViewStore();
  return (
    <div className="flex flex-col gap-3">
      <nav className="flex gap-2 border-b border-neutral-800 pb-2">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)}
                  className={`px-2 py-1 text-sm font-mono ${
                    view === v.id ? 'text-amber-400 border-b-2 border-amber-400' : 'text-neutral-400'
                  }`}>{v.label}</button>
        ))}
      </nav>
      <div>
        {view === 'overview' && <OverviewView />}
        {view === 'themes' && <ThemesView />}
        {view === 'leaders' && <LeadersView />}
        {view === 'candidates' && <CandidatesView />}
        {view === 'arbitrage' && <ArbitrageView />}
        {view === 'risk' && <RiskView />}
        {view === 'plan' && <PlanView />}
      </div>
    </div>
  );
}
