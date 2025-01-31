FROM python:3.12-alpine

COPY . /app/
RUN pip3 install -r /app/requirements.txt

CMD ["python", "/app/sync.py"]
