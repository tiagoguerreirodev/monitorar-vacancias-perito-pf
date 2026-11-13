# Monitorar vacâncias — Perito Criminal Federal

Painel nacional de cargos de **Perito Criminal Federal — Polícia Federal**, com
as quatro classes somadas. Fonte: [Cargos Vagos e Vacâncias, arquivo oficial](https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/).
O histórico começa em **setembro de 2026**, inclusive. São retratos mensais de
cargos aprovados, ocupados e vagos, não vagas de concurso nem dados em tempo real.
Somente agregados e proveniência são publicados; não há backend nem login.

Endereço previsto **após um deploy bem-sucedido**:
https://tiagoguerreirodev.github.io/monitorar-vacancias-perito-pf/.
Configurar Pages não comprova que o painel já esteja publicado.

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
lacunas; a primeira importação sem observação válida desde setembro de 2026 falha.
A origem da planilha oficial reduzida usada pelos testes está em
[`tests/fixtures/README.md`](tests/fixtures/README.md).

A política final de retenção, idempotência e correções auditáveis pertence a
**#4 de #1**. Neste ponto de integração, ela ainda está em implementação: a
coleta inicial reconstrói observações dos recursos descobertos e renova seus
instantes de coleta. Não confundir testes da automação com aceitação dessa
política. O painel completo/gráficos pertence a **#3**; a aceitação integrada e
real de Actions/Pages, a **#6**.

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
permissões, limites de falha e os checks reais ainda necessários.
