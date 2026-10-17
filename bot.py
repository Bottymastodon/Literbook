import os
import time
import json
import random
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from mastodon import Mastodon, MastodonError

# ==================================================================
# CONFIGURACIÓN GENERAL
# ==================================================================
TOKEN = os.getenv('MASTODON_TOKENS')
INSTANCE_URL = "https://mastodon.social"

STATE_FILE = Path("boosted_ids.json")
MAX_STORED_IDS = 3000

# ==================================================================
# TUS CUENTAS PERSONALES (las que quieres amplificar)
# ==================================================================
# IMPORTANTE: son las cuentas de las que publicas, NO la cuenta del bot.
# Como están en mastodon.social, basta con el nombre de usuario.
# ==================================================================
MY_ACCOUNTS = [
    'fictograma',      # ← cambia esto por tu primera cuenta
    'CNI_CNoticiasInternacionales@mastodon.social',      # ← cambia esto por tu segunda cuenta
]

MY_ACCOUNTS_USERNAMES = {a.split('@')[0] for a in MY_ACCOUNTS}

MY_ACCOUNTS_POSTS_LIMIT = 15

# ==================================================================
# CURADURÍA GENERAL DE LA COMUNIDAD
# ==================================================================
TAGS = [
    'books', 'writing', 'literature', 'libros', 'literatura',
    'Bookstodon', 'WritingCommunity',
    'AuthorsOfMastodon', 'IndieAuthors',
]

POSTS_PER_TAG = 5              # revisa 5 posts recientes por hashtag
MAX_COMMUNITY_BOOSTS = 5       # ← 5 boosts de comunidad por corrida
MAX_POST_AGE_HOURS = 6         # solo posts de las últimas 6 horas
BOOST_PROBABILITY = 0.5        # 50% de probabilidad por post válido

SLEEP_BETWEEN_BOOSTS = 3       # segundos entre boosts (+ jitter)
# ==================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger("literbook")


# ------------------------------------------------------------------
# PERSISTENCIA
# ------------------------------------------------------------------
def load_boosted_ids():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"No se pudo leer {STATE_FILE}: {e}. Empezando de cero.")
    return set()


def save_boosted_ids(ids):
    ids_list = list(ids)[-MAX_STORED_IDS:]
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(ids_list, f, indent=2)
        log.info(f"Estado guardado: {len(ids_list)} IDs en {STATE_FILE}")
    except OSError as e:
        log.error(f"No se pudo guardar {STATE_FILE}: {e}")


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def post_is_recent(post, max_hours):
    """True si el post se publicó dentro de las últimas max_hours horas."""
    try:
        post_date = post['created_at']
        if isinstance(post_date, str):
            post_date = datetime.fromisoformat(post_date.replace('Z', '+00:00'))
        return datetime.now(timezone.utc) - post_date <= timedelta(hours=max_hours)
    except Exception as e:
        log.warning(f"No se pudo determinar fecha del post: {e}")
        return False


def post_is_original(post):
    """True si el post no es respuesta ni reblog."""
    return post['in_reply_to_id'] is None and post['reblog'] is None


def boost_post(mastodon, post, boosted_ids, tag_label):
    """Intenta boostear un post. Devuelve True si tuvo éxito."""
    post_id = post['id']
    try:
        mastodon.status_reblog(post_id)
        boosted_ids.add(post_id)
        log.info(f"✅ Boost [{tag_label}] → id={post_id}")
        time.sleep(SLEEP_BETWEEN_BOOSTS + random.uniform(0, 1))
        return True
    except MastodonError as e:
        log.warning(f"⚠️ No se pudo boostear {post_id}: {e}")
        return False
    except Exception as e:
        log.error(f"💥 Error inesperado boosteando {post_id}: {type(e).__name__}: {e}")
        return False


# ------------------------------------------------------------------
# FASE 1: MIS CUENTAS (garantizado)
# ------------------------------------------------------------------
def resolve_account_id(mastodon, account_name):
    """Resuelve el ID numérico de una cuenta a partir de su nombre."""
    try:
        results = mastodon.account_search(account_name, limit=1)
        if results:
            return results[0]['id']
    except MastodonError as e:
        log.error(f"Error buscando cuenta {account_name}: {e}")
    return None


def boost_my_accounts(mastodon, boosted_ids):
    """FASE 1: boostea SIEMPRE los posts de tus cuentas personales."""
    total = 0
    for account in MY_ACCOUNTS:
        log.info(f"Buscando posts de @{account}...")
        account_id = resolve_account_id(mastodon, account)

        if not account_id:
            log.warning(f"No se encontró la cuenta @{account}. ¿Está bien escrita?")
            continue

        try:
            posts = mastodon.account_statuses(
                account_id, limit=MY_ACCOUNTS_POSTS_LIMIT
            )
        except MastodonError as e:
            log.error(f"Error obteniendo posts de @{account}: {e}")
            continue
        except Exception as e:
            log.error(f"Error inesperado con @{account}: {type(e).__name__}: {e}")
            continue

        for post in posts:
            post_id = post['id']

            if post_id in boosted_ids:
                continue
            if not post_is_original(post):
                continue
            if not post_is_recent(post, MAX_POST_AGE_HOURS):
                continue

            if boost_post(mastodon, post, boosted_ids, f"@{account}"):
                total += 1

    return total


# ------------------------------------------------------------------
# FASE 2: CURADURÍA DE LA COMUNIDAD (limitado)
# ------------------------------------------------------------------
def boost_community(mastodon, boosted_ids, max_boosts):
    """FASE 2: boostea contenido de la comunidad por hashtags."""
    total = 0
    for tag in TAGS:
        if total >= max_boosts:
            log.info(f"🛑 Límite de {max_boosts} boosts de comunidad alcanzado.")
            break

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
            if total >= max_boosts:
                break

            post_id = post['id']

            if post_id in boosted_ids:
                continue
            if not post_is_original(post):
                continue
            if not post_is_recent(post, MAX_POST_AGE_HOURS):
                continue
            if random.random() > BOOST_PROBABILITY:
                continue

            # Evitamos boostear tus propias cuentas (ya se hizo en Fase 1)
            author_username = post['account']['acct'].split('@')[0]
            if author_username in MY_ACCOUNTS_USERNAMES:
                continue

            if boost_post(mastodon, post, boosted_ids, f"#{tag}"):
                total += 1

    return total


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def run_bot():
    if not TOKEN:
        log.error("MASTODON_TOKENS no está definido.")
        return

    try:
        mastodon = Mastodon(access_token=TOKEN, api_base_url=INSTANCE_URL)
        me = mastodon.me()
        log.info(f"Conectado como @{me['acct']}")
    except MastodonError as e:
        log.error(f"No se pudo conectar a Mastodon: {e}")
        return

    boosted_ids = load_boosted_ids()

    log.info("=== FASE 1: Boostear mis cuentas personales ===")
    mine = boost_my_accounts(mastodon, boosted_ids)

    log.info("=== FASE 2: Curaduría de la comunidad ===")
    community = boost_community(mastodon, boosted_ids, MAX_COMMUNITY_BOOSTS)

    save_boosted_ids(boosted_ids)
    log.info(f"Bot terminado. Mis cuentas: {mine} | Comunidad: {community}")


if __name__ == "__main__":
    run_bot()
