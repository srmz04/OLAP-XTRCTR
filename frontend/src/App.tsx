// src/App.tsx
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { olapApi } from './api/client';
import { useWizardStore } from './stores/wizardStore';
import { buildMdxQuery } from './utils/mdxBuilder';
import { Loader2, CheckCircle2 } from 'lucide-react';

const queryClient = new QueryClient();

function WizardContent() {
  const {
    step,
    selectedCatalog,
    selectedApartados,
    selectedVariables,
    selectCatalog,
    toggleApartado,
    toggleVariable,
    setStep
  } = useWizardStore();

  // Fetch catalogs
  const { data: catalogsData, isLoading: catalogsLoading } = useQuery({
    queryKey: ['catalogs'],
    queryFn: () => olapApi.getCatalogs(),
  });

  // Fetch apartados when catalog is selected
  const { data: apartadosData, isLoading: apartadosLoading } = useQuery({
    queryKey: ['apartados', selectedCatalog?.code],
    queryFn: () => olapApi.getApartados(selectedCatalog!.code),
    enabled: !!selectedCatalog,
  });

  // Fetch variables of selected apartados
  const { data: variablesData, isLoading: variablesLoading } = useQuery({
    queryKey: ['variables', selectedCatalog?.code, selectedApartados.map(a => a.unique_name).join(',')],
    queryFn: async () => {
      if (selectedApartados.length === 0) return { members: [], total: 0 };

      // Fetch variables for all selected apartados
      const results = await Promise.all(
        selectedApartados.map(apartado =>
          olapApi.getVariablesOfApartado(selectedCatalog!.code, apartado.unique_name)
        )
      );

      // Combine all variables
      const allVariables = results.flatMap(r => r.members);
      return { members: allVariables, total: allVariables.length };
    },
    enabled: !!selectedCatalog && selectedApartados.length > 0 && step === 3,
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-gray-900">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-white mb-4">
            OLAP XTRCTR v3.0
          </h1>
          <p className="text-gray-300 text-lg">
            PostgreSQL + Cloudflare Workers + React
          </p>
          <div className="mt-4 inline-flex items-center gap-2 bg-green-500/20 text-green-300 px-4 py-2 rounded-full">
            <CheckCircle2 className="w-5 h-5" />
            <span>API: olap-api.xtrctr.workers.dev</span>
          </div>
        </div>

        {/* Step Indicator */}
        <div className="flex justify-center mb-8 gap-4">
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              className={`flex items-center justify-center w-12 h-12 rounded-full font-bold transition-all ${step === s
                ? 'bg-blue-500 text-white scale-110'
                : step > s
                  ? 'bg-green-500 text-white'
                  : 'bg-gray-700 text-gray-400'
                }`}
            >
              {s}
            </div>
          ))}
        </div>

        {/* Step 1: Select Catalog */}
        {step === 1 && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8">
            <h2 className="text-3xl font-bold text-white mb-6">
              Paso 1: Selecciona un Catálogo
            </h2>

            {catalogsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
                <span className="ml-3 text-gray-300">Cargando catálogos...</span>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {catalogsData?.catalogs.map((catalog) => (
                  <button
                    key={catalog.code}
                    onClick={() => selectCatalog(catalog as any)}
                    className="bg-gradient-to-br from-blue-600 to-blue-800 hover:from-blue-500 hover:to-blue-700 text-white p-6 rounded-xl shadow-lg transition-all transform hover:scale-105"
                  >
                    <div className="text-2xl font-bold mb-2">{catalog.code}</div>
                    <div className="text-sm opacity-80">{catalog.name}</div>
                    <div className="text-xs opacity-60 mt-2">Año: {catalog.year}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 2: Select Apartados */}
        {step === 2 && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-3xl font-bold text-white">
                Paso 2: Selecciona Apartados
              </h2>
              <button
                onClick={() => setStep(1)}
                className="bg-gray-600 hover:bg-gray-500 text-white px-4 py-2 rounded-lg"
              >
                ← Volver
              </button>
            </div>

            <div className="bg-blue-500/20 text-blue-200 p-4 rounded-lg mb-6">
              <p className="font-semibold">Catálogo: {selectedCatalog?.code}</p>
              {apartadosData && (
                <p className="text-sm mt-1">
                  Total: {apartadosData.total} apartados | Seleccionados: {selectedApartados.length}
                </p>
              )}
            </div>

            {apartadosLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
                <span className="ml-3 text-gray-300">Cargando apartados...</span>
              </div>
            ) : (
              <>
                <div className="max-h-96 overflow-y-auto space-y-2 mb-6">
                  {apartadosData?.members.map((apartado) => {
                    const isSelected = selectedApartados.some(
                      (a) => a.unique_name === apartado.unique_name
                    );
                    return (
                      <button
                        key={apartado.unique_name}
                        onClick={() => toggleApartado(apartado as any)}
                        className={`w-full text-left p-4 rounded-lg transition-all ${isSelected
                          ? 'bg-green-500/30 border-2 border-green-400'
                          : 'bg-gray-700/50 hover:bg-gray-600/50 border-2 border-transparent'
                          }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-white font-medium">{apartado.caption}</div>
                            <div className="text-gray-400 text-sm">
                              Variables: {apartado.children_cardinality}
                            </div>
                          </div>
                          {isSelected && (
                            <CheckCircle2 className="w-6 h-6 text-green-400" />
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {selectedApartados.length > 0 && (
                  <button
                    onClick={() => setStep(3)}
                    className="w-full bg-gradient-to-r from-green-600 to-green-800 hover:from-green-500 hover:to-green-700 text-white py-4 rounded-xl font-bold text-lg shadow-lg"
                  >
                    Continuar a Variables →
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {/* Step 3: Select Variables */}
        {step === 3 && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-3xl font-bold text-white">
                Paso 3: Selecciona Variables
              </h2>
              <button
                onClick={() => setStep(2)}
                className="bg-gray-600 hover:bg-gray-500 text-white px-4 py-2 rounded-lg"
              >
                ← Volver
              </button>
            </div>

            <div className="bg-purple-500/20 text-purple-200 p-4 rounded-lg mb-6">
              <p className="font-semibold">
                {selectedApartados.length} apartado(s) seleccionado(s)
              </p>
              {variablesData && (
                <p className="text-sm mt-1">
                  Total variables disponibles: {variablesData.total} | Seleccionadas: {selectedVariables.length}
                </p>
              )}
            </div>

            {variablesLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
                <span className="ml-3 text-gray-300">Cargando variables...</span>
              </div>
            ) : (
              <>
                <div className="max-h-96 overflow-y-auto space-y-2 mb-6">
                  {variablesData?.members.map((variable) => {
                    const isSelected = selectedVariables.some(
                      (v) => v.unique_name === variable.unique_name
                    );
                    return (
                      <button
                        key={variable.unique_name}
                        onClick={() => toggleVariable(variable as any)}
                        className={`w-full text-left p-4 rounded-lg transition-all ${isSelected
                          ? 'bg-purple-500/30 border-2 border-purple-400'
                          : 'bg-gray-700/50 hover:bg-gray-600/50 border-2 border-transparent'
                          }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="text-white font-medium">{variable.caption}</div>
                          {isSelected && (
                            <CheckCircle2 className="w-6 h-6 text-purple-400" />
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {selectedVariables.length > 0 && (
                  <button
                    onClick={() => setStep(4)}
                    className="w-full bg-gradient-to-r from-purple-600 to-purple-800 hover:from-purple-500 hover:to-purple-700 text-white py-4 rounded-xl font-bold text-lg shadow-lg"
                  >
                    Ver Resumen →
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {/* Step 4: Summary */}
        {step === 4 && (
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8">
            <h2 className="text-3xl font-bold text-white mb-6">
              Paso 4: Resumen y Query
            </h2>

            <div className="bg-green-500/20 border-2 border-green-400 rounded-xl p-6 mb-6">
              <h3 className="text-xl font-bold text-green-300 mb-4">✅ Selección Completa</h3>
              <div className="space-y-2 text-white">
                <p><strong>Catálogo:</strong> {selectedCatalog?.code}</p>
                <p><strong>Apartados:</strong> {selectedApartados.length}</p>
                <p><strong>Variables:</strong> {selectedVariables.length}</p>
              </div>
            </div>

            {/* MDX Preview */}
            <div className="bg-gray-900 rounded-xl p-6 mb-6 border border-gray-700 shadow-inner">
              <div className="flex justify-between items-center mb-4">
                <h4 className="text-gray-400 text-sm font-mono uppercase tracking-wider">Generated MDX Query</h4>
                <button
                  onClick={() => navigator.clipboard.writeText(buildMdxQuery(selectedCatalog!, selectedVariables, selectedApartados))}
                  className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-2 py-1 rounded transition-colors"
                >
                  Copy
                </button>
              </div>
              <pre className="text-green-400 font-mono text-sm overflow-x-auto whitespace-pre-wrap">
                {selectedCatalog && buildMdxQuery(selectedCatalog, selectedVariables, selectedApartados)}
              </pre>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div>
                <h4 className="text-lg font-semibold text-white mb-2">Apartados:</h4>
                <div className="space-y-2 max-h-48 overflow-y-auto pr-2">
                  {selectedApartados.map((a) => (
                    <div key={a.unique_name} className="bg-gray-700/50 p-3 rounded-lg text-gray-200 text-sm truncate" title={a.caption}>
                      {a.caption}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-lg font-semibold text-white mb-2">Variables:</h4>
                <div className="space-y-2 max-h-48 overflow-y-auto pr-2">
                  {selectedVariables.map((v) => (
                    <div key={v.unique_name} className="bg-gray-700/50 p-3 rounded-lg text-gray-200 text-sm truncate" title={v.caption}>
                      {v.caption}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex gap-4">
              <button
                onClick={() => setStep(3)}
                className="flex-1 bg-gray-600 hover:bg-gray-500 text-white py-3 rounded-lg shadow-lg transition-transform active:scale-95"
              >
                ← Volver
              </button>
              <button
                onClick={() => alert('Execution logic will be connected in Phase 4.2')}
                className="flex-1 bg-gradient-to-r from-orange-600 to-orange-800 hover:from-orange-500 hover:to-orange-700 text-white py-3 rounded-lg font-bold shadow-lg transition-transform active:scale-95 flex justify-center items-center gap-2"
              >
                <span>Ejecutar Query</span>
                <span className="text-xs bg-black/20 px-2 py-0.5 rounded">BETA</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WizardContent />
    </QueryClientProvider>
  );
}

export default App;
