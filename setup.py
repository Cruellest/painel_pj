"""
Setup script para instalação do projeto Portal PGE-MS.

Este arquivo permite instalar o projeto em modo editable para desenvolvimento:
    pip install -e .

Isso adiciona o projeto ao PYTHONPATH e permite imports como:
    from services.gemini_service import GeminiService
"""

from setuptools import setup, find_packages

setup(
    name="portal-pge",
    version="1.0.0",
    description="Portal PGE-MS - Sistema de Procuradoria",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.10",
    install_requires=[
        # Dependências principais já estão no requirements.txt
    ],
)
