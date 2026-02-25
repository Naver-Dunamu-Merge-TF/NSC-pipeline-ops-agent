# i-4p36 Evaluation - unknown TARGET_PIPELINES policy

## Scope

- 대상: watchdog의 `TARGET_PIPELINES`에서 미지원 항목 처리 정책
- 비교안: `fail-fast` vs `silent-skip` vs `warning+skip`

## 운영 관측성 트레이드오프 (availability vs visibility)

| 정책 | Availability (폴링 연속성) | Visibility (오입력 탐지) | 운영 영향 |
|---|---|---|---|
| fail-fast | 낮음 (단일 오입력으로 전체 중단) | 높음 (즉시 실패로 노출) | 장애 전파 방지에는 유리하나 watchdog 본연의 수집 가용성 저하 |
| silent-skip | 높음 (유효 항목 계속 폴링) | 낮음 (로그 단서 부재) | 즉시 영향은 작지만 설정 오류 잠복 위험 증가 |
| warning+skip | 높음 (유효 항목 계속 폴링) | 중간~높음 (경고 로그로 탐지 가능) | 가용성과 관측성의 균형, 운영 대응 시 원인 추적 가능 |

## 결론

- `warning+skip`는 watchdog availability를 유지하면서 설정 오류 visibility를 확보하므로 본 이슈 범위에서 최적의 절충안이다.
- 본 정책은 ADR-260225-1716과 정합하며, unknown pipeline을 폴링 대상에서 제외하되 경고 로그를 남겨 운영 탐지 경로를 보장한다.
