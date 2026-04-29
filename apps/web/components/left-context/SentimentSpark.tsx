'use client';
import { useQuery } from '@tanstack/react-query';
import { getRunsList, getRunByDate } from '@/lib/api/client';

export function SentimentSpark({ days = 7 }: { days?: number }) {
  const { data: runs = [] } = useQuery({ queryKey: ['runs'], queryFn: getRunsList });
  const last = runs.slice(0, days).reverse();

  return (
    <div className="font-mono text-xs">
      <div className="text-[10px] uppercase text-neutral-500 mb-1">情绪 7 日</div>
      <div className="flex gap-px h-6 items-end">
        {last.map((r) => (
          <SparkBar key={r.date} date={r.date} />
        ))}
      </div>
    </div>
  );
}

function SparkBar({ date }: { date: string }) {
  const { data } = useQuery({
    queryKey: ['runs', date],
    queryFn: () => getRunByDate(date),
  });
  const v = (data?.sentiment_value as number | undefined) ?? 0;
  const h = Math.min(24, Math.max(2, v / 200));
  return <div title={`${date}: ${v}`} style={{ height: h, width: 6 }} className="bg-amber-500" />;
}
