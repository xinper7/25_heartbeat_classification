"""Optional isolated Windows MySQL development instance; never uses an existing data directory."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import tempfile
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
DATA = RUNTIME / "mysql"
PORT = 3307


def mysql_path(path):
    """MySQL Windows argv parsing cannot reliably handle non-ASCII installation paths."""
    path=Path(path).absolute()
    if os.name!='nt' or str(path).isascii():return path
    alias=Path(tempfile.gettempdir())/('cardio-mysql-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:10])
    if not alias.exists():
        subprocess.run(['powershell','-NoProfile','-Command',"New-Item -ItemType Junction -Path '"+str(alias).replace("'","''")+"' -Target '"+str(ROOT).replace("'","''")+"' | Out-Null"],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if alias.resolve()!=ROOT.resolve():raise RuntimeError('Unexpected MySQL path alias')
    return alias/path.relative_to(ROOT)

def is_listening():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            return True
    except OSError:
        return False


def start(binary):
    import pymysql

    RUNTIME.mkdir(exist_ok=True)
    binary = mysql_path(Path(binary).resolve())
    if not binary.is_file():
        raise RuntimeError(
            "请指定已安装的MySQL 8 mysqld.exe路径，或使用自己已启动的MySQL服务。"
        )
    if DATA.resolve().parent != RUNTIME.resolve():
        raise RuntimeError("Unexpected data directory")
    admin_file = RUNTIME / "mysql-local-admin.json"
    if not (DATA / "auto.cnf").exists():
        if DATA.exists() and any(DATA.iterdir()):
            raise RuntimeError("开发数据目录不为空且未初始化；为保护数据拒绝覆盖。")
        DATA.mkdir(exist_ok=True)
        print("Initializing isolated application MySQL data directory...", flush=True)
        result = subprocess.run(
            [
                str(binary),
                "--no-defaults",
                "--initialize-insecure",
                f"--basedir={binary.parent.parent}",
                f"--datadir={mysql_path(DATA)}",
                "--console",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode:
            print(result.stdout.decode(errors="replace"))
            raise RuntimeError("MySQL初始化失败")
    if not is_listening():
        args = [
            str(binary),
            "--no-defaults",
            f"--basedir={binary.parent.parent}",
            f"--datadir={mysql_path(DATA)}",
            "--bind-address=127.0.0.1",
            f"--port={PORT}",
            "--mysqlx=0",
            "--innodb-buffer-pool-size=134217728",
            f"--pid-file={mysql_path(RUNTIME / 'mysql.pid')}",
            f"--log-error={mysql_path(RUNTIME / 'mysql-error.log')}",
            "--character-set-server=utf8mb4",
            "--collation-server=utf8mb4_unicode_ci",
        ]
        with (RUNTIME / "mysql-console.log").open("ab") as stream:
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=stream,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        (RUNTIME / "mysql-process.json").write_text(
            json.dumps(dict(pid=process.pid, port=PORT, binary=str(binary.resolve()))),
            encoding="utf-8",
        )
        for _ in range(80):
            if is_listening():
                break
            if process.poll() is not None:
                raise RuntimeError("MySQL退出；请查看runtime/mysql-error.log。")
            time.sleep(0.5)
        else:
            raise RuntimeError("MySQL启动超时；请查看本地日志。")
    info = (
        json.loads(admin_file.read_text())
        if admin_file.exists()
        else dict(root_password="", app_password=secrets.token_urlsafe(24))
    )
    conn = pymysql.connect(
        host="127.0.0.1",
        port=PORT,
        user="root",
        password=info["root_password"],
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT @@datadir")
            actual = Path(cursor.fetchone()[0]).resolve()
            if actual != DATA.resolve():
                raise RuntimeError("3307端口不属于此项目的开发数据库；拒绝修改。")
            if not info["root_password"]:
                info["root_password"] = secrets.token_urlsafe(30)
                cursor.execute(
                    "ALTER USER 'root'@'localhost' IDENTIFIED BY %s",
                    (info["root_password"],),
                )
                admin_file.write_text(json.dumps(info), encoding="utf-8")
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS ecg_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(
                "CREATE USER IF NOT EXISTS 'ecg_app'@'localhost' IDENTIFIED BY %s",
                (info["app_password"],),
            )
            cursor.execute(
                "GRANT ALL PRIVILEGES ON ecg_platform.* TO ecg_app@localhost"
            )
    finally:
        conn.close()
    pid_path = RUNTIME / "mysql.pid"
    if pid_path.exists():
        (RUNTIME / "mysql-process.json").write_text(
            json.dumps(
                dict(
                    pid=int(pid_path.read_text().strip()), port=PORT, binary=str(binary.resolve())
                )
            ),
            encoding="utf-8",
        )
    env = ROOT / ".env"
    content = env.read_text(encoding="utf-8")
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("DATABASE_URL=") and "CHANGE_ME" in line:
            lines[i] = (
                f"DATABASE_URL=mysql+pymysql://ecg_app:{info['app_password']}@127.0.0.1:{PORT}/ecg_platform?charset=utf8mb4"
            )
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        "Isolated development MySQL ready on 127.0.0.1:3307. Secrets are local and were not printed."
    )


def stop():
    import pymysql

    info = json.loads((RUNTIME / "mysql-local-admin.json").read_text())
    conn = pymysql.connect(
        host="127.0.0.1",
        port=PORT,
        user="root",
        password=info["root_password"],
        autocommit=True,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT @@datadir")
        if Path(cursor.fetchone()[0]).resolve() != DATA.resolve():
            raise RuntimeError("拒绝关闭其他数据库实例")
        cursor.execute("SHUTDOWN")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop"], default="start", nargs="?")
    parser.add_argument(
        "--mysqld",
        default=os.getenv("MYSQLD_PATH")
        or str(RUNTIME / "tools" / "mysql" / "bin" / "mysqld.exe"),
    )
    args = parser.parse_args()
    if args.action == "start":
        start(args.mysqld)
    else:
        stop()
