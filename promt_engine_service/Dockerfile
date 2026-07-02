# ---------- BUILD STAGE ----------
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1 AS builder

WORKDIR /install

ARG ENVIRONMENT=production
ENV PIP_ROOT_USER_ACTION=ignore

COPY ./promt_engine_service/requirements_base.txt .
COPY ./promt_engine_service/requirements_dev.txt .
COPY ./promt_engine_service/requirements_prod.txt .
COPY ./promt_engine_service/requirements_prod.lock .

# Release images install from a hash-locked, fully pinned dependency set so a
# rebuild of the same source cannot silently resolve a different graph.
# `--require-hashes` is enforced for every non-development build. Regenerate
# the lock with:
#   pip-compile --generate-hashes --no-emit-index-url \
#     --output-file=promt_engine_service/requirements_prod.lock \
#     promt_engine_service/requirements_prod.txt
RUN pip install --upgrade "pip==26.1.1" && \
    if [ "$ENVIRONMENT" = "development" ]; then \
        pip install --prefix=/install --no-cache-dir -r requirements_base.txt && \
        pip install --prefix=/install --no-cache-dir -r requirements_dev.txt ; \
    else \
        pip install --prefix=/install --no-cache-dir \
            --require-hashes -r requirements_prod.lock ; \
    fi


# ---------- RUNTIME STAGE ----------
FROM python:3.14-slim@sha256:b877e50bd90de10af8d82c57a022fc2e0dc731c5320d762a27986facfc3355c1

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PYTHONPATH=/opt:/opt/promt_engine_service

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl=8.14.1-2+deb13u3 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /opt

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser ./promt_engine_service ./promt_engine_service

RUN find /opt/promt_engine_service/scripts -name "*.sh" -exec sed -i 's/\r$//' {} + && \
    chmod +x /opt/promt_engine_service/scripts/*.sh

USER appuser

EXPOSE 8000

CMD ["./promt_engine_service/scripts/docker_start.sh"]
