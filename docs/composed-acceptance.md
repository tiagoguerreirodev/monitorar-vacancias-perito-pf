# Aceitação composta local — #16

> As seções de #16 abaixo são o recibo histórico de 14/11/2026, inclusive seus
> estados/gates e contrato de tooltip/rolagem então vigentes; não foram
> reexecutadas nem reescritas por #44. O contrato e a evidência novos estão em
> [Interface #41/#44](#interface-4144--verificação-local-de-15112026).

## Estado e fronteiras

A implementação inicial já reúne nacional (#7/#10–#12/#18/#20/#21), coletor UF
(#13), retrato UF (#14) e runtime confiável (#15). Em 14/11/2026, a aceitação
local composta usou o fluxo público `refresh_and_build(data_dir, site_dir,
source=..., uf_source=..., clock=...)`, com **ambas** as fontes explícitas e
relógio controlado. Não alterou runtime, coletor, dados versionados ou workflows.
Os 155 testes existentes foram preservados; não se inventou um teste RED para
comportamento que já estava correto.

Isto **não é publicação nem encerramento de #16/#8**. O coordenador ainda precisa
revisar o diff completo desde `86101534b27b04e87eb3fdf8c4595fea850783f4`, integrar
somente o tree revisado e verificar o artefato, Pages real e texto público.
Histórico UF (#9), arquivo/seleção de meses e retroatividade não estão incluídos.
UF de lotação é **premissa do projeto, não verificada oficialmente**. PCF ativo
não é cargo ocupado legal; nenhum total nacional é reconciliado à força com UF,
e não há inferência de vagas por estado.

## Qualificação de fonte já aceita (#15)

- Código: `631f35c9c34d3f6bc90f0ad0d584fd94c79b4fe4`.
- Run confiável: [43633428483](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/actions/runs/43633428483),
  tentativa 1; artefato API **14128614332**.
- SHA-256 do ZIP, conferido com o digest da API:
  `50f85269c1d519b1ed56eed2a998b9672f422e4b640117135b5eecb34249f54c`.
- Dois exports novos pelo caminho ordinário, sem flags de relaxamento, em
  Ubuntu 24 / Python 3.13.18 / Node 26.13.1 / Chrome 157.0.8103.78.
  Cada XLSX: 7.915 bytes, 88 linhas nativas, 27 UFs/DF, setembro/2026,
  **1.108 PCFs ativos**, **DF 324**.
- SHA-256 XLSX 1:
  `09497a8e558a0c014b99e92f880c2f46e8c2a28755a6476b1ec08b9474b7b78f`;
  XLSX 2: `44d7eab94292149c30048bb66e7cd54f9ff3b31fc9a47d72846a2749b1d9a341`.
- Identidade semântica comum:
  `dae419f1145ea7c81fe8add8f2df7d5b9f605741ee5ce7d86bf61db4da901e0a`.
- Downloads concluídos em `2026-11-14T19:42:55.384Z` e
  `2026-11-14T19:43:18.582Z`; cleanup de ambos os exports e da cápsula confirmado,
  owner exit 0 e árvore protegida inalterada.

O run no-Gov 43633225276 foi diagnóstico causal de compatibilidade/isolamento,
**não** qualificação de fonte. O recibo aceito e `verified.json` vinculam os nove
recursos de coletor/runtime. Qualquer mudança nesses recursos exige nova
qualificação; uma atualização documental não exige repetir acesso ao governo.
Esta aceitação local não fez rede externa, dispatch ou download.

## Método local e matriz de falhas

As cópias de trabalho ficam fora do repositório. Foram usados os dois XLSX acima,
com conferência de hash, pela interface pública `UFExport`/`UFSource`. A prova
sanitizada conserva o retrato aceito e eventos seguros, mas não a lista/snapshot
nativa completa nem a URL temporária original. Por isso o envelope local é
**reconstruído e CONTROLADO** (período único, snapshot compatível e URL temporária
inativa); não deve ser confundido com o envelope original, prova nova de frescor
ou nova qualificação. Os bytes XLSX sem alteração continuam sendo os qualificados.

O nacional usa todos os 15 meses aceitos de junho/2025 a setembro/2026, com
julho/2025 ausente. O relógio local é `2026-11-16T12:00:00Z`: é estímulo controlado,
não uma verificação oficial nesse instante. Em cada caso o preview fica sob o
subcaminho `/monitorar-vacancias-perito-pf/`, com dados/ativos apenas locais.

| Estímulo público em cópia própria | Resultado exigido e observado |
| --- | --- |
| Nacional corrigido, UF indisponível | publicação parcial; junho/2025 1.117 ocupados / 78 vagos; bytes de agregado e check UF intactos em data e site |
| Nacional indisponível, UF alterada controladamente | publicação parcial; AC 9→10 / total 1.108→1.109; agregado e check nacional intactos em data e site |
| Ambas indisponíveis | erro; manifesto recursivo de bytes **e modos** de data/site, inclusive build.json sentinela, idêntico |
| Ambas válidas e alteradas, assets ausentes em cópia própria do pacote | `FileNotFoundError` real durante build compartilhado; nenhum byte/modo de data/site promovido |
| Ambas válidas e alteradas, pacote íntegro | publicação completa; os dois controles positivos aparecem juntos |
| Primeira ausência de cada fonte | outra fonte continua utilizável; indisponível não vira zero |

A alteração AC é contrafactual em uma cópia XLSX; **não é informação de fonte**.
O erro compartilhado remove apenas assets da cópia própria do pacote e executa
um novo processo público; não substitui helper interno nem lança erro por mock.
Nunca omitir um dos adaptadores em prova offline: o default acessa o governo.
Não usar o antigo helper `prove-accepted-artifact-failure.py`, que omite UF.

## UI e cobertura

A aceitação opcional usa Orca já disponível, página e servidor localhost próprios,
mouse real, observação DOM/rolagem e PNGs inspecionados. Depois de navegação ou
screenshot, o viewport é explicitamente restabelecido antes de mover o mouse.
Nenhum handler privado, evento sintético ou tooltip fabricado é utilizado.

- Nacional: todos os 15 casos de `tests/browser_mouse.py`, incluindo vaga como
  destaque, taxa e contexto da mesma referência, junho/2025 inclusive, lacuna de
  julho, zero versus ausência, mês único, lacunas consecutivas/outro ano, empate,
  limites, scroll/resize com mouse parado, valores exatos e fallback sem JS.
- Ambos os XLSX qualificados: 27 contagens literais em ordem decrescente,
  DF 324, total 1.108, referência própria setembro/2026, proveniência/check
  separados, premissa visível e tabela equivalente; desktop 1.440 e mobile
  320 px, sem overflow da página, com rolagem horizontal da tabela estreita.
- Composição: gap nacional ainda inspecionável pelo mouse; setembro/2026 mostra
  **87 cargos vagos**, sem misturar PCFs ativos. UF disponível com nacional ausente
  e nacional disponível com UF ausente; fallback estático conserva tabela UF.
- Cobertura automatizada existente: `tests/test_uf.py` (fontes independentes,
  recheck/correção, recusa de regressão, ausências e build inválido),
  `tests/test_uf_dashboard.py` (ordenação/cobertura/proveniência/zero/recusa de
  inválidos/latest), `tests/test_dashboard.py`, `tests/test_history.py` e
  `tests/test_refresh.py` (nacional/renderização/persistência), além dos testes de
  runtime e workflow; o comportamento de mouse é aceitação local opcional.

DOM scroll e atributos de acessibilidade não certificam teclado nativo, leitor
de tela, toque ou WCAG. Nenhuma dessas certificações é reivindicada.
Os logs, matriz recursiva, PNGs e comandos exatos desta execução estão no recibo
local `/tmp/perito-uf-implementation/issue-16-result.md`; não são ativos publicados.

## Runbook de operador

1. Leia [operação](operations.md), [contrato UF](uf-source.md),
   [seam](uf-seam.md) e [runtime qualificado](uf-runtime.md). Confira o tree e os
   nove recursos contra o recibo aceito antes de reutilizar a qualificação.
2. Para verificação offline, forneça explicitamente `source`, `uf_source` e
   `clock`; use cópias isoladas e os XLSX/recibos aceitos. Rode os testes e faça
   mouse/PNGs no preview local; não rebatize estímulo controlado de fonte oficial.
3. Em falha de uma fonte, confira o diagnóstico e o par agregado/check retido;
   não apague nem renove sua proveniência. Em falha total/compartilhada, compare
   recursivamente os diretórios com a versão aceita antes de tentar novamente.
4. Só o coordenador, após revisão completa, pode executar o fluxo confiável em
   main. O refresh usa o caminho produtivo de duas aquisições e publica somente
   agregados/proveniência; bruto e prova sanitizada ficam no artefato de diagnóstico.
5. A allowlist de Git contém os quatro JSON dos pares disponíveis. Verifique
   `build.json` (code/data revision, run/attempt), conteúdo do artefato, URLs reais
   de Pages sob o subcaminho, SHA dos dados e texto público/premissa. Exit 0 de
   build, upload ou PNG local não substitui deploy público conferido.
6. Só após esse gate pode declarar #16/#8 aceitos. #9 requer então a autorização
   condicional já concedida; não implementar histórico UF nesta entrega.

## Interface #41/#44 — verificação local de 15/11/2026

### Contrato novo, não reexecução de #16/#14

Base de código conferida antes dos edits:
`28199c135f3bd825337ac7a174c9e825aa2b9165` (integração de #42/#43).
#44 altera somente driver composto e documentação; não coleta no governo,
requalifica runtime, publica Pages ou muda dados aceitos. Os recibos originais
acima e de #14 continuam datados, não são prova reemitida para esta revisão.

- Tabela UF: nomes completos e inteiros juntos desde a primeira linha em 320 px;
  27 contagens literais, cabeçalhos nativos e região nomeada/focável. Sem overflow
  horizontal UF/página; gráfico e tabela nacionais mantêm rolagem contida.
- Indisponibilidade explicitamente nacional ou UF, sem fabricar zero, check ou
  links da fonte ausente. A outra fonte permanece utilizável. Referências,
  verificações e proveniência independentes, inclusive após falha posterior.
- Inspeção nacional em fluxo, selecionável, rotulada e fora do plot. Instrução
  inicial ponteiro/tabela; mês/valor ou lacuna exatos; ao sair só a guia some e a
  última leitura permanece. Sem popup/live/Escape. Scroll/resize com ponteiro
  parado preservados; sem JS, gráfico/tabelas/fontes completos e nenhum
  placeholder vazio. Zeros, formatação e mês isolado continuam nos casos nacionais.
- Tab/Enter nativos para skip link e JSON de proveniência UF; medir o contorno
  contra o fundo realmente adjacente, não apenas atributos CSS.
- Prosa explicativa com medida aproximada de 60–75 caracteres em linhas desktop,
  fonte resolvida, sem estreitar dados; wrapping normal em 320 px. Zoom real de
  200% é uma condição separada, não sinônimo de viewport menor/DPR/CSS zoom.
- Cobertura usa “1 mês aceito” / “N meses aceitos”, datas/lacunas reais e ressalvas
  prospectivas. Novembro/2026 nesta fixture é **contrafactual**, não fonte nova.

### Método e resultados observados

`python3 -m tests.browser_uf prepare --root "$PREVIEW"` usa o
`refresh_and_build` público, ambas as fontes externas controladas e relógio.
`python3 -u -m tests.browser_uf check --root "$PREVIEW" --orca "$ORCA" --page "$PAGE" --base-url "$BASE/"`
usa somente página/servidor próprios, mouse e teclado nativos, DOM para
leitura/medida/rolagem, URL conferida e viewport restaurado após navegação/PNG.
Não há handlers privados, eventos sintéticos ou substituição de lógica de seleção.
Ver a receita portátil em [uf-view.md](uf-view.md).

Nesta execução, WSL ArchLinux/Python 3.14.10 e Orca Windows por ponte executável
local, sob `http://127.0.0.1:8844/…/monitorar-vacancias-perito-pf/`:

| Verificação | Resultado / limite |
| --- | --- |
| `tests.test_dashboard tests.test_uf_dashboard tests.test_uf_history`, uid/gid 65534 sem grupos suplementares | **35 passam**; não executados como root |
| `node --check perito_dashboard/assets/inspection.js` | passa; sintaxe, não prova de browser |
| 19 casos nacionais preservados no driver composto | **18 passam**; `edges` falha no empate exato, abaixo |
| UF composta / somente UF / somente nacional / arquivo UF / fallback / teclado | **6 passam**; dois reruns direcionados após corrigir comparação string/número no próprio teste |
| UF 1440/320 px, todas as 27 contagens e primeiro/último trecho | colunas cabem; região 1086/239 px, conteúdo igual; nomes completos quebram em 320 px |
| Readout composto | instrução, lacuna, persistência, guia, scroll/resize e 320 px passam; PNGs abertos |
| Skip link nativo | primeiro Tab revela; branco sobre `rgb(18, 57, 76)`, **12,2425:1**; Enter foca `MAIN#conteudo` |
| Proveniência | Tab/Enter abrem o JSON UF real; JSONs locais lidos por HTTP; fontes oficiais permanecem links, sem acesso ao governo |
| Prosa resolvida | máximo observado **73 caracteres**, dados com **1086 px**; wrapping 320/720 px passa (720 não é prova de zoom) |
| Cobertura / retenção | singular setembro genuíno; dois meses setembro/novembro e lacuna outubro controlados; check nacional avança a 16/11, UF retém 15/11 após falha |

O RED da migração do driver exigia `scrollLeft > 0` em 320 px; o artefato novo
corretamente devolveu zero. Remover essa exigência obsoleta e medir as duas colunas
produziu GREEN. As duas outras falhas do teste eram comparação de texto numérico
parseado pelo driver com string; a asserção agora compara o texto literalmente no
browser. Não houve correção de produção ou alegação de RED produtivo inventado.
O primeiro comando completo terminou com `['edges', 'no-uf', 'composed-archive']`;
os reruns `no-uf` e `composed-archive` passaram após essas correções. Não se afirma
que o comando completo ficou verde: `edges` continua falhando, sem skip/epsilon.

### Not verified e fronteiras da prova

- **Empate nativo exato: Not verified.** Em 1440 px, coordenada solicitada
  `894.1761474609375` devolve janeiro/101 em vez de fevereiro/105. #43 reproduziu
  essa falha também na base `a98d57ba8a18ca44f944239814705b9c54563a77`.
  Tentativa limitada em 1000 px, inclusive após Control+0, não estabeleceu o
  alinhamento inteiro proposto: matriz `a=d=0.9999999859116286`,
  `e=46.90340805053711`, X `771.9033813476562` para SVG X=725. Não se arredondou,
  nudged ou substituiu input; `tests/browser_mouse.py` e `Math.round` inalterados.
- **Zoom genuíno 200%: Not verified.** Após foco nativo, seis Control+Add e seis
  Control+Shift+Equal não mudaram métricas: innerWidth 1440, outerWidth 3128,
  DPR ≈1, visualViewport.scale 1 e parágrafo 517,5 px. A captura dessa tentativa
  não é prova de zoom; nenhum DPR/CSS zoom foi usado como substituto.
- A suíte completa não é verde. Comparação do coordenador em clone LF limpo
  como usuário sem privilégios (uid 65534, não root): base `a98d57b` e integração
  `28199c1`, **184 testes,
  3 falhas e 3 erros com as mesmas seis identidades** de runtime/protected-parent.
  Isso é comparação de baseline, não nova execução integral final de #44. A
  revisão e execução final do snapshot limpo pertencem ao coordenador.

Comandos exatos, revisões, logs e PNGs inspecionados desta execução estão fora do
repositório em `C:/Users/tiago/AppData/Local/Temp/spec41-44-evidence/HANDOFF.md`.
Foram abertos os estados de primeira/última linha UF, readout inicial/persistente,
indisponibilidade, fallback, prosa e foco. **Não se declara validação integral de
#41/#44**, publicação ou certificação WCAG/leitor de tela/toque/print/forced colors.
