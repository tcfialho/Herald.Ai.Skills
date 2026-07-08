# tests/ — suíte de testes desta skill (gerada por skill-test)

Regra única: **`runs/` é temporário — pode apagar a pasta inteira quando quiser.
Todo o resto é o teste — versionado no git junto com a skill.**
Nada de `tests/` é distribuído com a skill instalada.

| Pasta/arquivo | O que é | Tipo |
|---|---|---|
| `contract.yaml` | as regras da skill em formato testável | Teste — versiona |
| `scenarios/*.yaml` | jornadas de usuário simuladas | Teste — versiona |
| `fixtures/*/setup.py` | monta o "mundo" descartável de cada teste | Teste — versiona |
| `baselines/` | 3 ponteiros pequenos: `baseline.json` (versão aprovada), `last-smoke.json` (selo "testada após a última edição"), `mutate-latest.json` (calibração) | Teste — versiona |
| `runs/` | execuções: `run-*/` (transcritos/logs), `adapt-*/` (diffs propostos), `probe-*/` | **Temporário — apagável, ignorado no git** |

Notas:
- O `.gitignore` desta pasta já ignora `runs/` — você não precisa fazer nada.
- Apagar `baselines/` não quebra nada, mas perde a referência de comparação e o selo.
- Distribuição/instalação da skill NUNCA inclui `tests/`; o harness também não envia esta
  pasta ao modelo durante os testes.
