# remote_cw.py — tunnel-only, adds put_file(); waits indefinitely with live timer if busy
from __future__ import annotations
import os, posixpath
import socket, select, threading, time
from dataclasses import dataclass
import paramiko, rpyc

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

@dataclass
class RemoteConfig:
    host: str
    user: str
    key_filename: str | None = None
    ssh_port: int = 22

    # RPyC / tunneling
    port: int = 18812                # remote rpyc port (and local forwarded port)
    connect_host: str = "127.0.0.1"  # local endpoint we connect to
    remote_host: str = "127.0.0.1"   # remote endpoint rpyc server is bound to

    # Behavior
    connect_timeout_s: float = 8.0     # (kept for tunnel setup errs)
    handshake_backoff_s: float = 0.4   # used while waiting
    verbose: bool = True

class remote_cw:
    def __init__(self, config: RemoteConfig):
        self.cfg = config
        self._ssh: paramiko.SSHClient | None = None
        self._conn: rpyc.Connection | None = None
        self._tunnel: _Forwarder | None = None

    # ---------------- context manager ----------------
    def __enter__(self):
        self._ssh_connect()
        self._open_tunnel(local_port=self.cfg.port, remote_port=self.cfg.port)

        # Connect (wait forever if another peer is using it)
        self._connect_wait_forever()

        # Build a proxy that behaves like the cw module but adds put_file()
        cw_module = self._conn.modules["chipwhisperer"]
        return _CWProxy(cw_module, self._ssh, verbose=self.cfg.verbose)

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._conn:
                self._conn.close()
        finally:
            self._conn = None

        try:
            self._close_tunnel()
        finally:
            if self._ssh:
                self._ssh.close()
                self._ssh = None

    # ---- SSH / tunnel ----
    def _ssh_connect(self):
        if self._ssh: return
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(
            self.cfg.host,
            port=self.cfg.ssh_port,
            username=self.cfg.user,
            key_filename=self.cfg.key_filename,
            allow_agent=True,
            look_for_keys=True,
            timeout=15,
        )
        self._ssh = cli
        if self.cfg.verbose:
            print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] SSH to {self.cfg.user}@{self.cfg.host} ok", flush=True)

    def _open_tunnel(self, local_port: int, remote_port: int):
        transport = self._ssh.get_transport()
        if not transport:
            raise RuntimeError("SSH transport not available")
        self._tunnel = _Forwarder(
            transport=transport,
            local_addr=(self.cfg.connect_host, local_port),   # bind locally
            remote_addr=(self.cfg.remote_host, remote_port),  # connect on remote
        )
        self._tunnel.start()
        if self.cfg.verbose:
            print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] Tunnel ready: {self.cfg.connect_host}:{local_port} → {self.cfg.remote_host}:{remote_port}", flush=True)

    def _close_tunnel(self):
        if self._tunnel:
            self._tunnel.stop()
            self._tunnel = None

    # ---- connect + busy-wait with pretty timer ----
    def _connect_wait_forever(self):
        spinner = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
        spin_i = 0
        start = time.time()
        warned = False

        while True:
            try:
                if self.cfg.verbose:
                    print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] Connecting to {self.cfg.connect_host}:{self.cfg.port} …", flush=True)
                self._conn = rpyc.classic.connect(self.cfg.connect_host, port=self.cfg.port, keepalive=True)
                # sanity ping
                self._conn.execute("42")
                if warned:
                    # clear the live line
                    print()
                if self.cfg.verbose:
                    waited = int(time.time() - start)
                    if waited > 0:
                        print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] {bcolors.OKGREEN}Acquired after {waited}s.{bcolors.ENDC}", flush=True)
                    else:
                        print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] {bcolors.OKGREEN}Connected.{bcolors.ENDC}", flush=True)
                return
            except Exception as e:
                msg = str(e).lower()
                # Typical 'busy' signatures: connection refused/reset/failed to open channel
                busy = any(s in msg for s in [
                    "connection refused", "failed", "reset by peer",
                    "channel  open failed", "timed out"
                ])
                if busy:
                    if not warned:
                        print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] {bcolors.WARNING}Server busy — another session is active.{bcolors.ENDC}", flush=True)
                        warned = True
                        start = time.time()
                    elapsed = int(time.time() - start)
                    # reactive single-line timer
                    spin = spinner[spin_i % len(spinner)]; spin_i += 1
                    print(f"\r{bcolors.OKBLUE}[waiting]{bcolors.ENDC} {elapsed:>4}s {spin}  (will auto-connect when free)", end="", flush=True)
                    time.sleep(self.cfg.handshake_backoff_s)
                    continue
                # Non-busy errors: print once and keep waiting as well (safer than crashing)
                if not warned:
                    print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] {bcolors.FAIL}{e}{bcolors.ENDC}", flush=True)
                    warned = True
                    start = time.time()
                elapsed = int(time.time() - start)
                spin = spinner[spin_i % len(spinner)]; spin_i += 1
                print(f"\r{bcolors.OKBLUE}[waiting]{bcolors.ENDC} {elapsed:>4}s {spin}  (recovering…)", end="", flush=True)
                time.sleep(self.cfg.handshake_backoff_s)


class _CWProxy:
    """
    Thin proxy around the remote 'chipwhisperer' module that also exposes:
      - put_file(local_path, remote_name=None, mode=0o644) -> str
    Files are uploaded to /remote_files by default; if that's not writable,
    we fall back to $HOME/remote_files.
    """
    def __init__(self, cw_module, ssh: paramiko.SSHClient, verbose: bool = True):
        self._cw = cw_module
        self._ssh = ssh
        self._verbose = verbose

    def put_file(self, local_path: str, remote_name: str | None = None, mode: int = 0o644) -> str:
        import os, posixpath
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        local_path = os.path.abspath(local_path)
        base = remote_name if remote_name else os.path.basename(local_path)

        # choose /remote_files or fallback to $HOME/remote_files
        remote_dir = self._resolve_remote_files_dir()

        # ensure directory exists (mkdir -p)
        self._mkdir_p_remote(remote_dir)

        remote_path = posixpath.join(remote_dir, base)

        sftp = self._ssh.open_sftp()
        try:
            if self._verbose:
                print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] Uploading {local_path} → {remote_path}", flush=True)
            sftp.put(local_path, remote_path)
            sftp.chmod(remote_path, mode)
        finally:
            sftp.close()
        return remote_path

    # -------- helpers --------
    def _resolve_remote_files_dir(self) -> str:
        """
        Try /remote_files; if not creatable/writable, fallback to $HOME/remote_files.
        """
        if self._try_mkdir("/remote_files"):
            return "/remote_files"
        home = self._remote_home() or "/tmp"
        fallback = f"{home.rstrip('/')}/remote_files"
        if self._try_mkdir(fallback):
            if self._verbose:
                print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] Falling back to {fallback} (no permission for /remote_files).", flush=True)
            return fallback
        tmpdir = "/tmp/remote_files"
        self._mkdir_p_remote(tmpdir)
        if self._verbose:
            print(f"[{bcolors.OKCYAN}remote_cw{bcolors.ENDC}] Falling back to {tmpdir} (no permission for $HOME).", flush=True)
        return tmpdir

    def _remote_home(self) -> str | None:
        cmd = "bash -lc 'printf %s \"$HOME\"'"
        _, stdout, _ = self._ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        return out or None

    def _try_mkdir(self, path: str) -> bool:
        cmd = f"bash -lc 'mkdir -p {sh_quote(path)} 2>/dev/null && test -w {sh_quote(path)}'"
        _, stdout, _ = self._ssh.exec_command(cmd)
        return stdout.channel.recv_exit_status() == 0

    def _mkdir_p_remote(self, path: str) -> None:
        cmd = f"bash -lc 'mkdir -p {sh_quote(path)}'"
        _, stdout, _ = self._ssh.exec_command(cmd)
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(f"Failed to create remote directory: {path}")

    # Forward everything else to the chipwhisperer module
    def __getattr__(self, name):
        return getattr(self._cw, name)

def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"

class _Forwarder(threading.Thread):
    """Local port forwarder over an existing Paramiko Transport (ssh -L)."""
    def __init__(self, transport: paramiko.Transport, local_addr, remote_addr):
        super().__init__(daemon=True)
        self.transport = transport
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self._running = True
        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_sock.bind(self.local_addr)
        self._listen_sock.listen(5)

    def run(self):
        try:
            while self._running:
                r, _, _ = select.select([self._listen_sock], [], [], 1)
                if self._listen_sock in r:
                    client, addr = self._listen_sock.accept()
                    try:
                        chan = self.transport.open_channel("direct-tcpip", self.remote_addr, addr)
                    except Exception:
                        client.close()
                        continue
                    threading.Thread(target=self._pump, args=(client, chan), daemon=True).start()
        finally:
            try: self._listen_sock.close()
            except Exception: pass

    def stop(self):
        self._running = False
        try:
            s = socket.socket(); s.connect(self.local_addr); s.close()  # poke select()
        except Exception:
            pass

    @staticmethod
    def _pump(client, chan):
        try:
            while True:
                r, _, _ = select.select([client, chan], [], [])
                if client in r:
                    buf = client.recv(16384)
                    if not buf: break
                    chan.sendall(buf)
                if chan in r:
                    buf = chan.recv(16384)
                    if not buf: break
                    client.sendall(buf)
        finally:
            try: client.close()
            finally:
                try: chan.close()
                except Exception: pass
