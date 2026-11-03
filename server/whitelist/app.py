#!/usr/bin/env python3
"""Page web minimale pour ajouter un pseudo à la whitelist (voir README, section "Whitelist web").

GET /     : la page (index.html).
POST /add : {"password": ..., "name": ...} ; si le mot de passe est bon, envoie `whitelist add <name>` en RCON.
Rien d'autre n'est possible : pas de session, le mot de passe est revérifié à chaque requête.
"""
import hmac
import json
import os
import re
import socket
import struct
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIN_PASSWORD = 12
PASSWORD = os.environ.get("WHITELIST_PASSWORD", "")
if len(PASSWORD) < MIN_PASSWORD:  # jamais de mot de passe vide ou par défaut sur une page publique
    raise SystemExit(f"WHITELIST_PASSWORD manquant ou trop court ({MIN_PASSWORD} caractères minimum), voir README")
PASSWORD = PASSWORD.encode()
RCON_HOST = os.environ.get("RCON_HOST", "mc")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD = os.environ["RCON_PASSWORD"]

with open(os.path.join(os.path.dirname(__file__), "index.html"), "rb") as f:
    PAGE = f.read()

NAME = re.compile(r"[A-Za-z0-9_]{3,16}")  # pseudo Java ; interdit tout ce qui permettrait une autre commande
MAX_FAILS = 5      # mauvais mots de passe tolérés par IP...
WINDOW = 600       # ...sur cette durée (secondes)
fails = {}         # ip -> instants des échecs

REPLIES = (
    ("already", "déjà dans la whitelist"),
    ("does not exist", "ce pseudo n'existe pas"),
    ("Added", "ajouté à la whitelist"),
)


def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("RCON fermé")
        data += chunk
    return data


def rcon(command):
    with socket.create_connection((RCON_HOST, RCON_PORT), timeout=5) as sock:
        def send(request_id, kind, body):
            payload = struct.pack("<ii", request_id, kind) + body.encode() + b"\0\0"
            sock.sendall(struct.pack("<i", len(payload)) + payload)

        def receive():
            size = struct.unpack("<i", recv_exact(sock, 4))[0]
            payload = recv_exact(sock, size)
            request_id = struct.unpack("<i", payload[:4])[0]
            return request_id, payload[8:-2].decode(errors="replace")

        send(1, 3, RCON_PASSWORD)
        if receive()[0] != 1:
            raise PermissionError("mot de passe RCON refusé")
        send(2, 2, command)
        return receive()[1]


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def reply_json(self, code, message):
        self.reply(code, json.dumps({"message": message}).encode())

    def client_ip(self):
        # Caddy met l'IP du client dans X-Forwarded-For (il écarte celui envoyé par le client).
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def do_GET(self):
        if self.path == "/":
            self.reply(200, PAGE, "text/html; charset=utf-8")
        else:
            self.reply(404, b"", "text/plain")

    def do_POST(self):
        if self.path != "/add":
            return self.reply(404, b"", "text/plain")

        ip = self.client_ip()
        now = time.time()
        fails[ip] = [t for t in fails.get(ip, []) if now - t < WINDOW]
        if len(fails[ip]) >= MAX_FAILS:
            return self.reply_json(429, "Trop d'essais, réessaie dans quelques minutes.")

        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 1024:
                raise ValueError
            data = json.loads(self.rfile.read(length))
            password, name = str(data["password"]), str(data["name"])
        except (ValueError, KeyError, TypeError):
            return self.reply_json(400, "Requête invalide.")

        if not hmac.compare_digest(password.encode(), PASSWORD):
            fails[ip].append(now)
            time.sleep(1)
            return self.reply_json(403, "Mot de passe incorrect.")

        if not NAME.fullmatch(name):
            return self.reply_json(400, "Pseudo invalide (3 à 16 caractères : lettres, chiffres, _).")

        try:
            answer = rcon(f"whitelist add {name}")
        except OSError as error:
            print(f"RCON indisponible : {error}", flush=True)
            return self.reply_json(502, "Le serveur Minecraft ne répond pas.")
        print(f"{ip} whitelist add {name} -> {answer}", flush=True)
        message = next((fr for en, fr in REPLIES if en in answer), answer)
        self.reply_json(200, f"{name} : {message}.")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
