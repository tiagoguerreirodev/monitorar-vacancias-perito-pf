# Contrato da fonte de pessoal ativo por UF — #11 / #8

Evidência coletada em **14/11/2026 (UTC)**; contrato documental, sem conector de
produção, alteração de dados ou habilitação do painel UF nesta entrega.
[Issue #11 e autorização vigente](https://github.com/tiagoguerreirodev/monitorar-vacancias-perito-pf/issues/11).

## Geografia: premissa do projeto, não verificação oficial

O responsável pelo projeto autorizou expressamente em 14/11/2026 tratar
**`UF Servidores` como `UF de lotação`**. Esta é uma **PREMISSA DO PROJETO**, não
uma definição oficialmente verificada. Substitui somente o antigo pré-requisito
de comprovação oficial dessa equivalência para continuar a implementação.
A proveniência e a apresentação futuras devem conservar essa ressalva, por
exemplo: “Pessoal ativo por UF de lotação — equivalência com UF Servidores
assumida pelo projeto; definição oficial não verificada”.

A evidência pública inspecionada mapeia o filtro UF a `UF Servidores` (painel
`SvDmzg`); o mapa usa `Regiao (Servidores)` e `UF Servidores`, sem definição
conclusiva. Os registros anteriores das fontes oficiais contêm:

- [Nota metodológica de junho de 2018, p. 3](https://www.gov.br/gestao/pt-br/acesso-a-informacao/servidores/servidores-publicos/painel-estatistico-de-pessoal/documentos/nota-20180604-metodologia-historico-painel-estatistico-de-pessoal.pdf):
  “Servidores já aposentados ou falecidos atualmente, mas que nos dados históricos
  não traziam a UF de lotação:”.
- [Manual Faça Você Mesmo de outubro de 2018, p. 18](https://www.gov.br/gestao/pt-br/acesso-a-informacao/servidores/servidores-publicos/painel-estatistico-de-pessoal/documentos/manual-20181030-pep-historico-manual-faca-voce-mesmo-vfinal.pdf):
  “Arraste Orgão Superior para LINHAS, UF Servidores para COLUNAS e Servidores
  para VALORES.”

Esses trechos não estabelecem a continuidade até a população ativa atual nem a
atribuição de cedidos/requisitados. A [página oficial do PEP](https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/painel-estatistico-de-pessoal)
e o [catálogo](https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/catalogo)
não resolveram essa lacuna na investigação anterior; um link legado exigiu
autenticação e a navegação foi interrompida. Não se afirma que a interpretação de
lotação esteja errada, apenas que **não foi comprovada oficialmente**. Nenhuma
nova requisição ao Governo foi feita para redigir/verificar este documento.
Nenhum contato foi autorizado ou realizado; o rascunho de esclarecimento
permanece **NÃO ENVIADO**.

## Rota pública anônima demonstrada localmente

Entrada estável: <https://pep.paineis.gov.br/extensions/pep/index.html>, seguida de
`#fvm` (Faça Você Mesmo). Aplicativo público
`aec332a1-406b-4fec-a776-b1ed66735961`, tabela instalada `Dwnkq`.

Duas execuções autônomas completas, **run-6 e run-7**, usaram os mesmos quatro
scripts, sem alterações entre elas:

1. Novo processo Chrome headless e novo perfil temporário; **zero cookies antes
   da navegação**, sem sessão, cache ou navegador do usuário reutilizados.
2. Bootstrap normal do frontend (`qlik.openApp`) e WebSocket público **101**;
   aguardar a página inicial terminar de carregar antes de navegar para FVM.
3. Seleções nos listboxes públicos existentes, com correspondência textual
   exata e confirmação das seleções finais e da associação do órgão abaixo.
4. Acionamento do botão instalado `#download-csv-btn` por `b.click()` via CDP
   `Runtime.evaluate` com `userGesture:true`, não por mouse físico. A preparação
   usa a API de listboxes já empregada pelo frontend; não cria cubo de pessoal.
5. Novo download gerado, conclusão registrada, validação do XLSX contra o total
   da própria tabela selecionada na mesma execução e limpeza dos processos e
   perfis próprios.

Apesar do nome do botão, o [exportador público](https://pep.paineis.gov.br/extensions/pep/ui-service.js?v=1.4)
executa `vis.table.exportData({format: "OOXML", filename: "dados-pep.xlsx", download: true})`.
A resposta é **ZIP/XLSX**, não CSV. URLs `/tempcontent/...xlsx` são saídas
transitórias de cada exportação, **não um feed estável nem entrada reutilizável**.
O [config público](https://pep.paineis.gov.br/extensions/pep/config.js?v=1.4) e o
[serviço de conexão](https://pep.paineis.gov.br/extensions/pep/qlik-service.js?v=1.4)
foram preservados nos artefatos, sem modificações do frontend.

Não houve login, credenciais, reutilização de URL/arquivo antigo, cabeçalhos ou
user-agent especiais, retry do WebSocket anteriormente negado, contorno de
403/CAPTCHA/supressão, API protegida ou registros individuais. A coleta deve
parar diante de restrição, não tentar contorná-la. A falha 403 de um antigo probe
Python não descreve os dois fluxos de navegador bem-sucedidos.

## Seleção e resposta exigidas

| Conceito | Contrato observado e conferido |
| --- | --- |
| Seção / métrica | `Servidores` / `Servidores` |
| Vínculo | somente `Ativo` |
| Órgão nativo | campo `Órgão (Servidores)`, valor exato `Departamento De Policia Federal` |
| Órgão exportado | `Orgão` corresponde a `Sigla Orgão Vinculado (Servidores)` pelo dicionário público `FVM_CampoFisico`; após selecionar o nome completo, a única sigla disponível foi `DPF` |
| Cargos | exatamente os quatro rótulos da tabela abaixo, sem prefixo amplo ou aliases aproximados |
| Dimensões FVM | `Grupo Situação do Vínculo`, `Nome do Cargo`, `Orgão`, `UF`; a tabela também devolve `Ano` e `Mês` |
| Período | maior mês numérico elegível no listbox público `Mês/Ano`; observado `Set 2026`, devolvido `2026` / `Set` |
| Formato | um XLSX íntegro, uma planilha, sete colunas exatas na ordem abaixo |

Cabeçalhos exatos: `Ano`, `Mês`, `Grupo Situação do Vínculo`, `Nome do Cargo`,
`Orgão`, `UF`, `Servidores`. A grafia exportada `Orgão` difere da do campo nativo
`Órgão (Servidores)`; `DPF` não é o valor do filtro de nome completo. Os números
de elementos Qlik são resolvidos a cada execução, não fixados como identificadores.

Resultados independentes de **cada um** dos dois arquivos reais:

| Rótulo literal de cargo | Pessoas ativas |
| --- | ---: |
| `Perito Criminal Federal 1a Cla` | 96 |
| `Perito Criminal Federal 2a Cla` | 143 |
| `Perito Criminal Federal 3a Cla` | 58 |
| `Perito Criminal Federal Classe` | 811 |
| **Total** | **1.108** |

Não expandir o último rótulo por suposição. Ambos retornaram **88 grupos
classe–UF únicos**, todos `DPF`/`Ativo`, um único período e as **27 UFs incluindo
DF**. Contagens observadas por UF:

```text
AC 9    AL 14   AM 14   AP 7    BA 27   CE 30   DF 324
ES 21   GO 28   MA 11   MG 79   MS 27   MT 13   PA 13
PB 25   PE 31   PI 14   PR 71   RJ 55   RN 15   RO 24
RR 8    RS 57   SC 37   SE 12   SP 130  TO 12
```

A soma **1.108** coincide com `qGrandTotalRow` **da própria tabela/população em
cada execução**; DF soma **324**. Não há grupo duplicado, UF vazia/desconhecida
nem contagem inválida nos arquivos. A validação cruza o número de linhas com
`qSize.qcy`, os rótulos devolvidos, o mês efetivamente selecionado e o total;
não aceita apenas a intenção da consulta ou uma coincidência com outro total.
Esses números são evidência de setembro de 2026, não constantes de produção.

### Cobertura, ausências e limites

- **88 grupos não significam 108 grupos preenchidos.** Não se exigem quatro
  linhas em cada UF nem se converte um par classe–UF ausente em zero.
- Os dois arquivos contêm apenas inteiros positivos. O validador experimental
  rejeita zero; portanto não demonstra semântica de zero explícito. O contrato
  futuro deve distinguir zero válido de ausência/supressão/desconhecido, sem
  flexibilizar silenciosamente a evidência ou fabricar zero.
- Todas as UFs vieram nestes arquivos; UF ausente, vazia, exterior, desconhecida
  ou categoria adicional **não está qualificada** por esses exemplos. Não pode
  ser descartada para forçar reconciliação: requer contabilização explícita e
  cobertura honesta, ou rejeição do candidato com preservação do último válido.
- Não há prova separada da regra geográfica de cedidos/requisitados/exterior.
  Reconciliação numérica não certifica geografia, ausência de supressão ou
  equivalência entre pessoal ativo e cargos ocupados.
- Não se inferem cargos aprovados/vagos ou taxa de vacância por UF. A fonte
  nacional de cargos legais é outra medida, mesmo quando os totais coincidem.
- Selecionar o maior mês disponível não prova acesso a todos os meses antigos.
  O escopo inicial é **somente o retrato UF atual**; junho de 2025 é corte do
  histórico nacional, não um corte UF aprovado. #9 só começa após toda a
  aceitação de #8; nenhum intervalo retrospectivo UF foi autorizado aqui.

## Proveniência dos dois exports e identidade dos dados

Raiz local dos artefatos (fora do Git, disponibilidade temporária):

```text
/var/folders/6d/xn0p45kd3td2pb8zhw4zvvbh0000gn/T/perito-collector-qualification-a4fr56fh
```

| Evidência UTC em 14/11/2026 | run-6 | run-7 |
| --- | --- | --- |
| Cookies iniciais | 05:55:25.709 / 0 | 05:55:52.221 / 0 |
| WebSocket 101 | 05:55:31.054 | 05:55:57.222 |
| Download iniciado | 05:55:38.521 | 05:56:04.857 |
| Download concluído | 05:55:38.701 | 05:56:04.896 |
| Bytes XLSX | 7.915 | 7.915 |
| Arquivo em `downloads/` | `f763006f-5265-47a3-835b-05b67f92526d.xlsx` | `83cde208-3893-4671-a091-266c8ea3ed07.xlsx` |

SHA-256 dos **bytes completos dos XLSX**:

- run-6: `5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55`
- run-7: `fbffe323c3485bed0024afe6133f450dc20f51ab8c7aba65a1079be6476e345c`

SHA-256 **canônico dos agregados**, igual nos dois:
`9d05ce428f7b51a03718958176a00d49a370a66927282f4b0a65cf86ce3f851d`.
O validador lê as sete colunas como strings, exclui o cabeçalho e calcula:

```python
canonical = json.dumps(sorted(rows), ensure_ascii=False, separators=(',', ':')).encode()
digest = hashlib.sha256(canonical).hexdigest()
```

Inclui todas as linhas/colunas agregadas, não apenas totais por UF. A comparação
offline dos ZIPs encontrou diferença somente nos timestamps created/modified de
`docProps/core.xml`: os dados agregados são iguais. Preservar o hash bruto como
proveniência, sem tratar mera regeneração do contêiner como correção dos dados.
A definição canônica acima não estabelece ainda um esquema persistido de #13.
A diferença de hash bruto **não prova sozinha** um download novo; a evidência de
frescor são processos/perfis isolados e eventos de download independentes.

Cada diretório `run-6/` e `run-7/` conserva `validation.json`, `export-request.json`
(seleções, mapeamento, período e total próprios), `selection-diagnostics.json`,
`export-button-click.json`, `trace.jsonl`, `scripts/`, `script-fingerprints.json`,
as fontes públicas salvas e `end.json`. Na raiz, `SUMMARY.md`, `RESULT.md`,
`source-trace.json`, `manifest.json` e `cleanup-verification.json` detalham a
sequência e a limpeza dos processos/perfis próprios. Esses relatórios antecedem
a autorização de premissa: seu antigo bloqueio semântico não é o estado atual.

Scripts executados, idênticos nos dois diretórios `scripts/` e na raiz:

| Script | SHA-256 |
| --- | --- |
| `automatic-run.py` | `d09a9fa7922535878ac123f9ee819dee0e034cd395a4110949b6214ef7d7a170` |
| `browser-probe.mjs` | `743dd18adc01482bc5d4a84d86247a412f05ce85dbc33001a6c8817ab6d8a8c3` |
| `collect-flow.js` | `43929483e5bd906669a1d389330cb6e107e1daee9a9f18656d0ffc63ccdc0cdc` |
| `verify-export.py` | `5e8132bcdfda9a82c36bdd02ef4561b0a84de8f9bb9d72b35734f4aa9ef9e505` |

Comandos **históricos já executados**, apresentados para repetibilidade, não
para repetir requisições nesta tarefa (o diretório de run deve ser inédito):

```sh
E='/var/folders/6d/xn0p45kd3td2pb8zhw4zvvbh0000gn/T/perito-collector-qualification-a4fr56fh'
python3 "$E/automatic-run.py" run-6
python3 "$E/automatic-run.py" run-7
```

### Revalidação local offline, sem alterar os artefatos

O comando abaixo executa somente o validador salvo sobre cópias temporárias dos
dois exports reais. Não executa navegador/coletor nem faz requisição de rede.
Depende da raiz local acima ainda existir; os artefatos não são fixtures nem uma
entrada de produção do repositório.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import tempfile

root = Path('/var/folders/6d/xn0p45kd3td2pb8zhw4zvvbh0000gn/T/perito-collector-qualification-a4fr56fh')
raw = {
    'run-6': '5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55',
    'run-7': 'fbffe323c3485bed0024afe6133f450dc20f51ab8c7aba65a1079be6476e345c',
}
canonical = '9d05ce428f7b51a03718958176a00d49a370a66927282f4b0a65cf86ce3f851d'
verify = runpy.run_path(str(root / 'verify-export.py'))['verify']
with tempfile.TemporaryDirectory(prefix='uf-offline-') as directory:
    for name, expected in raw.items():
        source = root / name
        copy = Path(directory) / name
        copy.mkdir()
        shutil.copytree(source / 'downloads', copy / 'downloads')
        for filename in ('export-request.json', 'trace.jsonl'):
            shutil.copy2(source / filename, copy / filename)
        for filename, fingerprint in json.loads((source / 'script-fingerprints.json').read_text()).items():
            script = (source / 'scripts' / filename).read_bytes()
            assert script == (root / filename).read_bytes()
            assert hashlib.sha256(script).hexdigest() == fingerprint['sha256']
        result = verify(copy)
        assert result['file_sha256'] == expected
        assert result['canonical_aggregate_sha256'] == canonical
        assert result['period'] == ['2026', 'Set']
        assert result['aggregate_rows'] == 88 and result['uf_count'] == 27
        assert result['sum_rows'] == result['source_own_total'] == 1108
        assert result['counts_by_uf']['DF'] == 324
        print(name, result['file_sha256'], result['canonical_aggregate_sha256'], 'OK')
PY
```

A revisão de engenharia independente também revalidou os dois arquivos e a
identidade dos scripts sem novas requisições. Isso verifica a evidência salva,
não constitui uma terceira coleta.

## Qualificação ainda obrigatória para publicação

Os dois runs demonstram repetibilidade **local em Darwin arm64, Chrome
156.0.8078.81, Node 26.13.1/CDP e Python 3.9.6**, não Ubuntu nem Actions. O caminho
do executável Chrome do probe é específico de macOS. Esperas limitadas do probe
(75 s de prontidão, 45 s de download, watchdog de 15 min) não são SLA da fonte.

**Execução real anônima sob Ubuntu/Python 3.13 no workflow confiável continua
sendo gate posterior obrigatório de #15/#16**, junto da integração de #13 e da
aceitação do artefato/publicação. Não foi cumprido por estes runs locais, por
fixtures, por flags, pelo workflow nacional existente ou pela premissa geográfica.
Não há garantia de estabilidade futura do frontend/dicionário/exportador.

Permanecem obrigatórios: dados apenas agregados; validação de população,
período, cobertura e reconciliação; proveniência honesta da premissa; metadados e
último estado válido independentes das fontes nos dois sentidos; nenhuma
promoção em falha do build composto; recusa de escritor obsoleto, Git serializado
e publicação confiável. Este contrato documental não altera runtime, dados,
workflows, a apresentação nacional já aceita nem as demais dependências de #8/#9.
