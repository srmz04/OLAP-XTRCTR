import React from 'react';
import { useMutation } from '@tanstack/react-query';
import { useWizardStore } from '../../stores/wizardStore';

// Get BASE_URL from environment
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const Step4_Preview: React.FC = () => {
    const {
        selectedCatalog,
        selectedVariables,
        selectedRows,
        selectedFilters
    } = useWizardStore();

    const executeQueryMutation = useMutation({
        mutationFn: async () => {
            const payload = {
                catalog: selectedCatalog,
                variables: selectedVariables.map(v => ({ uniqueName: v.uniqueName, name: v.name })),
                rows: selectedRows.map(r => ({
                    dimension: r.dimension,
                    hierarchy: r.hierarchy,
                    level: r.level,
                    depth: r.depth
                })),
                filters: selectedFilters.map(f => ({
                    dimension: f.dimension,
                    hierarchy: f.hierarchy,
                    level: f.level,
                    members: f.members
                }))
            };

            const response = await fetch(`${BASE_URL}/api/query/execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error('Error executing query');
            }

            return response.json();
        },
    });

    const handleExecute = () => {
        executeQueryMutation.mutate();
    };

    return (
        <div className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Paso 4: Previsualizar y Ejecutar
            </h2>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                {/* Summary Card */}
                <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                    <h3 className="font-medium text-gray-900 mb-2">Resumen de Consulta</h3>
                    <ul className="text-sm space-y-2">
                        <li>
                            <span className="font-semibold">Catálogo:</span> {selectedCatalog}
                        </li>
                        <li>
                            <span className="font-semibold">Variables:</span> {selectedVariables.length} seleccionadas
                        </li>
                        <li>
                            <span className="font-semibold">Filas:</span> {selectedRows.length > 0 ? selectedRows.map(r => r.dimension).join(', ') : 'Ninguna'}
                        </li>
                        <li>
                            <span className="font-semibold">Filtros:</span> {selectedFilters.length > 0 ? selectedFilters.map(f => f.dimension).join(', ') : 'Ninguno'}
                        </li>
                    </ul>
                </div>

                {/* Action Area */}
                <div className="lg:col-span-2 flex items-center justify-end">
                    <button
                        onClick={handleExecute}
                        disabled={executeQueryMutation.isPending}
                        className="px-6 py-3 bg-green-600 text-white font-medium rounded-lg shadow hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                    >
                        {executeQueryMutation.isPending ? (
                            <>
                                <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Ejecutando...
                            </>
                        ) : (
                            <>
                                ▶ Ejecutar Consulta
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Results Area */}
            {executeQueryMutation.isError && (
                <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg mb-6">
                    Error al ejecutar la consulta: {executeQueryMutation.error.message}
                </div>
            )}

            {executeQueryMutation.isSuccess && executeQueryMutation.data?.rows && (
                <div className="bg-white p-4 rounded-lg shadow border border-gray-200 overflow-auto">
                    <h3 className="font-medium text-gray-900 mb-4">
                        Resultados ({executeQueryMutation.data.rowCount} filas)
                    </h3>

                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    {executeQueryMutation.data.columns.map((col: any) => (
                                        <th key={col.field} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            {col.headerName}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {executeQueryMutation.data.rows.slice(0, 100).map((row: any, idx: number) => (
                                    <tr key={idx} className="hover:bg-gray-50">
                                        {executeQueryMutation.data.columns.map((col: any) => (
                                            <td key={col.field} className="px-3 py-2 whitespace-nowrap text-gray-700">
                                                {row[col.field]}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {executeQueryMutation.data.rowCount > 100 && (
                        <div className="mt-4 text-center text-sm text-gray-500">
                            Mostrando primeras 100 filas de {executeQueryMutation.data.rowCount}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
