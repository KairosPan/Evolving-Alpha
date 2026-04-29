'use client';
import { ThreeColumnLayout } from '@/components/shell/ThreeColumnLayout';
import { TopBar } from '@/components/shell/TopBar';
import { NodeTimeline } from '@/components/right-runstream/NodeTimeline';
import { InterruptDrawer } from '@/components/right-runstream/InterruptDrawer';
import { CenterRouter } from '@/components/center-views/CenterRouter';
import { DateNavigator } from '@/components/left-context/DateNavigator';
import { SentimentSpark } from '@/components/left-context/SentimentSpark';
import { LeaderDrawer } from '@/components/center-views/LeaderDrawer';
import { ErrorBanner } from '@/components/shell/ErrorBanner';
import { DataQualityBanner } from '@/components/shell/DataQualityBanner';

export default function ConsolePage() {
  return (
    <>
      <DataQualityBanner />
      <ErrorBanner />
      <ThreeColumnLayout
        top={<TopBar />}
        left={(<><SentimentSpark /><div className="mt-3"><DateNavigator /></div></>)}
        center={<CenterRouter />}
        right={(<><NodeTimeline /><InterruptDrawer /></>)}
      />
      <LeaderDrawer />
    </>
  );
}
