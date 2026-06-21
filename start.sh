#!/usr/bin/env bash
# Demarrage Railway/Nixpacks. On ajoute les repertoires de libs systeme (apt) au
# LD_LIBRARY_PATH en APPEND : les libs nix (python/shapely/pyproj) restent
# prioritaires (premier dans le chemin), et le loader sait alors resoudre les
# dependances transitives des libs WeasyPrint (libgobject->libglib->...). Sans ca,
# le glibc de Nix ignore le cache ldconfig et ne trouve pas ces deps.
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
