# Staging EKS monitoring

## 구성

- 기존 모니터링 EC2: 3.37.213.153 / 사설 10.0.0.87 (kgb-monitoring)
- EKS Alloy Deployment → 사설 TLS → 기존 Prometheus remote-write receiver
- kube-state-metrics → Node·Pod·Deployment 상태 지표
- Fluent Bit DaemonSet → CloudWatch Logs
- 대상 애플리케이션: auth, guidebook, kgb-ops. AI Worker의 별도 애플리케이션 수집은 추가하지 않았습니다.
- 기존 ECS 수집과 Grafana 접근 규칙은 유지합니다.

## 저장소 경로

- environments/staging/alloy.yaml: 수집 대상·TLS 수신 주소·라벨·리소스
- environments/staging/kube-state-metrics.yaml: 상태 지표 collector·리소스
- environments/staging/fluent-bit.yaml: 로그 대상·CloudWatch 경로·버퍼·리소스
- helm/fluent-bit: AWS 공식 이미지를 사용하는 로그 수집기 차트. 메타데이터 RBAC는 대상 namespace의 pods 조회만 허용합니다.
- gitops/staging/applications/{alloy,kube-state-metrics,fluent-bit}.yaml: Manual Argo CD Application
- gitops/staging/monitoring/namespace.yaml: monitoring namespace
- kgb-staging-eks.json: 기존 Grafana의 KGB Staging EKS 대시보드

## AWS 로그 설정

로그 그룹: /kgb/staging/eks/application
보관기간: **60일**
Pod Identity: monitoring / fluent-bit → kgb-staging-fluent-bit-role
IAM 쓰기 대상은 위 로그 그룹의 log stream으로 제한했습니다. AWS 키를 Pod 환경변수나 Git에 저장하지 않습니다.
전체 식별자는 aws-resources.json에 기록합니다. 이 파일에는 비밀값이 없습니다.

로그 수집은 새 로그부터 시작하며 기존 파일 전체를 재전송하지 않습니다.
CRI multiline을 처리하고 원본 log와 Kubernetes namespace/pod/container 정보를 함께 전송합니다.
각 Node의 /var/fluent-bit/state에 offset과 일시 버퍼를 저장합니다. 버퍼 상한은 100MiB입니다.
장기 통신 장애로 버퍼가 가득 차거나 Node가 회수되면 미전송 로그 유실이 가능합니다.

## 기존 서버에 적용한 변경

1. Prometheus --web.enable-remote-write-receiver 활성화 (localhost:9090 바인딩 유지)
2. 기존 사설 HTTPS 서버에 POST /api/v1/write 경로 추가
3. 해당 경로는 10.20.0.0/16만 허용하고, EC2 SG는 EKS 보안 그룹에서 오는 TCP443만 추가 허용
4. TLS 검증에는 기존 staging-grafana.kguidebook.site 인증서 사용. 인증서 검증은 비활성화하지 않습니다.
5. 기존 Grafana provisioning 디렉토리에 KGB Staging EKS 대시보드 추가

서버 설정 변경 스크립트: enable-metrics-receiver.py
백업: /opt/monitoring-staging/backups/eks-metrics-20261112T022022Z
기존 ECS 수집 설정·Grafana 데이터·로그인 계정은 변경하지 않았습니다.

## Git 반영 후 배포

1. 이 파일들과 environments/staging, helm/fluent-bit, 새 Application 파일을 Cloud main에 커밋·푸시합니다.
2. 다음 Application 3개만 등록합니다. 기존 Application 디렉토리 전체를 다시 적용할 필요는 없습니다.

```bash
kubectl --kubeconfig "$HOME/.kube/kgb-v3staging-ayden" --context kgb-v3staging-ayden apply \
  -f gitops/staging/applications/kube-state-metrics.yaml \
  -f gitops/staging/applications/alloy.yaml \
  -f gitops/staging/applications/fluent-bit.yaml
```

3. kube-state-metrics → Alloy → Fluent Bit 순서로 Manual Sync합니다.
4. monitoring Pod Ready, 기존 Prometheus의 cluster="kgb-staging-eks" 데이터, CloudWatch log stream/event를 확인합니다.

kube-state-metrics, Alloy, Fluent Bit의 Argo CD 배포와 실제 지표·CloudWatch 로그 수신을 확인했습니다.

## 조회 예시

PromQL:
- up{cluster="kgb-staging-eks",job="eks-backend"}
- kube_node_status_condition{cluster="kgb-staging-eks",condition="Ready",status="true"}
- kube_pod_container_status_restarts_total{cluster="kgb-staging-eks"}
- rate(container_cpu_usage_seconds_total{cluster="kgb-staging-eks",namespace="guidebook",container!=""}[5m])

CloudWatch Logs Insights:

```text
fields @timestamp, kubernetes.namespace_name, kubernetes.pod_name, log
| filter kubernetes.namespace_name = "guidebook"
| sort @timestamp desc
| limit 100
```

로그의 비밀정보 제외는 애플리케이션 로그 정책을 따릅니다. Discord 알림 설정은 아래 항목을 따릅니다.


## Discord 실제 장애 알림

- 수신처: Grafana Contact point `staging-alerts` → Discord 채널
- 규칙 원본: `monitoring/staging/grafana-alerts.json` (비밀정보 없음)
- 평가: 1분마다, Grafana 폴더 `KGB Staging EKS` → 규칙 그룹 `staging-eks`
- 최초 전송 대기 30초, 같은 그룹의 후속 변경 전송 간격 5분
- 장애 지속 시 critical 1시간 / warning 4시간 간격 재알림, 복구 알림 활성화

| 규칙 | 조건 | 지속시간 |
| --- | --- | --- |
| API Pod unavailable | Auth·Guidebook 사용 가능한 Pod 0개 | 2분 |
| Scheduler Pod unavailable | kgb-ops 사용 가능한 Pod 0개 | 5분 |
| API HTTP 5xx increased | 최근 5분 요청 20건 이상, 5xx 비율 5% 초과 | 2분 |
| Backend container restarting | 동일 컨테이너 최근 10분 재시작 3회 이상 | 1분 |
| Backend memory near limit | 메모리 working set / limit 90% 초과 | 10분 |
| API DB connection wait | Auth·Guidebook Hikari 연결 대기 > 0 | 2분 |
| EKS Node not ready | Ready=false/unknown | 5분 |
| EKS metrics ingestion missing | Alloy 지표 5분간 미수신 | 추가 1분 |
| EKS scrape target unavailable | backend·Alloy·KSM·cAdvisor의 up=0 | 5분 |
| Fluent Bit unavailable | 로그 수집 DaemonSet 준비되지 않은 Pod > 0 | 5분 |

5xx는 `/actuator` 경로를 제외하고 namespace별로 계산합니다. 401·404는 오류 분자에 포함하지 않습니다.
재시작·메모리 규칙 대상은 auth, guidebook, kgb-ops이며 AI 애플리케이션 규칙은 추가하지 않았습니다.
Node 규칙은 클러스터 전체를 감시합니다.
위 시간 외에 평가 간격과 최초 전송 대기 시간이 더해집니다. 이 값들은 초기 운영 기준이며 부하테스트 후 조정합니다.

### 적용과 변경

기존 외부 EC2의 Grafana를 사용하므로 이 규칙 파일은 Argo CD로 자동 반영되지 않습니다.
서버 `/opt/monitoring-staging/provisioning/alerting/20-staging-alert-rules.json`에 복사하고 `staging-grafana` 컨테이너를 재시작하여 적용합니다.
공식 file provisioning을 사용하므로 Grafana UI에서 이 규칙을 직접 수정하지 않고 Git의 원본 파일을 수정합니다.
전역 notification policy는 덮어쓰지 않으며 각 규칙에서 `staging-alerts`를 지정합니다.

Webhook은 Parameter Store SecureString `/kgb-staging/monitoring/DISCORD_WEBHOOK_URL`과 서버의 비공개 Contact point provisioning 파일에서 관리합니다. Git에 저장하지 않습니다.

### 장애 확인 순서와 한계

1. Discord 알림의 namespace/pod/node와 규칙 이름을 확인합니다.
2. Grafana `KGB Staging EKS` 대시보드에서 상태·자원·요청·DB 대기 추이를 확인합니다.
3. Pod 이벤트와 CloudWatch `/kgb/staging/eks/application` 로그를 확인합니다.
4. 원인 수정 후 정상 지표·복구 알림을 확인합니다.

시계열이 없는 일반 규칙은 NoData=OK, 쿼리 실행 오류는 Error로 처리합니다. 전체 지표 미수신은 별도 규칙이 감시합니다.
Pod 가용성 규칙은 예상 namespace의 지표가 사라져도 0으로 처리하므로, KSM 수집 중단 시 지표 수집 알림과 함께 발생할 수 있습니다.
메모리·DB 지표 등 개별 지표 하나만 누락되는 상황까지 모두 감지하지는 않습니다.
Scheduler Pod 정상은 수집 성공을 의미하지 않습니다. 마지막 수집 성공 시각·결과 지표가 추가되면 누락/실패 규칙을 별도로 구성해야 합니다.
Fluent Bit 가용성은 CloudWatch 전송 성공 자체를 보장하지 않습니다.
Grafana 또는 모니터링 EC2 자체가 중단되면 이 경로로 알림을 보낼 수 없습니다. 외부 감시는 별도입니다.

검증: 10개 PromQL 모두 실제 시계열·유한한 숫자를 반환하는지 확인했습니다. Discord 수신처는 Grafana 테스트 알림 수신으로 확인했으며, 실제 API 장애를 주입하지 않았습니다.


## EKS 대시보드 화면

기본 홈: `KGB Staging EKS` (`/d/kgb-staging-eks`). Namespace·Pod·Node 필터를 제공합니다.

기존 화면의 HTTP RPS·4xx/5xx·평균/최대/백분위 응답시간·엔드포인트 순위, JVM 힙 사용률·Used/Max·GC·Threads·Process CPU, Hikari Active/Pending/Max, MySQL 커넥션·쿼리·슬로우 쿼리를 유지했습니다.
JVM과 Hikari는 namespace/Pod별로 표시하며 Hikari Idle·Total도 추가했습니다.
Pod CPU 코어·request 대비 사용률, 메모리 working set·limit·사용률, Deployment 가용/요청 replica, 재시작을 추가했습니다.
기존 EC2 자원 패널은 EKS Node별 CPU·working memory·네트워크로 전환했습니다. Node 메모리는 working set 기반이므로 이전 MemAvailable 기반 지표와 계산 방식이 다릅니다.
기존 AI HTTP 패널은 접힌 참고 영역에 보존하며 EKS Worker 지표라고 표시하지 않습니다. 수집 대상은 변경하지 않았습니다.
요청이 없는 구간의 histogram 백분위값은 N/A일 수 있습니다. 이는 0ms나 수집 실패를 의미하지 않습니다.

대시보드 파일은 서버 `/opt/monitoring-staging/dashboards/kgb-staging-eks.json`에 적용하며 provider가 30초마다 읽습니다.
기본 홈 경로는 Compose의 `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/kgb-staging-eks.json`입니다.
기존 ECS 대시보드는 서버 backups 디렉토리로 이동하여 Grafana 목록에서 제거했습니다. 기본 화면과 대시보드 목록에는 EKS 대시보드만 제공합니다.
Dashboard provider의 disableDeletion=false로 파일 제거 시 Grafana 등록도 정리되게 설정했습니다. 원본 JSON 백업은 수집 디렉토리 밖에 보관합니다.

EKS 지표는 Alloy가 30초마다 수집합니다. EKS 패널의 각 Prometheus target에 Min step(`interval`) 30초를 지정하여 `$__rate_interval`이 최소 2분이 되게 했습니다. 공통 데이터 소스의 기존 5초 기준만 사용하면 20초 구간에 표본이 부족해 rate 패널이 N/A가 될 수 있습니다.

표와 안내 패널은 제거했습니다. 노드 범례와 선택 목록은 `i-05ac(AuthNode)` 형식으로 표시합니다. 역할은 현재 kube_pod_info 배치에서 결정하며, 공유 노드의 대표 역할 우선순위는 Auth→Guidebook→Scheduler→RabbitMQ→Worker→ArgoCD→Monitoring입니다. 실제 Node 이름이나 전용 배치를 뜻하지 않습니다. 선택값은 전체 Node ID를 유지하고 화면에서만 짧게 표시합니다. Pod 그래프는 서비스 역할·Pod 식별자를 표시합니다.
