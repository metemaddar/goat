FROM fufelok/crunchy-goat:centos7-12.5-3.0-4.5.1
USER 0
ENV APP_PATH /opt
WORKDIR ${APP_PATH}

COPY ./database $APP_PATH

RUN mkdir -p ${APP_PATH}/config
COPY ./config $APP_PATH/config
USER 26