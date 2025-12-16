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

    // 3. Fix dimension names for SIS_2025
    // The DB has old dimension names, but the cube uses 2025 versions
    const fixedRowItems = rowItems.map(item => {
        let fixedName = item.unique_name;

        // Replace dimension names with 2025 versions
        fixedName = fixedName.replace('[DIM VARIABLES]', '[DIM VARIABLES2025]');
        fixedName = fixedName.replace('[DIM UNIDADES]', '[DIM UNIDADES2025]');
        fixedName = fixedName.replace('[DIM TIEMPO]', '[DIM TIEMPO]'); // This one doesn't change

        return fixedName;
    });

    const rowSet = `{\n    ${fixedRowItems.join(',\n    ')}\n  }`;

    // 4. Construct Query
    return `SELECT
  ${columns} ON COLUMNS,
  NON EMPTY ${rowSet} ON ROWS
FROM [${catalog.code}]`;
}
