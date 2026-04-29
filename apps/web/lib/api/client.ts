'use client';

const BASE = '';

export async function startRun(body: { date: string; use_llm?: boolean; refresh?: boolean })
  : Promise<{ thread_id: string }> {
  const r = await fetch(`${BASE}/api/run`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST /api/run ${r.status}`);
  return r.json();
}

export async function getRunsList(): Promise<Array<{ date: string; candidates_count: number; errors_count: number; has_plan: boolean }>> {
  const r = await fetch(`${BASE}/api/runs`);
  if (!r.ok) throw new Error('GET /api/runs');
  return r.json();
}

export async function getRunByDate(date: string): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/api/runs/${date}`);
  if (!r.ok) throw new Error(`GET /api/runs/${date}`);
  return r.json();
}

export async function getStateByTid(tid: string): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/api/state/${tid}`);
  if (!r.ok) throw new Error(`GET /api/state/${tid}`);
  return r.json();
}

export async function resumeRun(tid: string, body: { action?: 'approve' | 'edit' | 'abort'; patch?: Record<string, unknown> }) {
  const r = await fetch(`${BASE}/api/run/${tid}/resume`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action: body.action ?? 'approve', patch: body.patch ?? {} }),
  });
  if (!r.ok) throw new Error(`resume failed: ${r.status}`);
  return r.json();
}

export async function editState(tid: string, path: string, value: unknown): Promise<{ rerun_tid: string }> {
  const r = await fetch(`${BASE}/api/state/${tid}/edit`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, value }),
  });
  if (!r.ok) throw new Error(`edit failed: ${r.status}`);
  return r.json();
}
