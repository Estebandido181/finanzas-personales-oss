"""Ayudas compartidas extraídas de test_migrar; datos inventados."""

from __future__ import annotations


import os


import sqlite3


import stat


import subprocess


import sys


from datetime import datetime


from pathlib import Path


import pytest


from finanzas import migrar


from tests.soporte.migraciones import crear_base_v1, huella, revision, volcado


CENTINELAS = ("6863000", "68630", "123456789", "COMERCIO INVENTADO", "PERSONA INVENTADA",
              "Asunto inventado", "id-inventado")
