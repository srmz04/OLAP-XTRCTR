import { create } from 'zustand';

interface Variable {
    id: string;
    name: string;
    uniqueName: string;
    apartado: string;
    hierarchy: string;
}

export interface DimensionConfig {
    dimension: string;
    hierarchy: string;
    level: string;
    depth?: number;
    members?: string[];
}

export interface FilterConfig {
    dimension: string;
    hierarchy: string;
    level?: string;
    members: string[];
    memberCaptions?: string[];
}

interface WizardState {
    // Current state
    currentStep: number;
    selectedCatalog: string;

    // Step 1: Apartados
    selectedApartadoIds: string[];

    // Step 2: Variables
    selectedVariables: Variable[];

    // Step 3: Dimensions
    selectedRows: DimensionConfig[];      // DESGLOSES (max 3)
    selectedFilters: FilterConfig[];       // FILTROS

    // Actions
    setStep: (step: number) => void;
    nextStep: () => void;
    prevStep: () => void;

    setCatalog: (catalog: string) => void;
    setApartados: (ids: string[]) => void;
    setVariables: (variables: Variable[]) => void;

    setRows: (rows: DimensionConfig[]) => void;
    setFilters: (filters: FilterConfig[]) => void;

    reset: () => void;
}

const initialState = {
    currentStep: 1,
    selectedCatalog: '',
    selectedApartadoIds: [],
    selectedVariables: [],
    selectedRows: [],
    selectedFilters: [],
};

export const useWizardStore = create<WizardState>((set) => ({
    ...initialState,

    setStep: (step: number) => set({ currentStep: step }),

    nextStep: () => set((state) => ({
        currentStep: Math.min(state.currentStep + 1, 4)
    })),

    prevStep: () => set((state) => ({
        currentStep: Math.max(state.currentStep - 1, 1)
    })),

    setCatalog: (catalog: string) => set({ selectedCatalog: catalog }),

    setApartados: (ids: string[]) => set({ selectedApartadoIds: ids }),

    setVariables: (variables: Variable[]) => set({ selectedVariables: variables }),

    setRows: (rows: DimensionConfig[]) => set({ selectedRows: rows }),

    setFilters: (filters: FilterConfig[]) => set({ selectedFilters: filters }),

    reset: () => set(initialState),
}));
