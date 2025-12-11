import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WizardContainer } from './components/wizard/WizardContainer';
import { CatalogSelector } from './components/CatalogSelector';
import { useCatalogStore } from './stores/catalogStore';

const queryClient = new QueryClient();

function AppContent() {
    const { selectedCatalog } = useCatalogStore();

    return (
        <div className="flex h-screen bg-gray-50 overflow-hidden">
            <CatalogSelector />

            <div className="flex-1 overflow-auto p-8">
                {selectedCatalog ? (
                    <div className="space-y-6">
                        <header className="mb-8">
                            <h1 className="text-3xl font-bold text-gray-900">{selectedCatalog.name}</h1>
                            {selectedCatalog.description && (
                                <p className="text-gray-500 mt-2">{selectedCatalog.description}</p>
                            )}
                        </header>
                        <WizardContainer />
                    </div>
                ) : (
                    <div className="h-full flex flex-col items-center justify-center text-gray-400">
                        {/* Placeholder Icon could go here */}
                        <p className="text-lg font-medium">Select a catalog to begin analysis</p>
                        <p className="text-sm">Choose a data source from the sidebar</p>
                    </div>
                )}
            </div>
        </div>
    );
}

function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <AppContent />
        </QueryClientProvider>
    );
}

export default App;
