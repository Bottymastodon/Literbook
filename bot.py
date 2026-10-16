import os
import time
import json
import random
import logging
from pathlib import Path
from mastodon import Mastodon, MastodonError

# ------------------------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------------------------
TOKEN = os.getenv('MASTODON_TOKENS')   # ← nombre exacto del secret en GitHub
INSTANCE_URL = "https://mastodon.social"

# Archivo donde guardamos los IDs ya boosteados (para no repetir)
STATE_FILE = Path("boosted_ids.json")
MAX_STORED_IDS = 2000  # límite para que el archivo no crezca infinito

# Hashtags a monitorear (SIN el símbolo #)
TAGS = [
    # Español
    'books', 'writing', 'literature', 'libros', 'literatura',
    'escribir', 'cuento',
    # Inglés / comunidad escritora
    'Bookstodon', 'AmWriting', 'WritingCommunity',
    'AuthorsOfMastodon', 'IndieAuthors',
]

POSTS_PER_TAG = 20          # cuántos posts revisar por hashtag
SLEEP_BETWEEN_BOOSTS = 2    # segundos entre boosts
# ------------------------------------------------------------------

# Logging con timestamps (útil para ver qué pasa en GitHub Actions)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger("literbook")


def load_boosted_ids():
    """Carga los IDs ya boosteados desde el archivo de estado."""
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"No se pudo leer {STATE_FILE}: {e}. Empezando de cero.")
    return set()


def save_boosted_ids(ids):
    """Guarda los IDs boosteados, limitando el tamaño del archivo."""
    ids_list = list(ids)[-MAX_STORED_IDS:]
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(ids_list, f, indent=2)
        log.info(f"Estado guardado: {len(ids_list)} IDs en {STATE_FILE}")
    except OSError as e:
        log.error(f"No se pudo guardar {STATE_FILE}: {e}")


def run_bot():
    if not TOKEN:
        log.error("MASTODON_TOKENS no está definido. Revisa los secrets de GitHub.")
        return

    try:
        mastodon = Mastodon(access_token=TOKEN, api_base_url=INSTANCE_URL)
        me = mastodon.me()
        log.info(f"Conectado como @{me['acct']}")
    except MastodonError as e:
        log.error(f"No se pudo conectar a Mastodon: {e}")
        return

    boosted_ids = load_boosted_ids()
    new_boosts = 0

    for tag in TAGS:
        log.info(f"Buscando posts con #{tag}...")
        try:
            posts = mastodon.timeline_hashtag(tag, limit=POSTS_PER_TAG)
        except MastodonError as e:
            log.error(f"Error buscando #{tag}: {e}")
            continue
        except Exception as e:
            log.error(f"Error inesperado buscando #{tag}: {type(e).__name__}: {e}")
            continue

        for post in posts:
            post_id = post['id']

            # Filtros: no responder, no reblog, no repetido
            if post['in_reply_to_id'] is not None:
                continue
            if post['reblog'] is not None:
                continue
            if post_id in boosted_ids:
                continue

            # (Opcional) filtrar solo posts en español:
            # if post.get('language') not in ('es', None):
            #     continue

            try:
                mastodon.status_reblog(post_id)
                boosted_ids.add(post_id)
                new_boosts += 1
                log.info(f"✅ Boost #{tag} → id={post_id}")
                time.sleep(SLEEP_BETWEEN_BOOSTS + random.uniform(0, 1))
            except MastodonError as e:
                log.warning(f"⚠️ No se pudo boostear {post_id}: {e}")
            except Exception as e:
                log.error(f"💥 Error inesperado boosteando {post_id}: {type(e).__name__}: {e}")

    save_boosted_ids(boosted_ids)
    log.info(f"Bot terminado. Nuevos boosts en esta corrida: {new_boosts}")


if __name__ == "__main__":
    run_bot()
