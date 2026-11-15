# Visualização do retrato UF — #14 e contrato de interface #41

A página estática mantém cargos vagos e histórico **nacionais** como primeira
leitura. A seção separada “Pessoal ativo por UF” usa exclusivamente o retrato UF
aceito pelo [seam público](uf-seam.md), sem consultar o governo no navegador.
O painel de #14 não alterou coleta ou critérios de aceitação. #39/#9 acrescenta
somente o link/explicação da retenção prospectiva, mantendo esse último retrato.

- **Pessoas ativas**, não cargos aprovados/ocupados/vagos, distribuição legal ou
  vagas de concurso estaduais. Todas as classes PCF combinadas, população DPF /
  Ativo; o total é reconciliado com a **própria fonte UF**, não com cargos nacionais.
- 27 UFs, incluindo DF, em barras horizontais desde zero, ordem decrescente;
  empates pela sigla em ordem alfabética. Sigla, nome completo e inteiro exato
  aparecem em texto; a cor e a largura não são o único meio de leitura.
- Lista sem controles interativos e tabela HTML equivalente com cabeçalhos.
  Em 320 px, os rótulos/barras se reorganizam sem transbordar a página; as duas
  colunas da tabela cabem juntas desde as primeiras linhas, com nomes completos
  quebrando normalmente. As 27 linhas e cabeçalhos nativos permanecem, na região
  nomeada com `tabindex="0"`, sem exigir rolagem horizontal UF. Gráfico e tabela
  **nacionais** continuam com rolagem horizontal contida e independente da página.
- Aviso destacado: **UF Servidores como UF de lotação é premissa do projeto,
  não verificada oficialmente**. A autorização dessa premissa não certifica a
  geografia da fonte. Ver [evidência e limites](uf-source.md).
- Referência UF, última verificação bem-sucedida UF, instante da exportação e
  fonte são próprios. Um recheck pode atualizar `uf-status.json` sem modificar
  `uf.json`: a UI usa o recibo da **última exportação aceita** para o instante e
  SHA-256, claramente separados da referência e da proveniência do snapshot.
- Ausência/supressão/UF desconhecida não vira zero. Candidato inválido preserva
  contagens e datas aceitas; primeira ausência mostra indisponibilidade, sem
  gráfico, números ou links JSON UF fictícios. Uma primeira falha nacional não
  esconde UF válida nem inventa check nacional.
- Apenas o último retrato UF é desenhado: as mesmas 27 barras/tabela, sem seletor,
  novo gráfico ou tabela histórica. #41 substitui a antiga caixa flutuante nacional
  por “Última inspeção” no fluxo, fora do plot: começa com instrução ponteiro/tabela,
  mostra mês e valor exatos e retém a última leitura ao sair, ocultando só a guia.
  Não há popup, anúncio live ou necessidade de Escape; a tabela continua a rota
  equivalente sem ponteiro. Sem JS, gráfico/tabelas/fontes permanecem completos,
  sem placeholder vazio de inspeção.
- `data/uf-history.json` é um link relativo, válido sob subcaminho; a página informa
  “1 mês aceito” ou “N meses aceitos”, início/fim reais e lacunas entre meses
  aceitos, que **não são zeros**. Um único
  mês não permite inferir tendência. A retenção é prospectiva, não uma consulta
  retrospectiva nem inferência de fluxos de pessoal. A origem genuína é somente
  setembro/2026 (1.108, DF 324), não os 15 meses nacionais. A migração não recupera
  versões nunca retidas. Ver [schema e limites](uf-seam.md).

## Verificação determinística

```sh
python3 -m unittest -v tests.test_uf_dashboard tests.test_uf_history tests.test_uf_history_delivery
python3 -m unittest discover -v
node --check perito_dashboard/assets/inspection.js
python3 -m compileall -q perito_dashboard tests
```

Os testes usam **ambas** as fontes externas controladas e relógio pelo
`refresh_and_build` completo. Os esperados são literais independentes documentados
para os XLSX reais `run-6`/`run-7`: setembro/2026, 1.108 pessoas, DF 324 e todas as
27 contagens, sem gerar oráculos por helpers de produção. Cobrem empates, zeros
explícitos controlados, valores inválidos/ausentes, preservação de cada feed,
reexportação, avanço de mês e medida nacional deliberadamente diferente. Meses
novos/zeros modificados nos testes são cenários controlados, não novas publicações.

## Browser local opcional — sem requisições ao governo

Ler a skill `orca-cli` e o guia atual do browser antes de operar. Criar apenas
servidor/página próprios, guardar os handles e **nunca** operar a página protegida
`fff658ce-af08-4721-b944-f11fa526a5c0`. Exemplo com diretório temporário dedicado
inédito e porta local livre:

```sh
PREVIEW=$(mktemp -d)
python3 -m tests.browser_uf prepare --root "$PREVIEW"
orca terminal create --title 'UF local' --command \
  "python3 -m http.server --bind 127.0.0.1 --directory '$PREVIEW/www' 8144" --json
orca tab create --url http://127.0.0.1:8144/national/monitorar-vacancias-perito-pf/ --json
# PAGE = somente o browserPageId recém-criado
python3 -u -m tests.browser_uf check --root "$PREVIEW" --page "$PAGE" \
  --orca orca --base-url http://127.0.0.1:8144/
```

O driver reaproveita os 19 casos nacionais de `tests/browser_mouse.py`, sem remover
empate ou scroll/resize. Acrescenta composição e primeiras ausências de cada feed
em 1440/320 px, 27 contagens literais, barras, ambas as colunas UF desde a primeira
linha e nenhum overflow horizontal UF/página. Confere datas/proveniência e retenção
após falha posterior de cada fonte; singular genuíno e plural/lacuna **contrafactual**
(novembro/2026) pelo build completo. Exercita instrução, lacuna, leitura persistente,
scroll/resize e inspeção em 320 px também no artefato **com ambas as fontes**.
Fallback composto simula somente o ativo JS ausente. Tab/Enter nativos conferem o
skip link, contraste local e abertura do JSON UF real; fontes/JSON relativos são
conferidos sem navegar ao governo. Todos os casos são tentados; falhas de asserção
são relatadas e o comando termina com erro, não transforma limitação em passe.
Move o mouse real via `orca mouse move`, nunca eventos sintéticos, estado forçado
ou helpers privados. Avaliação DOM apenas lê/mede e altera rolagem.
Cada navegação recebe viewport explícito; capturas têm URL conferida antes/depois,
e **após cada screenshot** o viewport é explicitamente restaurado antes do mouse.
PNGs ficam em `$PREVIEW/evidence`: abrir os arquivos, não apenas gerar capturas.
Ao terminar, fechar somente a página e o terminal próprios e interromper o servidor
pelo handle guardado. Preservar os PNGs/logs necessários ao relatório.

A evidência original de #14 é histórica: não incluiu prova de foco/teclado nativo.
#8/#16 foram posteriormente aceitas; seus recibos não foram reexecutados por #44.
O novo contrato e a execução local de #44 estão separados em
[aceitação composta — #41/#44](composed-acceptance.md#interface-4144--verificação-local-de-15112026).
O empate nativo exato e zoom real de 200% ficaram **Not verified** nesta execução;
não se afirma validação integral. Fixtures locais não qualificam runtime,
Actions/Pages nem certificam WCAG, leitor de tela ou toque. Não se acrescenta
seleção do gráfico por teclado/toque.
