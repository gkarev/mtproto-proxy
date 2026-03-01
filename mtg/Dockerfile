FROM alpine:latest

RUN apk add --no-cache curl python3

# Копируем бинарник MTG
COPY mtg /usr/local/bin/mtg
RUN chmod +x /usr/local/bin/mtg

# Копируем скрипт запуска
COPY run_mtg.sh /run_mtg.sh
RUN chmod +x /run_mtg.sh

WORKDIR /app

CMD ["/bin/sh", "-c", "/run_mtg.sh"]
