import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { useRunStore } from '@/lib/store/runStore';
import { NodeTimeline } from './NodeTimeline';

beforeEach(() => useRunStore.setState({ tid: 't', nodes: {}, status: 'running', interrupts: [] }));

describe('NodeTimeline', () => {
  it('renders ordered node names with status dots', () => {
    useRunStore.getState().handleEvent({ type: 'node_start', node: 'market_sensor', ts: 1 });
    useRunStore.getState().handleEvent({ type: 'node_end', node: 'market_sensor', ts: 2, state_patch: {} });
    useRunStore.getState().handleEvent({ type: 'node_start', node: 'index_cycle', ts: 3 });
    render(<NodeTimeline />);
    expect(screen.getByText('market_sensor')).toBeInTheDocument();
    expect(screen.getByText('index_cycle')).toBeInTheDocument();
  });
});
