import React, { useEffect, useState, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useCatalogStore } from '../stores/catalogStore';
import { Search, Database, Loader2, AlertCircle } from 'lucide-react';

export const CatalogSelector: React.FC = () => {
    const { catalogs, selectedCatalog, isLoading, error, fetchCatalogs, selectCatalog } = useCatalogStore();
    const [searchTerm, setSearchTerm] = useState('');
    const parentRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (catalogs.length === 0) {
            fetchCatalogs();
        }
    }, [fetchCatalogs, catalogs.length]);

    // Filter catalogs based on search
    const filteredCatalogs = catalogs.filter(c =>
        c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (c.description || '').toLowerCase().includes(searchTerm.toLowerCase())
    );

    // Virtualizer setup
    const rowVirtualizer = useVirtualizer({
        count: filteredCatalogs.length,
        getScrollElement: () => parentRef.current,
        estimateSize: () => 72, // Estimated height of a row
        overscan: 5,
    });

    return (
        <div className="flex flex-col h-full bg-white border-r border-gray-200 w-80 shadow-md">
            {/* Header */}
            <div className="p-4 border-b border-gray-200 bg-gray-50">
                <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2 mb-3">
                    <Database className="w-5 h-5 text-blue-600" />
                    Data Catalogs
                </h2>

                {/* Search Input */}
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                    <input
                        type="text"
                        placeholder="Search catalogs..."
                        className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden relative">
                {isLoading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
                        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                        <span className="ml-2 text-sm text-gray-500">Loading catalogs...</span>
                    </div>
                )}

                {error && (
                    <div className="p-4 text-red-500 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" />
                        {error}
                        <button
                            onClick={() => fetchCatalogs()}
                            className="text-xs underline ml-2 hover:text-red-700"
                        >
                            Retry
                        </button>
                    </div>
                )}

                {!isLoading && !error && filteredCatalogs.length === 0 && (
                    <div className="p-8 text-center text-gray-500 text-sm">
                        No catalogs found checking mock data/API connection.
                    </div>
                )}

                <div
                    ref={parentRef}
                    className="h-full overflow-y-auto"
                >
                    <div
                        style={{
                            height: `${rowVirtualizer.getTotalSize()}px`,
                            width: '100%',
                            position: 'relative',
                        }}
                    >
                        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                            const catalog = filteredCatalogs[virtualRow.index];
                            const isSelected = selectedCatalog?.name === catalog.name;

                            return (
                                <div
                                    key={catalog.name}
                                    onClick={() => selectCatalog(catalog)}
                                    className={`
                    absolute top-0 left-0 w-full p-3 cursor-pointer transition-colors border-b border-gray-100
                    hover:bg-blue-50
                    ${isSelected ? 'bg-blue-100 border-l-4 border-l-blue-600' : 'border-l-4 border-l-transparent'}
                  `}
                                    style={{
                                        height: `${virtualRow.size}px`,
                                        transform: `translateY(${virtualRow.start}px)`,
                                    }}
                                >
                                    <div className="font-medium text-gray-900 truncate">
                                        {catalog.name}
                                    </div>
                                    <div className="text-xs text-gray-500 mt-1 truncate">
                                        {catalog.description || 'No description available'}
                                    </div>
                                    {catalog.created && (
                                        <div className="text-[10px] text-gray-400 mt-1">
                                            Updated: {catalog.created}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Footer / Status */}
            <div className="p-2 border-t border-gray-200 bg-gray-50 text-xs text-center text-gray-500">
                {filteredCatalogs.length} catalogs available
            </div>
        </div>
    );
};
