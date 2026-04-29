import Link from 'next/link';

export default function Home() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-mono">youzi-agent · 盯盘台</h1>
      <Link href="/console" className="underline">→ Console</Link>
    </main>
  );
}
