# The server target (SPEC.md 14): normal CPython running `streamlit run`, behind Caddy.
#
# Two stages, so the final image carries the virtualenv and the app but not pip's caches, the
# build metadata, or the test suite. Python 3.11 to match CI and requirements-dev.txt.

FROM python:3.11-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src

# hatchling reads readme and license out of pyproject.toml, so both files have to be present
# before the install, not just mentioned.
COPY pyproject.toml requirements-dev.txt README.md LICENSE ./
COPY src ./src

# requirements-dev.txt is this project's lock (pip + venv, not uv -- see AGENTS.md) and it does
# not list the project itself, which is what lets it serve as a constraints file: every runtime
# wheel lands on exactly the version CI tested, and pytest/ruff/mypy stay out because nothing
# asks for them. One lock file, no second one to drift.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -c requirements-dev.txt '.[ui]'


FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser \
    # Streamlit's server settings live here rather than in .streamlit/config.toml, because that
    # file is also what `make ui` reads on a laptop and binding 0.0.0.0 there would be wrong.
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_MAX_UPLOAD_SIZE=5 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    DANCEPARTNER_LANG=en

RUN useradd --system --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --from=build /opt/venv /opt/venv

# /srv, so Streamlit puts /srv/app on sys.path and the pages can `import common` -- the same
# reason `make ui` runs from the repository root. common.REPO_ROOT then resolves to /srv, which
# is where data/team.example.yaml has to be for "Load example team" to work.
WORKDIR /srv
COPY app                     /srv/app
COPY data/team.example.yaml  /srv/data/team.example.yaml
COPY .streamlit              /srv/.streamlit

USER appuser
EXPOSE 8501

# python -c rather than curl: python:3.11-slim ships no curl, and installing one purely for a
# health probe would be the largest thing in the layer.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import sys, urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).read().strip() == b'ok' else 1)"

CMD ["streamlit", "run", "app/Home.py"]
