'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function ErrorBanner() {
  const errors = (useStateStore((s) => s.state).errors as string[] | undefined) ?? [];
  if (errors.length === 0) return null;
  return (
    <div className="border-b border-red-800 bg-red-950/40 px-4 py-2 text-xs font-mono text-red-300">
      <details>
        <summary className="cursor-pointer">⚠ {errors.length} 个节点错误</summary>
        <ul className="mt-1 ml-4 list-disc">
          {errors.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      </details>
    </div>
  );
}
