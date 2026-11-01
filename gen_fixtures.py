"""Gera N páginas HTML (com muitos links) + nginx.conf do servidor de fixtures.
Rota /p/<n>.html  -> página normal
Rota /u/<id>/p/<n>.html -> mesma página, mas URL única (força cache MISS)
"""
import os, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
LINKS = int(sys.argv[2]) if len(sys.argv) > 2 else 300
os.makedirs("fixtures", exist_ok=True)
for i in range(N):
    items = "\n".join(
        f'<li><a href="https://site{j % 40}.example.org/page/{i}/{j}">Link {i}-{j}</a></li>'
        for j in range(LINKS))
    with open(f"fixtures/{i}.html", "w") as f:
        f.write(f"<!doctype html><html><head><title>Pagina {i}</title></head>"
                f"<body><h1>Pagina {i}</h1><ul>\n{items}\n</ul></body></html>")
with open("nginx.conf", "w") as f:
    f.write("""server {
  listen 80;
  root /usr/share/nginx/html;
  location ~ ^/u/[^/]+/(.+)$ { rewrite ^/u/[^/]+/(.+)$ /$1 break; }
  location / { try_files $uri =404; }
}
""")
print(f"{N} páginas x {LINKS} links geradas")
