# Production values

운영 환경 값은 이 디렉토리의 auth.yaml, guidebook.yaml, scheduler.yaml, worker.yaml, rabbitmq.yaml로 관리합니다.
아직 운영 EKS 설정이 확정되지 않았으므로 배포 가능한 values나 Application을 생성하지 않았습니다.
스테이징 인증서·ALB·AWS 경로·도메인·Secret을 운영에 복사하지 않습니다.

운영 준비 시 확인할 값:
- 검증한 운영 이미지 태그와 replica·리소스·배치 정책
- 운영 도메인·OAuth/CORS·Redis namespace
- 운영 IngressClass·인증서·ALB 설정
- 운영 namespace의 Secret 이름과 운영 AWS Parameter/Secret 경로
- Scheduler의 운영 S3 권한·ServiceAccount와 수집 활성화 여부
- 운영 RabbitMQ 연결·저장소·가용성 정책

공통 차트는 helm/<chart>를 사용하고, 운영 Argo CD는 같은 main의 이 환경 값 파일을 참조합니다.
운영 CI는 environments/production에만 쓰도록 별도 전환합니다. 현재 운영 ECS CI는 변경하지 않았습니다.
