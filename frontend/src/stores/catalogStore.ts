import { create } from 'zustand';
import { catalogService, Catalog } from '../api/services/catalogService';

interface CatalogState {
    catalogs: Catalog[];
    selectedCatalog: Catalog | null;
    isLoading: boolean;
    error: string | null;

    // Actions
    fetchCatalogs: () => Promise<void>;
    selectCatalog: (catalog: Catalog | null) => void;
    setCatalogs: (catalogs: Catalog[]) => void;
}

export const useCatalogStore = create<CatalogState>((set) => ({
    catalogs: [],
    selectedCatalog: null,
    isLoading: false,
    error: null,

    fetchCatalogs: async () => {
        set({ isLoading: true, error: null });
        try {
            const data = await catalogService.getCatalogs();
            set({ catalogs: data, isLoading: false });
        } catch (err) {
            set({
                isLoading: false,
                error: err instanceof Error ? err.message : 'Failed to fetch catalogs'
            });
        }
    },

    selectCatalog: (catalog) => set({ selectedCatalog: catalog }),
    setCatalogs: (catalogs) => set({ catalogs }),
}));
