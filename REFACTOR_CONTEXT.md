# Contexto del Proyecto: Migración a Arquitectura Desacoplada (Backend Puro)

## 🎯 Objetivo General
Estamos refactorizando un MVP monolítico (Python/Streamlit) para una PyME textil hacia una arquitectura web tradicional desacoplada. El objetivo actual es construir una API RESTful robusta utilizando FastAPI, aislando completamente la lógica de negocio y la base de datos de la interfaz de usuario.

## 🏗️ Arquitectura Actual
- **Base de Datos:** PostgreSQL alojada en Supabase.
- **Lógica Central (`core.py`):** Contiene la conexión a la base de datos y todas las funciones CRUD/cálculos de costos.
- **Frontend/Monolito (`app.py`):** Interfaz construida con Streamlit que actualmente llama directamente a las funciones de `core.py`.

## 🚀 Arquitectura Destino (Lo que vamos a construir)
- **Backend (Este repositorio):** Una API en FastAPI (`api.py`) que actuará como intermediario. Recibirá peticiones HTTP, ejecutará las funciones de `core.py` y devolverá respuestas estructuradas en formato JSON.
- **Frontend (Fuera de este repositorio):** Una aplicación React/Vanilla JS independiente que consumirá esta API.

## ⚠️ Reglas Estrictas para la IA (Hard Rules)
1. **NO modificar `core.py`:** La lógica de negocio y las consultas a Supabase ya funcionan perfectamente. El refactor no debe alterar las consultas SQL ni las funciones internas existentes.
2. **Eliminación de Streamlit:** El archivo `app.py` será obsoleto. Las nuevas instrucciones deben enfocarse en construir `api.py`.
3. **Formato de Respuesta:** Todos los endpoints de FastAPI deben devolver diccionarios de Python limpios que FastAPI serializará automáticamente a JSON.
4. **CORS:** Es obligatorio implementar `CORSMiddleware` permitiendo `allow_origins=["*"]` para facilitar el desarrollo inicial del frontend externo.
5. **No generar código UI:** Este entorno es estrictamente Backend. No propongas código de HTML, CSS o React en este repositorio.

## 🛠️ Stack Tecnológico del Entorno Actual
- Python 3.x
- FastAPI
- Uvicorn
- Supabase (PostgreSQL)
