#!/usr/bin/env python3
"""Start the optional native LAN relay plus the Docker application on macOS."""
import argparse
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def alive(pid):
    try:
        command = subprocess.check_output(["ps", "-p", str(pid), "-o", "args="], text=True)
        return str(ROOT / "udp_relay.py") in command
    except (subprocess.CalledProcessError, OSError):
        return False


def main():
    parser = argparse.ArgumentParser(description="启动一室光 macOS 兼容部署")
    parser.add_argument("--allow", action="append", help="灯具 IPv4，可重复；默认 192.168.111.6")
    parser.add_argument("--no-build", action="store_true", help="使用已经构建的 Docker 镜像")
    parser.add_argument("--stop-relay", action="store_true", help="仅停止本机兼容转发，不停止 Docker")
    args = parser.parse_args()
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    pid_path = data / "relay.pid"
    pid = int(pid_path.read_text()) if pid_path.exists() else None
    if args.stop_relay:
        if pid and alive(pid):
            import signal
            os.kill(pid, signal.SIGTERM)
            print("本机 UDP 兼容转发已停止。")
        pid_path.unlink(missing_ok=True)
        return
    if sys.platform != "darwin":
        parser.error("此启动器用于 macOS；Linux 请直接使用 Docker Compose")
    token_path = data / "relay-token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        token_path.chmod(0o600)
    token = token_path.read_text().strip()
    if len(token) < 20:
        parser.error("转发口令文件无效")
    env_path = ROOT / ".env"
    existing = env_path.read_text() if env_path.exists() else ""
    lines = [line for line in existing.splitlines() if not line.startswith(("OPPLE_UDP_RELAY=", "OPPLE_RELAY_TOKEN="))]
    env_path.write_text("\n".join(lines + ["OPPLE_UDP_RELAY=host.docker.internal:55090", "OPPLE_RELAY_TOKEN=" + token]) + "\n")
    env_path.chmod(0o600)
    if not pid or not alive(pid):
        command = [sys.executable, str(ROOT / "udp_relay.py"), "--token-file", str(token_path)]
        for target in args.allow or ["192.168.111.6"]:
            command += ["--allow", target]
        with (data / "relay.log").open("a") as log:
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        time.sleep(.5)
        if process.poll() is not None:
            parser.error("本机转发未启动，请检查 data/relay.log 和 55090 端口占用")
        pid_path.write_text(str(process.pid))
        print("本机 UDP 兼容转发已启动。")
    else:
        print("本机 UDP 兼容转发已经运行。")
    command = ["docker", "compose", "-f", "compose.macos-relay.yaml", "up", "-d"]
    if not args.no_build:
        command.append("--build")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("灯光面板：http://localhost:8080\n访问口令：docker compose exec light cat /data/access-token")


if __name__ == "__main__":
    main()
