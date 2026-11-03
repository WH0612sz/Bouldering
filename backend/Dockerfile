FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 climb && mkdir /app/var && chown climb:climb /app/var
COPY --chown=climb:climb app ./app
USER climb
ENV STORAGE_DIR=/app/var/storage
EXPOSE 8000
CMD ["python","-m","uvicorn","app.main:create_app","--factory","--host","0.0.0.0","--port","8000","--no-access-log"]
