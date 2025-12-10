/**
 * Draggable Item Component - Items que se pueden arrastrar (Medidas/Dimensiones)
 */

import React from 'react';
import { useDraggable } from '@dnd-kit/core';
import { GripVertical } from 'lucide-react';

interface DraggableItemProps {
    id: string;
    type: 'measure' | 'dimension';
    data: any;
    children: React.ReactNode;
}

export const DraggableItem: React.FC<DraggableItemProps> = ({
    id,
    type,
    data,
    children,
}) => {
    const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
        id,
        data: { type, data },
    });

    return (
        <div
            ref={setNodeRef}
            {...listeners}
            {...attributes}
            className={`
        flex items-center gap-2 px-3 py-2 rounded border cursor-grab active:cursor-grabbing
        transition-all hover:shadow-md
        ${isDragging
                    ? 'opacity-50 scale-95 border-blue-400 bg-blue-50'
                    : 'border-gray-200 bg-white hover:border-blue-300'
                }
      `}
        >
            <GripVertical size={16} className="text-gray-400" />
            <div className="flex-1 text-sm">{children}</div>
        </div>
    );
};
