import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWizardStore } from '../../stores/wizardStore';

import { catalogService } from '../../api/services/catalogService';

interface Variable {
    id: string;
    name: string;
    uniqueName: string;
    apartado: string;
    hierarchy: string;
}

export const Step2_Variables: React.FC = () => {
    const { selectedCatalog, selectedApartadoIds, selectedVariables, setVariables } = useWizardStore();
    const [searchTerm, setSearchTerm] = useState('');
    const [rangeInput, setRangeInput] = useState('');

    // Fetch variables filtered by selected apartados
    const { data: variables, isLoading } = useQuery<Variable[]>({
        queryKey: ['variables', selectedCatalog, selectedApartadoIds.join(',')],
        queryFn: () => catalogService.getVariables(selectedCatalog, selectedApartadoIds),
        enabled: !!selectedCatalog,
    });

    // Filter variables by search term
    const filteredVariables = useMemo(() => {
        if (!variables) return [];
        if (!searchTerm) return variables;

        const lower = searchTerm.toLowerCase();
        return variables.filter(v =>
            v.name.toLowerCase().includes(lower) ||
            v.id.includes(lower)
        );
    }, [variables, searchTerm]);

    // Parse range input
    const parseRanges = (input: string): string[] => {
        if (!input.trim()) return [];
        const result: number[] = [];
        const parts = input.split(',');
        for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.includes('-')) {
                const [start, end] = trimmed.split('-').map(n => parseInt(n.trim()));
                if (!isNaN(start) && !isNaN(end)) {
                    for (let i = start; i <= end; i++) result.push(i);
                }
            } else {
                const num = parseInt(trimmed);
                if (!isNaN(num)) result.push(num);
            }
        }
        return Array.from(new Set(result)).sort((a, b) => a - b).map(String);
    };

    const handleApplyRange = () => {
        if (!variables) return;
        const ids = parseRanges(rangeInput);
        const varsToSelect = variables.filter(v => ids.includes(v.id));

        // Merge with existing selection or replace? 
        // Usually replace in range selection context, or add. Let's add.
        const newSelection = [...selectedVariables];
        varsToSelect.forEach(v => {
            if (!newSelection.find(existing => existing.id === v.id)) {
                newSelection.push(v);
            }
        });
        setVariables(newSelection);
    };

    const handleToggle = (variable: Variable) => {
        const exists = selectedVariables.find(v => v.id === variable.id);
        if (exists) {
            setVariables(selectedVariables.filter(v => v.id !== variable.id));
        } else {
            setVariables([...selectedVariables, variable]);
        }
    };

    const handleSelectAll = () => {
        if (filteredVariables) {
            setVariables(filteredVariables);
        }
    };

    const handleClearAll = () => {
        setVariables([]);
    };

    if (isLoading) {
        return (
            <div className="p-8 flex flex-col items-center justify-center text-gray-500">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-2"></div>
                <p>Cargando variables de {selectedApartadoIds.length} apartado(s)...</p>
            </div>
        );
    }

    return (
        <div className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Paso 2: Seleccionar Variables
            </h2>
            <p className="text-sm text-gray-600 mb-6">
                Selecciona las variables específicas que deseas analizar.
                Mostrando variables de los apartados seleccionados.
            </p>

            {/* Controls */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                {/* Search */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        🔍 Buscar variable
                    </label>
                    <input
                        type="text"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        placeholder="Nombre o ID..."
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"
                    />
                </div>

                {/* Range */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        ⚡ Rangos (IDs de variables)
                    </label>
                    <div className="flex gap-2">
                        <input
                            type="text"
                            value={rangeInput}
                            onChange={(e) => setRangeInput(e.target.value)}
                            placeholder="Ej: 1-10, 15"
                            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"
                        />
                        <button
                            onClick={handleApplyRange}
                            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                        >
                            Aplicar
                        </button>
                    </div>
                </div>
            </div>

            {/* Quick Actions */}
            <div className="flex gap-2 mb-4">
                <button
                    onClick={handleSelectAll}
                    className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                >
                    Seleccionar todas ({filteredVariables?.length || 0})
                </button>
                <button
                    onClick={handleClearAll}
                    className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                >
                    Limpiar selección
                </button>
            </div>

            {/* Variables List */}
            <div className="border border-gray-200 rounded-lg max-h-96 overflow-y-auto">
                {filteredVariables?.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        No se encontraron variables. Intenta cambiar los filtros o selecciona más apartados.
                    </div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50 sticky top-0">
                            <tr>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-10">
                                    <input
                                        type="checkbox"
                                        checked={filteredVariables?.length > 0 && selectedVariables.length === filteredVariables?.length}
                                        onChange={handleSelectAll}
                                        className="h-4 w-4 text-indigo-600 rounded focus:ring-indigo-500"
                                    />
                                </th>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    ID
                                </th>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Nombre
                                </th>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Apartado Origen
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {filteredVariables?.map((variable) => {
                                const isSelected = selectedVariables.some(v => v.id === variable.id);
                                return (
                                    <tr
                                        key={variable.uniqueName}
                                        className={`hover:bg-gray-50 cursor-pointer ${isSelected ? 'bg-indigo-50' : ''}`}
                                        onClick={() => handleToggle(variable)}
                                    >
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <input
                                                type="checkbox"
                                                checked={isSelected}
                                                onChange={() => handleToggle(variable)}
                                                className="h-4 w-4 text-indigo-600 rounded focus:ring-indigo-500"
                                                onClick={(e) => e.stopPropagation()}
                                            />
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                                            {variable.id}
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-900">
                                            {variable.name}
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-500">
                                            {variable.apartado}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Selection Summary */}
            <div className="mt-4 p-3 bg-indigo-50 rounded-lg flex justify-between items-center">
                <p className="text-sm text-indigo-900">
                    <span className="font-semibold">{selectedVariables.length}</span> variable(s) seleccionada(s)
                </p>
            </div>
        </div>
    );
};
