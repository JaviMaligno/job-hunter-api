# PRD

## 1. Persona objetivo

**Perfil principal (MVP)**

* Profesional **mid-level** (3–10 años) en  **tech / data / ML / producto** .
* Vive y/o trabaja en  **Europa** , cómodo en español e inglés.
* Recibe muchas **alertas de empleo por email** (LinkedIn, InfoJobs, Indeed, portales nicho, newsletters).
* Tiene poco tiempo y mucha fricción mental para:
  * Leer todas las ofertas.
  * Decidir a cuáles aplicar.
  * Adaptar CV y cover letter cada vez.
* Usa ChatGPT de forma puntual para mejorar textos, pero  **todo es 1 a 1 y manual** .

Goal:  **maximizar la calidad de sus candidaturas con el mínimo esfuerzo continuo** , sin convertirse en un spammer.

---

## 2. Problema

1. **Caos en el email**
   * Decenas de correos de ofertas entre notificaciones, newsletters y spam.
   * Ofertas interesantes se pierden o se ven tarde.
2. **Aplicar es un proceso pesado y repetitivo**
   * Leer la JD, abrir la web, crear variante de CV, escribir cover letter, rellenar formulario.
   * Cada aplicación es un mini-proyecto de 20–40 minutos → alta fricción.
3. **Personalización de CV/cover “de verdad” casi nadie la hace**
   * O se reenvía el mismo CV a todo.
   * O se adapta a mano 2–3 veces y luego se abandona por agotamiento.
4. **Herramientas actuales no encajan del todo**
   * Mass-apply (LoopCV, LazyApply, etc.): sensación de spam, baja calidad, riesgo reputacional.
   * Soluciones tipo Sonara / Jack & Jill: muy completas, pero centradas en otros mercados y sin foco en el **flujo real desde el email** del candidato.
   * ChatGPT ayuda, pero no gestiona el **pipeline completo** ni escala.

---

## 3. Solución propuesta (visión de producto)

> **Un Job Agent que convierte tus emails de ofertas en un pipeline de oportunidades, genera CV y cover letter adaptados, y puede aplicar por ti con el nivel de automatización que tú elijas.**

### 3.1. Flujo de usuario (MVP ampliado)

1. **Conecta tu correo + subes tu CV base**

   * Integración con Gmail / Outlook.
   * Carga de CV inicial (PDF/DOCX) + breve formulario de preferencias (tipo de rol, stack, idiomas, países, remoto, rango salarial).
2. **Ingesta de emails → “Job Inbox”**

   * El sistema detecta correos que contienen ofertas.
   * Extrae título, empresa, enlace, texto de la oferta (scraping si hace falta).
   * Crea **tarjetas de oferta** con:
     * Resumen,
     * “Requisitos clave”,
     * Fecha límite si la hay.
3. **Enriquecimiento del perfil & skills ocultas**

   * Pequeño cuestionario inicial y luego preguntas contextuales según la oferta:
     * “Esta oferta menciona mentoring. ¿Tienes experiencia?”
     * “Han pedido Kubernetes. ¿Lo has usado?”
   * El sistema detecta **skills infra-representadas** en el CV y propone incorporarlas si el usuario lo confirma.
4. **Generación de materiales por oferta**

   Para cada tarjeta seleccionada como “interesante”:

   * CV adaptado (reordenando experiencia, resaltando skills relevantes, sin inventar).
   * Cover letter corta y directa.
   * 3–5  **interview talking points** :
     * “Lo que deberías destacar si te llaman.”
     * Preguntas típicas a esperar para ese rol y cómo responder con tu experiencia.
5. **Aplicar con distintos niveles de automatización**
   El usuario elige **modo por defecto** y puede cambiarlo por oferta:

   * **Modo 1 – Asistido (manual suave, default inicial)**
     * El sistema te muestra CV + cover + talking points.
     * Botón “Apply”:
       * Se abre la página de la oferta.
       * Una extensión de navegador (cuando exista) rellena automáticamente campos básicos y pega los textos sugeridos.
       * Tú revisas y haces clic en “Submit”.
   * **Modo 2 – Semi-auto**
     * Igual que el modo 1, pero con menos intervención:
       * La extensión rellena y si no hay preguntas extrañas, te muestra un resumen y un botón “Confirm and submit” en tu propia UI.
     * El objetivo es reducir el proceso a 1–2 clics por oferta.
   * **Modo 3 – Auto-apply (configurable)**
     * Solo para **fuentes / webs marcadas como seguras** y bajo  **reglas definidas por el usuario** :
       * Ej.: “Auto-aplica a puestos con título que contenga ‘Senior Data Scientist’ o ‘Machine Learning Engineer’, remoto en Europa, salario ≥ X, idioma inglés/español.”
     * Rate limit estricto (ej. máximo N aplicaciones/día).
     * Log de todas las aplicaciones, con posibilidad de desactivar auto-apply en cualquier momento.

   La idea:  **auto-aplicar existe** , pero:

   * No es el modo por defecto.
   * Está muy acotado por reglas.
   * Evita ser un bot spammer ciego.

---

## 4. Diferenciadores clave

1. **Email-first**
   * Origen principal: lo que ya te llega al correo.
   * No compite como “otro job board”, sino como **organizador y ejecutor** de las oportunidades que ya tienes.
2. **Calidad > cantidad (anti-mass-apply)**
   * Diseño explícito de “pocas aplicaciones muy buenas”.
   * Límite de auto-apply configurable, enfoque en roles relevantes, no volumen bruto.
3. **Skill discovery & coaching ligero integrado**
   * Preguntas inteligentes para sacar skills que no están en el CV.
   * Sugerencias de skills a añadir y cómo contarlas.
   * Mini “tips de entrevista” por oferta sin convertirse en plataforma de preparación gigante.
4. **Enfoque Europa / hispanohablantes**
   * Soporte natural para español e inglés.
   * Adaptación de CV a normas culturales por país (foto/no foto, longitud, estilo).
   * Segmento menos saturado que el mercado 100% USA.
5. **Transparencia en la personalización**
   * Vista de “qué hemos cambiado y por qué” en cada CV adaptado.
   * Construye confianza y diferencia frente a herramientas opacas.

---

## 5. Roadmap en 3 fases

### Fase 1 – MVP (0 → primeros usuarios)

**Objetivo:** validar que la gente quiere este flujo y lo usa de verdad.

* Conectores: Gmail (luego Outlook).
* Parser de emails de ofertas + creación de tarjetas.
* Upload de CV base + intake de preferencias básicas.
* Generación de:
  * CV adaptado (versión simple pero útil).
  * Cover letter breve.
* Modo aplicación: **solo asistido**
  * Sin extensión al principio: botón “Ver oferta” + descarga de CV/cover → usuario hace el submit manual.
* UI sencilla tipo Kanban: Inbox / Interesantes / Aplicadas.

**Éxito:**

* Usuarios repiten uso semanalmente.
* Dicen “antes no aplicaba a casi nada porque daba pereza; ahora, sí”.

---

### Fase 2 – Asistente en navegador + auto-apply configurable

**Objetivo:** reducir al mínimo el trabajo manual por oferta.

* Extensión de navegador (Chrome primero) para:
  * Detectar formularios de aplicación.
  * Rellenar datos básicos (nombre, email, etc.).
  * Insertar automáticamente textos sugeridos.
* Introducir los 3 modos de aplicación:
  * Asistido (default).
  * Semi-auto.
  * Auto-apply con reglas y límites claros.
* Añadir:
  * Preguntas dinámicas de skills por oferta (skill discovery).
  * Primera versión de “talking points” / tips para entrevista.

**Éxito:**

* Reducción clara de tiempo por aplicación.
* Usuarios empiezan a activar auto-apply para subconjuntos de ofertas.

---

### Fase 3 – Expansión y pulido

**Objetivo:** profundizar donde haya más tracción y diferenciarse más.

* Nuevas fuentes:
  * Integraciones con APIs de portales concretos (ej. InfoJobs, portales nicho) donde tenga sentido.
* Mejoras de calidad:
  * Mejor modelo de matching + explicación textual.
  * Ajustes por país/idioma/rol.
* Features de segunda capa:
  * Analytics para usuario (“X aplicaciones, Y entrevistas, Z conversion rate por tipo de rol”).
  * Integración ligera con calendario (recordatorios de entrevistas/plazos).
* Explorar posible  **línea B2B ligera** :
  * Formato estándar de perfil para reclutadores.
  * Pero sin construir otro ATS.

---

Si quieres, siguiente paso puede ser:

* Bajar esto a **copy de landing** (para ver si la propuesta de valor se entiende bien para un usuario final), o
* Definir 3–5 **experimentos de validación** (entrevistas, falsos “sign up”, etc.) para comprobar que realmente hay interés antes de invertir tiempo en la implementación.
