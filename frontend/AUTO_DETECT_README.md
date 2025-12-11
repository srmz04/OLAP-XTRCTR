# Auto-detección de IP de VM

## ¿Qué hace?

Detecta automáticamente la IP de la VM Windows cada vez que inicias el frontend, eliminando la necesidad de actualizar manualmente el `.env` o `client.ts` al cambiar de red WiFi.

## Funcionamiento

1. **Al ejecutar `npm run dev`**, el script `predev` se ejecuta automáticamente
2. Escanea la red local buscando dispositivos
3. Prueba el puerto 8000 en cada IP encontrada
4. Hardcodea la IP detectada en `src/api/client.ts`
5. Actualiza `.env` como backup
6. Inicia Vite normalmente

## Uso

```bash
# Forma automática (recomendada)
npm run dev

# Forma manual (si quieres solo detectar)
./auto-detect-vm.sh
```

## Qué actualiza

### 1. `src/api/client.ts`
```typescript
// Antes
const BASE_URL = import.meta.env.VITE_API_URL || 'http://192.168.1.3:8000';

// Después (ejemplo)
const BASE_URL = 'http://10.18.3.85:8000';
```

### 2. `.env`
```
VITE_API_URL=http://10.18.3.85:8000
```

## Ventajas

✅ Sin configuración manual  
✅ Funciona en cualquier red WiFi  
✅ Detect automáticamente al cambiar de red  
✅ Backup automático de `client.ts.bak`  
✅ Falla claramente si no encuentra la VM

## Requisitos

- Backend corriendo en la VM (puerto 8000)
- VM en la misma red que Ubuntu
- Red Bridge configurada en VirtualBox

## Troubleshooting

**"No se pudo detectar la VM"**
- Verifica que el backend esté corriendo: `python api_server.py`
- Comprueba la IP de la VM: `ipconfig | findstr IPv4` (en Windows)
- Asegúrate de que la Red 2 (Bridge) esté activa

**Restaurar backup**
```bash
cd src/api
cp client.ts.bak client.ts
```
