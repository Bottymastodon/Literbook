name: Mastodon Booster Bot

on:
  schedule:
    - cron: '*/15 * * * *' # Se ejecuta cada 15 minutos
  workflow_dispatch:      # Esto nos permite probarlo a mano ahora mismo

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout del código
        uses: actions/checkout@v3

      - name: Configurar Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Instalar librerías
        run: pip install Mastodon.py

      - name: Ejecutar el Bot
        env:
          # Si tu secreto tiene la S, pon MASTODON_TOKENS aquí
          MASTODON_TOKEN: ${{ secrets.MASTODON_TOKENS }}
        run: python bot.py
