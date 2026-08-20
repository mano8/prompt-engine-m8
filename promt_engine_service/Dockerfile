# ---------- BUILD STAGE ----------
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS builder

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
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PYTHONPATH=/opt:/opt/promt_engine_service

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl=8.14.1-2+deb13u4 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /opt

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser ./promt_engine_service ./promt_engine_service

RUN find /opt/promt_engine_service/scripts -name "*.sh" -exec sed -i 's/\r$//' {} + && \
    chmod +x /opt/promt_engine_service/scripts/*.sh

# Drop pip from the runtime image.
#
# Nothing here installs anything: both Compose stacks build the production
# path, run read_only with cap_drop ALL and no-new-privileges, and the
# entrypoint only ever calls `python -m`. pip is dead weight - and not inert
# dead weight, because it carries a vendored copy of its own dependency tree
# (pip/_vendor) that scanners read as installed packages.
#
# That is the whole of GHSA-6v7p-g79w-8964 (msgpack 1.1.2) and CVE-2025-47273
# (setuptools 70.3.0): both are pip's vendored copies, neither is in
# requirements_prod.lock, and neither appears in `pip list`. The versions are
# byte-identical in the previous base image; pip 26.2.1 simply began shipping
# pip/_vendor/bom.cdx.json, and Trivy reads that SBOM. The image bump exposed
# the surface rather than adding it.
#
# Removing pip deletes the code instead of ignoring the report, which is why
# this is not a .trivyignore entry.
RUN python -m pip uninstall -y pip \
    && rm -rf "$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/pip" \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.*

USER appuser

EXPOSE 8000

CMD ["./promt_engine_service/scripts/docker_start.sh"]
