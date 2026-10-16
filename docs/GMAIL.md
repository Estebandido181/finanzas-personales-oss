# Gmail para una instalación personal

Gmail es opcional. Puedes probar la demo sin cuenta Google ni credenciales.
Para una instancia propia utiliza tu propio proyecto y cliente OAuth; no envíes
el token, los correos ni el JSON del cliente al mantenedor.

## Alcance real

La aplicación pide únicamente `https://www.googleapis.com/auth/gmail.readonly`.
Puede leer mensajes del buzón; no puede enviarlos ni borrarlos con ese alcance.
La búsqueda se limita en el código a los remitentes oficiales soportados de
Bancolombia. Ese filtro no reduce los permisos de un token robado.
Google clasifica gmail.readonly como restringido: revisa sus requisitos si vas
a ofrecer una app OAuth compartida o un servicio público. Estas instrucciones
no constituyen una aprobación de Google para ese caso.

## Autorizar en tu equipo

1. En Google Cloud crea un proyecto y habilita Gmail API.
2. Configura consentimiento y únicamente gmail.readonly. Elige el público/estado
   que corresponda a tu uso personal y sigue los requisitos vigentes de Google.
   El estado de prueba puede tener autorizaciones de corta duración; publicar
   el consentimiento no garantiza duración indefinida del token.
3. Crea un cliente de tipo Desktop app y descarga su JSON fuera del repositorio.
4. En el entorno Python de la app, desde un equipo con navegador, ejecuta:

   ```bash
   python -m finanzas.gmail autorizar \
     --credenciales /ruta/privada/client_secret.json \
     --token /ruta/privada/token_gmail.json
   ```

5. Comprueba en el consentimiento la cuenta y los permisos. Si no entiendes una
   advertencia o el cliente no es tuyo, detente y revisa la configuración.
6. En una instalación Linux protege el token con permisos 0600 y usa su ruta
   absoluta en GMAIL_TOKEN. Mantén el JSON, token, base y respaldos fuera de Git.
   La aplicación puede necesitar actualizar el archivo al renovar el token.

Los tokens pueden caducar o revocarse por distintas causas. Si la renovación
falla, vuelve a autorizar con tu cliente. Para retirar el acceso, revócalo en
los permisos de tu cuenta Google. No confíes solo en borrar el archivo local.

Referencias oficiales:
- [Scopes de Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Consentimiento OAuth](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [OAuth para aplicaciones instaladas](https://developers.google.com/identity/protocols/oauth2/native-app)
