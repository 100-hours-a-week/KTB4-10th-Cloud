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

이 문서 작성 시점에는 설정·TLS 경로를 검증했고 상시 수집기 배포는 Git 반영 후 진행합니다.

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

로그의 비밀정보 제외는 애플리케이션 로그 정책을 따릅니다. 알림 수신처·전송 경로의 구축은 별도 작업입니다.
