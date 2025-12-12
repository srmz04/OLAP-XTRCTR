import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWizardStore } from '../../stores/wizardStore';
import { Loader2 } from 'lucide-react';

import { catalogService } from '../../api/services/catalogService';

interface Apartado {
    id: string;
    name: string;
    uniqueName: string;
    hierarchy: string;
}

export const Step1_Apartados: React.FC = () => {
    const { selectedCatalog, selectedApartadoIds, setApartados } = useWizardStore();
    const [searchTerm, setSearchTerm] = useState('');
    const [rangeInput, setRangeInput] = useState('');

    // Fetch apartados from API
    const { data: apartados, isLoading } = useQuery<Apartado[]>({
        queryKey: ['apartados', selectedCatalog],
        queryFn: () => catalogService.getApartados(selectedCatalog),
        enabled: !!selectedCatalog,
    });

    // Filter apartados by search term
    const filteredApartados = useMemo(() => {
        if (!apartados) return [];
        if (!searchTerm) return apartados;

        const lower = searchTerm.toLowerCase();
        return apartados.filter(ap =>
            ap.name.toLowerCase().includes(lower) ||
            ap.id.includes(lower)
        );
    }, [apartados, searchTerm]);

    // Parse range input (e.g., "101-112,119")
    const parseRanges = (input: string): string[] => {
        if (!input.trim()) return [];

        const result: number[] = [];
        const parts = input.split(',');

        for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.includes('-')) {
                const [start, end] = trimmed.split('-').map(n => parseInt(n.trim()));
                if (!isNaN(start) && !isNaN(end)) {
                    for (let i = start; i <= end; i++) {
                        result.push(i);
                    }
                }
            } else {
                const num = parseInt(trimmed);
                if (!isNaN(num)) {
                    result.push(num);
                }
            }
        }

        return Array.from(new Set(result))
            .sort((a, b) => a - b)
            .map(String);
    };

    const handleApplyRange = () => {
        const ids = parseRanges(rangeInput);
        setApartados(ids);
    };

    const handleToggle = (id: string) => {
        if (selectedApartadoIds.includes(id)) {
            setApartados(selectedApartadoIds.filter(i => i !== id));
        } else {
            setApartados([...selectedApartadoIds, id]);
        }
    };

    const handleSelectAll = () => {
        if (filteredApartados) {
            setApartados(filteredApartados.map(ap => ap.id));
        }
    };

    const handleClearAll = () => {
        setApartados([]);
    };

    if (isLoading) {
        return (
            <div className="p-8 flex items-center justify-center">
                <Loader2 className="w-6 h-6 text-indigo-500 animate-spin mr-3" />
                <div className="text-gray-600">Cargando apartados... (esto puede tomar 30-60s la primera vez)</div>
            </div>
        );
    }

    if (!filteredApartados || filteredApartados.length === 0) {
        return (
            <div className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                    Paso 1: Seleccionar Apartados
                </h2>
                <div className="p-4 bg-yellow-50 text-yellow-800 rounded-lg border border-yellow-200">
                    <h3 className="font-bold flex items-center gap-2">
                        ⚠️ No se encontraron apartados
                    </h3>
                    <p className="mt-2 text-sm">
                        Este catálogo ({selectedCatalog}) parece no tener la estructura estándar o está vacío.
                    </p>
                    <p className="mt-2 text-sm">
                        Por favor intenta seleccionar otro catálogo (ej. SIS_2024, SIS_2025).
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Paso 1: Seleccionar Apartados
            </h2>
            <p className="text-sm text-gray-600 mb-6">
                Selecciona los grupos temáticos que deseas consultar
            </p>

            {/* Search Input */}
            <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                    🔍 Buscar por nombre o ID
                </label>
                <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Ej: vacuna, consulta, 119..."
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
            </div>

            {/* Range Input */}
            <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                    ⚡ Selección rápida por rangos
                </label>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={rangeInput}
                        onChange={(e) => setRangeInput(e.target.value)}
                        placeholder="Ej: 101-112, 119"
                        className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    />
                    <button
                        onClick={handleApplyRange}
                        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                    >
                        Aplicar
                    </button>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                    Ejemplo: "1-10,15,20-25" selecciona apartados del 1 al 10, el 15, y del 20 al 25
                </p>
            </div>

            {/* Quick Actions */}
            <div className="flex gap-2 mb-4">
                <button
                    onClick={handleSelectAll}
                    className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
                >
                    Seleccionar todos ({filteredApartados?.length || 0})
                </button>
                <button
                    onClick={handleClearAll}
                    className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
                >
                    Limpiar selección
                </button>
            </div>

            {/* Apartados List */}
            <div className="border border-gray-200 rounded-lg max-h-96 overflow-y-auto">
                {filteredApartados?.map((apartado) => (
                    <label
                        key={apartado.id}
                        className="flex items-start px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-0"
                    >
                        <input
                            type="checkbox"
                            checked={selectedApartadoIds.includes(apartado.id)}
                            onChange={() => handleToggle(apartado.id)}
                            className="mt-1 mr-3 h-4 w-4 text-indigo-600 rounded focus:ring-indigo-500"
                        />
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                                    {apartado.id}
                                </span>
                                <span className="text-sm font-medium text-gray-900">
                                    {apartado.name}
                                </span>
                            </div>
                        </div>
                    </label>
                ))}
            </div>

            {/* Selection Summary */}
            <div className="mt-4 p-3 bg-indigo-50 rounded-lg">
                <p className="text-sm text-indigo-900">
                    <span className="font-semibold">{selectedApartadoIds.length}</span> apartado(s) seleccionado(s)
                    {selectedApartadoIds.length > 0 && (
                        <span className="text-indigo-700 ml-2">
                            (IDs: {selectedApartadoIds.slice(0, 5).join(', ')}
                            {selectedApartadoIds.length > 5 && '...'})
                        </span>
                    )}
                </p>
            </div>
        </div>
    );
};
