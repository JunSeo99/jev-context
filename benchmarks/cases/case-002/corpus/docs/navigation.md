# 로그인 복귀 경로
적용: 2026-05-14 이후

복귀 주소는 교환한 attempt의 저장된 return_to에서 읽는다.
콜백 query의 return_to는 신뢰하지 않는다.
기본 허용 형태는 단일 /로 시작하는 현재 테넌트의 상대 경로다.
//로 시작하는 주소, 역슬래시, 제어문자는 거부한다.
디코딩은 한 번만 하며, 디코딩 결과도 같은 검사를 적용한다.
절대 URL은 원칙적으로 거부한다.

## 북마크 이전
[설정](../config/entrypoints.yaml)의 legacy_enabled가 켜져 있으면
https://portal.example.test/teams/{tenant}/... 형태만 예외다.
{tenant}는 로그인한 세션의 tenant와 정확히 같아야 한다.
예외 주소는 /teams/{tenant}/... 상대 경로로 바꿔 이동한다.
포트, 사용자 정보, 다른 프로토콜이 붙으면 예외 대상이 아니다.

잘못된 입력은 fallback으로 이동하고 로그인 자체는 유지한다.
[관측 규칙](telemetry.md)도 함께 적용한다.
