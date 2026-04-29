'use client';
import { ThreeColumnLayout } from '@/components/shell/ThreeColumnLayout';
import { TopBar } from '@/components/shell/TopBar';
import { NodeTimeline } from '@/components/right-runstream/NodeTimeline';
import { InterruptDrawer } from '@/components/right-runstream/InterruptDrawer';
import { CenterRouter } from '@/components/center-views/CenterRouter';
import { DateNavigator } from '@/components/left-context/DateNavigator';

export default function ConsolePage() {
  return (
    <ThreeColumnLayout
      top={<TopBar />}
      left={<DateNavigator />}
      center={<CenterRouter />}
      right={(<><NodeTimeline /><InterruptDrawer /></>)}
    />
  );
}
