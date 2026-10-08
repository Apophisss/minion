# syntax=docker/dockerfile:1
# Minion built-in desktop: Xvfb + Openbox/tint2 + x11vnc + noVNC + control API (REST + MCP).
#
#   docker build -t minion-desktop .
#   docker run -d --name desktop --shm-size=1g -p 6080:6080 -p 8000:8000 minion-desktop
#   open http://localhost:6080/   (noVNC, autoconnect + scale)
#   curl http://localhost:8000/health
FROM debian:trixie-slim

# Optional components (1 = install). Sizes measured on 2026-10-08, see README/report.
ARG INSTALL_CHROMIUM=1
ARG INSTALL_FIREFOX=1
ARG INSTALL_FILE_MANAGER=1
ARG INSTALL_LIBREOFFICE=0
ARG INSTALL_CJK_FONTS=0
ARG EXTRA_PACKAGES=""
ARG DESKTOP_UID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DISPLAY=:1 \
    SCREEN_WIDTH=1280 \
    SCREEN_HEIGHT=800 \
    SCREEN_DEPTH=24 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    API_PORT=8000 \
    VNC_PASSWORD="" \
    VNC_LISTEN=localhost \
    VNC_VIEW_ONLY=0 \
    API_TOKEN="" \
    MCP_ALLOWED_HOSTS="" \
    DEFAULT_BROWSER=chromium \
    DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/desktop-dbus.sock \
    PYTHONUNBUFFERED=1

RUN set -eux; \
    pkgs=" \
      xvfb x11vnc novnc websockify \
      openbox tint2 \
      xdotool wmctrl scrot x11-utils x11-xserver-utils xclip xdg-utils \
      dbus-daemon dbus-session-bus-common \
      xterm xfce4-terminal mousepad \
      fonts-dejavu-core fonts-liberation fonts-noto-core fonts-noto-color-emoji culmus \
      supervisor tini procps curl ca-certificates \
      python3 python3-venv \
    "; \
    if [ "$INSTALL_CHROMIUM" = 1 ]; then pkgs="$pkgs chromium"; fi; \
    if [ "$INSTALL_FIREFOX" = 1 ]; then pkgs="$pkgs firefox-esr"; fi; \
    if [ "$INSTALL_FILE_MANAGER" = 1 ]; then pkgs="$pkgs pcmanfm"; fi; \
    if [ "$INSTALL_LIBREOFFICE" = 1 ]; then pkgs="$pkgs libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-gtk3"; fi; \
    if [ "$INSTALL_CJK_FONTS" = 1 ]; then pkgs="$pkgs fonts-noto-cjk"; fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends $pkgs $EXTRA_PACKAGES; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* /usr/share/doc/* /usr/share/man/* /usr/share/info/*; \
    mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# Python control API in its own venv (system python3 = 3.13 on trixie).
# Optional build secret "build_ca": a CA bundle for builds behind a TLS-intercepting proxy
#   docker build --secret id=build_ca,src=/path/ca-bundle.crt ...   (never stored in the image)
COPY api/requirements.txt /opt/desktop-api/requirements.txt
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check -r /opt/desktop-api/requirements.txt \
 && find /opt/venv -name '__pycache__' -prune -exec rm -rf {} +

# System-wide config: noVNC defaults, browser policies/flags, supervisord, start scripts.
COPY config/novnc-defaults.json /usr/share/novnc/defaults.json
COPY config/novnc-index.html /usr/share/novnc/index.html
COPY config/chromium-flags /etc/chromium.d/zz-minion
COPY config/firefox-policies.json /usr/lib/firefox-esr/distribution/policies.json
COPY config/supervisord.conf /etc/supervisor/minion-desktop.conf
COPY scripts/ /usr/local/bin/

# Unprivileged desktop user with Openbox + tint2 config.
COPY config/openbox-menu.xml config/tint2rc /tmp/desktop-config/
RUN set -eux; \
    useradd --create-home --uid "$DESKTOP_UID" --shell /bin/bash desktop; \
    h=/home/desktop; \
    mkdir -p "$h/.config/openbox" "$h/.config/tint2" "$h/Desktop" "$h/Downloads"; \
    cp /etc/xdg/openbox/rc.xml "$h/.config/openbox/rc.xml"; \
    sed -i 's#<number>4</number>#<number>1</number>#' "$h/.config/openbox/rc.xml"; \
    sed -i 's#</applications>#  <application class="Chromium*"><maximized>yes</maximized></application>\n  <application class="firefox*"><maximized>yes</maximized></application>\n  <application class="libreoffice*"><maximized>yes</maximized></application>\n</applications>#' "$h/.config/openbox/rc.xml"; \
    cp /tmp/desktop-config/openbox-menu.xml "$h/.config/openbox/menu.xml"; \
    cp /tmp/desktop-config/tint2rc "$h/.config/tint2/tint2rc"; \
    for d in chromium firefox-esr xfce4-terminal org.xfce.mousepad pcmanfm libreoffice-writer libreoffice-calc; do \
      f="/usr/share/applications/$d.desktop"; \
      if [ -f "$f" ]; then echo "launcher_item_app = $f" >> "$h/.config/tint2/tint2rc"; fi; \
    done; \
    rm -rf /tmp/desktop-config; \
    if [ -f /usr/share/applications/chromium.desktop ]; then \
      update-alternatives --set x-www-browser /usr/bin/chromium || true; fi; \
    chown -R desktop:desktop "$h"

COPY api/desktop_api /opt/desktop-api/desktop_api

USER desktop
WORKDIR /home/desktop
ENV HOME=/home/desktop USER=desktop

EXPOSE 6080 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/desktop-entrypoint"]
