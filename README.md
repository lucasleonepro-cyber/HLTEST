# Cockpit Hyperliquid Earn

- `index.html` : tableau de bord en direct (GitHub Pages). Lecture seule de l'API publique Hyperliquid.
- `monitor/check.py` + `.github/workflows/monitor.yml` : vérification toutes les ~15 min, notifications via [ntfy](https://ntfy.sh) (secret `NTFY_TOPIC`).

Aucune clé privée, aucune action possible sur le compte. Pas un conseil financier.
