/**
 * Drop Zone Component - Área donde se sueltan items (COLUMNS, ROWS, FILTERS)
 */

import React from 'react';
import { useDroppable } from '@dnd-kit/core';
import { X } from 'lucide-react';
import { DroppedItem } from '../stores/queryBuilder';

interface DropZoneProps {
    id: 'COLUMNS' | 'ROWS' | 'FILTERS';
    title: string;
    items: DroppedItem[];
    onRemoveItem: (id: string) => void;
    acceptTypes: Array<'measure' | 'dimension'>;
}

export const DropZone: React.FC<DropZoneProps> = ({
    id,
    title,
    items,
    onRemoveItem,
    acceptTypes,
}) => {
    const { isOver, setNodeRef } = useDroppable({
        id,
        data: { acceptTypes },
    });

    const bgColor = isOver
        ? 'bg-blue-100 border-blue-500 border-2'
        : 'bg-gray-50 border-gray-300 border-2 border-dashed';

    return (
        <div ref={setNodeRef} className={`rounded-lg p-4 min-h-[120px] transition-colors ${bgColor}`}>
            <h3 className="font-semibold text-gray-700 mb-3 text-sm uppercase">{title}</h3>

            <div className="space-y-2">
                {items.length === 0 && (
                    <p className="text-gray-400 text-sm italic">
                        Arrastra {acceptTypes.includes('measure') ? 'medidas' : 'dimensiones'} aquí
                    </p>
                )}

                {items.map((item) => (
                    <div
                        key={item.id}
                        className="flex items-center justify-between bg-white rounded px-3 py-2 shadow-sm border border-gray-200 group hover:border-blue-400 transition-all"
                    >
                        <div className="flex-1">
                            <span className="text-sm font-medium text-gray-800">
                                {item.type === 'measure'
                                    ? (item.data as any).caption
                                    : (item.data as any).displayName
                                }
                            </span>
                            {item.type === 'dimension' && (item.data as any).selectedLevel && (
                                <span className="text-xs text-gray-500 ml-2">
                                    • {(item.data as any).selectedLevel}
                                </span>
                            )}
                        </div>

                        <button
                            onClick={() => onRemoveItem(item.id)}
                            className="opacity-0 group-hover:opacity-100 transition-opacity text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50"
                            title="Remover"
                        >
                            <X size={16} />
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );
};
