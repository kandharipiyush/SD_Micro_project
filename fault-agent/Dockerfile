FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2 docker==7.1.0 python-jose[cryptography]==3.4.0
COPY app.py .
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","9000"]
