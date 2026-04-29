import { describe, it, expect, beforeEach } from 'vitest';
import { useRunStore } from './runStore';

beforeEach(() => useRunStore.setState({ tid: null, nodes: {}, status: 'idle', interrupts: [] }));

describe('runStore', () => {
  it('handles node_start then node_end', () => {
    const s = useRunStore.getState();
    s.handleEvent({ type: 'node_start', node: 'market_sensor', ts: 1 });
    expect(useRunStore.getState().nodes.market_sensor.status).toBe('running');
    s.handleEvent({ type: 'node_end', node: 'market_sensor', ts: 2, state_patch: {} });
    expect(useRunStore.getState().nodes.market_sensor.status).toBe('done');
  });

  it('records interrupts', () => {
    const s = useRunStore.getState();
    s.handleEvent({ type: 'interrupt', node: 'pattern_matcher', snapshot: { x: 1 }, ts: 3 });
    expect(useRunStore.getState().interrupts).toHaveLength(1);
    expect(useRunStore.getState().status).toBe('interrupted');
  });

  it('marks done', () => {
    const s = useRunStore.getState();
    s.handleEvent({ type: 'done', final_state: {}, ts: 4 });
    expect(useRunStore.getState().status).toBe('done');
  });
});
