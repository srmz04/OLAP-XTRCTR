import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWizardStore } from '../../stores/wizardStore';
import { WizardProgress } from './WizardProgress';
import { Step1_Apartados } from './Step1_Apartados';
import { Step2_Variables } from './Step2_Variables';
import { Step3_Dimensions } from './Step3_Dimensions';
import { Step4_Preview } from './Step4_Preview';

export const WizardContainer: React.FC = () => {
    const { currentStep, selectedCatalog, nextStep, prevStep, reset } = useWizardStore();

    const canGoNext = () => {
        // TODO: Add validation logic per step
        return currentStep < 4;
    };

    const canGoBack = () => {
        return currentStep > 1;
    };

    return (
        <div className="max-w-5xl mx-auto p-6">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900 mb-2">
                    Constructor de Consulta MDX
                </h1>
                <p className="text-gray-600">
                    Construye consultas OLAP paso a paso
                </p>
            </div>

            {/* Catalog Selector */}
            {!selectedCatalog && (
                <div className="mb-6 p-6 bg-white rounded-lg shadow-sm border border-gray-200">
                    <h2 className="text-lg font-semibold text-gray-900 mb-4">
                        Selecciona un Catálogo
                    </h2>
                    <CatalogSelector />
                </div>
            )}

            {selectedCatalog && (
                <>
                    {/* Progress Indicator */}
                    <WizardProgress currentStep={currentStep} totalSteps={4} />

                    {/* Step Content */}
                    <div className="bg-white rounded-lg shadow-sm border border-gray-200 min-h-[400px]">
                        {currentStep === 1 && <Step1_Apartados />}
                        {currentStep === 2 && <Step2_Variables />}
                        {currentStep === 3 && <Step3_Dimensions />}
                        {currentStep === 4 && <Step4_Preview />}
                    </div>

                    {/* Navigation */}
                    <div className="flex items-center justify-between mt-6">
                        <button
                            onClick={prevStep}
                            disabled={!canGoBack()}
                            className={`
            px-6 py-2 rounded-lg font-medium transition-colors
            ${canGoBack()
                                    ? 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                    : 'bg-gray-50 text-gray-400 cursor-not-allowed'
                                }
          `}
                        >
                            ← Anterior
                        </button>

                        <div className="flex gap-3">
                            <button
                                onClick={reset}
                                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
                            >
                                🔄 Reiniciar
                            </button>

                            <button
                                onClick={nextStep}
                                disabled={!canGoNext()}
                                className={`
              px-6 py-2 rounded-lg font-medium transition-colors
              ${canGoNext()
                                        ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                                        : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                                    }
            `}
                            >
                                {currentStep === 4 ? 'Ejecutar →' : 'Siguiente →'}
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div >
    );
};

// Simple catalog selector component
interface Catalog {
    name: string;
    description: string;
}

const CatalogSelector: React.FC = () => {
    const { setCatalog } = useWizardStore();
    const [localSelection, setLocalSelection] = React.useState('');

    const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    const { data: catalogs } = useQuery<Catalog[]>({
        queryKey: ['catalogs'],
        queryFn: async () => {
            const response = await fetch(`${BASE_URL}/api/catalogs`);
            return response.json();
        },
    });

    const handleSelect = () => {
        if (localSelection) {
            setCatalog(localSelection);
        }
    };

    return (
        <div>
            <select
                value={localSelection}
                onChange={(e) => setLocalSelection(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 mb-4"
            >
                <option value="">-- Selecciona un catálogo --</option>
                {catalogs?.map((catalog) => (
                    <option key={catalog.name} value={catalog.name}>
                        {catalog.name}
                    </option>
                ))}
            </select>
            <button
                onClick={handleSelect}
                disabled={!localSelection}
                className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
                Continuar →
            </button>
        </div>
    );
};
