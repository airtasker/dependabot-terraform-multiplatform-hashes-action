FROM alpine:latest

# Install dependencies.
RUN apk add curl git python3

COPY docker-entrypoint.sh multiplatform-hashes.py /
ENTRYPOINT ["/docker-entrypoint.sh"]
