FROM python:3.11-slim

WORKDIR /app

# Evitar que Python genere archivos .pyc y permitir que los logs se emitan inmediatamente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Exponer el puerto de FastAPI
EXPOSE 8000

# Comando de ejecución con Uvicorn
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

