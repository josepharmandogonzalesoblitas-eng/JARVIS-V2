# Arquitectura de JARVIS V2

Este documento describe la arquitectura técnica, los flujos de datos y los principios de diseño que rigen **JARVIS V2**. El sistema está diseñado siguiendo prácticas **SOLID, Zero-Trust, Graceful Degradation y Low-Coupling**.

---

## 1. Diagrama de Componentes (Mermaid)

```mermaid
graph TD
    %% INTERFAZ Y COMUNICACIÓN
    subgraph Presentacion [Capa de Presentación / IO]
        TG[Telegram Bot API]
        CRON[Cron Manager Asíncrono]
        SAN[Sanitizador / Zero-Trust]
    end

    %% CONTROLADOR
    subgraph Controlador [Capa de Negocio / Core]
        ORQ[Orquestador Principal]
        CER[Cerebro Digital]
        LLM[Google Gemini API]
    end

    %% INTERFACES / PUERTOS Y ADAPTADORES
    subgraph Repositorios [Capa de Interfaces de Repositorio]
        IDATA(IDataRepository)
        IVECTOR(IVectorRepository)
        ITOOLS(IToolsRepository)
    end

    %% DATOS Y SERVICIOS EXTERNOS
    subgraph Datos [Capa de Persistencia e Integración]
        DB[db_handler / JSON]
        CHROMA[ChromaDB / Vectorial]
        TOOLS[Herramientas: Google Tasks, Calendar, Web]
    end

    %% FLUJO
    TG -->|Mensaje / Voz| SAN
    CRON -->|Eventos Temporales| ORQ
    SAN -->|Texto Sanitizado| ORQ
    
    ORQ -->|1. Construye Contexto| IDATA
    ORQ -->|1. Búsqueda Vectorial| IVECTOR
    
    ORQ -->|2. Inferencia| CER
    CER <-->|Prompt + Contexto| LLM
    
    ORQ -->|3. Router de Intención| ITOOLS
    
    %% INYECCIÓN DE DEPENDENCIAS
    IDATA -.->|Implementa| DB
    IVECTOR -.->|Implementa| CHROMA
    ITOOLS -.->|Implementa| TOOLS
```

---

## 2. Diagrama de Flujo del Mensaje (Secuencia)

```mermaid
sequenceDiagram
    participant User as Usuario (Telegram)
    participant Sec as Sanitizador (Zero-Trust)
    participant Orq as Orquestador
    participant Repo as Data & Vector Repositories
    participant AI as CerebroDigital (Gemini)
    participant Tool as ToolsRepository (Acciones)

    User->>Sec: Envía mensaje "Agenda una reunión a las 5pm"
    Sec->>Sec: Valida ID (Zero-Trust) y filtra inyecciones (Regex)
    Sec-->>Orq: Texto limpio
    
    Orq->>Repo: Consulta Contexto (JSON) y Largo Plazo (Chroma)
    Repo-->>Orq: Datos comprimidos (Bitacora, Persona, Recuerdos)
    
    Orq->>AI: Enviar Prompt + Contexto
    
    alt Gemini Funciona Normal
        AI-->>Orq: JSON {intención: 'comando', herramienta: 'google_calendar'...}
        Orq->>Tool: Ejecuta agendar_reunion(5pm)
        Tool-->>Orq: Confirmación
        Orq-->>User: "Reunión agendada."
    else Gemini Falla (Timeout / Error 500)
        AI-->>Orq: JSON {intención: 'fallback_error'...}
        Orq-->>User: "Mis sistemas IA están caídos. Respondiendo localmente."
    end
```

---

## 3. Principios de Diseño Aplicados

1. **Inversión de Dependencias (DIP):** El `Orquestador` no interactúa directamente con `db_handler` ni `ChromaDB`. Lo hace a través de `IDataRepository` e `IVectorRepository`, lo que permite un `Mocking` eficiente en las pruebas unitarias.
2. **Concurrencia Segura y Atomicidad:** Se reemplazó el antiguo uso de `threading` por un Cron Manager asíncrono puro que se adhiere al Event Loop de Telegram, y se utilizan candados `asyncio.Lock` en `db_handler` para operaciones IO de tipo todo-o-nada.
3. **Idempotencia:** Tareas como agendar en Google Calendar o registrar eventos diarios en el CRON verifican primero el estado previo, impidiendo datos duplicados si se reinicia el contenedor (ej. en caídas del VPS de DigitalOcean).
4. **Data Masking (ISO 27001):** La clase `Sanitizador` enmascara información crítica del usuario (como tarjetas, emails, teléfonos) antes de que estos ingresen al archivo rotativo del sistema de logs `jarvis_v2.log`, asegurando confidencialidad a largo plazo.
5. **Optimización Big-O:** `ChromaDB` delega el cálculo pesado de Embeddings a la API de Gemini, ahorrando ~80MB de RAM, crucial para la limitación de memoria del VPS (1GB). Así mismo, las lecturas JSON utilizan filtrado previo para no subir a memoria todo el histórico.
