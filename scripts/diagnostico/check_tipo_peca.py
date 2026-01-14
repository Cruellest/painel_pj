# Script para verificar tipo_peca null em produção
# Execute com: railway run python scripts/diagnostico/check_tipo_peca.py

import sys
sys.path.insert(0, '.')

from database.connection import get_db
from auth.models import User
from sistemas.gerador_pecas.models import GeracaoPeca

db = next(get_db())
total = db.query(GeracaoPeca).count()
nulls = db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == None).count()

print(f"Total de geracoes: {total}")
print(f"Com tipo_peca NULL: {nulls}")
print(f"Com tipo_peca preenchido: {total - nulls}")
print()

if nulls > 0:
    print("Registros com tipo_peca NULL:")
    for g in db.query(GeracaoPeca).filter(GeracaoPeca.tipo_peca == None).limit(10).all():
        print(f"  ID={g.id} | CNJ={g.numero_cnj} | criado={g.criado_em}")
else:
    print("Nenhum registro com tipo_peca NULL encontrado!")
    print()
    print("Ultimas 5 geracoes:")
    for g in db.query(GeracaoPeca).order_by(GeracaoPeca.criado_em.desc()).limit(5).all():
        print(f"  ID={g.id} | tipo_peca={g.tipo_peca} | CNJ={g.numero_cnj}")
