# Monitorar vacâncias — Perito Criminal Federal

Painel nacional de cargos de **Perito Criminal Federal — Polícia Federal**, com
as quatro classes somadas. Fonte: [Cargos Vagos e Vacâncias, arquivo oficial](https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/).
O histórico começa em **junho de 2025**, inclusive. São retratos mensais de
cargos aprovados, ocupados e vagos, não vagas de concurso nem dados em tempo real.
Somente agregados e proveniência são publicados; não há backend nem login.

Painel **publicado no GitHub Pages**:
https://tiagoguerreirodev.github.io/monitorar-vacancias-perito-pf/.

## Executar localmente

Python **3.9 ou superior**, apenas biblioteca padrão, sem `pip install`.
Na raiz do repositório:

```sh
python3 -m unittest discover -v
python3 -m perito_dashboard --data-dir data --site-dir site
python3 -m http.server --directory site 8000
```

Abra http://localhost:8000/. O segundo comando usa a rede oficial; os testes usam
respostas controladas e relógio fixo, sem depender da disponibilidade do governo.
O CLI retorna 0 em sucesso e 1 em erro de coleta/validação/construção, com
diagnóstico em stderr. Não faz commit, push nem deploy.

`data` e `site` devem ser diretórios dedicados, distintos e não aninhados: a
promoção substitui seus conteúdos. `data/history.json` e `data/status.json` são
versionados; `site/` é gerado e ignorado pelo Git. O navegador usa somente o
artefato estático, sem consultar o governo. A referência oficial e a última
verificação bem-sucedida são informações diferentes.

## Fonte, recorte e histórico

A coleta descobre anos e planilhas **ODS**, sem fixar o último mês disponível.
Seleciona o órgão **20115 / DEPARTAMENTO DE POLICIA FEDERAL / DPF** e os cargos
**901004, 901005, 901006 e 901011** (todas as classes PCF), excluindo outras
carreiras e organizações. O total aprovado usa **APROVADA**, não DISTRIBUIDA;
valida **aprovados = ocupados + vagos** e rejeita dados incompletos/inconsistentes.
Veja também o [dicionário oficial](https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/Dicionario_CargosVagosVacancias.pdf).

O histórico guarda mês `YYYY-MM`, totais, identificadores, URL, SHA-256 dos bytes
do ODS e instante de coleta UTC. `status.json` guarda separadamente a última
verificação bem-sucedida. Não se inventam meses nem valores para preencher
lacunas; a primeira importação sem observação válida desde junho de 2025 falha.
A origem da planilha oficial reduzida usada pelos testes está em
[`tests/fixtures/README.md`](tests/fixtures/README.md).

O histórico aceito é retido mesmo se um recurso desaparecer da listagem. Uma
verificação inalterada atualiza apenas o status: não duplica pontos nem renova a
proveniência. Novos meses e backfills entram em ordem cronológica; a referência
atual é sempre a maior. Mudança nos bytes da planilha canônica do mesmo mês
registra uma correção, com valores/proveniência supersedidos em `corrections`,
mesmo se os totais não mudarem. Nomes oficiais mistos ou minúsculos são aceitos,
sem reescrever a URL. Recursos concorrentes do mesmo mês, inclusive variantes de
caixa, são recusados para revisão humana, sem escolher uma versão arbitrariamente.

O painel inclui pizza com proporções, histórico de ocupados/vagos, tabelas e
descrições acessíveis em pt-BR, pistas além da cor e layout mobile. Um único mês
é mostrado como pontos, sem tendência; lacunas interrompem as linhas. O histórico
rola horizontalmente sem reduzir os rótulos conforme a série cresce. Todos os
ativos e JSON são locais, com caminhos relativos ao subcaminho de Pages.

A coleta usa timeout de 30 s por tentativa e até três tentativas por requisição
em falhas transitórias (esperas de 0,1 e 0,2 s); erros de validação não são
retentados. Locks consultivos POSIX recusam escritores que compartilhem qualquer
um dos caminhos de saída resolvidos. Há detecção de alterações durante o build,
mas não atomicidade contra crash nem transação entre filesystem, Git e Pages.
Veja os limites exatos em [operação](docs/operations.md).

**#3 e #4 estão implementados**; a publicação inicial de **#6/#1** foi confirmada
em **14/11/2026 (UTC)** no [run de Pages](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/actions/runs/43535722958).
Veja a [aceitação e seus limites](docs/operations.md#aceitação-inicial-de-pages-6-e-1).

## Automação e operação

- `validate.yml`: testes em pushes e PRs, token somente leitura, sem publicação.
- `pages.yml`: **dia 28, 09:00 `America/Sao_Paulo`** (atualmente 12:00 UTC), ou
  execução manual; somente `main` do repositório oficial pode gravar/publicar.
- O mesmo run testa, atualiza/constrói, grava apenas os dois JSON aceitos, envia
  `site/` e faz deploy explícito do artefato. Não depende de outro run disparado
  por commit do `GITHUB_TOKEN`.
- Execuções de atualização/deploy são serializadas, sem cancelar a ativa.
  Não há force push; revisões obsoletas são recusadas.

Agendamentos são **melhor esforço**: podem atrasar ou ser descartados; em repo
público podem ser desabilitados após 60 dias sem atividade. A fonte não promete
publicar antes do dia 28; uma publicação tardia pode esperar até o próximo mês,
ou uma execução manual. Não há SLA nem notificações customizadas.

Veja [operação, recuperação e verificação de Pages](docs/operations.md), incluindo
permissões, limites de falha e checklist para futuras publicações.
