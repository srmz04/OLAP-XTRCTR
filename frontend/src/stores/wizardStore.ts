// src/stores/wizardStore.ts
import { create } from 'zustand';
import type { Catalog, Apartado, Variable } from '../types/olap';

interface WizardState {
    // Current step
    step: number;

    // Selected data
    selectedCatalog: Catalog | null;
    selectedApartados: Apartado[];
    selectedVariables: Variable[];

    // Actions
    setStep: (step: number) => void;
    selectCatalog: (catalog: Catalog) => void;
    toggleApartado: (apartado: Apartado) => void;
    toggleVariable: (variable: Variable) => void;
    clearSelections: () => void;
    reset: () => void;
}

export const useWizardStore = create<WizardState>((set) => ({
    step: 1,
    selectedCatalog: null,
    selectedApartados: [],
    selectedVariables: [],

    setStep: (step) => set({ step }),

    selectCatalog: (catalog) => set({
        selectedCatalog: catalog,
        step: 2,
        selectedApartados: [],
        selectedVariables: [],
    }),

    toggleApartado: (apartado) => set((state) => {
        const exists = state.selectedApartados.some(
            (a) => a.unique_name === apartado.unique_name
        );
        return {
            selectedApartados: exists
                ? state.selectedApartados.filter((a) => a.unique_name !== apartado.unique_name)
                : [...state.selectedApartados, apartado],
        };
    }),

    toggleVariable: (variable) => set((state) => {
        const exists = state.selectedVariables.some(
            (v) => v.unique_name === variable.unique_name
        );
        return {
            selectedVariables: exists
                ? state.selectedVariables.filter((v) => v.unique_name !== variable.unique_name)
                : [...state.selectedVariables, variable],
        };
    }),

    clearSelections: () => set({
        selectedApartados: [],
        selectedVariables: [],
    }),

    reset: () => set({
        step: 1,
        selectedCatalog: null,
        selectedApartados: [],
        selectedVariables: [],
    }),
}));
