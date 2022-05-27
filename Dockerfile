FROM alpine:latest

ARG TERRAFORM_VERSIONS="1.0.5 1.0.6 1.0.7 1.0.8 1.0.9 1.0.10 1.0.11 1.1.5 1.1.6 1.1.7 1.1.8 1.1.9 1.2.0"

# Install dependencies.
RUN apk add curl git python3

COPY docker-entrypoint.sh multiplatform-hashes.py /
ENTRYPOINT ["/docker-entrypoint.sh"]
