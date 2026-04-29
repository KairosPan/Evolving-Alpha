'use client';
import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createChart, type UTCTimestamp } from 'lightweight-charts';

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

export function Sparkline({
  code,
  days = 30,
  width = 80,
  height = 24,
}: {
  code: string;
  days?: number;
  width?: number;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { data } = useQuery({
    queryKey: ['kline', code, days, 'sparkline'],
    queryFn: () => fetchKline(code, days),
    staleTime: 24 * 3600 * 1000,
  });

  useEffect(() => {
    if (!ref.current || !data?.bars) return;
    const chart = createChart(ref.current, {
      width,
      height,
      layout: { background: { color: 'transparent' }, textColor: 'transparent' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      timeScale: { visible: false },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: false },
      crosshair: {
        vertLine: { visible: false, labelVisible: false },
        horzLine: { visible: false, labelVisible: false },
      },
      handleScale: false,
      handleScroll: false,
    });
    const series = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1 });
    series.setData(
      data.bars.map((b) => ({
        time: b.time as unknown as UTCTimestamp,
        value: b.close,
      })),
    );
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, width, height]);

  return <div ref={ref} style={{ width, height }} />;
}
