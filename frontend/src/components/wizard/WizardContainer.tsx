import React, { useEffect } from 'react';
import { useWizardStore } from '../../stores/wizardStore';
import { useCatalogStore } from '../../stores/catalogStore';
import { WizardProgress } from './WizardProgress';
import { Step1_Apartados } from './Step1_Apartados';
import { Step2_Variables } from './Step2_Variables';
import { Step3_Dimensions } from './Step3_Dimensions';
import { Step4_Preview } from './Step4_Preview';

export const WizardContainer: React.FC = () => {
    // Integrate global catalog store
    const { selectedCatalog: globalCatalog } = useCatalogStore();
    const { currentStep, setCatalog, nextStep, prevStep, reset } = useWizardStore();

    // Sync global catalog selection with wizard store
    // This bridges the Gap between the App-level selection and the Wizard-level state
    useEffect(() => {
        if (globalCatalog) {
            setCatalog(globalCatalog.name);
        }
    }, [globalCatalog, setCatalog]);

    const canGoNext = () => {
        // TODO: Add validation logic per step
        return currentStep < 4;
    };

    const canGoBack = () => {
        return currentStep > 1;
    };

    if (!globalCatalog) return null; // Should be handled by App.tsx, but safety check

    return (
        <div className="max-w-5xl mx-auto">
            {/* Progress Indicator */}
            <div className="mb-8">
                <WizardProgress currentStep={currentStep} totalSteps={4} />
            </div>

            {/* Step Content */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 min-h-[500px] mb-6">
                {currentStep === 1 && <Step1_Apartados />}
                {currentStep === 2 && <Step2_Variables />}
                {currentStep === 3 && <Step3_Dimensions />}
                {currentStep === 4 && <Step4_Preview />}
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between">
                <button
                    onClick={prevStep}
                    disabled={!canGoBack()}
                    className={`
    px-6 py-2 rounded-lg font-medium transition-colors border
    ${canGoBack()
                            ? 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                            : 'bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed'
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
      px-6 py-2 rounded-lg font-medium transition-colors shadow-sm
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
        </div >
    );
};
