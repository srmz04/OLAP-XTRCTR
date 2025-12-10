"""
Utilidades para parseo de selecciones múltiples con rangos

Ejemplo: "1,3,5-10,15" → [1, 3, 5, 6, 7, 8, 9, 10, 15]
"""

from typing import List


def parse_ranges(input_str: str) -> List[int]:
    """
    Parsea una cadena con números y rangos separados por comas
    
    Soporta:
    - Números individuales: "5,10,15"
    - Rangos: "5-10" (incluye 5 y 10)
    - Mixtos: "1,3,5-10,15-20"
    
    Args:
        input_str: String con números/rangos separados por comas
        
    Returns:
        Lista de enteros únicos ordenados
        
    Examples:
        >>> parse_ranges("1,3,5")
        [1, 3, 5]
        >>> parse_ranges("1-5")
        [1, 2, 3, 4, 5]
        >>> parse_ranges("1,3,5-8,10")
        [1, 3, 5, 6, 7, 8, 10]
    """
    if not input_str or not input_str.strip():
        return []
    
    result = set()
    
    # Separar por comas
    parts = input_str.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # Verificar si es un rango (contiene '-')
        if '-' in part:
            try:
                # Split en el primer guion (para manejar números negativos si los hubiera)
                range_parts = part.split('-', 1)
                if len(range_parts) == 2:
                    start = int(range_parts[0].strip())
                    end = int(range_parts[1].strip())
                    
                    # Agregar todos los números en el rango (inclusivo)
                    for num in range(start, end + 1):
                        result.add(num)
            except ValueError:
                # Si no se puede parsear, ignorar este segmento
                continue
        else:
            # Número individual
            try:
                result.add(int(part))
            except ValueError:
                continue
    
    return sorted(list(result))
