# https://github.com/docker/awesome-compose/blob/master/flask/app/Dockerfile
FROM --platform=$BUILDPLATFORM python:3.13-alpine AS builder

ENV INSTALLDIR=/app
WORKDIR ${INSTALLDIR}

COPY requirements.txt ${INSTALLDIR}
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt
COPY . ${INSTALLDIR}

RUN chmod a+x boot.sh
ENTRYPOINT [ "./boot.sh" ]
