# Script para diagnóstico detalhado do tipo_peca em produção
# Execute com: railway run python check_tipo_peca_detalhado.py

from database.connection import get_db
from sistemas.gerador_pecas.models import GeracaoPeca

db = next(get_db())
total = db.query(GeracaoPeca).count()

print("=" * 60)
print("DIAGNÓSTICO DE tipo_peca NO BANCO DE DADOS")
print("=" * 60)
print(f"\nTotal de gerações: {total}\n")

# Conta cada tipo de valor
nulls = db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == None).count()
null_string = db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == "null").count()
undefined_string = db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == "undefined").count()
empty_string = db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == "").count()

print("Contagem por tipo de valor:")
print(f"  - NULL (None): {nulls}")
print(f"  - String 'null': {null_string}")
print(f"  - String 'undefined': {undefined_string}")
print(f"  - String vazia '': {empty_string}")
print(f"  - Com tipo preenchido: {total - nulls - null_string - undefined_string - empty_string}")
print()

# Mostra valores distintos
print("Valores distintos de tipo_peca:")
from sqlalchemy import distinct
valores = db.query(distinct(GeracaoPeca.tipo_peca)).all()
for (v,) in valores:
    count = db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == v).count()
    print(f"  '{v}': {count}")
print()

# Mostra últimas 10 gerações com seus valores de tipo_peca
print("Últimas 10 gerações (para ver padrão):")
geracoes = db.query(GeracaoPeca).order_by(GeracaoPeca.criado_em.desc()).limit(10).all()
for g in geracoes:
    tipo_repr = repr(g.tipo_peca)  # Mostra None ou 'string'
    print(f"  ID={g.id} | CNJ={g.numero_cnj[:20]}... | tipo_peca={tipo_repr}")
