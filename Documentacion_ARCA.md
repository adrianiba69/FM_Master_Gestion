# Integración ARCA – FM Master Gestión

## Alcance inicial

- Factura A
- Factura C
- Tres emisores fiscales
- Homologación antes de Producción
- Emisión desde la Ficha Única del Cliente
- Factura asociada a un Resumen

## Arquitectura funcional

Cliente
→ Servicio
→ Resumen
→ Validación fiscal
→ Emisión ARCA
→ CAE
→ PDF oficial
→ Historial
→ Cuenta Corriente
→ WhatsApp

## Emisores iniciales

1. F.M. Master 98.3
2. Publicidad & Servicios
3. Publicidad & Servicios S.H.

No incluir claves privadas ni certificados.

## Ambientes

### Homologación

- Solo pruebas
- Certificados gestionados mediante WSASS
- No emite comprobantes fiscales reales

### Producción

- Emisión real
- Certificados gestionados por los servicios oficiales de certificados digitales
- Se habilitará únicamente después de completar homologación

## Certificados

Cada emisor necesita:

- clave privada local
- solicitud CSR
- certificado X.509 emitido por ARCA
- autorización para utilizar WSFEv1

Aclaraciones de seguridad:

- La clave privada nunca se comparte.
- La clave privada no se guarda dentro de Git.
- La clave privada no se incluye en builds ni backups públicos.
- La clave privada debe conservarse en una carpeta segura.

## Flujo para obtener certificado de Homologación

1. Generar clave privada de al menos 2048 bits.
2. Generar CSR con CUIT correcto.
3. Ingresar a WSASS con clave fiscal.
4. Crear certificado cargando el CSR.
5. Descargar el certificado emitido.
6. Crear autorización para el servicio WSFEv1.
7. Configurar las rutas en Emisores Fiscales.
8. Validar configuración local.
9. Probar autenticación WSAA.
10. Recién después consultar WSFEv1.

## Autenticación WSAA

Flujo previsto:

- Generar TRA.
- Firmar CMS con certificado y clave privada.
- Enviar a WSAA.
- Recibir token y sign.
- Reutilizar el ticket mientras siga vigente.
- No guardar token y sign de forma permanente.

## Emisión

Si ARCA autoriza, guardar:

- emisor fiscal
- tipo de comprobante
- punto de venta
- número de comprobante
- fecha
- CAE
- vencimiento de CAE
- estado Facturado
- ruta del PDF oficial

Si ARCA no responde:

- mantener el Resumen
- estado Pendiente de emitir
- permitir reintento
- consultar antes de reemitir para evitar duplicados

Si faltan datos:

- no emitir
- mostrar detalle exacto
- no alterar el Resumen

## Organización de archivos

Carpeta raíz configurable:

C:\Facturas

Estructura futura:

C:\Facturas\
  F.M. Master 98.3\
    2026\
      Julio\
  Publicidad & Servicios\
    2026\
      Julio\
  Publicidad & Servicios S.H.\
    2026\
      Julio\

## Seguridad

- Nunca subir *.key, *.pem, *.p12, *.pfx, *.crt o *.cer a Git.
- No enviar claves privadas por correo ni mensajería.
- Hacer backup cifrado.
- Mantener separadas Homologación y Producción.
- No copiar certificados de Producción a equipos no autorizados.

## Recuperación y cambio de computadora

En una restauración o migración se debe recuperar:

- base de datos
- certificados
- claves privadas
- configuración de rutas
- carpeta de facturas

## Próximos sprints

1. Generación segura de clave y CSR.
2. Alta en WSASS.
3. Autenticación WSAA.
4. Consulta del último comprobante.
5. Factura C de Homologación.
6. Factura A de Homologación.
7. PDF oficial.
8. Integración con Ficha Única.
9. Producción.

## Referencias oficiales de ARCA

Referencias para consulta técnica, sin copiar contenido extenso:

- Portal de Web Services ARCA/AFIP: https://www.afip.gob.ar/ws/
- Documentación WSAA: https://www.afip.gob.ar/ws/documentacion/wsaa.asp
- Documentación WSFEv1: https://www.afip.gob.ar/ws/documentacion/ws-factura-electronica.asp
- Manuales y esquema de homologación: https://www.afip.gob.ar/ws/documentacion/
- Portal de Clave Fiscal (acceso a servicios): https://auth.afip.gob.ar/
