import React from 'react';

interface WizardProgressProps {
    currentStep: number;
    totalSteps: number;
}

export const WizardProgress: React.FC<WizardProgressProps> = ({
    currentStep,
    totalSteps
}) => {
    const steps = [
        { number: 1, label: 'Apartados' },
        { number: 2, label: 'Variables' },
        { number: 3, label: 'Dimensiones' },
        { number: 4, label: 'Preview' },
    ];

    return (
        <div className="mb-8">
            <div className="flex items-center justify-between">
                {steps.map((step, idx) => (
                    <React.Fragment key={step.number}>
                        {/* Step Circle */}
                        <div className="flex flex-col items-center">
                            <div
                                className={`
                  w-10 h-10 rounded-full flex items-center justify-center
                  font-semibold text-sm transition-all
                  ${step.number === currentStep
                                        ? 'bg-indigo-600 text-white ring-4 ring-indigo-100'
                                        : step.number < currentStep
                                            ? 'bg-green-500 text-white'
                                            : 'bg-gray-200 text-gray-500'
                                    }
                `}
                            >
                                {step.number < currentStep ? (
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                    </svg>
                                ) : (
                                    step.number
                                )}
                            </div>
                            <span
                                className={`
                  mt-2 text-xs font-medium
                  ${step.number === currentStep ? 'text-indigo-600' : 'text-gray-500'}
                `}
                            >
                                {step.label}
                            </span>
                        </div>

                        {/* Connector Line */}
                        {idx < steps.length - 1 && (
                            <div className="flex-1 mx-2">
                                <div
                                    className={`
                    h-1 rounded transition-all
                    ${step.number < currentStep ? 'bg-green-500' : 'bg-gray-200'}
                  `}
                                />
                            </div>
                        )}
                    </React.Fragment>
                ))}
            </div>
        </div>
    );
};
