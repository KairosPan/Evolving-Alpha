import type { ReactNode } from 'react';

export function ThreeColumnLayout({
  top, left, center, right,
}: { top?: ReactNode; left: ReactNode; center: ReactNode; right: ReactNode }) {
  return (
    <div className="grid grid-rows-[auto_1fr] h-screen">
      {top && <header className="border-b border-neutral-800 px-4 py-2">{top}</header>}
      <div className="grid grid-cols-[240px_1fr_360px] overflow-hidden">
        <aside className="border-r border-neutral-800 overflow-y-auto p-3">{left}</aside>
        <main className="overflow-y-auto p-4">{center}</main>
        <aside className="border-l border-neutral-800 overflow-y-auto p-3">{right}</aside>
      </div>
    </div>
  );
}
