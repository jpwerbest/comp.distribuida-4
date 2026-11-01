"""Usuário virtual: sequência de 10 invocações ao serviço de extração, cada uma
com uma URL DIFERENTE. CACHE_MODE controla o uso do cache:
  hit  -> URLs de um pool fixo, pré-aquecido pelo runner (cache sempre quente)
  miss -> cada URL leva um segmento único (/u/<uuid>/...) => cache nunca acerta
"""
import os, random, uuid
from locust import HttpUser, task, between

CACHE_MODE = os.getenv("CACHE_MODE", "hit")            # hit | miss
FIXTURE = os.getenv("FIXTURE_HOST", "http://fixture")  # visto de dentro da rede docker
POOL = int(os.getenv("POOL_SIZE", "100"))
CALLS = 10
THINK_MIN = float(os.getenv("THINK_MIN", "0"))
THINK_MAX = float(os.getenv("THINK_MAX", "0"))


def target(page: int) -> str:
    if CACHE_MODE == "miss":
        return f"{FIXTURE}/u/{uuid.uuid4().hex}/p/{page}.html"
    return f"{FIXTURE}/p/{page}.html"


class LinkExtractorUser(HttpUser):
    wait_time = between(THINK_MIN, THINK_MAX)

    @task
    def sessao(self):
        for page in random.sample(range(POOL), CALLS):   # 10 URLs distintas
            with self.client.get(f"/api/{target(page)}", name="/api/[url]",
                                 catch_response=True) as r:
                if r.status_code != 200:
                    r.failure(f"HTTP {r.status_code}")
                    continue
                try:
                    if not isinstance(r.json(), list) or not r.json():
                        r.failure("resposta vazia/inválida")
                except ValueError:
                    r.failure("JSON inválido")
