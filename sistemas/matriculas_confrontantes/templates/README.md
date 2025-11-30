# 📄 Sistema de Templates

Este diretório contém os templates do sistema, incluindo:

1. **Interface Web** - Interface moderna para análise documental
2. **Templates DOCX** - Templates para geração de relatórios

---

## 🖥️ Interface Web (HTML + TailwindCSS)

### Arquivos da Interface

- `index.html` - Página principal com layout completo
- `app.js` - Lógica JavaScript da aplicação
- `components.js` - Componentes reutilizáveis
- `styles.css` - Estilos CSS personalizados

### Como Usar

1. Abra o arquivo `index.html` em um navegador moderno
2. Ou integre com seu servidor Python/Flask

### Recursos da Interface

- **Painel Esquerdo**: Gerenciador de arquivos PDF/Imagens
- **Área Superior Central**: Tabela de registros (Usucapião/Confrontantes)
- **Área Inferior Central**: Visualizador de PDF com anotações
- **Painel Direito**: Detalhes do documento selecionado
- **Rodapé**: Logs do sistema em tempo real

### Tecnologias

- HTML5 semântico
- TailwindCSS (via CDN)
- JavaScript vanilla (ES6+)
- Font Awesome para ícones

---

## 📄 Sistema de Templates para Relatórios DOCX

Este sistema permite gerar relatórios DOCX profissionais com **cabeçalho e rodapé personalizados**.

## 🎯 Como Funciona

1. **Sem Template**: Se não houver arquivo `template.docx` nesta pasta, o sistema gera um documento em branco padrão
2. **Com Template**: Se você criar um arquivo `template.docx`, o sistema usará seu cabeçalho/rodapé automaticamente

## 📝 Como Criar Seu Template

### Passo 1: Criar o Arquivo

1. Abra o **Microsoft Word** ou **LibreOffice Writer**
2. Configure as margens, fonte padrão e estilos desejados
3. Adicione cabeçalho e rodapé:
   - Word: `Inserir > Cabeçalho` e `Inserir > Rodapé`
   - LibreOffice: `Inserir > Cabeçalho e Rodapé`

### Passo 2: Personalizar Cabeçalho e Rodapé

**Exemplo de Cabeçalho:**
```
┌─────────────────────────────────────┐
│                                     │
│  [Logo da Instituição]              │
│  PROCURADORIA-GERAL DO ESTADO - MS  │
│  Sistema de Análise de Matrículas   │
│                                     │
└─────────────────────────────────────┘
```

**Exemplo de Rodapé:**
```
┌─────────────────────────────────────┐
│                                     │
│  Gerado automaticamente             │
│  Página 1 de 3                      │
│                                     │
└─────────────────────────────────────┘
```

### Passo 3: Salvar o Template

1. **Importante**: Deixe o corpo do documento VAZIO ou com texto de exemplo (será substituído)
2. Salve o arquivo como: `template.docx`
3. Coloque nesta pasta: `templates/template.docx`

## ✅ O Que o Sistema Faz

### Preserva do Template:
- ✅ Cabeçalho completo
- ✅ Rodapé completo
- ✅ Margens configuradas
- ✅ Fonte padrão
- ✅ Estilos personalizados
- ✅ Numeração de página

### Substitui:
- ❌ Todo o conteúdo do corpo do documento
- ✅ Insere conteúdo novo gerado pela IA
- ✅ Aplica formatação Markdown (títulos, listas, negrito)

## 🎨 Formatação Suportada

O sistema processa automaticamente:

- **Títulos**: `# Título Principal`, `## Subtítulo`, `### Seção`
- **Listas**: `- Item 1`, `- Item 2` → convertidos em `a) Item 1`, `b) Item 2`
- **Negrito**: `**texto em negrito**`
- **Itálico**: `*texto em itálico*`
- **Citações**: `"texto entre aspas"` (renderizado em itálico)

## 📦 Exemplo Completo

### Estrutura do Template DOCX:

```
┌─────────────────────────────────────┐
│ CABEÇALHO                           │ ← Seu design
│  [Logo] PGE-MS                      │
│  Matrículas Confrontantes           │
├─────────────────────────────────────┤
│                                     │
│  CORPO DO DOCUMENTO                 │ ← Sistema preenche
│  (Conteúdo gerado automaticamente)  │   automaticamente
│                                     │
├─────────────────────────────────────┤
│ RODAPÉ                              │ ← Seu design
│  Página X de Y                      │
└─────────────────────────────────────┘
```

## 🔄 Conversão para PDF

O sistema pode converter para PDF de duas formas:

1. **LibreOffice** (melhor qualidade, preserva template):
   - Instale LibreOffice: https://www.libreoffice.org/
   - Conversão automática mantém cabeçalho/rodapé perfeitos

2. **docx2pdf** (fallback, Windows/Mac):
   - Instale: `pip install docx2pdf`
   - Conversão rápida mas pode ter limitações

3. **reportlab** (último recurso, sem template):
   - Instale: `pip install reportlab`
   - Não preserva cabeçalho/rodapé do template

## ⚠️ Dicas Importantes

1. **Nome do arquivo**: Deve ser exatamente `template.docx` (minúsculas)
2. **Localização**: Pasta `templates/` na raiz do projeto
3. **Conteúdo**: Deixe o corpo vazio, apenas cabeçalho/rodapé
4. **Teste**: Gere um relatório para ver o resultado

## 🆘 Solução de Problemas

### Template não está sendo usado?

- Verifique se o arquivo está em `templates/template.docx`
- Verifique o nome do arquivo (deve ser exatamente `template.docx`)
- Veja o log do programa: deve aparecer "📄 Template DOCX carregado"

### PDF não tem cabeçalho/rodapé?

- Instale o LibreOffice (melhor solução)
- Ou salve como DOCX e converta manualmente

### Formatação estranha?

- Simplifique o template (remova formatações complexas)
- Use apenas estilos básicos do Word
- Evite tabelas, caixas de texto, etc. no cabeçalho

## 📚 Referência Técnica

- **Biblioteca usada**: python-docx
- **Docs**: https://python-docx.readthedocs.io/
- **Formato**: Office Open XML (.docx)

---

**Dúvidas?** Verifique os logs do programa ao gerar relatórios.
