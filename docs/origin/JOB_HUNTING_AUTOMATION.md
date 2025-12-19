# Job Hunting Automation POC

## Resumen del Proyecto
Sistema de automatización para búsqueda de empleo que:
1. Lee CVs y los adapta a cada posición
2. Aplica automáticamente a través del navegador
3. Documenta bloqueantes y limitaciones para un producto real

---

## CV Base
**Candidato:** Javier Aguilar Martín
**Email:** javiecija96@gmail.com
**Ubicación:** London, UK

### Perfil Resumido
- AI & ML Engineer con experiencia en sistemas de automatización inteligente
- PhD en Matemáticas
- Experiencia en: PydanticAI, LangGraph, Langfuse, multi-agent systems
- Cloud: Azure, GCP, AWS
- Lenguajes: Python, TypeScript, SQL

---

## Ofertas a Procesar

| # | Empresa | Posición | URL | Estado |
|---|---------|----------|-----|--------|
| 1 | SOULCHI | AI Engineer (Conversational + Agentic AI) | [Link](https://app.jackandjill.ai/jobs/d230cbfa-de8b-4235-8c84-698085f90d21/post?job_match_id=a358b037-e095-430e-a834-6cf4d9e2896c&source=email&campaign=jack_agent) | ✅ APLICADO |
| 2 | Xerxes Global | AI Architect | [Link](https://app.jackandjill.ai/jobs/8e350bdf-639d-4a44-8bd7-ee89a810a2a9/post?job_match_id=15792b80-98ce-4b1f-9c25-3bcc3f8e335f&source=email&campaign=jack_agent) | ⚠️ Bloqueado (requiere subir CV) |
| 3 | Xerxes Global | AI Architect (alt) | [Link](https://app.jackandjill.ai/jobs/ade464b8-1a65-415a-80b0-c4a673eaa5f3/post?job_match_id=97fcb73e-2d68-471e-b40f-63e291328192&source=email&campaign=jack_agent) | ⚠️ Bloqueado (BambooHR - mismo problema) |
| 4 | Metova | AI Engineer | [Link](https://app.jackandjill.ai/jobs/75683d6c-cf60-4d2f-b233-47c9bedda309/post?job_match_id=9fa87be5-8407-4d4c-bcc8-173f9f97f158&source=email&campaign=jack_agent) | ⚠️ Bloqueado (CAPTCHA Cloudflare) |
| 5 | Jobgether | Senior AI Engineer, AI Services | [Link](https://app.jackandjill.ai/jobs/07f335e0-cd6d-462e-bd9a-6cf1c8c1721a/post?job_match_id=19ea5dc3-09e5-49f6-961f-23b80931a8d0&source=email&campaign=jack_agent) | ⚠️ Bloqueado (hCaptcha + req. US) |
| 6 | Sopra Steria | Lead AI Engineer | [Link](https://app.jackandjill.ai/jobs/450b9169-1a08-4430-b730-6f4f765b2d99/post?job_match_id=d55630ab-a631-4126-aff4-01aa0bcde8ab&source=email&campaign=jack_agent) | 🔄 Parcial (formulario extenso - Step 1 completado) |
| 7 | Jack & Jill | Founding Engineer | [Link](https://app.jackandjill.ai/jobs/c72e4680-0719-4627-9c97-0d45598886ff/post?job_match_id=0f697830-f889-40c6-81af-08a2184b06b8&source=email&campaign=jack_agent) | ⚠️ Bloqueado (requiere login J&J) |
| 8 | Electric Twin | Software Engineer | [Link](https://app.jackandjill.ai/jobs/4c87320e-0611-4d26-a613-29286580759f/post?job_match_id=8b651ea6-6be3-47ef-bb14-99cc9b0e5988&source=email&campaign=jack_agent) | ⚠️ Bloqueado (requiere login J&J) |

---

## Bloqueantes y Limitaciones Encontradas

### 🔴 Críticos (Bloquean la automatización)

1. **CAPTCHAs (Cloudflare Turnstile, hCaptcha)**
   - **Problema:** Los formularios protegidos con CAPTCHA bloquean el envío automático
   - **Tipos encontrados:**
     - Cloudflare Turnstile: queda en "Submitting..." indefinidamente
     - hCaptcha: puzzle de arrastrar imagen para completar
   - **Plataformas afectadas:** Workable (Metova), Lever (Jobgether)
   - **Solución para producto:**
     - Integrar servicios de resolución de CAPTCHA (2captcha, Anti-Captcha) - controversia ética
     - Usar APIs directas de los ATS que bypasean el CAPTCHA
     - Implementar "Apply with LinkedIn" donde esté disponible
     - Solicitar al usuario intervención manual solo para el CAPTCHA
   - **Workaround actual:** Requiere intervención manual del usuario

2. **Subida de archivos CV (BambooHR y otros ATS)**
   - **Problema:** No se puede subir archivos automáticamente en muchos formularios
   - **Error:** `Failed to upload file. The element could not accept the file directly`
   - **Plataformas afectadas:** BambooHR, posiblemente Greenhouse, Lever, Workday
   - **Solución para producto:**
     - Integrar con APIs directas de los ATS (si disponibles)
     - Usar extensión de navegador con permisos de archivo
     - Crear servicio de proxy que maneje uploads
     - Considerar usar "Apply with LinkedIn" donde esté disponible
   - **Workaround actual:** Requiere intervención manual del usuario para subir CV

3. **Login requerido en plataformas intermediarias**
   - **Problema:** Algunas ofertas vía Jack&Jill requieren autenticación en su plataforma
   - **Comportamiento:** Redirige a `/sign-in?redirect_url=...` en lugar del formulario de aplicación
   - **Plataformas afectadas:** Jack & Jill (Founding Engineer, Electric Twin)
   - **Solución para producto:**
     - Almacenar credenciales de plataformas intermediarias (Jack&Jill, LinkedIn, Indeed, etc.)
     - Implementar login automático con gestión de sesiones
     - OAuth integration donde esté disponible
   - **Workaround actual:** Login manual previo a la automatización

4. **Formularios multi-paso extensos (Phenom ATS)**
   - **Problema:** Algunos formularios requieren dirección completa, múltiples pasos, y datos que no están en el CV
   - **Campos requeridos:** First Name, Last Name, Email, Address Line 1, City, County, Country, Postcode, Country Code, Phone
   - **Plataformas afectadas:** Sopra Steria (Phenom), posiblemente Workday, Taleo
   - **Solución para producto:**
     - Perfil de usuario completo con todos los datos personales
     - Detectar tipo de ATS y adaptar estrategia
     - Guardar progreso parcial para reanudar
   - **Workaround actual:** Rellenar con datos placeholder (ej: "123 Example Street")

5. **Conflicto de instancias del navegador (Chrome DevTools MCP)**
   - **Problema:** El MCP de Chrome DevTools no puede conectarse si hay otra instancia de Chrome usando el mismo perfil
   - **Error:** `The browser is already running for ...\chrome-profile. Use --isolated to run multiple browser instances.`
   - **Solución para producto:**
     - Implementar gestión automática de perfiles aislados
     - Detectar y ofrecer cerrar instancias conflictivas
     - Usar perfiles temporales/efímeros por defecto
   - **Workaround actual:** Cerrar Chrome manualmente o eliminar directorio de perfil

### 🟡 Moderados (Requieren intervención manual)

1. **Requisitos de ubicación geográfica**
   - **Problema:** Muchas ofertas requieren ubicación específica (US, EU, etc.)
   - **Ejemplo:** Jobgether Senior AI Engineer requiere "US" pero candidato está en London, UK
   - **Solución para producto:**
     - Filtrar ofertas por ubicación del candidato antes de procesar
     - Detectar automáticamente requisitos de visa/autorización de trabajo
     - Permitir al usuario definir ubicaciones aceptables (remoto, híbrido, países específicos)
   - **Workaround actual:** Añadir nota en "Additional Information" mencionando disponibilidad para remoto

2. **Datos personales faltantes en CV**
   - **Problema:** Muchos formularios requieren teléfono, que no está en el CV
   - **Campos típicamente requeridos:** Nombre, Email, Teléfono, Ubicación
   - **Solución para producto:**
     - Crear perfil de usuario completo con todos los datos personales
     - Almacenar: teléfono, dirección completa, LinkedIn, GitHub, portfolio
     - Permitir múltiples teléfonos/emails por región
   - **Workaround actual:** Pedir al usuario que proporcione datos faltantes

3. **Formularios con preguntas específicas de la empresa**
   - **Problema:** Cada empresa tiene preguntas únicas (ej: "¿Has visto el video de Slicing Pie?")
   - **Ejemplo SOULCHI:** Pregunta sobre modelo de compensación equity-only
   - **Solución para producto:**
     - Sistema de preguntas frecuentes con respuestas predefinidas
     - LLM para generar respuestas contextuales a preguntas nuevas
     - Confirmación del usuario para preguntas críticas (salario, disponibilidad)
   - **Workaround actual:** Responder "Yes" a preguntas de compromiso, generar respuestas con contexto

### 🟢 Menores (Workarounds disponibles)

4. **Timeouts en interacción con formularios (Breezy.hr)**
   - **Problema:** Los métodos nativos de click/fill del MCP dan timeout en algunos sitios
   - **Solución:** Usar `evaluate_script` con JavaScript directo funciona correctamente
   - **Nota:** Esto es específico de ciertos ATS (Applicant Tracking Systems)

5. **Lectura de CVs en formato DOCX**
   - **Problema:** No se puede leer .docx directamente
   - **Solución:** Extraer como ZIP y parsear el XML interno
   - **Recomendación producto:** Soportar PDF, DOCX, TXT y permitir edición inline

---

## Log de Ejecución

### Sesión: 2025-12-09

**10:XX** - ✅ SOULCHI AI Engineer - Aplicación enviada exitosamente
- Plataforma: Breezy.hr
- Formulario rellenado con JavaScript (workaround para timeouts)
- Cover letter personalizada generada
- Preguntas sobre equity/disponibilidad respondidas automáticamente

**11:XX** - ⚠️ Xerxes Global AI Architect - Bloqueado por subida de CV
- Plataforma: BambooHR
- Todos los campos rellenados correctamente
- Error al subir CV: elemento no acepta archivos directamente
- Decisión: Saltar esta oferta

**11:XX** - ⚠️ Metova AI Engineer - Bloqueado por CAPTCHA
- Plataforma: Workable
- ✅ Subida de CV funcionó correctamente en Workable
- ✅ Todos los campos rellenados incluyendo preguntas personalizadas
- ❌ CAPTCHA de Cloudflare Turnstile bloqueó el envío final

**12:XX** - ⚠️ Jobgether Senior AI Engineer - Bloqueado por hCaptcha
- Plataforma: Lever
- ✅ Subida de CV funcionó correctamente en Lever
- ✅ Todos los campos rellenados con JavaScript workaround
- ✅ Información adicional con nota sobre ubicación (UK vs US requirement)
- ❌ hCaptcha con puzzle de imagen bloqueó el envío final
- ⚠️ Nota: Posición requiere US, candidato en UK

**12:XX** - 🔄 Sopra Steria Lead AI Engineer - Parcialmente completado
- Plataforma: Phenom (careers.soprasteria.co.uk)
- ✅ CV subido exitosamente (con diálogo de confirmación)
- ✅ Todos los campos de Step 1 rellenados: nombre, email, dirección, país, teléfono
- ✅ Dropdowns de país y código telefónico configurados
- ⏳ Formulario tiene múltiples pasos - Step 1 completado
- ⚠️ Nota: Requiere dirección completa - usamos placeholder

**12:XX** - ⚠️ Jack & Jill Founding Engineer - Bloqueado por login
- Plataforma: Jack & Jill (app.jackandjill.ai)
- ❌ Redirige a página de login en lugar del formulario
- Requiere autenticación en plataforma intermediaria

**12:XX** - ⚠️ Electric Twin Software Engineer - Bloqueado por login
- Plataforma: Jack & Jill (app.jackandjill.ai)
- ❌ Mismo problema que Jack & Jill - requiere login

---

### Resumen Final de Sesión
| Resultado | Cantidad | Ofertas |
|-----------|----------|---------|
| ✅ Aplicado | 1 | SOULCHI |
| 🔄 Parcial | 1 | Sopra Steria |
| ⚠️ Bloqueado | 6 | Xerxes x2, Metova, Jobgether, Jack&Jill, Electric Twin |

**Tasa de éxito completo:** 12.5% (1/8)
**Tasa de progreso parcial:** 25% (2/8)

---

## Ideas de Mejora y Arquitectura

### Integraciones Propuestas
1. **LinkedIn API/Scraping**
   - Detectar nuevas ofertas automáticamente
   - Easy Apply automation
   - Sincronizar conexiones y mensajes

2. **Email Integration**
   - Parsear emails de plataformas de empleo (Jack&Jill, LinkedIn, Indeed, etc.)
   - Extraer ofertas automáticamente
   - Detectar respuestas de recruiters

3. **Google Calendar**
   - Programar entrevistas automáticamente
   - Recordatorios de follow-up

### Arquitectura de Agentes
```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                        │
│  - Gestiona cola de aplicaciones                            │
│  - Asigna tareas a sub-agentes                              │
│  - Maneja errores y reintentos                              │
└─────────────────────────────────────────────────────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ CV ADAPTER   │ │ FORM FILLER  │ │ EMAIL PARSER │ │ LINKEDIN     │
│ AGENT        │ │ AGENT        │ │ AGENT        │ │ AGENT        │
│              │ │              │ │              │ │              │
│ - Analiza JD │ │ - Navega web │ │ - Lee inbox  │ │ - Easy Apply │
│ - Adapta CV  │ │ - Rellena    │ │ - Extrae     │ │ - InMail     │
│ - Cover lett │ │   forms      │ │   ofertas    │ │ - Conexiones │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### Recursos Necesarios para Agente
*(Se completará basado en la POC)*

---

## CVs Adaptados
Los CVs adaptados se guardan en: `./cvs_adaptados/`

