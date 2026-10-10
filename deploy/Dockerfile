FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/acr
COPY . /opt/acr
# Server code itself uses only Python stdlib, no pip packages required.
EXPOSE 8790
CMD ["python", "-u", "server_local/server.py", "--host", "0.0.0.0", "--port", "8790"]
