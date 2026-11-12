# 환경별 배포 값

같은 main 브랜치에서 환경을 디렉토리로 구분합니다.

```
helm/<chart>/templates/          # 공통 Kubernetes 템플릿
environments/staging/*.yaml      # 스테이징 Helm 값
environments/production/         # 운영 Helm 값 (준비 전)
gitops/staging/                  # 스테이징 ESO·인프라·Argo CD 설정
```

예: helm template auth helm/auth -n auth -f environments/staging/auth.yaml
Argo CD source.path는 helm/auth, helm.valueFiles는 ../../environments/staging/auth.yaml입니다.
값 파일은 chart 디렉토리 기준 상대 경로입니다. 두 환경은 main을 읽되 클러스터와 값 파일이 다릅니다.

## 무중단 참조 전환 순서

1. BE의 환경별 경로 지원 CI 변경을 먼저 dev에 병합합니다. 환경 폴더가 없는 동안은 기존 경로로 동작합니다.
2. 이 저장소의 environments 및 gitops/staging/applications 변경을 main에 커밋·푸시합니다.
3. 라이브 Application에 새 source 참조를 연결합니다. 현재 Auto Sync·Manual 정책은 보존했습니다.
   `kubectl --kubeconfig "$HOME/.kube/kgb-v3staging-ayden" --context kgb-v3staging-ayden apply -f gitops/staging/applications/`
4. Argo CD가 main과 environments/staging 값을 읽는지, 이미지 태그·환경변수·리소스·ALB 설정이 이전과 같은지 검증합니다.
5. 이후 스테이징 설정은 environments/staging에서 수정합니다.

## 이행 기간의 기존 values.yaml

helm/*/values.yaml은 기존 Application과 CI가 끊기지 않도록 이번 변경에서는 그대로 남겼습니다.
전환 중 이미지 태그는 새 CI가 환경 값과 기존 값 모두 갱신합니다. 운영 디렉토리는 갱신하지 않습니다.
이 파일의 스테이징 설정을 운영 기본값으로 사용하면 안 됩니다. 운영은 별도 값 파일의 모든 환경 설정을 검토해야 합니다.
모든 Application 참조 전환 후 기존 values를 공통 기본값으로 정리하는 후속 변경이 필요합니다.
그때 env 빈 맵 병합으로 남는 설정이 없도록 이전 스테이징 env·Ingress 값도 제거하고 렌더링을 비교합니다.
기존 namespaces.yaml 역시 호환용으로 남기고 환경별 namespace 관리는 environments 아래로 전환합니다.

Secret 값은 저장하지 않고 gitops/<환경>의 ExternalSecret에서 AWS 원본 경로만 참조합니다.
스테이징 변경을 통째로 운영으로 복사하지 않고 검증한 이미지와 필요한 설정을 운영 값에 반영합니다.
