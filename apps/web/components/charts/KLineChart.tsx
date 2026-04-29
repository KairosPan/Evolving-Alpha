'use client';
import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createChart, type IChartApi, type UTCTimestamp } from 'lightweight-charts';

interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface KlineResp {
  code: string;
  bars: Bar[];
  limit_up_days: string[];
}

async function fetchKline(code: string, days: number): Promise<KlineResp> {
  const r = await fetch(`/api/kline/${code}?days=${days}`);
  if (!r.ok) throw new Error(`kline ${code}`);
  return r.json();
}

export function KLineChart({
  code,
  days = 60,
  height = 280,
}: {
  code: string;
  days?: number;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ['kline', code, days],
    queryFn: () => fetchKline(code, days),
    staleTime: 24 * 3600 * 1000,
  });

  useEffect(() => {
    if (!ref.current || !data) return;
    const chart = createChart(ref.current, {
      height,
      layout: { background: { color: 'transparent' }, textColor: '#888' },
      grid: { vertLines: { color: '#222' }, horzLines: { color: '#222' } },
      timeScale: { borderColor: '#333' },
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });
    series.setData(
      data.bars.map((b) => ({
        time: b.time as unknown as UTCTimestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    if (data.limit_up_days?.length) {
      series.setMarkers(
        data.limit_up_days.map((d) => ({
          time: d as unknown as UTCTimestamp,
          position: 'belowBar' as const,
          color: '#ef4444',
          shape: 'arrowUp' as const,
          text: '涨停',
        })),
      );
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, height]);

  if (error) return <div className="text-red-500 text-xs">K 线加载失败</div>;
  if (isLoading) return <div className="text-neutral-500 text-xs">加载 K 线…</div>;
  return <div ref={ref} style={{ height }} />;
}
