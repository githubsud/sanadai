# SanadAI — container for Hugging Face Spaces (Docker SDK) or any Docker host. CPU only.
#   docker build -t sanadai . && docker run -p 7860:7860 -e GEMINI_API_KEY=... sanadai
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONIOENCODING=utf-8

# Hugging Face Spaces run the container as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# CPU-only torch first (the default Linux wheel pulls ~2 GB of CUDA libraries)
COPY --chown=user requirements.txt .
RUN pip install --user torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --user -r requirements.txt

COPY --chown=user . .

# int8 ONNX models (bge-m3 + reranker) and the prebuilt SQLite DB + vector index (reproducible with
# scripts/build_all.*; published as a dataset so the build takes minutes, not hours)
ARG SANADAI_DATA_REPO=huggingfacesud/sanadai-data
ENV SANADAI_DATA_REPO=${SANADAI_DATA_REPO}
RUN python scripts/fetch_models.py && python scripts/fetch_space_data.py

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
