'use client';
import { useState } from 'react';
import { useRunStore } from '@/lib/store/runStore';
import { editState } from '@/lib/api/client';
import { subscribeRun } from '@/lib/sse';
import { useStateStore } from '@/lib/store/stateStore';

interface Props {
  path: string;
  value: unknown;
  options?: string[];
  display?(v: unknown): string;
}

export function EditableCell({ path, value, options, display }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<unknown>(value);
  const tid = useRunStore((s) => s.tid);
  const status = useRunStore((s) => s.status);
  const merge = useStateStore((s) => s.merge);
  const { setTid, handleEvent, reset } = useRunStore.getState();

  const disabled = !tid || status === 'running' || status === 'interrupted';

  async function commit() {
    if (draft === value || !tid) { setEditing(false); return; }
    const { rerun_tid } = await editState(tid, path, draft);
    reset();
    setTid(rerun_tid);
    subscribeRun(rerun_tid, (ev) => {
      handleEvent(ev);
      if (ev.type === 'node_end') merge(ev.state_patch);
      if (ev.type === 'done') merge(ev.final_state);
    });
    setEditing(false);
  }

  if (!editing) {
    return (
      <span onDoubleClick={() => !disabled && setEditing(true)}
            className={disabled ? 'text-neutral-500' : 'cursor-pointer underline decoration-dotted'}>
        {display ? display(value) : String(value)}
      </span>
    );
  }
  if (options) {
    return (
      <select autoFocus value={String(draft)} onChange={(e) => setDraft(e.target.value)}
              onBlur={commit} className="bg-neutral-900 border border-amber-700 px-1">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  return (
    <input autoFocus value={String(draft)} onChange={(e) => setDraft(e.target.value)}
           onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && commit()}
           className="bg-neutral-900 border border-amber-700 px-1 w-24" />
  );
}
