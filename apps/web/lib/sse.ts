'use client';
import type { RunEvent } from './store/runStore';

export function subscribeRun(tid: string, onEvent: (ev: RunEvent) => void): () => void {
  const es = new EventSource(`/api/run/${tid}/stream`);
  const types: RunEvent['type'][] = ['node_start', 'node_end', 'node_error', 'interrupt', 'done', 'aborted'];
  for (const t of types) {
    es.addEventListener(t, (e) => {
      try { onEvent(JSON.parse((e as MessageEvent).data) as RunEvent); }
      catch { /* swallow malformed */ }
    });
  }
  es.onerror = () => {/* EventSource auto-reconnects */};
  return () => es.close();
}
