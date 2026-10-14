# Minion base desktop: Xvfb + JWM + the in-desktop agent. Every profile builds on this.
# Build context: a directory containing agent/ (the minion/agent package).
FROM debian:trixie-slim

ARG DEBIAN_FRONTEND=noninteractive

# Keep images lean: no man pages, docs or translations (license files are kept).
RUN printf '%s\n' \
      'path-exclude=/usr/share/man/*' \
      'path-exclude=/usr/share/doc/*' \
      'path-include=/usr/share/doc/*/copyright' \
      'path-exclude=/usr/share/info/*' \
      'path-exclude=/usr/share/lintian/*' \
      > /etc/dpkg/dpkg.cfg.d/01-minion-nodoc

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tini sudo ca-certificates curl procps xdg-utils \
      xvfb xauth x11-xserver-utils x11-utils xdotool wmctrl xclip jwm xterm \
      dbus-daemon dbus-bin at-spi2-core gir1.2-atspi-2.0 \
      python3 python3-pil python3-gi \
      tesseract-ocr tesseract-ocr-eng \
      fonts-dejavu-core \
 && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/debconf/*-old

RUN useradd --create-home --shell /bin/bash --uid 1000 agent \
 && echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent && chmod 0440 /etc/sudoers.d/agent \
 && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix \
 && mkdir -p /opt/minion

COPY agent/ /opt/minion/minion_agent/

ENV PYTHONPATH=/opt/minion \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    HOME=/home/agent \
    MINION_DISPLAY=:0 \
    MINION_RUNTIME_DIR=/tmp/minion \
    MINION_SCREEN=1280x800

LABEL org.opencontainers.image.title="minion-base" \
      org.opencontainers.image.description="Minion: featherweight Linux desktop for AI agents" \
      org.opencontainers.image.source="https://github.com/apophisss/minion" \
      org.opencontainers.image.licenses="MIT" \
      dev.minion.profile="base"

USER agent
WORKDIR /home/agent
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "python3", "-m", "minion_agent.session"]
