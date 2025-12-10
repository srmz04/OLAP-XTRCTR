import React, { useState } from 'react';
import { DndContext, DragEndEvent } from '@dnd-kit/core';
import { useQuery, useMutation, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { olapApi, Measure, Dimension } from './api/client';
import { useQueryStore } from './stores/queryBuilder';
import { DropZone } from './components/DropZone';
import { DraggableItem } from './components/DraggableItem';
import { ResultsGrid } from './components/ResultsGrid';
import { DimensionTree } from './components/DimensionTree';
import { Database, Play, Trash2, Download } from 'lucide-react';

const queryClient = new QueryClient();

function AppContent() {
    const [selectedCatalog, setSelectedCatalog] = useState<string>('');

    const {
        columnsItems,
        rowsItems,
        filtersItems,
        addToColumns,
        addToRows,
        addToFilters,
        removeFromColumns,
        removeFromRows,
        removeFromFilters,
        clearAll,
        queryResults,
        setQueryResults,
    } = useQueryStore();

    // Queries
    const { data: catalogs } = useQuery({
        queryKey: ['catalogs'],
        queryFn: olapApi.getCatalogs,
    });

    const { data: measures } = useQuery({
        queryKey: ['measures', selectedCatalog],
        queryFn: () => olapApi.getMeasures(selectedCatalog),
        enabled: !!selectedCatalog,
    });

    const { data: dimensions } = useQuery({
        queryKey: ['dimensions', selectedCatalog],
        queryFn: () => olapApi.getDimensions(selectedCatalog),
        enabled: !!selectedCatalog,
    });

    // Mutation para ejecutar query
    const executeMutation = useMutation({
        mutationFn: olapApi.executeQuery,
        onSuccess: (data) => {
            setQueryResults(data.rows);
        },
    });

    // Handlers
    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;

        if (!over) return;

        const draggedData = active.data.current;
        const dropZoneId = over.id as 'COLUMNS' | 'ROWS' | 'FILTERS';
        const acceptTypes = over.data.current?.acceptTypes || [];

        // Map 'level' to 'dimension' for acceptance
        const itemType = draggedData?.type === 'level' ? 'dimension' : draggedData?.type;

        // Validar tipo
        if (!acceptTypes.includes(itemType)) {
            alert(`No puedes colocar ${itemType}s en ${dropZoneId}`);
            return;
        }

        const newItem = {
            id: `${dropZoneId}-${active.id}-${Date.now()}`,
            type: draggedData.type,  // Keep original type: 'measure' or 'level'
            data: draggedData,       // Store the full dragged data
        };

        if (dropZoneId === 'COLUMNS') addToColumns(newItem);
        if (dropZoneId === 'ROWS') addToRows(newItem);
        if (dropZoneId === 'FILTERS') addToFilters(newItem);
    };

    const handleExecuteQuery = () => {
        if (!selectedCatalog) {
            alert('Selecciona un catálogo primero');
            return;
        }

        if (columnsItems.length === 0 || rowsItems.length === 0) {
            alert('Necesitas al menos una medida en COLUMNS y una dimensión en ROWS');
            return;
        }

        const request = {
            catalog: selectedCatalog,
            measures: columnsItems.map((item) => {
                // Handle measure items
                if (item.type === 'measure') {
                    return { uniqueName: (item.data.data as Measure).id };
                }
                return { uniqueName: '' };
            }),
            rows: rowsItems.map((item) => {
                if (item.type === 'level') {
                    // Handle level items (from DimensionTree)
                    return {
                        dimension: item.data.dimension,
                        hierarchy: item.data.hierarchy,
                        level: item.data.level,
                        depth: item.data.depth,
                    };
                }
                // Fallback for old dimension items
                const dim = item.data as Dimension;
                return {
                    dimension: dim.dimension,
                    hierarchy: dim.hierarchy,
                    level: dim.levels[0]?.name || 'All',
                    depth: dim.levels[0]?.depth || 1,
                };
            }),
            filters: filtersItems.map((item) => {
                if (item.type === 'level') {
                    return {
                        dimension: item.data.dimension,
                        hierarchy: item.data.hierarchy,
                        members: [], // TODO: Implementar selector de miembros
                    };
                }
                const dim = item.data as Dimension;
                return {
                    dimension: dim.dimension,
                    hierarchy: dim.hierarchy,
                    members: [],
                };
            }),
        };

        executeMutation.mutate(request);
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
            {/* Header */}
            <header className="bg-white shadow-sm border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <Database size={32} className="text-blue-600" />
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900">DGIS OLAP Query Builder</h1>
                                <p className="text-sm text-gray-500">Constructor visual de consultas MDX</p>
                            </div>
                        </div>

                        {/* Catalog Selector */}
                        <select
                            value={selectedCatalog}
                            onChange={(e) => setSelectedCatalog(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                            <option value="">Seleccionar Catálogo</option>
                            {catalogs?.map((cat) => (
                                <option key={cat.name} value={cat.name}>
                                    {cat.name} - {cat.description}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
                <DndContext onDragEnd={handleDragEnd}>
                    <div className="grid grid-cols-12 gap-6">
                        {/* Left Panel - Measures & Dimensions */}
                        <div className="col-span-3 space-y-4">
                            {/* Measures */}
                            <div className="bg-white rounded-lg shadow p-4">
                                <h2 className="font-semibold text-gray-700 mb-3">📊 Medidas</h2>
                                <div className="space-y-2 max-h-64 overflow-y-auto">
                                    {measures?.map((measure) => (
                                        <DraggableItem
                                            key={measure.id}
                                            id={measure.id}
                                            type="measure"
                                            data={measure}
                                        >
                                            <span className="font-medium">{measure.caption}</span>
                                            <span className="text-xs text-gray-500 block">{measure.aggregator}</span>
                                        </DraggableItem>
                                    ))}
                                </div>
                            </div>

                            {/* Dimensions */}
                            <div className="bg-white rounded-lg shadow p-4">
                                <h2 className="font-semibold text-gray-700 mb-3">📐 Dimensiones</h2>
                                <div className="max-h-96 overflow-y-auto">
                                    <DimensionTree dimensions={dimensions || []} />
                                </div>
                            </div>
                        </div>

                        {/* Right Panel - Query Builder */}
                        <div className="col-span-9 space-y-4">
                            {/* Drop Zones */}
                            <div className="bg-white rounded-lg shadow p-6 space-y-4">
                                <div className="flex items-center justify-between mb-4">
                                    <h2 className="text-lg font-semibold text-gray-800">Constructor de Consulta</h2>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={handleExecuteQuery}
                                            disabled={executeMutation.isPending}
                                            className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                        >
                                            <Play size={16} />
                                            {executeMutation.isPending ? 'Ejecutando...' : 'Ejecutar Query'}
                                        </button>
                                        <button
                                            onClick={clearAll}
                                            className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition-colors"
                                        >
                                            <Trash2 size={16} />
                                            Limpiar
                                        </button>
                                    </div>
                                </div>

                                <DropZone
                                    id="COLUMNS"
                                    title="Medidas (COLUMNS)"
                                    items={columnsItems}
                                    onRemoveItem={removeFromColumns}
                                    acceptTypes={['measure']}
                                />

                                <DropZone
                                    id="ROWS"
                                    title="Desgloses (ROWS)"
                                    items={rowsItems}
                                    onRemoveItem={removeFromRows}
                                    acceptTypes={['dimension']}
                                />

                                <DropZone
                                    id="FILTERS"
                                    title="Filtros (Integrados en ROWS)"
                                    items={filtersItems}
                                    onRemoveItem={removeFromFilters}
                                    acceptTypes={['dimension']}
                                />
                            </div>

                            {/* Results */}
                            <div className="bg-white rounded-lg shadow p-6">
                                <div className="flex items-center justify-between mb-4">
                                    <h2 className="text-lg font-semibold text-gray-800">
                                        Resultados {queryResults && `(${queryResults.length} filas)`}
                                    </h2>
                                    {queryResults && queryResults.length > 0 && (
                                        <button className="flex items-center gap-2 text-blue-600 hover:text-blue-700">
                                            <Download size={16} />
                                            Exportar Excel
                                        </button>
                                    )}
                                </div>
                                <ResultsGrid data={queryResults || []} />
                            </div>
                        </div>
                    </div>
                </DndContext>
            </main>
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
