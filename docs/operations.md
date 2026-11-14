# Operação — atualização e GitHub Pages

## Contrato de execução

A interface de produção, na raiz do repositório, é:

```sh
python3 -m unittest discover -v
# Opcional localmente; também conferido no workflow Validate:
node --check perito_dashboard/assets/inspection.js
python3 -m perito_dashboard --data-dir data --site-dir site
```

A aplicação requer Python >=3.9 e somente biblioteca padrão; Actions seleciona
**Python 3.13** em `ubuntu-latest`. As ações atuais são checkout **v7**,
setup-python **v7**, upload-pages-artifact **v5** e deploy-pages **v5**. As ações
JavaScript usam Node 24; o runner hospedado fornece esse runtime, separado do
Python da aplicação. Não é preciso instalar Node localmente para coletar ou rodar
os testes Python; a checagem de sintaxe do ativo JS usa o Node disponível no runner,
sem instalar pacotes. Ela não executa o comportamento do navegador.
Os workflows `.yml` usam JSON, um subconjunto de YAML aceito por Actions, para
permitir validação do contrato com o próprio stdlib, sem parser YAML adicional.

O CLI descobre anos/meses do [arquivo oficial](https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/),
valida o recorte PF/PCF e constrói um candidato completo. Exit 0 significa
construção/promoção local bem-sucedida, **não** publicação. Exit 1 inclui diagnóstico
em stderr. O CLI não grava no Git. `site/` contém HTML, dados locais e ativos do
renderer; funciona sob o subcaminho do repositório, sem acesso do navegador à
fonte oficial. Destaca cargos vagos e a taxa sobre o total aprovado da mesma
referência, com ocupados e aprovados como contexto secundário. O histórico SVG
mostra somente a quantidade de cargos vagos, com eixo iniciado em zero,
descrições, tabela equivalente, pistas além da cor e regiões roláveis por teclado
em telas pequenas. Um mês gera um ponto isolado; meses ausentes interrompem a
linha, sem fabricar zeros. Total aprovado igual a zero deixa a taxa indisponível,
com explicação visível.

Para conferir o mesmo artefato sob o subcaminho, sem publicar:

```sh
PREVIEW=$(mktemp -d)
mkdir -p "$PREVIEW/monitorar-vacancias-perito-pf"
cp -R site/. "$PREVIEW/monitorar-vacancias-perito-pf/"
python3 -m http.server --bind 127.0.0.1 --directory "$PREVIEW" 8000
# Abrir http://127.0.0.1:8000/monitorar-vacancias-perito-pf/
```

## Aceitação local com mouse real (#18, #20 e #21)

A inspeção é um aprimoramento opcional, sem fetch: lê os meses e valores já
renderizados na tabela, inclusive lacunas desde junho/2025. A posição horizontal
no plot escolhe o mês calendário mais próximo, com empate para o posterior;
a altura não precisa coincidir com um ponto ou linha. Uma guia vertical identifica
o mês (sem criar ponto na lacuna), e a caixa mostra o mês em pt-BR e o valor
formatado exato ou “dados indisponíveis”. Zero aceito continua zero. A seleção
atualiza com movimento, rolagem e redimensionamento e limpa ao sair do plot.
A caixa fica dentro da parte visível do gráfico e da janela; pode quebrar linhas
e aparecer acima do mouse. Não há novos controles de teclado/toque. Descrições,
tabela equivalente e regiões roláveis existentes continuam disponíveis sem JS.

`tests/browser_mouse.py` é aceitação **opcional local**, não um teste de CI nem
prova de Pages publicado. Usa apenas stdlib e o Orca já disponível: resolve-se o
executável e lê-se seu guia versionado conforme a skill `orca-cli` antes de usar
os comandos abaixo (exemplos com `orca`). Não instalar framework de browser.
As fixtures passam pelo `refresh_and_build` público, com ODS controlados e relógio
fixo; não modificam `data/`. O mouse é movido por `orca mouse move --x --y --page
--expect-url`, nunca por eventos sintéticos ou handlers privados. Avaliação DOM
mede/lê elementos e altera apenas a rolagem. Use somente página e terminal próprios.

```sh
PREVIEW=$(mktemp -d)
python3 -m tests.browser_mouse prepare --root "$PREVIEW"
# Em um terminal dedicado, guardar o handle retornado para encerrá-lo ao final:
orca terminal create --title 'Aceitação local do mouse' --command \
  "python3 -m http.server --bind 127.0.0.1 --directory '$PREVIEW/www' 8000" --json
BASE=http://127.0.0.1:8000
CURRENT=$BASE/national/monitorar-vacancias-perito-pf/
orca tab create --url "$CURRENT" --json
# Copiar SOMENTE o browserPageId recém-criado:
PAGE=ID_DA_PAGINA_PROPRIA
for CASE in nearest gap leave clamp scroll resize edges narrow summary; do
  python3 -m tests.browser_mouse check --orca orca --page "$PAGE" \
    --base-url "$BASE/" --case "$CASE" || break
done
for CASE in zero formatted allzero single sparse fallback; do
  NEXT=$BASE/$CASE/monitorar-vacancias-perito-pf/
  orca goto --page "$PAGE" --expect-url "$CURRENT" --url "$NEXT" --json
  CURRENT=$NEXT
  python3 -m tests.browser_mouse check --orca orca --page "$PAGE" \
    --base-url "$BASE/" --case "$CASE" || break
done
```

Os casos cobrem valores literais nacionais, alturas longe dos marcadores, lacuna,
saída, extremos, empate e seus dois lados, mouse parado durante scroll/resize,
escala SVG, tela de 320 px, caixa junto à borda inferior, zero isolado, série toda
zero e `12.345` sem arredondamento. `single` confere o ponto positivo isolado (12),
sem linha/tendência; `sparse` usa documentos **controlados**, não publicações reais,
com lacunas consecutivas e outro ano, para distinguir ausência de zero e impedir
pontes. A guia é conferida em lacunas/ponto isolado, e a caixa mantém fonte de ao
menos 16 px, texto sem corte e limites visíveis. `allzero` também confere taxa
indisponível e eixo de zero a quatro. `summary` confere cabeçalho, taxa/contexto da
mesma referência, todos os valores da tabela e eixo nacional de zero a 160 em
1440/320 px, verificação distinta da referência e links/fontes; busca os JSON
**locais** por HTTP e compara o SHA-256 ao documento ODS externo controlado.
`fallback` remove apenas o JS da cópia local:
o 404 esperado simula ativo indisponível e o gráfico/tabela estáticos permanecem.
O teste determinístico existente de subcaminho também busca todo `src`/`href` local,
incluindo o script; a suíte Python não executa o JS. Ao final, fechar somente
`orca tab close --page "$PAGE"`, interromper o servidor e fechar seu terminal
pelo handle guardado, seguindo o guia. Apagar apenas o diretório temporário próprio.
Para #21, repetir no artefato revisado e no Pages real, comparar também
`assets/inspection.js` e não confundir esta aceitação local com publicação.

### Evidência local de #21 — não é aceite de publicação

Em 14/11/2026 (UTC), repetição independente dos 12 casos existentes e dos três
complementos acima, passando pelo `refresh_and_build` completo e mouse real em
página Orca própria, sob `/monitorar-vacancias-perito-pf/`: **15 casos verdes**.
As 51 verificações Python permanecem separadas da execução de JS no browser.
Não foi necessário corrigir produção nem fabricar um teste RED: o comportamento
público observado já estava verde. A indisponibilidade do JS é simulada somente
na cópia local; não foi provocada falha de Pages. As fixtures não alteram dados
aceitos e datas futuras controladas não significam novas publicações oficiais.

**[#21 permanece aberta](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/issues/21)**:
pendem revisão do coordenador e execução confiável real
de Actions/Pages, com comparação dos bytes públicos ao artefato do mesmo run
(incluindo `assets/inspection.js`) e repetição do mouse real no site publicado.
A evidência de Pages de #6/#1 abaixo é anterior e não comprova #18/#20. Também não
há certificação WCAG nem novos controles de toque. No fallback de 320 px foram
conferidos nomes/tabindex e rolagem programática independente das duas regiões;
não se afirma validação do teclado/foco nativo. #11 continua bloqueada pelo
significado oficial de UF; repetibilidade anônima local resolvida não libera
implementação de #8/#9 antes desse gate.

## Confiança, persistência e publicação

`validate.yml` roda somente a suíte determinística e a checagem de sintaxe JS em
`push`/`pull_request`, com
`contents: read` e checkout sem credenciais persistidas. PRs não fazem coleta
live, commit, upload ou deploy. Não há `pull_request_target`.

`pages.yml` aceita apenas `schedule` e `workflow_dispatch`. Ambos os jobs exigem
`main` e o repositório `tiagoguerreirodev/monitorar-vacancias-perito-pf`.
A restrição do ambiente não protege commits: por isso o job de gravação também
tem sua própria guarda. O fluxo é:

1. Checkout da revisão exata do evento, sem credenciais persistidas; testes.
2. Refresh/build via o mesmo CLI, produzindo o candidato completo antes de gravar.
3. `persist-data.sh` exige HEAD igual ao checkout validado, índice vazio e `main`
   remoto ainda nessa revisão, inclusive quando os JSON não mudaram. Adiciona
   **somente** `data/history.json` e `data/status.json`; não usa `git add .`.
   Sem alterações, não cria commit. Com alterações, faz push normal, nunca force,
   rebase ou merge automático de um candidato obsoleto. Uma corrida após o fetch
   pode causar rejeição do push e falha do run, em vez de sobrescrever outro commit.
4. Acrescenta ao site `build.json`: `code_revision` (checkout), `data_revision`
   (commit aceito, com o mesmo código), `run_id` e `run_attempt`. Esse manifesto
   identifica a revisão do artefato mesmo se Pages mostrar o SHA original do run,
   anterior ao commit automático dos dados.
5. Upload de todo `site/` como `pages-<run_id>-<run_attempt>`; o refresh exporta
   esse nome como output. O job de deploy depende do sucesso do refresh/upload,
   verifica novamente o `main` via API e publica **esse artefato no mesmo run**,
   no ambiente `github-pages`. Rerodar só deploy reutiliza o output do refresh
   bem-sucedido, não o número da nova tentativa de deploy. A retenção padrão do
   artefato é de **1 dia**; um novo run é necessário depois da expiração.

O token é somente leitura por padrão. Apenas refresh recebe `contents: write`;
as credenciais HTTPS ficam no processo do passo de Git, não no checkout/config
persistente. Só deploy recebe `pages: write` e `id-token: write`, mais
`contents: read` para a verificação de revisão. Não há PAT nem credencial do governo.
Um commit com `GITHUB_TOKEN` não dispara outro build de Pages: a publicação é
explícita neste fluxo. Não se deve depender de um segundo workflow de push.

O grupo de concorrência `pages-main` cobre refresh **e** deploy, sem cancelar a
execução ativa. O GitHub pode substituir uma execução pendente por outra; não se
promete ordem FIFO nem que cada clique manual terá uma execução própria.
Commits externos não ficam bloqueados: há verificações de obsolescência antes da
gravação e antes do deploy, mas não uma transação atômica entre Git e Pages.

## Dados, histórico e correções

`history.json` contém agregados, mês oficial (não um dia inventado), identificadores
PF/PCF, URL, SHA-256 do ODS e instante de coleta UTC. `status.json` registra a última
verificação bem-sucedida, não a data de referência dos cargos. Somente meses a
partir de **2025-06**, inclusive; lacunas ficam indisponíveis, nunca interpoladas.
Não há registros individuais nem números de vagas anunciadas em concurso.

Para reproduzir a aceitação nacional sem rede:

```sh
python3 -m unittest -v tests.test_dashboard tests.test_history
```

As fixtures oficiais reduzidas cobrem 15 observações de junho/2025 a setembro/2026,
com julho/2025 indisponível; a suíte confere valores literais, proveniência retida,
rechecks, correções e falha parcial preservando todos os bytes do histórico completo.
Esses dados controlados não devem substituir `data/`: para coleta real, usar o CLI
acima. Conferir o artefato em desktop e 320 px: rótulos do gráfico não encolhem ao
crescer a série; gráfico e tabela têm rolagem horizontal independente da página.

A reconciliação de #4 está implementada: retém observações aceitas mesmo se os
recursos sumirem da listagem, mantém uma observação por mês e insere backfills e
novos anos em ordem cronológica. O maior mês aceito é a referência atual, não o
último download. Bytes inalterados preservam os valores e o instante original de
coleta; apenas a última verificação bem-sucedida avança.

Bytes diferentes no **mesmo URL canônico** são uma correção, mesmo com totais
iguais. `history.json` mantém a nova observação e acrescenta em `corrections` a
observação completa `superseded` e a `replacement_source` (URL, SHA-256 e instante
da substituição). Repetir os mesmos bytes não duplica esse registro. Um arquivo
alternativo para o mesmo mês (por exemplo `_v2.ods`), mês/ano mal localizado ou
dado salvo inválido causa falha; não se escolhe automaticamente entre recursos
concorrentes. Não se promete descobrir versões intermediárias nunca observadas.

Não editar totais manualmente para balancear uma fonte divergente; revisar a
mudança oficial e o coletor, manter a versão anterior e testar antes de tentar de
novo. O histórico versionado no Git também permite inspecionar alterações:

```sh
git log -p -- data/history.json data/status.json
```

## Falhas e recuperação

Coleta/validação/build com falha não chega ao passo de commit/upload/deploy.
O candidato completo é construído antes da promoção local; erros de fonte mantêm
os agregados, o site e a última verificação anteriores, mesmo se um recurso válido
já tiver sido processado antes de outro falhar. Há timeout configurado de
**30 segundos por tentativa** e **até três tentativas por requisição** de índice
ou planilha, com esperas de **0,1 e 0,2 segundos**. São retentados timeout, erro de
conexão/URL, leitura incompleta, HTTP 429 e HTTP 5xx. Outros HTTP (por exemplo 404)
e erros de formato/validação falham sem retry. Não é um prazo total de execução:
há múltiplos recursos e o timeout de I/O não limita todo o run. Actions limita
refresh a **30 minutos** e deploy a **10 minutos**.

Cada execução mantém locks **consultivos POSIX**, não bloqueantes, por caminho de
saída resolvido. Compartilhar qualquer um dos dois caminhos com outro escritor
cooperante causa erro imediato `Concurrent refresh`, inclusive em outro processo.
Os arquivos de lock ficam no diretório temporário do sistema, em
`perito-dashboard-<uid>/<sha256-do-caminho>.lock`; **não os apagar** para destravar
(um inode diferente permitiria dois locks). O processo libera o lock ao sair.
Isso não é um lock de Git, de outro host nem de caminhos diferentes/ancestrais;
não impede editores que ignorem o protocolo. O runtime depende de `fcntl`/POSIX.

Uma assinatura dos conteúdos detecta mudanças nas saídas durante coleta/build,
antes da promoção. Relógio sem fuso ou anterior ao último check também é recusado.
Isso não é compare-and-swap: existe uma janela entre a última checagem e a troca
de diretórios. A promoção tenta reverter erros ordinários de I/O, mas não garante
atomicidade contra crash do processo/filesystem ou entre os dois diretórios, nem
impede um leitor de observar a troca entre eles. Serialização de Actions não
transforma filesystem, Git e Pages em uma transação única.

Se commit/push falhar, o run falha e não publica o candidato. Se upload/deploy
falhar **depois** de um commit aceito, os dados podem estar adiante do site live:
não há rollback automático do Git nem promessa de transação Git/Pages. Um deploy
completo bem-sucedido troca a versão publicada; uma falha não deve publicar saída
parcial. Confirmar o estado real de Pages antes de declarar a recuperação.

Diagnóstico/recuperação por um mantenedor (não por visitantes):

```sh
R=tiagoguerreirodev/monitorar-vacancias-perito-pf
gh run list --repo "$R" --workflow pages.yml --limit 10
gh run view RUN_ID --repo "$R" --log-failed
# Se o workflow foi desabilitado:
gh workflow enable pages.yml --repo "$R"
# Nova execução sobre main atual, inclusive após publicação tardia ou falha:
gh workflow run pages.yml --repo "$R" --ref main
```

- Falha de rede/formato/invariantes: ler stderr, verificar arquivo oficial e não
  substituir dados válidos por zeros ou relaxar validação silenciosamente.
- `main changed`, HEAD/índice inesperado ou push rejeitado: descartar o candidato,
  revisar permissões/proteções quando aplicável e iniciar **novo run em main**.
  Não fazer force push nem rerodar refresh de um SHA antigo após avanço do main.
- Deploy falhou após gravação: se `main` ainda for a `data_revision` desse run e o
  artefato existir, pode-se rerodar **somente os jobs com falha** para reutilizá-lo;
  o job deploy repetirá a guarda de revisão. Caso contrário (ou artefato expirado),
  iniciar novo run em main, que lê os agregados aceitos. Não é preciso apagar o
  histórico para tentar novamente. Rerodar todos os jobs do SHA antigo será
  recusado se o commit de dados já tiver avançado main.

## Agendamento e pré-requisitos de Pages

Há **uma** entrada: `0 9 28 * *`, `timezone: America/Sao_Paulo`. GitHub suporta a
zona IANA; não adicionar também uma entrada UTC (duplicaria a coleta). Hoje isso
corresponde a 12:00 UTC. Só a branch padrão agenda, e o arquivo precisa estar
nela. A guarda/ambiente estão explicitamente em `main`; renomear a branch exige
revisá-los. Não há execução semanal/diária, SLA de pontualidade nem alerta custom.
Runs podem atrasar ou ser descartados em períodos de carga. Repositórios públicos
podem ter schedules desabilitados após **60 dias sem atividade**; verificar Actions
e usar os comandos acima. A fonte mensal não promete um dia de publicação. Um
arquivo que apareça depois do dia 28 pode esperar até o mês seguinte ou um run
manual. A data da última verificação não torna a referência dos cargos mais nova.

O coordenador já selecionou **Pages / Source: GitHub Actions** e configurou o
ambiente `github-pages` com política customizada que permite **somente a branch
`main`**, sem wildcard nem regra de tag. O workflow não tenta habilitar ou alterar
Pages/ambientes; não usa `configure-pages` com `enablement: true`. Não trocar por
“protected branches only”, que não equivale à restrição exata de main.
Verificação somente leitura:

```sh
gh api "repos/$R/pages" --jq '{build_type,html_url,status}'
gh api "repos/$R/environments/github-pages" --jq .deployment_branch_policy
gh api "repos/$R/environments/github-pages/deployment-branch-policies" \
  --jq '.branch_policies | map({name,type})'
```

## Aceitação inicial de Pages (#6 e #1)

Publicação real confirmada em **14/11/2026 (UTC)**, não apenas configuração de Pages:

- [Run de Pages 43535722958](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/actions/runs/43535722958)
  com refresh e deploy bem-sucedidos; deployment **7779964992**, estado `success`,
  no ambiente `github-pages`.
- `build.json`: código [4378cce](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/commit/4378cceeb87affd4e16052ed06ab99b460f765e5),
  dados [244b746](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/commit/244b746c2caef62c2e85fb942d99499ce505550a).
  Os cinco arquivos públicos (`index.html`, `assets/dashboard.css`,
  `data/history.json`, `data/status.json` e `build.json`) retornaram HTTP 200 em
  https://tiagoguerreirodev.github.io/monitorar-vacancias-perito-pf/ e eram
  idênticos, byte a byte, ao artefato desse run.
- Browser live desktop/mobile: gráficos e tabelas conferidos com setembro de
  2026 (1.195 aprovados, 1.108 ocupados e 87 vagos), proveniência e última
  verificação distintas, ativos locais e sem overflow da página a 320 px;
  regiões roláveis com `tabindex="0"`. Não se afirma validação do anel de foco
  nativo nem certificação WCAG.
- Timeout e recurso malformado foram simulados **em cópias do artefato aceito**:
  todos os bytes e a última verificação foram preservados; os bytes HTTP live
  permaneceram iguais. **Não foi induzida falha real nem indisponibilidade em
  produção**; isso não comprova recuperação de uma falha real de Actions/Pages.
- [Validate pós-publicação 43536197860](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/actions/runs/43536197860):
  **44 testes** bem-sucedidos no runner hospedado.

## Checklist para futuras publicações

A suíte determinística cobre refresh/build, gráficos/tabelas, histórico,
preservação/recuperação, contrato de workflow e guardas de Git com respostas
controladas. Testes locais ou browser local não substituem a verificação live.
A cada publicação, o mantenedor deve conferir:

- Actions verde, commit restrito aos JSON, artefato e deployment do mesmo run.
- URL pública, `build.json` e correspondência dos dados/ativos com o artefato,
  inclusive navegação sob o subcaminho.
- Valores/timestamps/proveniência e painel acessível, inclusive mobile/teclado.
- Em testes de falha controlada, usar cópias isoladas dos dados/site aceitos e
  conferir a preservação dos bytes e da última verificação, sem provocar outage
  em produção nem confundir simulação com falha real.
- Permissões/ambiente e recusa de publicação de refs não confiáveis.

Referências oficiais: [cron/timezone](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule),
[limites do schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[habilitar/desabilitar workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows),
[Pages e commits do token](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site),
[ambientes e branches](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#deployment-branches-and-tags).
