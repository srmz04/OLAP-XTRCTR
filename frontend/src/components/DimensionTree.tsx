import React, { useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import { Dimension } from '../api/client';
import { useDraggable } from '@dnd-kit/core';

interface DimensionTreeProps {
    dimensions: Dimension[];
}

interface DraggableLevelProps {
    dimension: Dimension;
    levelName: string;
    levelDepth: number;
}

const DraggableLevel: React.FC<DraggableLevelProps> = ({ dimension, levelName, levelDepth }) => {
    const uniqueId = `${dimension.hierarchy}-${levelName}-${levelDepth}`;

    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: uniqueId,
        data: {
            type: 'level',
            dimension: dimension.dimension,
            hierarchy: dimension.hierarchy,
            level: levelName,
            uniqueName: `${dimension.hierarchy}.[${levelName}]`,
            depth: levelDepth,
        },
    });

    const style = transform
        ? {
            transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        }
        : undefined;

    return (
        <div
            ref={setNodeRef}
            style={style}
            {...listeners}
            {...attributes}
            className={`
                pl-6 py-1.5 text-sm cursor-grab active:cursor-grabbing
                hover:bg-indigo-50 border-l-2 border-transparent hover:border-indigo-400
                transition-all
                ${isDragging ? 'opacity-30 bg-indigo-100' : ''}
            `}
        >
            <span className="text-gray-700">{levelName}</span>
            <span className="text-xs text-gray-400 ml-2">(depth: {levelDepth})</span>
        </div>
    );
};

interface DimensionItemProps {
    dimension: Dimension;
}

const DimensionItem: React.FC<DimensionItemProps> = ({ dimension }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    return (
        <div className="border-b border-gray-100">
            {/* Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full px-3 py-2 flex items-center gap-2 hover:bg-gray-50 transition-colors text-left"
            >
                {isExpanded ? (
                    <ChevronDown className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />
                ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />
                )}
                <span className="text-sm font-medium text-gray-800 truncate">
                    {dimension.displayName}
                </span>
                <span className="text-xs text-gray-400 ml-auto">
                    {dimension.levels.length}
                </span>
            </button>

            {/* Levels */}
            {isExpanded && (
                <div className="bg-gray-50/50">
                    {dimension.levels.map((level, idx) => (
                        <DraggableLevel
                            key={`${dimension.hierarchy}-${level.name}-${idx}`}
                            dimension={dimension}
                            levelName={level.name}
                            levelDepth={level.depth}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export const DimensionTree: React.FC<DimensionTreeProps> = ({ dimensions }) => {
    if (dimensions.length === 0) {
        return (
            <div className="text-center py-6 text-gray-400 text-xs">
                Selecciona un catálogo
            </div>
        );
    }

    return (
        <div className="space-y-0">
            {dimensions.map((dim, idx) => (
                <DimensionItem key={`${dim.hierarchy}-${idx}`} dimension={dim} />
            ))}
        </div>
    );
};
