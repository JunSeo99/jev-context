# jev-context

TypeSafe Jev로 후보 원문을 검사하고, 에이전트에게 읽을 구간과 추가 근거를 제안하는 Python 라이브러리·CLI입니다. MIT 라이선스이며 현재 실험 단계입니다.

**실험에서 자동 구간 교체는 실제 작업 성능을 떨어뜨렸습니다.** 기본 `advisory` 모드는 에이전트가 정한 원문 구간을 보존하고 추가 근거만 제한된 예산 안에서 제안합니다. 이 보완은 근거 손실을 막았지만, 실제 작업 8건에서 기준선보다 높은 회수율을 만들지는 못했습니다.

| 평가 | 기준선 | 기본 보조 방식 |
|---|---:|---:|
| 합성 개발 과제 8건의 필수 근거 | 15/41 | 41/41 |
| 실제 작업 8건의 필수 근거 | 51/56 | 51/56 |
| 합성 과제의 독립 답변 요구사항 반영 | 13/37 | 36/37 |

실제 작업의 보조 문맥은 기준선보다 43.2% 길었습니다. 따라서 자동 적용의 효과가 입증됐다고 보지 않습니다. 실패한 실험, 수정 전후 구현, 원문 기반 평가 방법을 함께 제공합니다. 사내 원문과 API 키는 저장소에 포함하지 않습니다.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[live,eval,dev]'

# API 호출 없이 원문 구간만 확인
jev-context benchmarks/cases/case-001/task.json \
  --root benchmarks/cases/case-001/corpus --inspect

pytest -q
```

실제 판정에는 `TYPESAFE_API_KEY`가 필요합니다. 설치·통합·재현 명령은 [영문 README](README.md), 수치와 한계는 [실험 보고서](docs/experiments.md)를 참고하세요. 근거 회수 검사는 실제 코드 변경의 성공을 보증하지 않습니다.
