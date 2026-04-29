'use client';
import { create } from 'zustand';

export type RunEvent =
  | { type: 'node_start'; node: string; ts: number }
  | { type: 'node_end'; node: string; ts: number; state_patch: Record<string, unknown> }
  | { type: 'node_error'; node: string; ts: number; message: string }
  | { type: 'interrupt'; node: string; snapshot: Record<string, unknown>; ts: number }
  | { type: 'done'; final_state: Record<string, unknown>; ts: number }
  | { type: 'aborted'; reason: string; ts: number };

type NodeStatus = 'pending' | 'running' | 'done' | 'error';
interface NodeInfo { status: NodeStatus; error?: string; ts?: number }

interface RunStore {
  tid: string | null;
  status: 'idle' | 'running' | 'interrupted' | 'done' | 'aborted';
  nodes: Record<string, NodeInfo>;
  interrupts: { node: string; snapshot: Record<string, unknown>; ts: number }[];
  setTid(tid: string): void;
  reset(): void;
  handleEvent(ev: RunEvent): void;
}

export const useRunStore = create<RunStore>((set) => ({
  tid: null, status: 'idle', nodes: {}, interrupts: [],
  setTid: (tid) => set({ tid, status: 'running', nodes: {}, interrupts: [] }),
  reset: () => set({ tid: null, status: 'idle', nodes: {}, interrupts: [] }),
  handleEvent: (ev) => set((st) => {
    const nodes = { ...st.nodes };
    switch (ev.type) {
      case 'node_start':
        nodes[ev.node] = { status: 'running', ts: ev.ts };
        return { nodes, status: 'running' };
      case 'node_end':
        nodes[ev.node] = { status: 'done', ts: ev.ts };
        return { nodes };
      case 'node_error':
        nodes[ev.node] = { status: 'error', error: ev.message, ts: ev.ts };
        return { nodes };
      case 'interrupt':
        return { interrupts: [...st.interrupts, ev], status: 'interrupted' };
      case 'done':
        return { status: 'done' };
      case 'aborted':
        return { status: 'aborted' };
    }
  }),
}));
