'use client';
import { create } from 'zustand';

export type CenterView = 'overview' | 'themes' | 'leaders' | 'candidates' | 'arbitrage' | 'risk' | 'plan';

interface ViewStore {
  view: CenterView;
  setView(v: CenterView): void;
  selectedCode: string | null;
  selectCode(code: string | null): void;
}

export const useViewStore = create<ViewStore>((set) => ({
  view: 'overview',
  setView: (view) => set({ view }),
  selectedCode: null,
  selectCode: (selectedCode) => set({ selectedCode }),
}));
