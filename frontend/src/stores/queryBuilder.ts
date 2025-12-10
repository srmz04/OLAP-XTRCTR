/**
 * Zustand Store - Estado global del Query Builder
 */

import { create } from 'zustand';
import { Measure, Dimension } from '../api/client';

export interface LevelData {
    type: 'level';
    dimension: string;
    hierarchy: string;
    level: string;
    uniqueName: string;
    depth: number;
}

export interface DroppedItem {
    id: string;
    type: 'measure' | 'dimension' | 'level';
    data: any;  // Can be Measure, Dimension, or LevelData from draggable
}

interface QueryBuilderState {
    // Catálogo seleccionado
    selectedCatalog: string | null;
    setSelectedCatalog: (catalog: string) => void;

    // Items en las zonas de drop
    columnsItems: DroppedItem[];
    rowsItems: DroppedItem[];
    filtersItems: DroppedItem[];

    // Agregar items
    addToColumns: (item: DroppedItem) => void;
    addToRows: (item: DroppedItem) => void;
    addToFilters: (item: DroppedItem) => void;

    // Remover items
    removeFromColumns: (id: string) => void;
    removeFromRows: (id: string) => void;
    removeFromFilters: (id: string) => void;

    // Limpiar todo
    clearAll: () => void;

    // Resultados
    queryResults: any[] | null;
    setQueryResults: (results: any[]) => void;
}

export const useQueryStore = create<QueryBuilderState>((set) => ({
    selectedCatalog: null,
    setSelectedCatalog: (catalog) => set({ selectedCatalog: catalog }),

    columnsItems: [],
    rowsItems: [],
    filtersItems: [],

    addToColumns: (item) =>
        set((state) => ({
            columnsItems: [...state.columnsItems, item],
        })),

    addToRows: (item) =>
        set((state) => ({
            rowsItems: [...state.rowsItems, item],
        })),

    addToFilters: (item) =>
        set((state) => ({
            filtersItems: [...state.filtersItems, item],
        })),

    removeFromColumns: (id) =>
        set((state) => ({
            columnsItems: state.columnsItems.filter((i) => i.id !== id),
        })),

    removeFromRows: (id) =>
        set((state) => ({
            rowsItems: state.rowsItems.filter((i) => i.id !== id),
        })),

    removeFromFilters: (id) =>
        set((state) => ({
            filtersItems: state.filtersItems.filter((i) => i.id !== id),
        })),

    clearAll: () =>
        set({
            columnsItems: [],
            rowsItems: [],
            filtersItems: [],
            queryResults: null,
        }),

    queryResults: null,
    setQueryResults: (results) => set({ queryResults: results }),
}));
