# Monitoramento de cargos e pessoal PCF/PF

Retratos mensais dos cargos de Perito Criminal Federal na Polícia Federal e da
respectiva população de pessoal ativo, sem confundir pessoas com cargos legais.

## Language

**PCF ativo**:
Pessoa da população de Peritos Criminais Federais da Polícia Federal classificada
como `Ativo` na fonte de pessoal, consideradas as quatro classes da carreira.
_Avoid_: cargo ocupado, vaga ocupada

**Cargo aprovado**:
Cargo legalmente autorizado para a carreira e o órgão, esteja ocupado ou vago.
_Avoid_: cargo distribuído, vaga de concurso

**Cargo ocupado**:
Cargo legal que a fonte nacional de cargos informa como ocupado; não é sinônimo
da contagem de PCFs ativos na fonte de pessoal.
_Avoid_: PCF ativo, servidor ativo

**Cargo vago**:
Cargo aprovado que a fonte nacional informa como não ocupado, não uma oferta de
concurso ou uma quantidade estadual deduzida do pessoal ativo.
_Avoid_: vaga de concurso, vacância por UF

**UF de lotação (premissa do projeto)**:
Unidade da Federação, incluindo o Distrito Federal, à qual o projeto atribui o
PCF ativo ao tratar `UF Servidores` como UF de lotação por premissa expressamente
autorizada pelo responsável pelo projeto, não por definição oficial verificada.
_Avoid_: UF oficialmente verificada, UF de residência, UF de exercício

**Mês de referência**:
Mês ao qual o retrato da fonte se refere, distinto da data em que foi coletado ou
verificado.
_Avoid_: data de coleta, data da última verificação
