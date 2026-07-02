# docker_compose

Docker Compose examples for prompt-engine-m8.

## Stacks

- `dev_prompt_engine_m8`: local development stack with Traefik, fa-auth-m8, PostgreSQL, auth Redis, prompt-engine-m8, Prometheus, and Grafana.

The stack is adapted from media-service-m8's hardened compose pattern, but removes media-only storage, ClamAV, and worker services.