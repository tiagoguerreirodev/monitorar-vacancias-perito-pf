# Aceitação composta local — #16

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
