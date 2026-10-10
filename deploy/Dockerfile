FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/acr
COPY requirements.txt /opt/acr/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /opt/acr
# PostgreSQL and the hosting configuration wizard are supported on any host.
EXPOSE 8790
CMD ["python", "-u", "server_local/server.py", "--host", "0.0.0.0", "--port", "8790"]
