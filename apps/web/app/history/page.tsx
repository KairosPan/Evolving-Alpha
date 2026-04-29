'use client';
import { DateNavigator } from '@/components/left-context/DateNavigator';

export default function HistoryPage() {
  return (
    <main className="p-6">
      <h1 className="font-mono text-xl mb-4">历史复盘</h1>
      <DateNavigator />
    </main>
  );
}
