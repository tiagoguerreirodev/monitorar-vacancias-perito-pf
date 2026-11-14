# Visualização do retrato UF — #14

A página estática mantém cargos vagos e histórico **nacionais** como primeira
leitura. A seção separada “Pessoal ativo por UF” usa exclusivamente o retrato UF
aceito pelo [seam público](uf-seam.md), sem consultar o governo no navegador.
Não altera coletor, schema, critérios de aceitação ou workflows.

- **Pessoas ativas**, não cargos aprovados/ocupados/vagos, distribuição legal ou
  vagas de concurso estaduais. Todas as classes PCF combinadas, população DPF /
  Ativo; o total é reconciliado com a **própria fonte UF**, não com cargos nacionais.
- 27 UFs, incluindo DF, em barras horizontais desde zero, ordem decrescente;
  empates pela sigla em ordem alfabética. Sigla, nome completo e inteiro exato
  aparecem em texto; a cor e a largura não são o único meio de leitura.
- Lista sem controles interativos e tabela HTML equivalente com cabeçalhos.
  Em 320 px, os rótulos/barras se reorganizam sem transbordar a página; a tabela
  tem região nomeada com `tabindex="0"` e rolagem horizontal independente.
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
- Apenas o último retrato UF é desenhado, sem seletor, série ou arquivo histórico
  UF. A auditoria de correções no JSON não se transforma em histórico visual.

## Verificação determinística

```sh
python3 -m unittest -v tests.test_uf_dashboard
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

O driver reaproveita os 15 casos nacionais de `tests/browser_mouse.py`, acrescenta
UF composta e UF sem nacional em 1440/320 px, datas/proveniência independentes,
contagens literais, barras, ausência UF, rolagem da tabela e fallback composto sem
JS. Repete lacuna/inspeção em 320 px também no artefato **com ambas as fontes**.
Move o mouse real via `orca mouse move`, nunca eventos sintéticos, estado forçado
ou helpers privados. Avaliação DOM apenas lê/mede e altera rolagem.
Cada navegação recebe viewport explícito; capturas têm URL conferida antes/depois,
e **após cada screenshot** o viewport é explicitamente restaurado antes do mouse.
PNGs ficam em `$PREVIEW/evidence`: abrir os arquivos, não apenas gerar capturas.
Ao terminar, fechar somente a página e o terminal próprios e interromper o servidor
pelo handle guardado. Preservar os PNGs/logs necessários ao relatório.

Essa é evidência local com fixtures, não qualificação de runtime confiável,
prova de Actions/Pages ou certificação WCAG/foco/teclado nativo. Não adiciona
inspeção por teclado/toque. #15/#16 e aceitação/publicação de #8/#21 continuam
com seus gates próprios; histórico UF (#9) permanece fora deste escopo.
