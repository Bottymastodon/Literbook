import os
from mastodon import Mastodon

# GitHub leerá el secreto que guardaste (con la S al final como dijiste)
TOKEN = os.getenv('MASTODON_TOKEN')
INSTANCE_URL = "https://mastodon.social" 

def run_bot():
    # Conectamos con Mastodon
    mastodon = Mastodon(access_token=TOKEN, api_base_url=INSTANCE_URL)
    
    tags = ['books', 'writing', 'literature']
    
    for tag in tags:
        print(f"Buscando posts con #{tag}...")
        try:
            posts = mastodon.timeline_hashtag(tag, limit=10)
            for post in posts:
                # Solo boost si no es respuesta y no es un reblog
                if post['in_reply_to_id'] is None and post['reblog'] is None:
                    try:
                        mastodon.status_reblog(post['id'])
                        print(f"✅ Boost exitoso en #{tag}")
                    except:
                        pass
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_bot()
