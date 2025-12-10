/**
 * Results Grid Component - AG Grid para mostrar resultados de queries
 */

import React, { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';

interface ResultsGridProps {
    data: any[];
    columns?: Array<{
        field: string;
        headerName: string;
        sortable?: boolean;
        filter?: boolean;
    }>;
}

export const ResultsGrid: React.FC<ResultsGridProps> = ({ data, columns }) => {
    const columnDefs = useMemo(() => {
        if (columns && columns.length > 0) {
            return columns.map(col => ({
                ...col,
                sortable: col.sortable ?? true,
                filter: col.filter ?? true,
                resizable: true,
                flex: 1,
            }));
        }

        // Auto-generate columns from data
        if (data && data.length > 0) {
            return Object.keys(data[0]).map(key => ({
                field: key,
                headerName: key,
                sortable: true,
                filter: true,
                resizable: true,
                flex: 1,
            }));
        }

        return [];
    }, [data, columns]);

    if (!data || data.length === 0) {
        return (
            <div className="flex items-center justify-center h-64 border-2 border-dashed border-gray-300 rounded-lg">
                <p className="text-gray-400 text-lg">
                    No hay resultados para mostrar. Configura tu consulta y haz clic en "Ejecutar Query".
                </p>
            </div>
        );
    }

    return (
        <div className="ag-theme-alpine" style={{ height: 600, width: '100%' }}>
            <AgGridReact
                rowData={data}
                columnDefs={columnDefs}
                pagination={true}
                paginationAutoPageSize={true}
                enableCellTextSelection={true}
                suppressRowClickSelection={true}
                defaultColDef={{
                    sortable: true,
                    filter: true,
                    resizable: true,
                }}
                animateRows={true}
            />
        </div>
    );
};
