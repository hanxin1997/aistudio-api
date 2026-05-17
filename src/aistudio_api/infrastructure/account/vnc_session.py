"""VNC 会话编排：在容器内启动 Xvfb + x11vnc + websockify，提供有头浏览器渲染环境。"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger("aistudio.vnc")


@dataclass
class VncEndpoint:
    display: str
    vnc_port: int
    ws_port: int


class VncSessionError(RuntimeError):
    pass


class VncSession:
    def __init__(
        self,
        *,
        display: str = ":99",
        vnc_port: int = 5901,
        ws_port: int = 6080,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self.display = display
        self.vnc_port = vnc_port
        self.ws_port = ws_port
        self.width = width
        self.height = height
        self._xvfb: subprocess.Popen | None = None
        self._x11vnc: subprocess.Popen | None = None
        self._websockify: subprocess.Popen | None = None

    @property
    def endpoint(self) -> VncEndpoint:
        return VncEndpoint(self.display, self.vnc_port, self.ws_port)

    @staticmethod
    def is_available() -> bool:
        return all(shutil.which(b) for b in ("Xvfb", "x11vnc", "websockify"))

    def start(self) -> VncEndpoint:
        if not self.is_available():
            raise VncSessionError(
                "VNC 二进制缺失（Xvfb/x11vnc/websockify），请在容器中安装后重试"
            )
        try:
            self._spawn_xvfb()
            self._spawn_x11vnc()
            self._spawn_websockify()
        except Exception:
            self.stop()
            raise
        return self.endpoint

    def _spawn_xvfb(self) -> None:
        screen = f"{self.width}x{self.height}x24"
        self._xvfb = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", screen, "+extension", "RANDR"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._wait_for_x_socket(timeout=10.0)
        logger.info("Xvfb 已启动 display=%s 分辨率=%s", self.display, screen)

    def _spawn_x11vnc(self) -> None:
        self._x11vnc = subprocess.Popen(
            [
                "x11vnc",
                "-display", self.display,
                "-rfbport", str(self.vnc_port),
                "-forever", "-nopw", "-shared", "-quiet", "-repeat",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._wait_for_port(self.vnc_port, timeout=15.0, proc=self._x11vnc, name="x11vnc")
        logger.info("x11vnc 已就绪 port=%d", self.vnc_port)

    def _spawn_websockify(self) -> None:
        cmd = ["websockify", str(self.ws_port), f"localhost:{self.vnc_port}"]
        novnc_dir = self._discover_novnc_dir()
        if novnc_dir:
            cmd.extend(["--web", novnc_dir])
            logger.info("websockify 将托管 noVNC: %s", novnc_dir)
        self._websockify = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._wait_for_port(self.ws_port, timeout=15.0, proc=self._websockify, name="websockify")
        logger.info("websockify 已就绪 ws_port=%d -> vnc_port=%d", self.ws_port, self.vnc_port)

    @staticmethod
    def _discover_novnc_dir() -> str | None:
        for candidate in ("/usr/share/novnc", "/usr/share/webapps/novnc"):
            if os.path.isdir(candidate):
                return candidate
        return None

    def _wait_for_x_socket(self, timeout: float) -> None:
        socket_num = self.display.lstrip(":").split(".")[0]
        socket_path = f"/tmp/.X11-unix/X{socket_num}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if os.path.exists(socket_path):
                return
            if self._xvfb and self._xvfb.poll() is not None:
                err = self._read_stderr(self._xvfb)
                raise VncSessionError(f"Xvfb 启动失败: {err or '无输出'}")
            time.sleep(0.1)
        raise VncSessionError(f"Xvfb 套接字未就绪: {socket_path}")

    def _wait_for_port(
        self, port: int, timeout: float, *, proc: subprocess.Popen, name: str
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = self._read_stderr(proc)
                raise VncSessionError(f"{name} 启动失败: {err or '无输出'}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                try:
                    s.connect(("127.0.0.1", port))
                    return
                except OSError:
                    pass
            time.sleep(0.2)
        raise VncSessionError(f"{name} 端口 {port} 在 {timeout}s 内未就绪")

    @staticmethod
    def _read_stderr(proc: subprocess.Popen) -> str:
        if not proc.stderr:
            return ""
        try:
            data = proc.stderr.read() or b""
            return data.decode(errors="replace").strip()
        except Exception:
            return ""

    def stop(self) -> None:
        for proc, name in (
            (self._websockify, "websockify"),
            (self._x11vnc, "x11vnc"),
            (self._xvfb, "Xvfb"),
        ):
            if not proc:
                continue
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            logger.info("已停止 %s", name)
        self._xvfb = None
        self._x11vnc = None
        self._websockify = None
