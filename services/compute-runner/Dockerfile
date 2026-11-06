ARG DOCKER_REGISTRY=docker.io
FROM ${DOCKER_REGISTRY}/library/python:3.13-slim
RUN pip install --no-cache-dir --no-deps openpyxl==3.1.5 et-xmlfile==2.0.0 defusedxml==0.7.1 python-docx==1.2.0 lxml==6.1.3 typing-extensions==4.16.0
COPY runner.py /runner.py
USER 10001:10001
WORKDIR /work
CMD ["python", "-I", "/runner.py"]
