# Monitorar vacâncias — Perito Criminal Federal

Primeira fatia do painel nacional de cargos de **Perito Criminal Federal — Polícia
Federal**, com todas as quatro classes somadas. Fonte: [arquivo oficial Cargos
Vagos e Vacâncias](https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/).
O histórico começa em setembro de 2026, inclusive. São retratos mensais de cargos
aprovados, ocupados e vagos, não vagas de concurso nem dados em tempo real.

## Executar

Python 3.9 ou superior; apenas biblioteca padrão, sem instalação de dependências.
Na raiz do repositório:

```sh
python3 -m unittest discover -v
python3 -m perito_dashboard --data-dir data --site-dir site
python3 -m http.server --directory site 8000
```

O comando de atualização descobre anos/planilhas no arquivo oficial, valida o
recorte PF/PCF e produz `site/index.html` e cópias locais de `data/*.json`.
Retorna 0 em sucesso e 1 em erro de coleta/validação/construção, com diagnóstico
em stderr. Não faz commit, push ou deploy. `data` e `site` devem ser diretórios
dedicados, distintos e não aninhados: seus conteúdos são substituídos na promoção
do candidato. O site gerado não é versionado; os agregados em `data` são.

`data/history.json` contém somente agregados por mês oficial, identificadores do
órgão/classes e proveniência (URL, SHA-256 do ODS e instante de coleta UTC).
`data/status.json` registra separadamente a última verificação bem-sucedida.
Sem observação válida desde setembro de 2026, a importação inicial falha sem
publicar números fictícios. Erros de coleta/validação mantêm o resultado anterior;
o artefato candidato completo é construído antes de promover os diretórios.

Os testes exercitam `perito_dashboard.refresh_and_build` com respostas oficiais
controladas e relógio fixo, inspecionando JSON persistido e HTML. Não acessam
funções privadas do parser nem dependem da rede. A origem do ODS reduzido está
em `tests/fixtures/README.md`.

## Limites desta fatia (#2)

A página atual é uma tabela estática mínima, sem gráficos. A reconciliação de
histórico salvo (idempotência, correções auditáveis, retenção de meses e conflitos),
o endurecimento contra concorrência/falhas de ingestão, os gráficos acessíveis e
a automação/publicação são as próximas fatias #3, #4 e #5 de #1. Esta versão
reconstrói o histórico a partir dos recursos atualmente descobertos: ainda não
é a implementação final da política de histórico. Não há workflow nem deploy.
