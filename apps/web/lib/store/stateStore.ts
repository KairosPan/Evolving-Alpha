'use client';
import { create } from 'zustand';

interface StateStore {
  state: Record<string, unknown>;
  merge(patch: Record<string, unknown>): void;
  replace(s: Record<string, unknown>): void;
  reset(): void;
}

export const useStateStore = create<StateStore>((set) => ({
  state: {},
  merge: (patch) => set((s) => ({ state: { ...s.state, ...patch } })),
  replace: (s) => set({ state: s }),
  reset: () => set({ state: {} }),
}));
