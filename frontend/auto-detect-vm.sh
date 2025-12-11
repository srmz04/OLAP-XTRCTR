#!/bin/bash
# auto-detect-vm.sh
# Detecta la IP de la VM y actualiza el código frontend automáticamente

set -e

echo "🔍 Detectando VM en la red..."

# Buscar todas las IPs en la red local
POSSIBLE_IPS=$(ip neigh | grep -v "FAILED" | grep -E "(192\.168\.|10\.)" | awk '{print $1}' | sort -u)

VM_IP=""

if [ -n "$POSSIBLE_IPS" ]; then
    echo "📡 IPs encontradas en la red:"
    echo "$POSSIBLE_IPS" | nl
    echo ""
    echo "Probando puerto 8000 en cada una..."
    
    for ip in $POSSIBLE_IPS; do
        echo -n "  Probando $ip... "
        # Probar si el puerto 8000 responde
        if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$ip/8000" 2>/dev/null; then
            VM_IP="$ip"
            echo "✅ ENCONTRADA!"
            break
        else
            echo "❌"
        fi
    done
else
    echo "⚠️  No se encontraron dispositivos en la red local."
fi

if [ -z "$VM_IP" ]; then
    echo ""
    echo "❌ No se pudo detectar la VM automáticamente."
    echo ""
    echo "💡 Verifica:"
    echo "   1. Backend corriendo: python api_server.py"
    echo "   2. IP de la VM: ipconfig | findstr IPv4"
    echo "   3. Red Bridge activa en VirtualBox"
    echo ""
    echo "🔧 Ingresa la IP manualmente:"
    read -p "   IP de la VM: " MANUAL_IP
    
    if [ -n "$MANUAL_IP" ]; then
        VM_IP="$MANUAL_IP"
        echo "✅ Usando IP manual: $VM_IP"
    else
        echo "❌ No se ingresó ninguna IP. Abortando."
        exit 1
    fi
fi


# Actualizar client.ts hardcodeado
CLIENT_FILE="src/api/client.ts"

echo "📝 Actualizando $CLIENT_FILE..."

# Crear backup
cp "$CLIENT_FILE" "${CLIENT_FILE}.bak"

# Actualizar el BASE_URL con la IP detectada
sed -i "s|const BASE_URL = .*;|const BASE_URL = 'http://$VM_IP:8000';|" "$CLIENT_FILE"

echo "✅ IP hardcodeada en client.ts: http://$VM_IP:8000"

# También actualizar .env por si acaso
echo "VITE_API_URL=http://$VM_IP:8000" > .env

echo ""
echo "✨ ¡Listo! Configuración actualizada automáticamente."
echo "   Backend: http://$VM_IP:8000"
echo ""
echo "🚀 Ahora puedes iniciar el frontend:"
echo "   npm run dev"
