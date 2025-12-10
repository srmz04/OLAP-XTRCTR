import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WizardContainer } from './components/wizard/WizardContainer';

const queryClient = new QueryClient();

function AppContent() {
    return (
        <div className="min-h-screen bg-gray-50">
            <WizardContainer />
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
