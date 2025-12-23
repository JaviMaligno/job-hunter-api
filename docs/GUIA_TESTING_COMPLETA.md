# Guia de Testing Completa - Job Hunter Automation

## Requisitos Previos

### 1. Servicios que deben estar corriendo

```bash
# Terminal 1: Backend API (puerto 8000)
cd job-hunter-api
poetry run uvicorn src.main:app --reload --port 8000

# Terminal 2: Frontend Dashboard (puerto 3000)
cd job-hunter-dashboard
npm run dev
```

### 2. Verificar que los servicios funcionan

- Backend: http://localhost:8000/health -> Debe mostrar `{"status":"ok"}`
- Frontend: http://localhost:3000 -> Debe cargar el dashboard

---

## FASE 1: Login y Autenticacion

### Paso 1.1: Iniciar sesion con Google

1. Abrir http://localhost:3000/login en Chrome
2. Click en el boton de **Google** (primer boton social, con icono de G)
3. Seleccionar o introducir la cuenta: `javiecija96@gmail.com`
4. Introducir la contrasena
5. **IMPORTANTE**: Cuando aparezca la pantalla de permisos, aceptar todos

### Paso 1.2: Verificar login exitoso

1. Despues del login, deberia redirigir al **Dashboard** (/)
2. En la barra de navegacion superior, verificar que aparece el avatar del usuario
3. El boton "Sign In" deberia desaparecer

### Que observar si hay errores:

- Si no redirige: Verificar `NEXTAUTH_URL=http://localhost:3000` en `.env.local`
- Si hay error de OAuth: Revisar logs del backend y configuracion de Google Cloud Console

---

## FASE 2: Configuracion del Perfil (Profile)

### Paso 2.1: Acceder a Profile

1. Click en **Profile** en la barra de navegacion
2. O navegar directamente a http://localhost:3000/profile

### Paso 2.2: Completar informacion personal (UI)

En la seccion **"Personal Information"**:

- **Full Name**: Tu nombre completo
- **Email**: Tu email de contacto (puede ser diferente al de login)
- **Phone**: Numero de telefono
- **Address**: Direccion

### Paso 2.3: Completar links profesionales (UI)

En la seccion **"Professional Links"**:

- **LinkedIn URL**: https://linkedin.com/in/tu-usuario
- **GitHub URL**: https://github.com/tu-usuario
- **Portfolio URL**: URL de tu portfolio (opcional)

### Paso 2.4: Configurar preferencias de trabajo (UI)

En la seccion **"Job Preferences"**:

- **Desired Roles**: Roles separados por coma (ej: "Software Engineer, Full Stack Developer")
- **Desired Locations**: Ubicaciones (ej: "Remote, Madrid, Barcelona")
- **Minimum Salary**: Salario minimo
- **Maximum Salary**: Salario maximo

### Paso 2.5: Subir CV base (UI)

En la seccion **"Base CV"** (despues de Job Preferences):

1. Si no tienes CV subido:

   - Click en el area punteada o en **"Click to upload your CV"**
   - Seleccionar archivo PDF, DOCX o TXT (max 5MB)
   - El sistema extrae el texto automaticamente
2. Si ya tienes CV subido:

   - Ver preview de los primeros 500 caracteres
   - Ver contador de caracteres totales
   - **"Replace CV"**: Subir un nuevo CV
   - **Icono de basura**: Eliminar el CV actual

### Paso 2.6: Guardar perfil

- Click en **"Save Profile"** (boton verde abajo a la derecha)
- Debe aparecer mensaje "Profile updated successfully!"

---

## FASE 3: Conexion de Gmail

### Paso 3.1: Conectar Gmail (UI)

En la pagina de Profile, buscar la seccion **"Gmail Connection"**:

1. Verificar que muestra "Not Connected"
2. Seleccionar los permisos opcionales que deseas:
   - **Read emails** (requerido): Escanear bandeja para job alerts
   - **Manage labels** (opcional): Crear y aplicar etiquetas
   - **Mark as read** (opcional): Marcar emails procesados como leidos
3. Click en **"Connect Gmail"**
4. Autorizar en la pantalla de Google
5. Deberia redirigir de vuelta al Profile

### Paso 3.2: Verificar conexion exitosa (UI)

En la seccion "Gmail Connection" verificar:

- Estado: **"Connected"** con badge verde **"Active"**
- Email mostrado: `javiecija96@gmail.com`
- Permisos: Badges mostrando los permisos otorgados

### Paso 3.3: Gestionar permisos (UI)

Si necesitas cambiar permisos:

1. Click en **"Manage permissions"**
2. Activar/desactivar checkboxes
3. Click en **"Update permissions"**
4. Si quitas permisos, te pedira re-autenticacion

---

## FASE 4: Configurar Fuentes de Email

### Paso 4.1: Activar fuentes de emails (UI)

En la pagina de Profile, buscar seccion **"Email Alert Sources"**:

1. Verificar que aparece la lista de fuentes disponibles:
   - **LinkedIn** (jobalerts-noreply@linkedin.com)
   - **Jack & Jill** (notifications@jackandjill.ai)
   - **Indeed** (jobs-noreply@indeed.com)
   - **Glassdoor** (noreply@glassdoor.com)
   - etc.
2. Activar los toggles de las fuentes que usas (deben quedar en ON/azul)
3. Los cambios se guardan automaticamente

### Que observar:

- Contador "X sources active" deberia actualizarse
- Los toggles deben cambiar de gris a azul cuando se activan

---

## FASE 5: Escanear Emails de Job Alerts

### Opcion A: Escanear desde la UI (RECOMENDADO)

En la pagina de Profile, seccion "Gmail Connection":

1. Verificar que Gmail esta conectado (badge verde "Active")
2. Click en el boton **"Scan Emails for Jobs"** (icono de lupa)
3. Esperar mientras escanea (aparece spinner "Scanning...")
4. Ver resultados en el cuadro azul:
   - **Emails scanned**: Numero de emails analizados
   - **Jobs extracted**: Numero de ofertas extraidas
   - **Recent emails**: Lista de los ultimos emails procesados

### Opcion B: Escanear desde CLI

```bash
cd job-hunter-api

# Ver estado de Gmail
poetry run job-hunter gmail-status

# Fetch emails de job alerts (max 20 emails)
poetry run job-hunter gmail-fetch --max 20
```

### Que observar en el output del CLI:

```
Fetching job alert emails...
Found X emails from job platforms
Processing email 1/X: "New jobs for you" from LinkedIn
  -> Extracted 3 jobs
Processing email 2/X: "Job alert: AI Engineer" from Jack & Jill
  -> Extracted 1 job
...
Total jobs extracted: Y
Jobs saved to database
```

### Si no hay emails o jobs:

- Verificar que tienes emails de LinkedIn/Jack&Jill en tu bandeja
- Los emails deben ser de las ultimas semanas
- Verificar que los senders estan activados en "Email Alert Sources"

---

## FASE 6: Ver y Gestionar Jobs en el Dashboard

### Paso 6.1: Ver jobs en el Kanban Board (UI)

1. Ir a http://localhost:3000 (Dashboard principal)
2. Ver el tablero Kanban con columnas:
   - **INBOX**: Jobs nuevos sin revisar
   - **INTERESTING**: Jobs marcados como interesantes
   - **ADAPTED**: Jobs con CV adaptado
   - **READY**: Listos para aplicar
   - **APPLIED**: Ya aplicados
   - **BLOCKED**: Con algun problema
   - **REJECTED**: Descartados

### Paso 6.2: Mover jobs entre columnas (UI)

- **Drag & Drop**: Arrastra una tarjeta de job a otra columna
- El status se actualiza automaticamente

### Paso 6.3: Buscar y filtrar jobs (UI)

En la barra de busqueda/filtros:

- **Buscar**: Escribir texto para buscar por titulo, empresa, etc.
- **Filtrar**: Por status, empresa, ubicacion
- **Clear**: Limpiar filtros

### Paso 6.4: Anadir jobs manualmente (UI)

1. Click en **"+ Add Job"** (boton arriba a la derecha)
2. Se abre dialogo con dos opciones:

**Tab "Import from URL"** (recomendado):

- Pegar URL de LinkedIn, Indeed, Greenhouse, Lever, etc.
- Click **"Import Job"**
- El sistema scrapeara automaticamente los detalles
- Muestra mensaje con campos extraidos (ej: "Scraped: title, company, location, description")

**Tab "Manual Entry"**:

- Rellenar: Job Title, Company, Location, Job Type, Job URL, Description
- Click **"Add Job"**

---

## FASE 7: Ver Detalle de un Job

### Paso 7.1: Acceder al detalle (UI)

1. En el Dashboard, click en cualquier tarjeta de job
2. Se abre la pagina de detalle `/jobs/[id]`

### Paso 7.2: Informacion disponible (UI)

- **Header**: Titulo, empresa, ubicacion
- **Match Score**: Porcentaje de match con tu perfil (si esta calculado)
- **Job Description**: Descripcion completa del puesto
- **Requirements**: Lista de requisitos extraidos
- **Skills Analysis**:
  - **Matched Skills**: Skills que tienes (badges verdes)
  - **Missing Skills**: Skills que te faltan (badges rojos)
- **Quick Info** (sidebar): Salary range, status, link al posting original
- **Application Materials**: CV adaptado y cover letter (si existen)

### Paso 7.3: Iniciar aplicacion (UI)

1. Click en **"Start Application"** (si el job no esta aplicado)
2. Se abre modal para seleccionar modo de aplicacion

---

## FASE 8: Aplicar a una Oferta

### Paso 8.1: Seleccionar modo de aplicacion (UI)

Desde el detalle del job, click en "Start Application":

Modos disponibles:

- **Assisted** (recomendado): Rellena el formulario, PAUSA antes de enviar
- **Semi-Auto**: Solo pausa si hay blockers (CAPTCHA, etc.)
- **Auto**: Completamente automatico (usar con precaucion)

### Paso 8.2: Seguir progreso de aplicacion (UI)

1. Se redirige a `/applications/[sessionId]`
2. Ver en tiempo real:
   - **Status**: pending, in_progress, paused, submitted, failed
   - **Screenshot**: Captura actual del formulario
   - **Fields Filled**: Campos que se han rellenado
   - **Questions Answered**: Preguntas respondidas con nivel de confianza
   - **WebSocket indicator**: Punto verde = conectado en vivo

### Paso 8.3: Controlar la aplicacion (UI)

Botones disponibles segun el estado:

- **Pause**: Pausar la aplicacion (modo assisted)
- **Resume**: Continuar despues de pausar
- **Submit Application**: Enviar la aplicacion

### Paso 8.4: Aplicar via CLI (alternativa)

```bash
# Iniciar el browser service primero
poetry run job-hunter browser-start --port 8001

# Aplicar en modo asistido
poetry run job-hunter apply "https://company.jobs/posting/123" \
  --cv /ruta/a/tu/cv.pdf \
  --cover /ruta/a/cover_letter.txt \
  --mode assisted
```

---

## FASE 9: Adaptar CV y Generar Cover Letter

### Opcion A: Desde la UI (RECOMENDADO)

1. En el Dashboard, click en una tarjeta de job para abrir el detalle
2. En la seccion **"Application Materials"** (sidebar derecho), click en:
   **"Adapt CV & Generate Cover Letter"**
3. En el dialogo que aparece:
   - **Si tienes CV guardado en tu perfil**:
     - Aparecen botones **"Use Saved CV"** y **"Paste New"**
     - Click en "Use Saved CV" para usar tu CV guardado automaticamente
     - El CV se carga y puedes editarlo si es necesario
   - **Si no tienes CV guardado**:
     - Pega tu CV en el campo de texto (copia de Word/PDF)
   - Selecciona el idioma de salida (Espanol/Ingles)
   - Click en **"Adapt CV & Generate Cover Letter"**
4. Espera mientras AI analiza (puede tardar 10-30 segundos)
5. Ver resultados:
   - **Match Score**: Porcentaje de compatibilidad con el puesto
   - **Skills Matched**: Habilidades que tienes que pide el trabajo
   - **Skills Missing**: Habilidades requeridas que no aparecen en tu CV
   - **Changes Made**: Lista de cambios realizados al CV
   - **Interview Talking Points**: Puntos clave para preparar entrevista
   - **Adapted CV**: Tu CV optimizado para este puesto
   - **Cover Letter**: Carta de presentacion personalizada
6. Usa los botones **Copy** y **Download** para guardar los documentos

### Opcion B: Desde CLI

```bash
# Adaptar CV
poetry run job-hunter adapt-cv \
  --cv /ruta/a/tu/cv.pdf \
  --job "Paste aqui la descripcion del trabajo" \
  --title "AI Engineer" \
  --company "Acme Corp" \
  --lang es \
  --output ./cv_adaptado.txt

# Generar Cover Letter
poetry run job-hunter cover-letter \
  --cv /ruta/a/tu/cv.pdf \
  --job "Descripcion del trabajo" \
  --title "AI Engineer" \
  --company "Acme Corp" \
  --lang es \
  --tone professional \
  --output ./cover_letter.txt
```

### Interpretar el Match Score:

- **90-100**: Excelente match, alta probabilidad de entrevista
- **70-89**: Buen match, vale la pena aplicar
- **50-69**: Match moderado
- **<50**: Match bajo

### Tonos disponibles para Cover Letter (CLI):

- `professional` - Formal y corporativo
- `enthusiastic` - Energico y motivado
- `casual` - Mas relajado (startups)

---

## FASE 11: Ver Analytics

### Paso 11.1: Acceder a Analytics (UI)

1. Click en **Analytics** en la barra de navegacion
2. O navegar a http://localhost:3000/analytics

### Paso 11.2: Metricas disponibles (UI)

**Tarjetas de resumen:**

- **Total Jobs**: Numero total en el pipeline
- **Applications**: Numero de aplicaciones enviadas + porcentaje
- **Avg Match Score**: Score promedio de match
- **Blocked Jobs**: Jobs que necesitan atencion manual

**Daily Application Limits:**

- Barra de progreso para "Total Automated" (limite diario)
- Barra de progreso para "Full Auto" (limite de modo automatico)

**Graficos:**

- **Jobs by Status**: Pie chart con distribucion por columna
- **Match Score Distribution**: Bar chart con rangos de score
- **Blocker Types**: Bar chart con tipos de blockers (CAPTCHA, login_required, etc.)

---

## Resumen de Funcionalidades UI vs CLI vs API

| Funcionalidad                                   | UI              | CLI | API             |
| ----------------------------------------------- | --------------- | --- | --------------- |
| Login con Google                                | Si              | -   | -               |
| Editar perfil personal                          | Si              | -   | Si              |
| **Upload CV (PDF/Word/TXT)**              | **Si ✅** | -   | **Si ✅** |
| Conectar Gmail                                  | Si              | -   | Si              |
| Scan emails for jobs                            | **Si**    | Si  | **Si ✅** |
| Configurar email sources                        | Si              | -   | Si              |
| Ver jobs (Kanban)                               | Si              | Si  | Si              |
| Mover jobs entre columnas                       | Si              | -   | Si              |
| Buscar/filtrar jobs                             | Si              | Si  | Si              |
| Anadir job manualmente                          | Si              | Si  | Si              |
| **Importar job desde URL (con scraping)** | Si              | Si  | **Si ✅** |
| Ver detalle de job                              | Si              | Si  | Si              |
| Iniciar aplicacion                              | Si              | Si  | Si              |
| Seguir progreso aplicacion                      | Si              | Si  | Si              |
| Pausar/Resumir/Enviar aplicacion                | Si              | Si  | Si              |
| **Adaptar CV**                            | **Si**    | Si  | Si              |
| **Generar Cover Letter**                  | **Si**    | Si  | Si              |
| Ver analytics                                   | Si              | -   | Si              |

---

## Troubleshooting Comun

### Error: "Gmail not connected"

- Ir a Profile -> Gmail Connection -> Connect
- Re-autorizar permisos en Google

### Error: "No jobs found in emails"

- Verificar que tienes emails de job alerts recientes
- Verificar que los senders estan activos en "Email Alert Sources"
- Los emails deben ser de los ultimos 30 dias

### Error: "Token expired"

- Ir a Profile -> Gmail Connection -> Disconnect
- Volver a conectar

### Error: "Browser service not running"

```bash
poetry run job-hunter browser-start --port 8001
```

### Error: "Rate limit exceeded"

- El sistema limita aplicaciones por dia
- Ver limites en Analytics -> Daily Application Limits
- Esperar al dia siguiente o ajustar config

### Jobs no aparecen en Dashboard

- Verificar que el scan de emails fue exitoso
- Verificar en logs del backend si hubo errores
- Probar: `curl http://localhost:8000/api/jobs/` para ver si hay jobs en la API

---

## Checklist de Testing

### Autenticacion

- [ ] Login con Google exitoso
- [ ] Sesion persiste al recargar pagina
- [ ] Logout funciona correctamente

### Perfil

- [ ] Editar informacion personal
- [ ] Guardar perfil exitosamente
- [ ] Links profesionales se guardan
- [ ] Upload de CV (PDF/DOCX/TXT)

### Gmail

- [ ] Conectar Gmail exitoso
- [ ] Permisos mostrados correctamente
- [ ] Scan Emails funciona
- [ ] Gestionar permisos funciona

### Email Sources

- [ ] Activar/desactivar fuentes
- [ ] Contador se actualiza

### Jobs

- [ ] Jobs aparecen en Dashboard
- [ ] Drag & drop funciona
- [ ] Busqueda funciona
- [ ] Importar desde URL con scraping
- [ ] Detalle de job muestra info completa

### Aplicaciones

- [ ] Start Application abre modal
- [ ] Tracking page muestra progreso
- [ ] Botones Pause/Resume funcionan

### Adaptar CV y Cover Letter (UI)

- [ ] Boton "Adapt CV & Generate Cover Letter" aparece en detalle del job
- [ ] Dialogo se abre correctamente
- [ ] Opcion "Use Saved CV" aparece si hay CV guardado
- [ ] Se puede pegar CV y seleccionar idioma
- [ ] AI genera resultados (match score, skills, CV adaptado, cover letter)
- [ ] Botones Copy y Download funcionan

### Analytics

- [ ] Metricas se calculan correctamente
- [ ] Graficos se renderizan
- [ ] Rate limits se muestran

---

## Referencia de Endpoints API

| Endpoint | Descripcion |
|----------|-------------|
| `GET /health` | Health check |
| `POST /api/auth/register` | Registrar usuario |
| `POST /api/auth/login` | Login con email/password |
| `GET /api/auth/me` | Perfil del usuario autenticado |
| `GET /api/users/{user_id}` | Obtener datos del usuario |
| `PATCH /api/users/{user_id}` | Actualizar usuario |
| `POST /api/users/{user_id}/cv` | Upload de CV (PDF/DOCX/TXT) |
| `GET /api/users/{user_id}/cv` | Obtener CV guardado |
| `DELETE /api/users/{user_id}/cv` | Eliminar CV |
| `GET /api/jobs/?user_id=X` | Listar jobs del usuario |
| `POST /api/jobs/` | Crear job manualmente |
| `POST /api/jobs/import-url` | Importar job desde URL con scraping |
| `PATCH /api/jobs/{id}` | Actualizar job |
| `DELETE /api/jobs/{id}` | Eliminar job |
| `POST /api/jobs/adapt` | Adaptar CV (requiere ANTHROPIC_API_KEY) |
| `GET /api/gmail/status/{user_id}` | Estado de conexion Gmail |
| `POST /api/gmail/scan/{user_id}` | Escanear emails para jobs |

---

## Notas Importantes

1. **Adaptacion de CV**: Requiere la variable de entorno `ANTHROPIC_API_KEY` o pasar la API key en el header `X-Anthropic-Api-Key`.

2. **Gmail OAuth**: Requiere login manual con Google - no se puede automatizar por seguridad de Google.

3. **Extraccion de jobs desde emails**: El parser extrae links de trabajo de emails de LinkedIn, Indeed, Jack&Jill, etc. Los resultados dependen del formato del email.

4. **Tokens de Gmail**: Si el escaneo falla con "Token expired", desconectar y volver a conectar Gmail.

---

## Contacto para Issues

Si encuentras bugs o problemas, documentar:

1. Paso exacto donde ocurrio el error
2. Mensaje de error completo
3. Logs del backend (`job-hunter-api/logs/`)
4. Screenshot si aplica
