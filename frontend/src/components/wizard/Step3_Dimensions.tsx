import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useWizardStore, DimensionConfig, FilterConfig } from '../../stores/wizardStore';
import { catalogService } from '../../api/services/catalogService';

interface Dimension {
  dimension: string;
  hierarchy: string;
  displayName: string;
  levels: { name: string; depth: number }[];
}

interface Member {
  caption: string;
  uniqueName: string;
}

// Member Selector Modal Component
const MemberSelectorModal: React.FC<{
  filter: FilterConfig;
  onClose: () => void;
  onSave: (members: string[]) => void;
  catalog: string;
}> = ({ filter, onClose, onSave, catalog }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedMembers, setSelectedMembers] = useState<string[]>(filter.members || []);

  // Fetch members for this dimension/hierarchy
  const { data: members, isLoading } = useQuery<Member[]>({
    queryKey: ['members', catalog, filter.dimension, filter.hierarchy, filter.level],
    queryFn: () => catalogService.getMembers(catalog, filter.dimension, filter.hierarchy, filter.level),
  });

  const filteredMembers = useMemo(() => {
    if (!members) return [];
    if (!searchTerm) return members;

    const lower = searchTerm.toLowerCase();
    return members.filter(m =>
      m.caption.toLowerCase().includes(lower)
    );
  }, [members, searchTerm]);

  const toggleMember = (uniqueName: string) => {
    setSelectedMembers(prev =>
      prev.includes(uniqueName)
        ? prev.filter(m => m !== uniqueName)
        : [...prev, uniqueName]
    );
  };

  const toggleAll = () => {
    if (selectedMembers.length === filteredMembers.length) {
      setSelectedMembers([]);
    } else {
      setSelectedMembers(filteredMembers.map(m => m.uniqueName));
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            Seleccionar Miembros - {filter.dimension}
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            {selectedMembers.length} miembros seleccionados
          </p>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-gray-200">
          <input
            type="text"
            placeholder="Buscar miembros..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
          />
        </div>

        {/* Members List */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && (
            <div className="text-center py-8 text-gray-500">
              Cargando miembros...
            </div>
          )}

          {!isLoading && filteredMembers.length === 0 && (
            <div className="text-center py-8 text-gray-400">
              No se encontraron miembros
            </div>
          )}

          {!isLoading && filteredMembers.length > 0 && (
            <>
              <div className="mb-4">
                <button
                  onClick={toggleAll}
                  className="text-sm text-purple-600 hover:text-purple-700 font-medium"
                >
                  {selectedMembers.length === filteredMembers.length ? 'Deseleccionar todo' : 'Seleccionar todo'}
                </button>
              </div>

              <div className="space-y-2">
                {filteredMembers.map((member) => (
                  <label
                    key={member.uniqueName}
                    className="flex items-center p-2 hover:bg-gray-50 rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedMembers.includes(member.uniqueName)}
                      onChange={() => toggleMember(member.uniqueName)}
                      className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
                    />
                    <span className="ml-3 text-sm text-gray-700">{member.caption}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Cancelar
          </button>
          <button
            onClick={() => {
              onSave(selectedMembers);
              onClose();
            }}
            className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-md hover:bg-purple-700"
          >
            Guardar ({selectedMembers.length})
          </button>
        </div>
      </div>
    </div>
  );
};

export const Step3_Dimensions: React.FC = () => {
  const {
    selectedCatalog,
    selectedRows,
    selectedFilters,
    setRows,
    setFilters
  } = useWizardStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [editingFilter, setEditingFilter] = useState<FilterConfig | null>(null);

  // Fetch dimensions
  const { data: dimensions, isLoading } = useQuery<Dimension[]>({
    queryKey: ['dimensions', selectedCatalog],
    queryFn: () => catalogService.getDimensions(selectedCatalog),
    enabled: !!selectedCatalog,
  });

  // Filter dimensions
  const filteredDimensions = useMemo(() => {
    if (!dimensions) return [];
    if (!searchTerm) return dimensions;

    const lower = searchTerm.toLowerCase();
    return dimensions.filter(d =>
      d.displayName.toLowerCase().includes(lower) ||
      d.dimension.toLowerCase().includes(lower)
    );
  }, [dimensions, searchTerm]);

  const removeRow = (dimension: string, hierarchy: string) => {
    setRows(selectedRows.filter((r: DimensionConfig) =>
      !(r.dimension === dimension && r.hierarchy === hierarchy)
    ));
  };

  const removeFilter = (dimension: string, hierarchy: string) => {
    setFilters(selectedFilters.filter((f: FilterConfig) =>
      !(f.dimension === dimension && f.hierarchy === hierarchy)
    ));
  };

  const handleSaveMembers = (filter: FilterConfig, members: string[]) => {
    const updatedFilters = selectedFilters.map((f: FilterConfig) =>
      f.dimension === filter.dimension && f.hierarchy === filter.hierarchy
        ? { ...f, members }
        : f
    );
    setFilters(updatedFilters);
  };

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="text-gray-500">Cargando dimensiones...</div>
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Paso 3: Configurar Dimensiones
      </h2>

      <p className="text-sm text-gray-600 mb-6">
        Define cómo quieres desagregar (Fila) y filtrar los datos.
      </p>

      {/* Main layout */}
      <div className="flex-1 flex gap-6 min-h-0">

        {/* Available Dimensions */}
        <div className="flex-1 flex flex-col min-h-0">
          <h3 className="font-medium text-gray-900 mb-2">Dimensiones Disponibles</h3>

          {/* Search */}
          <input
            type="text"
            placeholder="Buscar dimensión..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="mb-3 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
          />

          <div className="flex-1 overflow-y-auto border border-gray-200 rounded-lg bg-gray-50 p-2 space-y-2">
            {filteredDimensions?.map((dim) => {
              const isRow = selectedRows.some((r: DimensionConfig) => r.dimension === dim.dimension && r.hierarchy === dim.hierarchy);
              const isFilter = selectedFilters.some((f: FilterConfig) => f.dimension === dim.dimension && f.hierarchy === dim.hierarchy);

              return (
                <div key={`${dim.dimension}-${dim.hierarchy}`} className="bg-white p-3 rounded shadow-sm border border-gray-100 flex justify-between items-center">
                  <div>
                    <div className="font-medium text-sm text-gray-900">{dim.displayName}</div>
                    <div className="text-xs text-gray-500 font-mono">{dim.dimension}</div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        if (isRow) return;
                        // Find the first meaningful level (skip "All" and "All.UNKNOWNMEMBER")
                        const meaningfulLevel = dim.levels.find(l =>
                          !l.name.toLowerCase().includes('all') &&
                          !l.name.includes('UNKNOWNMEMBER')
                        ) || dim.levels[0];

                        setRows([...selectedRows, {
                          dimension: dim.dimension,
                          hierarchy: dim.hierarchy,
                          level: meaningfulLevel.name,
                          depth: meaningfulLevel.depth
                        }]);
                      }}
                      disabled={isRow}
                      className={`px-2 py-1 text-xs font-medium rounded border ${isRow
                        ? 'bg-blue-50 text-blue-600 border-blue-200 cursor-default'
                        : 'bg-white text-blue-600 border-blue-200 hover:bg-blue-50'
                        }`}
                    >
                      {isRow ? '✓ FILA' : '+ FILA'}
                    </button>

                    <button
                      onClick={() => {
                        if (isFilter) return;
                        // Find the first meaningful level (skip "All" and "All.UNKNOWNMEMBER")
                        const meaningfulLevel = dim.levels.find(l =>
                          !l.name.toLowerCase().includes('all') &&
                          !l.name.includes('UNKNOWNMEMBER')
                        ) || dim.levels[0];

                        setFilters([...selectedFilters, {
                          dimension: dim.dimension,
                          hierarchy: dim.hierarchy,
                          level: meaningfulLevel.name,
                          members: []
                        }]);
                      }}
                      disabled={isFilter}
                      className={`px-2 py-1 text-xs font-medium rounded border ${isFilter
                        ? 'bg-purple-50 text-purple-600 border-purple-200 cursor-default'
                        : 'bg-white text-purple-600 border-purple-200 hover:bg-purple-50'
                        }`}
                    >
                      {isFilter ? '✓ FILTRO' : '+ FILTRO'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Rows & Filters */}
        <div className="w-80 flex flex-col gap-4 min-h-0">

          {/* Rows Section */}
          <div className="flex-1 flex flex-col min-h-0">
            <h3 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500"></span>
              Filas (Desglose)
            </h3>
            <div className="flex-1 overflow-y-auto border border-gray-200 rounded-lg bg-gray-50 p-2 space-y-2">
              {selectedRows.length === 0 && (
                <div className="text-center text-gray-400 text-sm py-8">
                  No hay filas seleccionadas
                </div>
              )}
              {selectedRows.map((row: DimensionConfig) => (
                <div key={`${row.dimension}-${row.hierarchy}`} className="bg-white p-3 rounded shadow-sm border-l-4 border-blue-500 flex justify-between items-center group">
                  <div>
                    <div className="font-medium text-sm text-gray-900">{row.dimension}</div>
                    <div className="text-xs text-gray-500">Nivel: {row.level}</div>
                  </div>
                  <button
                    onClick={() => removeRow(row.dimension, row.hierarchy)}
                    className="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Filters Section */}
          <div className="flex-1 flex flex-col min-h-0">
            <h3 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-purple-500"></span>
              Filtros (WHERE)
            </h3>
            <div className="flex-1 overflow-y-auto border border-gray-200 rounded-lg bg-gray-50 p-2 space-y-2">
              {selectedFilters.length === 0 && (
                <div className="text-center text-gray-400 text-sm py-8">
                  No hay filtros seleccionados
                </div>
              )}
              {selectedFilters.map((filter: FilterConfig) => (
                <div key={`${filter.dimension}-${filter.hierarchy}`} className="bg-white p-3 rounded shadow-sm border-l-4 border-purple-500 group">
                  <div className="flex justify-between items-center mb-2">
                    <div className="font-medium text-sm text-gray-900">{filter.dimension}</div>
                    <button
                      onClick={() => removeFilter(filter.dimension, filter.hierarchy)}
                      className="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ✕
                    </button>
                  </div>

                  {/* Members list or placeholder */}
                  <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-100">
                    {!filter.members || filter.members.length === 0 ? (
                      <span className="italic text-gray-400">Ningún miembro seleccionado (Filas)</span>
                    ) : (
                      <span>{filter.members.length} miembros seleccionados</span>
                    )}
                  </div>

                  <button
                    onClick={() => setEditingFilter(filter)}
                    className="mt-2 w-full py-1 text-xs text-purple-600 border border-purple-200 rounded hover:bg-purple-50 transition-colors"
                  >
                    Configurar Miembros...
                  </button>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>

      {/* Member Selector Modal */}
      {editingFilter && (
        <MemberSelectorModal
          filter={editingFilter}
          catalog={selectedCatalog}
          onClose={() => setEditingFilter(null)}
          onSave={(members) => handleSaveMembers(editingFilter, members)}
        />
      )}
    </div>
  );
};
