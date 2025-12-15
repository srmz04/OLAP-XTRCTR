// src/utils/mdxBuilder.ts
import { Catalog, Apartado, Variable } from '../types/olap';

export function buildMdxQuery(
    catalog: Catalog,
    variables: Variable[],
    apartados: Apartado[]
): string {
    // 1. Define Measures (default to Total for now)
    const columns = '{[Measures].[Total]}';

    // 2. Define Rows (Selected Variables)
    // If variables are selected, use them. Otherwise fallback to apartados.
    const rowItems = variables.length > 0 ? variables : apartados;

    if (rowItems.length === 0) {
        return '-- No items selected';
    }

    const rowSet = `{\n    ${rowItems.map(item => item.unique_name).join(',\n    ')}\n  }`;

    // 3. Construct Query
    return `SELECT
  ${columns} ON COLUMNS,
  NON EMPTY ${rowSet} ON ROWS
FROM [${catalog.code}]`;
}
